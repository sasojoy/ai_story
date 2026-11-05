"""挑戰大勢人物本人的動作（功能包 figure_acts；全部拆包第 31 批）：閉門不見、這裡有哪幾位可以挑（選單那幾顆）、勝算、對手那一路、打一場、
打贏的那一串（心得與經驗、他敗走、掉寶物、三階、四階）、僵持。原本 Game 上的 13 個方法，名字去掉前導底線、第一個參數是 ctx。會改狀態。

`challenge` 的先後（扣體力 → 護衛那一關 → 判讀 → 打 → 戰報 → 贏了才有的一串 → 僵持／落敗 → 扣血 → 回合 → 頓悟 → 戰報 → 名聲 → 行狀）逐字照搬，
`msgs.insert(0, …)`、`msgs.insert(1, …)` 的位置也算行為。`act:challenge:<人物>` 是 act 子動詞（總表第 57 批才接 Verb），按下去、選單那一格、標題都還在核心原位叫
Game 的委派。被測試換掉的 odds（Game.challenge_odds）在 options 裡經 ctx 叫才打得到；被測試換掉的 _rout 也經 ctx 叫（Game 留一行委派）。
"""
from __future__ import annotations

import random

from tianxia.core import annal_base as annals  # 核心（行狀記一筆，第 29 批之二）
from tianxia import battlelog, calendar, deeds, four_tiers, materials, push, rise, team, treasures, wins
from tianxia import figure_life  # 共用規則層（人物活起來 figure_life，第 40 批收進）
from tianxia import figures  # 共用規則層（大勢人物 figures，第 40 批收進）
from tianxia import prologue as prologue_rules
from tianxia.calendar import DAY, HOUR
from tianxia.core.option import Option
from tianxia.core.services import BIG_FIGHT_WAIT, SNUB_NOTE
from tianxia.models import Squad
from tianxia.rules import add_world_flags, season_one, world_day

from . import figure_aid

OFF_FRONT_NOTE = "沒在戰線上領兵，不受挑戰"  # 戰線空著的人物（董卓、趙弘、重挫退下的人）：挑戰按鈕寫這一句（PM 2026-10-05 定；原本在 engine.py）


def snubbed(ctx, fid: str) -> bool:
    """這位人物剛被你打敗、還在閉門不見（snub_hours 個現實小時內）。看的是現實時間（ctx.now，sync 傳進來的），
    不是賽季時鐘：管理者快轉、補算時間都不會讓他提早見你；紀錄存在角色存檔，伺服器重開也照樣記得。
    沒有挑戰本人的季（figures.challenge_on 是假）就沒有閉門不見這回事。"""
    return figures.challenge_on(ctx.content, ctx.state.world) and ctx.now < ctx.state.player.snubbed_until.get(fid, 0.0)


def snubbed_character(ctx, character_id: str) -> bool:
    """這個對話人物（求見、交友用的 id）是不是剛被你打敗、還在閉門不見的大勢人物。"""
    fid = figures.of_character(ctx.content, character_id)
    return fid is not None and snubbed(ctx, fid)


def options(ctx, odds: bool) -> list[Option]:
    """挑戰本人：有挑戰本人的季（figures.challenge_on，每季都有）、自己有陣營時，這裡每一位在場的敵方大勢人物一個選項
    （體力照遊歷；odds 時寫勝算，難度跟著聲威走）。剛被你打敗、閉門不見的那幾位按不下去、寫明原因；戰線空著的人物（人物表
    標了 challenge_off_front 的何進除外）第一季也是灰鈕寫原因，沒有時刻表的季不畫。求見、交友照常。散人沒有；同陣營的人不打。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if p.faction is None or not figures.challenge_on(c, s.world):
        return []
    cost = ctx._action_costs()["train"]
    opts = []
    for fid in figures.present_at(s, c, p.location):
        fig = c.figures[fid]
        if fig.faction == ctx._side():  # 同陣營（豪強分屬兩軍：依附那一軍）的人物不打
            continue
        option_id = f"act:challenge:{fid}"
        if not figures.can_challenge(s, c, fid):
            if figures.untimed(c, s.world):  # 沒有時刻表的季戰線空著的人不畫鈕：看不到戰線，整季掛著一顆按不下去的鈕（設計 3.2）
                continue
            opts.append(Option(id=option_id, label=f"挑戰{fig.name}（{OFF_FRONT_NOTE}）", enabled=False))
        elif snubbed(ctx, fid):
            opts.append(Option(id=option_id, label=f"挑戰{fig.name}（{SNUB_NOTE}）", enabled=False))
        else:
            note = ctx.challenge_odds(fid) if odds else ""
            guards = len(figure_aid.posts(s, c, fid)) if figure_aid.on(c) else 0
            if guards:
                note = "・".join(x for x in (note, figure_aid.GUARDED_NOTE.format(n=guards)) if x)
            option = ctx._cost_option(option_id, f"挑戰{fig.name}", cost, note=note)
            option.wait = BIG_FIGHT_WAIT  # 挑戰本人一律是大場面：按下去先等模型判讀（武學與成長設計 8.3）
            opts.append(option)
    return opts


def odds(ctx, fid: str) -> str:
    """挑戰這位人物的勝算（跟遊歷同一套說法）：對手是代表本人的隊伍，難度照他此刻的聲威（figures.difficulty）與江湖水漲。"""
    squad = figure_squad(ctx, fid)
    return team.estimate(ctx.state, ctx.content, ctx.world, squad.id, difficulty=squad.difficulty,
                         draw_floor=rise.draw_floor(ctx.content))


def figure_squad(ctx, fid: str) -> Squad:
    """挑戰這位人物本人要打的那一路：難度照他此刻的聲威（figures.squad_of），再照江湖水漲浮上來——你此刻對他的全隊威力 ×
    倍數，倍數照你這一季打贏他幾次（figure_wins）往上加（rise.big）。勝算、備料（A、C 段）、打起來都照這一份。"""
    s, c = ctx.state, ctx.content
    squad = figures.squad_of(s, c, fid)
    if not rise.on(c):
        return squad
    # 地利不浮上去（武學隨地理環境 2.1）；玉璽碎片的戰力也不浮上去（改版 PM 五之一 2）
    power = team.power_vs(s, c, ctx.world, squad, fresh=True, terrain=False, seal=False)
    level = rise.big(c, squad.difficulty, power, s.player.figure_wins.get(fid, 0))
    return squad if level == squad.difficulty else squad.model_copy(update={"difficulty": round(level, 1)})


def challenge(ctx, fid: str) -> list[str]:
    """挑戰本人（軍令文件 4.5，企劃者 2026-10-04 改定）：跟他本人打一場單次判定，花遊歷的體力。打贏他敗走（_rout），
    拿那支隊伍的獎勵；落敗失落一成銀兩；不論勝負都照結果扣氣血（同遊歷）。可以重複打，只是打贏的人要等他消氣。
    不推戰線（推戰線的是遊歷；打擊人物削的是聲威），也不擲官銀（那是遊歷打贏官軍隊伍才有）。
    打贏另有機會掉一件寶物（_figure_treasure）。打贏記一次 figure_wins，第 signature_wins 次他讓你奪走本命兵器
    （_signature_arms，現在只有孫堅）。"""
    s, c = ctx.state, ctx.content
    fig = c.figures[fid]
    squad = figure_squad(ctx, fid)
    s.player.stamina -= ctx._action_costs()["train"]
    post, broke = figure_aid.contest(s, c, fid, s.player.name, ctx._battle_power()) if figure_aid.on(c) else (None, True)
    if not broke:  # 護衛擋下：這一次挑戰不成，不打他本人、不扣情誼（Joy 2026-10-17 第 6 條）
        return [figure_aid.BLOCKED_LINE.format(guard=post.name, name=fig.name)]
    judged = ctx._judged(squad)  # 挑戰本人一律是大場面：有鎖外的判讀就用（武學與成長設計 8.3）
    result = ctx._fight_with(squad, judged, difficulty=squad.difficulty, draw_floor=rise.draw_floor(c))
    record = battlelog.new_record(s, c, ctx.world, squad, result, "event", event=f"挑戰{fig.name}")
    record.notes += ctx._style_note(squad, result) + ctx._terrain_note()
    ctx._narrate(record, result, judged)
    msgs: list[str] = []
    arm_annals: list[tuple[str, str]] = []  # 本命兵器那一筆行狀：等這一場的行狀記完再記（照時間先後）
    if result.tier in team.WIN_TIERS:
        p, cfg = s.player, c.config
        first = p.figure_wins.get(fid, 0) == 0  # 丁 (c)：這一季第一次打贏他才有三階（預設表照擲；之後照擲、擲中不給）
        capped = bool(cfg.figure_rare_cap) and p.figure_rare_drops >= cfg.figure_rare_cap  # 一人一季上限，叛投不清
        p.figure_wins[fid] = p.figure_wins.get(fid, 0) + 1  # 本命兵器「打贏他本人三次」（兵器設計 4.10）：這一季累計
        reward = win_reward(ctx, fid, squad)
        held = held_tier3(ctx)
        msgs += ctx._battle_rewards(reward, record, max_tier=None if first and not capped else 2)
        p.figure_rare_drops += held_tier3(ctx) - held
        fame = ctx._deed_fame("challenge")  # 名聲 3.1：挑戰本人打贏 +2（推翻挑戰每季都有設計的「不給」）
        record.changes += fame
        msgs += fame
        extra = ctx._rout(fid)
        changes, notes = battlelog.split_changes(extra, for_record=True)
        record.changes += changes
        record.notes += notes
        msgs += extra
        msgs += treasure(ctx, fid, record)  # 打贏本人掉寶物（裝備四欄 6.4）：只進江湖紀錄，戰報的「得失」寫 GAIN_LINE（同兵器掉落）
        msgs += tier3(ctx, fid, squad, record)  # 打贏本人掉一個三階（兵器設計 4.9）：戰報「得失」與江湖紀錄
        msgs += tier4(ctx, fid, squad, record)  # 這一季第一次打贏他另擲一個四階（正式季整合 4.5）
        msgs += ctx._signature_arms(record, beaten=fid, later=arm_annals)  # 第三次打贏那一刻他讓你奪走（寫進這一場戰報的「得失」）；_rout 把他打到重創的這一場照給
    elif result.tier == "僵持":
        msgs += draw(ctx, fid, squad, record)
    elif result.tier == "落敗":
        msgs += ctx._lose_silver(record)
    toll, hp_lost, facts = ctx._take_toll(result.tier, clash=result.clash)
    record.changes += toll
    msgs += toll
    ctx._play_rounds(record, squad, result.tier, hp_lost, facts, clash=result.clash)  # squad 是照聲威的那一份：對手的身法跟著難度走
    msgs += ctx._seize(record, draw=c.config.figure_draw_share > 0)  # 挑戰本人打成僵持也算一次頓悟的契機（企劃者 2026-10-16）
    msgs.insert(0, ctx._file_battle(record, wear=True, armor_wear=True))  # 挑戰本人的戰報 kind 是 event，但兵器、防具照磨（兵器設計 3.4、裝備四欄 4.4）
    ctx._famed_news(c.locations[s.player.location].name, fig.name, result.tier)  # 名聲 4.5：挑戰本人一律是大場面
    won = result.tier in team.WIN_TIERS
    annals.note(s, c, annals.FIGHT, f"挑戰{fig.name}本人，{result.tier}" + ("，他敗走。" if won else "。"), 4 if won else 3,
                figure=fig.character or "")
    for text, who in arm_annals:
        annals.note(s, c, annals.FIGURE, text, 4, figure=who)
    if post is not None:
        msgs.insert(1, figure_aid.BROKE_LINE.format(guard=post.name, name=fig.name))
    return msgs


def win_reward(ctx, fid: str, squad: Squad) -> Squad:
    """挑戰本人打贏的那一份心得、經驗。戊 (b)：被打弱的人物照難度比例少給——照聲威的那一份算，江湖水漲浮上去的難度不多給。"""
    s, c = ctx.state, ctx.content
    ratio = min(1.0, figures.difficulty(s, c, fid) / figures.start_difficulty(c, fid))
    return squad.model_copy(update={"reward_xinde": int(squad.reward_xinde * ratio + 0.5), "exp": int(squad.exp * ratio + 0.5)})


def draw(ctx, fid: str, squad: Squad, record) -> list[str]:
    """挑戰本人打成僵持（企劃者 2026-10-16「僵持也給一點東西，讓重複挑戰不是純虧體力」）：險勝那一份心得、經驗的
    draw_share（一半），不乘寶物與遊俠名號的「打贏」加成；不給銀兩、素材、三階、寶物、碎片，聲威不動、不閉門不見、
    不算打贏（figure_wins、本命兵器、江湖水漲的倍數都不動）。情誼也不扣：扣情誼是把他打到敗走的代價（_rout），
    平手是堂堂正正過了招，不是折辱他。頓悟的契機在 _seize(draw=True)。"""
    p, share = ctx.state.player, ctx.content.config.figure_draw_share
    won = win_reward(ctx, fid, squad)
    xinde, exp = int(won.reward_xinde * share + 0.5), int(won.exp * share + 0.5)
    msgs = [figures.DRAW_LINE.format(name=ctx.content.figures[fid].name)]
    if xinde:
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        record.xinde = xinde
        msgs.append(f"心得 +{xinde}")
    msgs += ctx._record_exp(record, exp, "challenge")
    levels, record.levelups = team.grant_team_exp(ctx.state, ctx.content, ctx.world, exp, "challenge")
    record.notes += levels
    return msgs + levels


def rout(ctx, fid: str) -> list[str]:
    """打贏了，他敗走：
    1. 聲威扣 figure_defeat_prestige，照陣營人數緩衝（push.buffered，n＝自己陣營活躍時窗內推過大勢的人，含自己）；
       扣到 0 退場或重創、由接位的人接手（figures.defeat）；
    2. 打贏的人跟他的情誼扣 figure_defeat_affinity（沒有對話人物的彭脫、韓忠沒有情誼）；
    3. snub_hours 個現實小時內他不見你、也不跟你交手（其他人照常）；
    4. 記貢獻（只在第一季：其他季沒有晉升，同截殺）：照推 figure_defeat_prestige 點大勢算（contrib_per_push，不打人數緩衝的折），
       記在這一週。"""
    s, c = ctx.state, ctx.content
    p, w, cfg = s.player, s.world, c.config
    fig = c.figures[fid]
    window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
    n = push.active_count(s, ctx._side(), w.time, window)
    msgs = [f"{fig.name}敗走。"]
    cap = figures.loss_cap(c, w)  # 甲 (d)：沒有時刻表的季與 21 天季（正式季整合 3.9）每位人物一天最多被打掉幾點；週末的第一季照人數緩衝
    today = world_day(c, w)  # 21 天季台灣 00:00 換日（正式季整合設計 1.3）
    if cfg.figure_dent_once_per_day and p.figure_dented.get(fid) == today:  # 同一個人同一位人物一天只有第一場扣聲威（PM 2026-10-16）
        msgs.append(figures.DENT_ONCE_LINE.format(name=fig.name))
    else:
        p.figure_dented[fid] = today
        msgs += figures.defeat(s, c, fid, push.buffered(cfg.figure_defeat_prestige, n), cap=cap)
    if fig.out_flag and figures.untimed(c, w) and figures.is_out(s, fid):  # 丙 (c)：沒有時刻表的季打退波才＝擊敗波才（第一季不記）
        add_world_flags(s, [fig.out_flag])
    if fig.character is not None:
        before = p.affinities.get(fig.character, 0)
        p.affinities[fig.character] = max(0, before - cfg.figure_defeat_affinity)
        if p.affinities[fig.character] != before:
            msgs.append(f"{fig.name}情誼 {p.affinities[fig.character] - before:+d}")
    msgs += figure_life.spread(  # 風聞（大勢人物擴充）：同一大區的人物聽說了，同一方的情誼掉、對頭的漲
        s, c, "beat", fid, at=p.location, side=fig.faction,
        text=f"在{c.locations[p.location].name}打退了{fig.name}")
    deeds.record(s, c, "beat", f"{p.name}在{c.locations[p.location].name}打退了{fig.name}。", place=p.location,  # 世界活起來
                 figures=[fig.character] if fig.character else [], actors=[p.name], side=ctx._side())
    p.snubbed_until[fid] = ctx.now + cfg.snub_hours * HOUR
    if season_one(c, w):
        wins.credit(p, c, w, calendar.point(w.time, c, w).week, cfg.figure_defeat_prestige * cfg.contrib_per_push)
    msgs += ctx._order_credit(  # 「打擊大勢人物」軍令（計畫 T6）：只算目標本人
        kind="challenge", location=p.location, front=figures.state_of(s, c, fid).front, figure=fid,
    )
    return msgs


def treasure(ctx, fid: str, record) -> list[str]:
    """挑戰本人打贏掉寶物（裝備四欄 6.4；treasures.challenge_drop）：掉出來的那一件寫進這一場戰報的「得失」（record.materials），
    江湖紀錄寫撿到的那一句與放哪。不寫進 _battle_rewards：挑戰本人的戰報 kind 是 event，劇情戰也走那裡。"""
    item, lines = treasures.challenge_drop(ctx.state, ctx.content, fid, ctx.world.get_season_number(), record.id)
    if item is not None:
        record.materials.append(treasures.GAIN_LINE.format(name=item.name))
    return lines


def tier3(ctx, fid: str, squad: Squad, record) -> list[str]:
    """挑戰本人打贏掉一個三階（兵器設計 4.9；challenge_tier3）：同一位人物對同一個人每季最多 tier3_per_figure 次（0＝不設限；
    正式值 1：這一季第一次打贏才有，挑戰每季都有設計丁 (c)；PlayerState.tier3_drops，角色每季重來自然清掉，同 treasure_drops）；
    挑戰本人掉的三階（連預設表那一條）一人一季最多 figure_rare_cap 個（figure_rare_drops）。"""
    rule, p, cap = ctx.content.config.forge_secrets, ctx.state.player, ctx.content.config.figure_rare_cap
    if rule.tier3_per_figure and p.tier3_drops.get(fid, 0) >= rule.tier3_per_figure:
        return []
    if cap and p.figure_rare_drops >= cap:
        return []
    got = ctx._tier3(squad, record, rule.challenge_tier3, f"挑戰|{fid}", materials.CHALLENGE_SOURCE)
    if got:
        p.tier3_drops[fid] = p.tier3_drops.get(fid, 0) + 1
        p.figure_rare_drops += 1
    return got


def tier4(ctx, fid: str, squad: Squad, record) -> list[str]:
    """挑戰本人這一季第一次打贏某位人物另擲一個四階（正式季整合 4.5，第 4 批）：只看「這一季第一次」（PlayerState.tier4_wins，
    另一本帳，不讀三階的 tier3_drops；三階的 6 個滿了照擲），擲 Config.four_tiers.challenge_chance，一人一季最多 challenge_cap 個
    （tier4_challenge_drops，叛投不清）。屬性照他的隊伍（materials.tier_pick）。自己的亂數，不碰 Game.rng。素材四階關著、序章不擲。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.four_tiers
    if not four_tiers.on(c) or prologue_rules.active(s, c) or fid in p.tier4_wins:
        return []
    p.tier4_wins.append(fid)
    if p.tier4_challenge_drops >= cfg.challenge_cap:
        return []
    seed = f"四階|{ctx.world.get_season_number()}|{p.name}|{record.id}|挑戰|{fid}"
    if random.Random(seed).random() >= cfg.challenge_chance:
        return []
    mid = materials.tier_pick(c, squad.attribute, seed, four_tiers.TIER)
    line = materials.grant(s, c, mid) if mid is not None else None
    if not line:
        return []
    p.tier4_challenge_drops += 1
    materials.add_cell(record.materials, c, mid, 1, source=materials.CHALLENGE_SOURCE)
    return [materials.extra_line(c, mid, 1, materials.CHALLENGE_SOURCE)]


def held_tier3(ctx) -> int:
    """背包裡的三階素材合計（_challenge 照它算挑戰本人這一場的預設表掉了幾個三階，記進 figure_rare_drops）。"""
    mats = ctx.content.materials
    return sum(n for mid, n in ctx.state.player.materials.items() if n > 0 and mid in mats and mats[mid].tier == 3)
