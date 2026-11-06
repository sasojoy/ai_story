"""擂台（隨時挑擂）：原本 Game 上的 22 個方法（全部拆包第 12 批；計畫 docs/superpowers/plans/2026-11-03-單挑包-第1批.md 1.1），本體照抄、
self 換成 ctx（第一階 ctx 就是 Game，開發規範手冊 3.3）；名字去掉前導底線（_arena → arena_choice、_arena_crowd → roll_crowd：
包裡有模組也叫 arena_crowd）。加上原位接上第 11 批掛鉤的那幾段（1.4）：坐在擂台邊的選單（店面登記 Shop.menu → arena_options）、
「此地還能做」裡那一顆（Shop.entry → entry_option）、收起來（Shop.close → close）、打開擂台與那一下的標題（act 子動詞 Verb → arena_open、
arena_sign）、報名與挑擂的標題（choose 掛鉤 → arena_title）、打到一半的三招與認輸（menu 掛鉤 → fight_menu）；choose 那一下灰掉的挑擂鈕
回原因（arena_fight_problem：Game 原位叫一行委派）。

- 快照：arena_side、arena_bare、arena_arts、arena_power、arena_left；入口與選單：arena_entry、arena_options；分派：arena_choice、
  arena_join、arena_start；動畫：arena_move_art、arena_burst；場景：arena_scene、arena_last_round；場邊事件：roll_crowd、
  arena_crowd_request、apply_arena_crowd（鎖外重寫那一句的 A、C 段）；出招：arena_act、arena_gamble、arena_after、arena_finish；
  補送：deliver_arena

留在 Game 的經 ctx：單打服務（_player_hp_and_cap、_battle_power、_battle_scores、_battle_role、_file_battle）、記錄（_write、_save_season）、
回體丹那一套的今天（_pill_day）、模型（client、_quick_client）、形象包的 arena_look、arena_move（查詢服務；這一包的 tianxia/features/bout/tests/test_arena.py
換掉 Game.arena_look）；這一包被換掉的委派 _arena_bare（tianxia/features/seal/tests/test_seal_revamp_hidden.py 換掉它）也經 ctx。
"""
from __future__ import annotations

from tianxia.core import annal_base as annals  # 核心（行狀記一筆，第 29 批之二）
from tianxia import battlelog, encounter, renown, tactics, treasures
from tianxia.core import battle_base as battle_instance
from tianxia import attrset, gender, team
from tianxia.characters import name_key
from tianxia.core import duel_base
from tianxia.core.option import Option
from tianxia.core.travel_base import TravelBlock  # 核心（動身被擋那一句的型別，core_seams）
from tianxia.models import MOVES, Squad
from tianxia.rules import add_rumor
from tianxia.state import ArenaEntry, ArenaFight, ArenaReport, ArenaResult, ArenaSide, CrowdNote

from . import arena_crowd, duel_actions
from . import arena_rules as arena
from .duel_rules import COUNTER_WORDS, DuelTextRequest


def arena_side(ctx) -> ArenaSide:
    """此刻的身手（同頭目戰的快照：威力、不算騎兵與部下的份量、職位）；池子從滿的開始。"""
    _, cap = ctx._player_hp_and_cap()
    return ArenaSide(
        name=ctx.state.player.name, power=ctx._battle_power(), scores=ctx._battle_scores(mounted=False),
        role=ctx._battle_role(), hp=cap, hp_cap=cap, bare=ctx._arena_bare(),
        cut=duel_actions.duel_cut(ctx),  # 防具減損（鐵匠鋪與合成流程 3.9）：開打、報名這一刻身上那件的
        card=team.pvp_card(ctx.state, ctx.content, ctx.world),  # 五項屬性的季：開打時照對手重算（faced）
    )


def faced(content, me: ArenaSide, foe: ArenaSide) -> None:
    """五項屬性的季：兩邊的威力與份量照對手真正的五項重算（我的武力對他的統御；企劃者 2026-11-04）。舊的季、舊的分身不動。"""
    if me.card is None or foe.card is None:
        return
    mine, theirs = me.card, foe.card
    me.power, me.scores, me.bare = team.pvp_faced(content, me.power, me.scores, mine, theirs, me.bare)
    foe.power, foe.scores, foe.bare = team.pvp_faced(content, foe.power, foe.scores, theirs, mine, foe.bare)
    me.dodge, foe.dodge = team.pvp_dodge(content, mine, theirs), team.pvp_dodge(content, theirs, mine)
    me.role, me.scores = team.pvp_unrole(content, me.role, me.scores)
    foe.role, foe.scores = team.pvp_unrole(content, foe.role, foe.scores)


def arena_bare(ctx) -> float | None:
    """戴著玉璽碎片（改版開著，treasures.power_scale 不是 1）時，不含碎片戰力的威力；沒有是 None（威力本身就是給別人看的那一份）。
    擂台挑人的「身手」與四種戰報的「對手威力」照它寫（FB-625、FB-615）；打起來照 power（含碎片）。"""
    if treasures.power_scale(ctx.state, ctx.content) == 1.0:
        return None
    return ctx._battle_power(seal=False)


def arena_arts(ctx) -> list[str]:
    s, c, m = ctx.state, ctx.content, ctx.state.player.member
    arts = (team.player_art(s, c, ctx.world, m.wugong_id), team.player_art(s, c, ctx.world, m.neigong_id))
    return [a.name for a in arts if a is not None]


def arena_power(ctx) -> float:
    """此刻上擂台的威力（假人照它決定報名、更新分身；bot_policy._arena）。"""
    return ctx._battle_power()


def arena_left(ctx) -> int:
    """今天還能挑幾次擂（ArenaTuning.per_day；同回體丹的現實時間換日）。"""
    return arena.left_today(ctx.state, ctx.content.config.arena, ctx._pill_day())


def arena_entry(ctx) -> list[Option]:
    """「擂台」那一顆：哪裡都有（地點上、路上、閉關中），只是打開第二層選單，不花體力。"""
    return [Option(id="act:arena", label=arena.ARENA)] if arena.here(ctx.state, ctx.content) else []


def arena_options(ctx) -> list[Option]:
    """擂台的第二層選單：報名（報過了是更新分身）、排在你前面 reach 名內的人一人一顆（挑不了的灰掉寫為什麼）、返回。都不花體力，
    挑擂一天 per_day 次。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    mine = arena.entry_of(s.world, p.name)
    power = ctx._battle_power()
    shown = ctx._battle_power(seal=False)  # 身手兩邊都照不含玉璽碎片的算（FB-625）：自己看自己也一樣，畫面才跟別人看到的對得上
    left = arena_left(ctx)
    opts = [Option(id=arena.JOIN_ID, label=arena.UPDATE if mine is not None else arena.JOIN, enabled=power > 0)]
    others = arena.challengers(s.world, c, p.name, left)
    for e, problem in others:
        note = problem or arena.LEFT.format(n=left)
        title = arena.title_for(e.rank)
        label = (f"挑{e.name}（第 {e.rank} 名{'・' + title if title else ''}・{arena.record_text(e)}・"
                 f"身手{arena.strength_words(c, shown, e.shown)}・{note}）")
        opts.append(Option(id=f"arena:fight:{name_key(e.name)}", label=label, enabled=problem is None))
    if mine is not None and not others:
        opts.append(Option(id="arena:none", label=arena.NOBODY if mine.rank == 1 else arena.NOBODY_AHEAD, enabled=False))
    opts.append(Option(id=arena.BACK_ID, label=arena.BACK))
    return opts


def arena_choice(ctx, arg: str) -> list[str]:
    """擂台第二層的選擇：報名或更新分身、挑一個人（開打）、返回（收起選單）。"""
    verb, _, rest = arg.partition(":")
    if verb == "back":
        ctx.state.player.picking_arena = False
        ctx.state.player.arena_last = None
        return ["你離開了擂台。"]
    if verb == "join":
        return arena_join(ctx)
    if verb == "fight":
        return arena_start(ctx, rest)
    return ["（此刻無法這麼做。）"]


def arena_join(ctx) -> list[str]:
    s, p = ctx.state, ctx.state.player
    side = arena_side(ctx)
    if side.power <= 0:
        return [arena.NO_ARTS]
    arts = arena_arts(ctx)
    text = "、".join(arts)
    entry = arena.entry_of(s.world, p.name)
    famed = renown.arena_famed(s, ctx.content)  # 名聲 4.7
    if entry is not None:
        entry.name, entry.power, entry.scores, entry.role, entry.hp_cap, entry.arts, entry.famed = (
            p.name, side.power, side.scores, side.role, side.hp_cap, arts, famed)
        entry.bare = side.bare  # 碎片沒了再更新分身：不含碎片的那一份跟著清掉
        entry.card = side.card
        entry.cut = side.cut  # 防具也換成此刻身上那件的（含耐久；沒穿就是 0），鐵匠鋪與合成流程 3.9
        entry.kit = team.self_side(s, ctx.content, ctx.world)
        entry.crowd = arena_crowd.snapshot(s, ctx.content, ctx.world)  # 場邊事件看的底細（照更新這一刻）
        entry.weapon = arena.held_kind(p)  # 擂台動畫：分身手上拿什麼
        entry.look = ctx.arena_look()  # 擂台形象：分身穿哪一套
        entry.move = ctx.arena_move()  # 招式動畫：分身出招疊哪一張
        entry.move_art = arena_move_art(ctx, entry.move)
        return [arena.UPDATED.format(arts=text)]
    entry = arena.join(s.world, ArenaEntry(
        name=p.name, power=side.power, bare=side.bare, scores=side.scores, role=side.role, hp_cap=side.hp_cap, arts=arts, joined=s.world.time,
        kit=team.self_side(s, ctx.content, ctx.world), famed=famed, crowd=arena_crowd.snapshot(s, ctx.content, ctx.world),
        cut=side.cut, card=side.card,  # 分身留下報名那一刻的防具減損（3.9）與五項（開打時照挑的人重算）
        weapon=arena.held_kind(p), look=ctx.arena_look(), move=ctx.arena_move(),
    ))
    entry.move_art = arena_move_art(ctx, entry.move)
    return [arena.JOINED.format(rank=entry.rank, arts=text)]


def arena_move_art(ctx, move: str) -> str:
    """招式動畫綁在哪一門上：疊得上光效（move 不是空的）就是現在練的那一門（looks 只在現在練的那一門綁了招式時才給 move）。"""
    return (ctx.state.player.member.wugong_id or "") if move else ""


def arena_burst(fight: ArenaFight, skills) -> None:
    """招式動畫：這一回合兩邊綁了招式的那一門的戰法發動了沒（光效只在發動的那一回合疊，Joy 2026-11-01）。"""
    arts = (list(fight.fx_arts) + ["", ""])[:2]
    fight.bursts.append([int(bool(art) and art in fired) for art, fired in zip(arts, skills)])


def arena_start(ctx, key: str) -> list[str]:
    """挑一個守擂的人：記今天挑了幾次、冷卻與他今天被挑了幾場，快照兩邊，擲分身第一回合的招。不花體力。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    cfg = c.config.arena
    foe = s.world.arena.get(key)
    if foe is None or name_key(foe.name) == name_key(p.name):
        return ["（此刻無法這麼做。）"]
    problem = arena.challenge_problem(s.world, p.name, foe, cfg, arena_left(ctx), c.config.time_scale)
    if problem is not None:
        return [f"（{problem}。）"]
    arena.spend(s, ctx._pill_day())
    arena.note_challenge(s.world, p.name, foe)
    p.newbie_marks.add("arena")  # 新手目標：上一次擂台
    s.world.arena_seq += 1
    fight = ArenaFight(
        id=s.world.arena_seq, foe_key=key, me=arena_side(ctx), rounds=cfg.rounds,
        foe=ArenaSide(name=foe.name, power=foe.power, scores=dict(foe.scores), role=foe.role, hp=foe.hp_cap, hp_cap=foe.hp_cap,
                      bare=foe.bare, cut=foe.cut, card=foe.card),  # 分身的防具是他報名、更新那一刻的（3.9）
        edge=c.config.duel.start,
        crowd_me=arena_crowd.snapshot(s, c, ctx.world), crowd_foe=foe.crowd,  # 場邊事件看的底細（arena_crowd）
        looks=[arena.held_kind(p), foe.weapon],  # 擂台動畫：兩邊手上的兵器（分身的照報名那一刻）
        skins=[ctx.arena_look(), foe.look],  # 擂台形象：兩邊穿哪一套（分身的照報名那一刻）
        fx=[ctx.arena_move(), foe.move],  # 招式動畫：兩邊出招疊哪一張（同上）
        fx_arts=[arena_move_art(ctx, ctx.arena_move()), foe.move_art if foe.move else ""],
    )
    faced(c, fight.me, fight.foe)
    p.arena_crowd_note = None
    arena.roll_next(fight, arena.rng_for(p.season_number, p.name, fight, "招"), cfg, c.config.duel)
    p.arena = fight
    p.picking_arena = False
    p.arena_last = None
    lines = [arena.OPENING.format(foe=foe.name)]
    if foe.arts:
        lines.append(arena.FOE_ARTS.format(arts="、".join(foe.arts)))
    fight.bout = tactics.open_bout(  # 本命戰法（第二批）：兩邊身上的兩門（他的是報名那一刻的）
        team.self_side(s, c, ctx.world), foe.kit, "你", foe.name, a_faction=p.faction, pvp=True,
    )
    return lines


def arena_scene(ctx) -> str:
    fight = ctx.state.player.arena
    lines = [
        f"**{arena.ARENA}・{fight.foe.name}的分身**（第 {fight.round + 1}／{fight.rounds} 回合）",
        arena.OPENING.format(foe=fight.foe.name) if fight.round == 0 else "\n\n".join(arena_last_round(ctx)),
        f"氣勢：{duel_base.edge_words(fight.edge)}（{fight.edge:.0f}／100）　"
        f"你的氣血：{fight.me.hp:.0f}／{fight.me.hp_cap:.0f}　他：{fight.foe.hp:.0f}／{fight.foe.hp_cap:.0f}",
        *duel_actions.bout_lines(fight.bout),
        f"{fight.tell}{tactics.SEEN_NOTE if tactics.locks(fight.bout).sees else arena.TELL_NOTE}",
        arena.HOWTO,
    ]
    return "\n\n".join(lines)


def arena_last_round(ctx) -> list[str]:
    """上一回合那一行，後面跟著那一回合的場邊事件（有的話）。"""
    lines = ctx.state.player.arena.lines
    if len(lines) >= 2 and lines[-1].startswith(arena_crowd.PREFIX):
        return lines[-2:]
    return lines[-1:]


def roll_crowd(ctx, label: str = "", move: str = "", his: str = "") -> str | None:
    """這一回合有沒有場邊事件（arena_crowd）：一場最多一件，擲中了套效果、記這一種今天落在誰身上，回那一行（〔場邊〕…）。
    模型叫得到時（伺服器）記一張單子，伺服器在鎖外重寫那一句（apply_arena_crowd）。亂數另開用途「場邊」，不碰 Game.rng。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    fight = p.arena
    if fight is None or not arena_crowd.on(c):
        return None
    cfg = c.config.arena.crowd
    today = ctx._pill_day()
    foe = s.world.arena.get(fight.foe_key)
    rng = arena.rng_for(p.season_number, p.name, fight, "場邊")
    happening = arena_crowd.roll(fight, s.world, p.name, cfg, today, p.arena_crowd_seen,
                                 foe.crowd_seen if foe is not None else {}, rng, label)
    if happening is None:
        return None
    applied = arena_crowd.apply(fight, happening, cfg)
    if happening.side == "me":
        p.arena_crowd_seen[happening.kind] = today
    elif foe is not None:
        foe.crowd_seen[happening.kind] = today
        ctx._save_season()  # 守的人那一本帳在這一季的 WorldState
    name, rival = arena_crowd.names(fight, p.name, happening.side)
    text = arena_crowd.fixed_text(c, happening, name, rival, rng)
    line = arena_crowd.line_of(text, applied)
    p.arena_crowd_note = CrowdNote(
        fight_id=fight.id, round=fight.round, kind=happening.kind, side=happening.side, name=name, rival=rival,
        helper=happening.helper, title=happening.title, battle=happening.battle, move=move, his=his, fixed=line, text=text,
    ) if ctx.client is not None else None
    return line


def arena_crowd_request(ctx) -> CrowdNote | None:
    """還等著模型重寫的那一句場邊事件（server 鎖外寫；A 段，只讀）。"""
    return ctx.state.player.arena_crowd_note


def apply_arena_crowd(ctx, note: CrowdNote, text: str) -> bool:
    """C 段：還是同一張單子才換。句子那一截換成模型寫的（括號的數字照舊），擂台這一場、收場卡、戰報、江湖紀錄裡的那一行都換；
    寫不出來（空字串）就收掉單子、照固定句。換了是 True。"""
    p = ctx.state.player
    if p.arena_crowd_note is None or p.arena_crowd_note != note:
        return False
    p.arena_crowd_note = None
    if not text:
        return False
    new = note.fixed.replace(note.text, text, 1)

    def swap(lines: list[str]) -> None:
        for i, line in enumerate(lines):
            if line == note.fixed:
                lines[i] = new

    if p.arena is not None and p.arena.id == note.fight_id:
        swap(p.arena.lines)
    if p.arena_last is not None and p.arena_last.id == note.fight_id:
        swap(p.arena_last.lines)
    for record in ctx.state.battles[-3:]:
        if record.kind == "arena":
            swap(record.rounds)
    for entry in ctx.state.journal[-5:]:
        swap(entry.lines)
    return True


def arena_act(ctx, arg: str) -> list[str]:
    """擂台上的一招，或認輸。"""
    c, p = ctx.content, ctx.state.player
    fight = p.arena
    if fight is None:
        return ["（此刻無法這麼做。）"]
    if arg == "yield":
        return arena_finish(ctx, "落敗", arena.YIELDED)
    if arg not in MOVES:
        return ["（此刻無法這麼做。）"]
    if arg in tactics.locks(fight.bout).no_moves:
        return [tactics.NO_MOVE.format(move=arg)]
    out = arena.exchange_full(fight, arg, c, arena.rng_for(p.season_number, p.name, fight, "交手"),
                              arena.rng_for(p.season_number, p.name, fight, "戰法"))
    line = tactics.round_line(
        f"第 {fight.round + 1} 回合：你{out.mine or '出不了手'}，他{out.his or '出不了手'}——{COUNTER_WORDS[out.beat]}。"
        f"（氣勢 {out.delta:+d}，你氣血 {-out.mine_hp:+d}，他氣血 {-out.foe_hp:+d}）", out.lines,
    )
    fight.picks.append([out.mine or "", out.his or ""])  # 擂台動畫：兩邊照出的招演
    arena_burst(fight, out.skills)
    return arena_after(ctx, line, roll_crowd(ctx, move=out.mine or "", his=out.his or ""))


def arena_gamble(
    ctx, text: str, rate: int | None, stories: tuple[str, str] | None, request: DuelTextRequest | None, crowd: str = "",
) -> list[str]:
    """擂台的放手一搏（C 段）：同一場、同一回合、同一句才用鎖外評好的分，對不上就回原因、不重評、不套用（同頭目戰）。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    fight = p.arena
    stale = duel_actions.stale_duel_request(request, f"arena:{fight.id}", fight.round, text)
    if stale:
        return stale
    if rate is None:
        verdict = battle_instance.assess_gamble(
            ctx._quick_client(), arena.scene(fight), duel_actions.duel_side(ctx), text, p.name,
            setting=arena.SETTING, place=arena.PLACE, target=arena.foe_line(fight.me, fight.foe, c), sex=gender.of(s),
        )
        rate, stories = verdict.rate, (verdict.win, verdict.lose)
    s.battle_card = None
    p.guide_done = []
    fired: list[str] = []
    skills: tuple[list[str], list[str]] = ([], [])
    rate = int(rate) + round(attrset.charm(s, c, "gamble"))  # 魅力略為提高放手一搏（五項屬性的季；企劃者 2026-11-04）
    won, delta, hp, _ = arena.gamble(fight, int(rate), c, arena.rng_for(p.season_number, p.name, fight, "搏"),
                                     arena.rng_for(p.season_number, p.name, fight, "戰法"), fired, skills)
    story = (stories or ("", ""))[0 if won else 1]
    moment = battle_instance.GambleMoment(name=p.name, faction=duel_actions.duel_side(ctx), text=text, story=story, rate=int(rate), won=won)
    old = (battle_instance.GambleMoment(name=p.name, faction="", text=fight.best_text, rate=fight.best_rate, won=fight.best_won)
           if fight.best_set else None)
    if battle_instance.more_dramatic(moment, old):
        fight.best_text, fight.best_story, fight.best_rate, fight.best_won, fight.best_set = text, story, int(rate), won, True
    if not story:
        story = f"你放手一搏：「{text}」——{'成了！' if won else '沒成，反倒露了破綻。'}"
    line = tactics.round_line(f"第 {fight.round + 1} 回合：{story}（氣勢 {delta:+d}，你氣血 {-hp:+d}）", fired)
    fight.picks.append(["搏", ""])  # 擂台動畫：放手一搏照氣勢與氣血演
    arena_burst(fight, skills)
    return arena_after(ctx, line, roll_crowd(ctx, label=crowd, move=text))


def arena_after(ctx, line: str, crowd: str | None = None) -> list[str]:
    """出完一招（或放手一搏）之後：記這一回合（與這一回合的場邊事件），分出勝負就收場，否則擲分身下一回合的招。"""
    c, p = ctx.content, ctx.state.player
    fight = p.arena
    fight.lines.append(line)
    if crowd:
        fight.lines.append(crowd)
    fight.round += 1
    tier = arena.verdict(fight, c.config.duel)
    if tier is not None:
        msgs = arena_finish(ctx, tier, line)
        return msgs[:1] + [crowd] + msgs[1:] if crowd else msgs
    arena.roll_next(fight, arena.rng_for(p.season_number, p.name, fight, "招"), c.config.arena, c.config.duel)
    return [line, crowd] if crowd else [line]


def arena_finish(ctx, tier: str, line: str) -> list[str]:
    """收場：兩邊的積分與戰績、留給守的人一筆（他下次同步補戰報）、挑的人的戰報與一則江湖紀錄、天下大事（爆冷、連勝、最精彩的一搏）。
    不扣氣血、不磨兵器防具（池子是快照）。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    cfg, w = c.config.arena, s.world
    fight = p.arena
    p.arena = None
    mine, foe = arena.entry_of(w, p.name), w.arena.get(fight.foe_key)
    score = arena.SCORES[tier]
    squad = Squad(id=f"arena:{fight.foe_key}", name=f"{fight.foe.name}的分身", difficulty=fight.foe.power)
    result = encounter.EncounterResult(tier=tier, margin=fight.edge - c.config.duel.start, our_power=fight.me.power,
                                       difficulty=fight.foe.shown)  # 戰報的「對手威力」不含玉璽碎片（FB-615）；打是照 power 打的
    title = f"{arena.ARENA}・{fight.foe.name}"
    record = battlelog.new_record(s, c, ctx.world, squad, result, "arena", event=title)
    record.ours = record.ours[:1]
    record.rounds = list(fight.lines)
    news: list[str] = []
    if mine is not None and foe is not None:
        before_me, before_foe = mine.rank, foe.rank
        was_first = foe.rank == 1
        moved = score >= 1 and arena.swap(mine, foe)
        arena.note_result(mine, score)
        arena.note_result(foe, 1 - score)
        record.changes.append(arena.SWAPPED.format(before=before_me, after=mine.rank) if moved else arena.KEPT.format(rank=mine.rank))
        foe.inbox.append(ArenaReport(
            challenger=p.name, tier=arena.defender_tier(tier, fight.edge, c.config.duel), time=w.time,
            rank=foe.rank, before=before_foe, power=fight.me.power, bare=fight.me.bare,
        ))
        if moved and was_first:
            news.append(arena.NEW_FIRST.format(winner=p.name, loser=foe.name))
        for who in (mine, foe):
            if who.streak and who.streak % cfg.streak_news == 0 and (who is mine) == (score >= 1):
                news.append(arena.STREAK.format(name=who.name, n=who.streak))
    if fight.best_set and fight.best_won and fight.best_rate <= cfg.highlight_rate:
        news.append(arena.HIGHLIGHT.format(name=p.name, text=fight.best_text))
        record.changes += renown.gain(s, c, "fame", cfg.highlight_fame)  # 名聲設計 3.2
    for text in news:
        add_rumor(s, text, content=c, layer="world")
    summary = ctx._file_battle(record, wear=False, armor_wear=False)
    msgs = [line, summary, *battlelog.gains_list(record)]
    ctx._write(title, msgs, tag=battlelog.outcome_text(record))
    # 收場之後回到擂台那一頁（擂台獨立一頁，Joy 2026-10-14「擂台應該要是獨立的一頁」）：收場卡照 arena_last 畫
    p.arena_last = ArenaResult(id=fight.id, foe=fight.foe.name, tier=tier, lines=list(fight.lines), changes=list(record.changes),
                               looks=list(fight.looks), skins=list(fight.skins), fx=list(fight.fx),
                               picks=list(fight.picks), bursts=[list(x) for x in fight.bursts])
    p.picking_arena = arena.here(s, c)
    won = tier in team.WIN_TIERS
    annals.note(s, c, annals.FIGHT, f"上擂台挑{fight.foe.name}，{tier}。", 2 if won else 1, keep=[fight.foe.name])
    ctx._save_season()  # 名次、戰績、留給守的人那一筆都在這一季的 WorldState
    return msgs


def deliver_arena(ctx) -> None:
    """同步時補擂台的事：季收了還沒打完的那一場作廢；換日記俸（arena.roll_day）；被挑了的每一場一份戰報與一則「守擂・挑的人」；
    領俸；休季時季末前三名的獎勵。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    w, cfg = s.world, c.config.arena
    if p.arena is not None and w.ended:
        p.arena = None
        ctx._write(arena.ARENA, [arena.UNSETTLED])
    rolled = arena.on(c) and arena.roll_day(w, cfg, ctx._pill_day())  # 擂台關著不動 WorldState（同步什麼都沒有時不存季）
    entry = arena.entry_of(w, p.name)
    if entry is not None and not w.ended and entry.famed != renown.arena_famed(s, c):  # 名聲 4.7：照此刻的名望段重寫
        entry.famed = not entry.famed
        rolled = True
    if entry is None or not (entry.inbox or entry.wages or (w.ended and entry.place and not entry.prized)):
        if rolled:
            ctx._save_season()
        return
    for report in entry.inbox:
        squad = Squad(id=f"arena:{name_key(report.challenger)}", name=report.challenger, difficulty=report.power)
        result = encounter.EncounterResult(tier=report.tier, margin=0.0, our_power=entry.power, difficulty=report.shown)  # 不含碎片（FB-615）
        title = f"守擂・{report.challenger}"
        record = battlelog.new_record(s, c, ctx.world, squad, result, "arena", event=title)
        record.time = report.time
        record.ours = record.ours[:1]
        record.notes.append(arena.DEFENDED.format(name=report.challenger))
        record.changes.append(arena.SWAPPED.format(before=report.before, after=report.rank) if report.rank != report.before
                              else arena.KEPT.format(rank=report.rank))
        battlelog.add_record(s, record)
        ctx._write(title, [arena.DEFENDED.format(name=report.challenger), battlelog.summary_line(record),
                           *battlelog.gains_list(record)], tag=battlelog.outcome_text(record))
    entry.inbox = []
    for _, rank in entry.wages:
        if not 1 <= rank <= len(cfg.wages):
            continue
        silver, fame = cfg.wages[rank - 1]
        p.stats["silver"] = p.stats.get("silver", 0) + silver
        renown.gain(s, c, "fame", fame)  # 名聲設計 3.2；俸那一句自己寫了名望
        ctx._write(arena.ARENA, [arena.WAGE.format(rank=rank, title=arena.title_for(rank) or "", silver=silver, fame=fame)])
    entry.wages = []
    if w.ended and entry.place and not entry.prized:
        entry.prized = True
        fame = cfg.prizes[entry.place - 1]
        renown.gain(s, c, "fame", fame)  # 名聲設計 3.2；季末那一句自己寫了名望
        lines = [arena.PRIZE.format(place=entry.place, fame=fame)]
        if cfg.prize_treasure:
            lines += treasures.arena_prize(s, c, p.season_number, entry.place)
        ctx._write(arena.ARENA, lines)
    ctx._save_season()


# ── 原位接上第 11 批掛鉤的那幾段（計畫 1.4；本體照抄原位那幾行）──


def fight_menu(ctx) -> list[Option]:
    """擂台打到一半（原本 Game._everyday_options 在 features_core.menu 下一行那一支）：三招與認輸；放手一搏同頭目戰走輸入框。"""
    held = tactics.locks(ctx.state.player.arena.bout).no_moves
    return [Option(id=f"arena:{move}", label=duel_base.move_label(move) + (tactics.lock_note(move) if move in held else ""),
                   enabled=move not in held) for move in MOVES] + [
        Option(id=arena.YIELD_ID, label=arena.YIELD),
    ]


def entry_option(ctx) -> Option | None:
    """「此地還能做」裡那一顆（原本 _everyday_options 最後那一行；店面登記 Shop.entry 回一顆或 None；閉關中、路上是 busy、road 那兩格，第 56 批）。"""
    found = arena_entry(ctx)
    return found[0] if found else None


def close(ctx) -> None:
    """收起擂台（原本 _depart、sync、_drop_stale_references 那三行：picking_arena = False）。"""
    ctx.state.player.picking_arena = False


def arena_open(ctx) -> list[str]:
    """按「擂台」（原本 Game._act 的 act:arena 那一支）：打開擂台（見 arena_options），不花體力；頭一句是名次、稱號與戰績。"""
    ctx.state.player.picking_arena = True  # 打開擂台（見 arena_options），不花體力
    ctx.state.player.arena_last = None
    return arena.standing(ctx.state.world, ctx.state.player.name, ctx.content.config.arena)


def arena_sign(ctx) -> str:
    """按「擂台」那一下江湖紀錄的標題（原本 Game._action_title 那張表的 arena）：「擂台・此地」。"""
    return f"{arena.ARENA}・{ctx.content.locations[ctx.state.player.location].name}"


def arena_title(ctx, arg: str) -> str:
    """arena:join／fight／back 那一下江湖紀錄的標題（原本 Game._action_title 的 kind == "arena" 那一支）：挑人寫「擂台・他」，其餘「擂台」。"""
    foe = arena.entry_of(ctx.state.world, arg.partition(":")[2]) if arg.startswith("fight:") else None
    return f"{arena.ARENA}・{foe.name}" if foe is not None else arena.ARENA


def arena_fight_problem(ctx, option_id: str) -> str | None:
    """按到灰掉的挑擂鈕（原本 Game.choose 查完選單之後那一段；兩個分頁、畫面還沒重抓）：為什麼挑不了、還要等多久；Game 原位照它回 Refused。
    守擂的人不在榜上是 None（照原本的 foe and …）。"""
    foe = ctx.state.world.arena.get(option_id.removeprefix("arena:fight:"))
    return foe and arena.challenge_problem(ctx.state.world, ctx.state.player.name, foe, ctx.content.config.arena,
                                           arena_left(ctx), ctx.content.config.time_scale)


def travel_block(state, content) -> TravelBlock | None:
    """block/bout 那一格（core_seams，全部拆包第 56 批；原本在 atlas.travel_block，字與先後一字不動）：頭目戰打到一半、擂台打到一半、坐在擂台邊。"""
    p = state.player
    if p.duel is not None:  # 單人頭目戰打到一半
        return TravelBlock("正跟人交手，先分出勝負或抽身退走", to_jianghu=True)
    if p.arena is not None:  # 擂台打到一半
        return TravelBlock("正在擂台上，先分出勝負或認輸下台", to_jianghu=True)
    if p.picking_arena:
        return TravelBlock("還在擂台邊，先返回才能安排前往", to_jianghu=True)
    return None
