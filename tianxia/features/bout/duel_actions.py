"""單人頭目戰：原本 Game 上的 16 個方法（全部拆包第 12 批；計畫 docs/superpowers/plans/2026-11-03-單挑包-第1批.md 1.1），本體照抄、self 換成 ctx
（第一階 ctx 就是 Game，開發規範手冊 3.3）；名字去掉前導底線。頭目戰與擂台共用的幾樣（放手一搏的輸入框與重驗、本命戰法那幾行、
戰法的亂數、陣營名）也在這裡，擂台那一份（arena_actions）直接叫。

- 撞上與收場：duel_start、duel_act、duel_after、duel_finish；場景：duel_scene、bout_lines；放手一搏（頭目戰、擂台共用的鎖外三段式）：
  duel_free_text_prompt、duel_free_text_note、duel_text_check、duel_text_request、duel_gamble、stale_duel_request；戰法的亂數 bout_rng、
  陣營名 duel_side；防具的減損快照 duel_cut（戰力快照 Game._battle_gear 也叫它的委派：奪璽單挑吃防具）
- 頭目的查詢：boss_face（那一面的名字）、boss_here、boss_ready、boss_wait_text、boss_used_up——探索包、三選一的練功、舊探索經 Game 的委派問

留在 Game 的經 ctx：單打服務（_player_hp_and_cap、_battle_power、_battle_scores、_battle_role、_record_exp、_file_battle）、記錄（_log、_write、
_outcome）、模型（_quick_client）；這一包被換掉的委派 _duel_finish（scripts/sim_season_one.py 換掉它數頭目戰的結果）也經 ctx。
"""
from __future__ import annotations

import random

from tianxia import annals  # 過渡：待搬（行狀）
from tianxia import battle_instance, battlelog, encounter, materials, renown, rise, rounds, tactics, treasures
from tianxia import gender, team
from tianxia.core.services import PAUSED_TEXT
from tianxia.models import FREE_TEXT_MAX, MOVES, DuelBoss, Squad
from tianxia.state import PLAYER, DuelState

from . import arena_actions
from . import arena_rules as arena
from . import duel_rules
from .duel_rules import DUEL_GAMBLE_NOTE, DuelTextRequest


def duel_start(ctx, boss: DuelBoss) -> list[str]:
    """探索遇上頭目：快照份量、職位與氣血池（同加入決戰），記這一季遇上幾次與冷卻，擲他第一回合的招。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.duel
    now, cap = ctx._player_hp_and_cap()
    key = duel_rules.season_key(s, boss.id)
    power = ctx._battle_power()
    duel = DuelState(
        boss=boss.id, foe=duel_rules.foe_index(boss, p.faction), edge=cfg.start, hp=now, hp_cap=cap, hp_start=now,
        power=power, scores=ctx._battle_scores(mounted=False), role=ctx._battle_role(),
        # 頭目戰不算騎兵：設計 2.1 的三個用途沒有頭目戰
        # 江湖水漲：照你的武學威力浮上來；玉璽碎片的戰力不浮上去（改版 PM 五之一 2），沒碎片時跟 power 一樣
        difficulty=rise.duel(c, boss.difficulty, ctx._battle_power(seal=False), p.duel_tally.get(key, 0)),
        cut=duel_cut(ctx),  # 防具（鐵匠鋪與合成流程 3.9）：開打這一刻身上那件的減損抄下來，他打中你的那一下乘 1 − 它；頭目沒有防具
    )
    p.duel_tally[key] = p.duel_tally.get(key, 0) + 1
    if cfg.per_boss_week:  # 21 天季另記這一週的帳（正式季整合 2.5）；季的帳照記，江湖水漲照它算
        week = duel_rules.week_key(s, c, boss.id)
        p.duel_tally[week] = p.duel_tally.get(week, 0) + 1
    p.duel_last = [float(p.season_number), s.world.time]
    foe = boss.foes[duel.foe]
    duel.bout = tactics.open_bout(  # 本命戰法（第二批）：只算你身上的兩門；頭目沒有本命戰法
        team.self_side(s, c, ctx.world), None, "你", foe.name, a_faction=p.faction, b_faction=foe.side,
        b_agility=rounds.foe_agility(duel_rules.foe_difficulty(duel, boss)),
    )
    duel_rules.roll_next(duel, foe, cfg, ctx.rng)
    p.duel = duel
    ctx._outcome(f"遇上{foe.title}{foe.name}", "")
    role = battle_instance.role_name(c.config.battle, duel.role)
    meet = renown.duel_meet_line(s, c)  # 名聲 4.4：名望高、攔路的也多，說出原因
    return [f"你在{c.locations[p.location].name}走著，{foe.title}{foe.name}攔住了去路！", foe.intro] + (
        [f"你以{role}的架勢迎上去。"] if role else []
    ) + ([meet] if meet else [])


def duel_scene(ctx) -> str:
    duel = ctx.state.player.duel
    boss, foe = duel_rules.foe_of(ctx.content, duel)
    lines = [
        f"**{foe.title}・{foe.name}**（頭目戰 第 {duel.round + 1}／{boss.rounds} 回合）",
        foe.intro if duel.round == 0 else duel.lines[-1],
        f"氣勢：{duel_rules.edge_words(duel.edge)}（{duel.edge:.0f}／100）　你的氣血：{duel.hp:.0f}／{duel.hp_cap:.0f}",
        *bout_lines(duel.bout),
        f"{duel.tell}{tactics.SEEN_NOTE if tactics.locks(duel.bout).sees else '（架勢不一定是真的。）'}",
        "固守剋強攻、強攻剋奇襲、奇襲剋固守；也可以在下面寫一句，放手一搏。",
    ]
    return "\n\n".join(lines)


def duel_free_text_prompt(ctx) -> str | None:
    """頭目戰打到一半時輸入框的提示語，否則 None（server.py 照它決定輸入框，送出走 duel_text）。"""
    if ctx.state.player.arena is not None:
        return arena.PROMPT
    return "放手一搏：寫下你要怎麼對付他（20 字以內）" if ctx.state.player.duel is not None else None


def duel_free_text_note(ctx) -> str | None:
    return DUEL_GAMBLE_NOTE if ctx.state.player.duel is not None or ctx.state.player.arena is not None else None


def duel_text_check(ctx, text: str) -> str | list[str]:
    if ctx.world.paused_at() is not None:
        return [f"（{PAUSED_TEXT}。）"]
    if ctx.state.player.duel is None and ctx.state.player.arena is None:
        return ["（此刻無法這麼做。）"]
    text = text.strip()[:FREE_TEXT_MAX]
    if not text:
        return ["（請先輸入你想做的事。）"]
    p = ctx.state.player
    if tactics.locks(p.arena.bout if p.arena is not None else p.duel.bout).no_gamble:
        return [tactics.NO_GAMBLE]
    return text


def bout_lines(bout: tactics.Bout | None) -> list[str]:
    """頭目戰、擂台的場景：兩邊身上的本命戰法狀態各一行（沒有就不寫）。"""
    return [line for line in (tactics.status_text(bout, "a"), tactics.status_text(bout, "b")) if line]


def bout_rng(ctx, kind: str, key: object, round_: int) -> random.Random:
    """本命戰法這一回合的亂數（不碰 Game.rng）：種類｜季數｜名號｜哪一場｜第幾回合。"""
    p = ctx.state.player
    return random.Random(f"{kind}|{p.season_number}|{p.name}|{key}|{round_}|戰法")


def duel_text_request(ctx, text: str) -> DuelTextRequest | list[str]:
    """頭目戰放手一搏的 A 段（鎖內、只讀）：送得出去回傳要在鎖外送模型的單子，不行回傳那一句話。"""
    checked = duel_text_check(ctx, text)
    if isinstance(checked, list):
        return checked
    s, c = ctx.state, ctx.content
    fight = s.player.arena
    if fight is not None:  # 擂台：對手那一行寫分身的身手（同奪璽單挑），場合寫擂台
        here = arena.scene(fight)
        return DuelTextRequest(
            boss=f"arena:{fight.id}", round=fight.round, text=checked, name=s.player.name, faction_name=duel_side(ctx),
            title=here.title, scene=here.text, sex=gender.of(s), target=arena.foe_line(fight.me, fight.foe, c),
            setting=arena.SETTING, place=arena.PLACE,
        )
    duel = s.player.duel
    here = duel_rules.scene(c, duel)
    return DuelTextRequest(
        boss=duel.boss, round=duel.round, text=checked, name=s.player.name, faction_name=duel_side(ctx),
        title=here.title, scene=here.text, sex=gender.of(s),
    )


def duel_side(ctx) -> str:
    faction = ctx.state.player.faction
    return ctx.content.scenario.faction_name(faction, faction) if faction else "散人"


def duel_gamble(
    ctx, text: str, llm_rate: int | None = None, stories: tuple[str, str] | None = None,
    request: DuelTextRequest | None = None, crowd: str = "",
) -> list[str]:
    """頭目戰放手一搏的 C 段（擂台也走這裡：crowd 是鎖外判的觀眾反應，arena_crowd.judge_gamble）：llm_rate 是鎖外評好的成功率，request 是當時開的單子——還是同一隻、同一回合、同一句才用；
    對不上（這一回合已經出過招、換了一場）回「這一回合已經結算」、句子不同回「請再送一次」，不重評、不套用（同 seal_gamble：
    鎖內重評會把第 r 回合寫的那一句套到第 r＋1 回合，還佔住全服的鎖；M-05）。沒給 request（假人不寫自由文字；腳本、測試）
    而且沒給分數，在這裡用 _quick_client 評，評不到是保底的 40。擲骰、推進、損耗全在 duel.gamble。"""
    checked = duel_text_check(ctx, text)
    if isinstance(checked, list):
        return ctx._log(checked)
    s, c = ctx.state, ctx.content
    if s.player.arena is not None:
        return ctx._log(arena_actions.arena_gamble(ctx, checked, llm_rate, stories, request, crowd))
    duel = s.player.duel
    stale = stale_duel_request(request, duel.boss, duel.round, checked)
    if stale:
        return ctx._log(stale)
    if llm_rate is None:
        verdict = battle_instance.assess_gamble(
            ctx._quick_client(), duel_rules.scene(c, duel), duel_side(ctx), checked, s.player.name,
            setting=duel_rules.SETTING, place=duel_rules.PLACE, sex=gender.of(s),
        )
        llm_rate, stories = verdict.rate, (verdict.win, verdict.lose)
    s.battle_card = None
    s.player.guide_done = []
    boss, _ = duel_rules.foe_of(c, duel)
    fired: list[str] = []
    won, delta, hp, _ = duel_rules.gamble(duel, int(llm_rate), c.config.duel, c.config.battle, ctx.rng,
                                          c.config.tactics, bout_rng(ctx, "頭目戰", duel.boss, duel.round), fired)
    story = (stories or ("", ""))[0 if won else 1]
    if not story:
        story = f"你放手一搏：「{checked}」——{'成了！' if won else '沒成，反倒露了破綻。'}"
    line = tactics.round_line(f"第 {duel.round + 1} 回合：{story}（氣勢 {delta:+d}，你氣血 {-hp:+d}）", fired)
    return ctx._log(duel_after(ctx, line))


def stale_duel_request(request: DuelTextRequest | None, boss: str, round_: int, text: str) -> list[str]:
    """頭目戰、擂台 C 段的重驗：單子是別一場、別一回合的回 duel.STALE，同一回合換了一句回 duel.RESEND；沒給單子或對得上是 []。"""
    if request is None:
        return []
    if (request.boss, request.round) != (boss, round_):
        return [f"（{duel_rules.STALE}）"]
    if request.text != text:
        return [f"（{duel_rules.RESEND}）"]
    return []


def duel_act(ctx, arg: str) -> list[str]:
    """選單上的一招，或抽身退走。"""
    s, c = ctx.state, ctx.content
    duel = s.player.duel
    if duel is None:
        return ["（此刻無法這麼做。）"]
    boss, foe = duel_rules.foe_of(c, duel)
    if arg == "flee":
        return ctx._duel_finish(None, "你虛晃一招，抽身退走。")
    if arg not in MOVES:
        return ["（此刻無法這麼做。）"]
    if arg in tactics.locks(duel.bout).no_moves:
        return [tactics.NO_MOVE.format(move=arg)]
    out = duel_rules.exchange_full(duel, boss, arg, c.config.duel, c.config.battle, ctx.rng,
                                   c.config.tactics, bout_rng(ctx, "頭目戰", duel.boss, duel.round), c.config.armor.total_cap)
    line = tactics.round_line(
        f"第 {duel.round + 1} 回合：你{out.mine or '出不了手'}，{foe.name}{out.his or '出不了手'}——{duel_rules.COUNTER_WORDS[out.beat]}。"
        f"（氣勢 {out.delta:+d}，你氣血 {-out.hp:+d}）", out.lines,
    )
    return duel_after(ctx, line)


def duel_after(ctx, line: str) -> list[str]:
    """出完一招（或放手一搏）之後：記這一回合，分出勝負就收場，否則擲他下一回合的招。"""
    s, c = ctx.state, ctx.content
    duel = s.player.duel
    boss, foe = duel_rules.foe_of(c, duel)
    duel.lines.append(line)
    duel.round += 1
    tier = duel_rules.verdict(duel, boss, c.config.duel)
    if tier is not None:
        return ctx._duel_finish(tier, line)
    duel_rules.roll_next(duel, foe, c.config.duel, ctx.rng)
    return [line]


def duel_finish(ctx, tier: str | None, line: str) -> list[str]:
    """收場：池子掉的氣血扣回本人（兩成變內傷，根骨減，同遊歷）、照結果發獎勵、一份戰報與一則江湖紀錄。tier 是 None 是抽身退走
    （不寫戰報，沒有獎勵）。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.duel
    duel = p.duel
    boss, foe = duel_rules.foe_of(c, duel)
    p.duel = None
    lost = max(0.0, duel.hp_start - duel.hp)
    now, _ = ctx._player_hp_and_cap()
    if lost > 0:
        con = team.con_of(s, c, ctx.world, PLAYER)
        injury = treasures.amount(s, c, "injury")  # 螭首（玉璽碎片改版）：變成內傷的減半；沒帶是 1
        p.member.injury += lost * c.config.injury_share * max(0.0, 1 - team.stat_bonus(c, con, s.world)) * injury
        p.member.neili = max(0.0, now - lost)
    title = f"頭目戰・{foe.name}"
    if tier is None:
        msgs = [line] + ([f"氣血 -{round(lost)}"] if round(lost) else [])
        ctx._write(title, msgs, tag="抽身退走")
        return msgs
    level = duel_rules.foe_difficulty(duel, boss)
    squad = Squad(id=f"duel:{boss.id}", name=f"{foe.title}{foe.name}", difficulty=level, attribute=boss.attribute)
    result = encounter.EncounterResult(tier=tier, margin=duel.edge - cfg.start, our_power=duel.power, difficulty=level)
    record = battlelog.new_record(s, c, ctx.world, squad, result, "duel", event=title)
    record.ours = record.ours[:1]  # 同伴不上場：比的是你一個人
    record.rounds = list(duel.lines)
    won = tier in team.WIN_TIERS
    record.notes.append(foe.win if won else foe.lose if tier == "落敗" else f"{foe.name}見討不了好，虛晃一招退走了。")
    share = cfg.reward_share.get(tier, 0.0)
    extra: list[str] = []
    more = renown.duel_reward(s, c) if won else 1.0  # 名聲 4.4：名動一方以上打贏，經驗、銀兩、心得多兩成（名望、素材照舊）
    share *= more
    if more > 1.0:
        record.notes.append(renown.duel_paid_line(s, c))
    exp = round(boss.exp * share)
    if exp:  # 同伴不上場：只給本人；升級給屬性點同決戰的軍餉
        before = p.member.level
        # 滿級換心得（先換，升到滿級那一下剩下的不換）：extra 會進戰報敘事、紀錄另接得失（已含換來的那一份），所以只留那一句，
        # 「心得 +N」不接（同切磋；FB-453：以前紀錄寫心得 +39、實際 +27）
        extra += [n for n in ctx._record_exp(record, exp, "boss") if not n.startswith("心得 +")]
        extra += team.add_exp(c, p.member, exp, p.name, "boss")  # 頭目戰是仗（減法季 45 級以後照算）
        if p.member.level > before:
            points = team.level_points(ctx.state, c, before, p.member.level)
            p.stat_points += points
            if points:
                extra.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
    silver = round(boss.silver * share)
    if silver:
        p.stats["silver"] = p.stats.get("silver", 0) + silver
        record.silver = silver
    xinde = round(boss.xinde * share)
    if xinde:
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        record.xinde = (record.xinde or 0) + xinde  # 滿級換來的那一份已經在裡面（_record_exp，FB-450）
    if won:
        for material_id in boss.drops:
            if materials.grant(s, c, material_id) is not None:
                materials.add_cell(record.materials, c, material_id)  # 同一種合成一格（FB-140）
        if boss.fame:
            record.changes += renown.gain(s, c, "fame", boss.fame)  # 名聲設計 3.2
        chance = cfg.legend_chance.get(tier, 0.0)
        if chance > 0 and ctx.rng.random() < chance:
            p.legend_items += 1
            record.changes.append(f"{c.config.legend_item_name} +1")
            extra.append(f"他身上掉出一枚【{c.config.legend_item_name}】——{c.config.legend_item_note}")
    if round(lost):
        record.changes.append(f"氣血 -{round(lost)}")
    record.notes += extra
    summary = ctx._file_battle(record)
    msgs = [line, summary, *record.notes, *battlelog.gains_list(record)]
    ctx._write(title, msgs, tag=battlelog.outcome_text(record))
    annals.note(s, c, annals.FIGHT, f"獨力對上{foe.title}{foe.name}，{tier}。", 3 if won else 2)
    return msgs


def boss_face(ctx, boss: DuelBoss) -> str:
    """這一隻頭目對你露的那一面（照你的陣營，duel_rules.foe_index）的名字：練功鈕與行動列底下那一行同一個。"""
    return boss.foes[duel_rules.foe_index(boss, ctx.state.player.faction)].name


def duel_cut(ctx) -> float:
    """單挑類的仗（頭目戰、擂台、奪璽單挑）此刻要抄的防具減損（team.duel_armor_cut）。"""
    return team.duel_armor_cut(ctx.state, ctx.content, ctx.world)


# ── 頭目的查詢（全部拆包第 12 批：原位叫 duel_rules 的那幾處改叫 Game 的一行委派，別的包經 ctx 問）──


def boss_here(ctx) -> list[DuelBoss]:
    """站在這裡的頭目（照 id 排），不管冷卻與次數（duel_rules.here）。"""
    return duel_rules.here(ctx.state, ctx.content)


def boss_ready(ctx) -> DuelBoss | None:
    """此刻在這裡遇得上的頭目（duel_rules.available）：不在序章、沒有正在打的、不在冷卻、這一隻的次數還沒用完。"""
    return duel_rules.available(ctx.state, ctx.content)


def boss_wait_text(ctx) -> str:
    """頭目冷卻還要等多久（現實的倒數，arena.wait_text：世界秒 ÷ time_scale）；不在冷卻是空字串（三選一的 Game._boss_away 讀）。"""
    c = ctx.content
    wait = duel_rules.cooldown_left(ctx.state, c.config.duel)
    return arena.wait_text(wait / c.config.time_scale) if wait > 0 else ""


def boss_used_up(ctx, boss_id: str) -> bool:
    """這一隻的次數用完了沒（duel_rules.used_up：21 天季照這一週、其餘照這一季）。"""
    return duel_rules.used_up(ctx.state, ctx.content, boss_id)
