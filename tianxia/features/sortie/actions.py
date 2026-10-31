"""出陣的動作（功能包 tianxia/features/sortie/；原本是 Game 上出陣本體、混戰、出陣回報的 21 個方法，開發規範手冊 3.2、主動搬六包第 1 批）。

ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。本體照搬、一個字不改（self 換成 ctx、sortie 模組換成 rules）。
函式名＝原本的方法名去掉前導底線，兩個例外：`_sortie_mode(loc)` 是 `sortie_mode_of`（跟 `sortie_mode()` 分開）、`_clash` 是 `do_clash`
（`sortie` 裡有區域變數叫 clash）。Game 上留 13 個一行委派（server、假人、測試、腳本與核心原位還在叫：選單那一格、`_act` 的
act:train、行動列底下那一行、`_squad_encounter` 的 as_sortie、守勢行動、輿圖）。包裡互相叫直接叫這裡的函式（約戰，第 2 批的
duel_actions，也直接叫 sortie_line、sortie_rewards；約戰開著時出陣那一格與次數，這裡直接叫 duel_actions）；只有
`sorties_left`、`_sortie_hold` 經 ctx 叫（測試換掉 Game.sorties_left、腳本換掉 Game._sortie_hold，換掉的才打得到）。
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from tianxia import gender, team
from tianxia import allied  # 過渡：待搬（豪強依附的那一軍：混戰撞不撞得上）
from tianxia import annals  # 過渡：待搬（行狀：混戰那一筆交手）
from tianxia import battlelog  # 過渡：待搬（戰報）
from tianxia import conquest  # 過渡：待搬（地盤：區塊、進度、推不推得動、混戰的對象）
from tianxia import encounter  # 過渡：待搬（單次判定：混戰）
from tianxia import four_tiers  # 過渡：待搬（素材四階：打贏照掉落表掉素材）
from tianxia import howto  # 過渡：待搬（行動列底下那一行的句子）
from tianxia import materials  # 過渡：待搬（素材的掉落與發放）
from tianxia import orders  # 過渡：待搬（軍令：截糧的運糧隊、出陣回報的軍令小籤）
from tianxia import precise  # 過渡：待搬（一類一顆：打贏的獎勵怎麼算）
from tianxia import prologue as prologue_rules  # 過渡：待搬（序章：雪恥、不掉東西）
from tianxia import ranger  # 過渡：待搬（遊俠名號：經驗倍數）
from tianxia import roster  # 過渡：待搬（截殺的新手期：混戰照它）
from tianxia import territory  # 過渡：待搬（地盤：誰控制、這裡駐著哪幾路）
from tianxia import treasures  # 過渡：待搬（寶物：多掉一個素材、出陣的稀有掉落）
from tianxia.characters import name_key
from tianxia.core.option import Option
from tianxia.core.services import drill_share
from tianxia.guide import note_action  # 過渡：待搬（入伍段的「出一次力」）
from tianxia.models import Location, Squad
from tianxia.state import FrontReport

from . import duel_actions  # 出陣約戰（第 2 批搬進同一包）：約戰開著時出陣那一格與次數
from . import duel_rules as sortie_duel
from . import rules

if TYPE_CHECKING:
    from tianxia.engine import Game


def sortie_line(ctx: Game, loc: Location) -> str:
    """出陣那一行（howto.sortie_line）：這裡是哪一種、推不推得動（_push_room，同第 3、4 階行動）、今天還能出陣幾次；用完寫什麼時候再來。"""
    how = sortie_mode_of(ctx, loc)
    if how is None:
        if rules.out_of_contest(ctx.content, ctx.state.world, ctx._side(), loc.id):
            return rules.OUT_LINE  # 領地爭奪：別人的大本營、廣宗不給攻（裁決 18）
        if not rules.ranger_here(ctx.content, ctx._side(), loc.id, ctx.state.world):
            return ""
        if ctx._outing_on():  # 減法季探索一顆：沒有尋敵了，散人的仗靠出門一趟的遭遇拍（FB-817）
            return rules.RANGER_LINE_OUTING
        return rules.RANGER_LINE_PRECISE if precise.on(ctx.content, ctx.state.world) else rules.RANGER_LINE
    left = ctx.sorties_left()
    if left <= 0:
        return rules.USED_UP.format(n=ctx.content.config.sortie.per_day) + "。"
    own = how == "attack" and territory.controller(ctx.state.world, ctx.content, loc.id) == ctx._side()
    # 領地爭奪：出陣推的是這一塊的進度（大本營、廣宗推不動），不是線——那一句照進度寫；推不動照 conquest.push_problem 寫原因
    # （剛易手、戰書凍結、不相連、守了沒得拉；翻地與爭搶）
    why = conquest.push_problem(ctx.state.world, ctx.content, ctx._side(), loc.id, how)
    note = "convoy" if own else how  # 自家地盤上攻的只有運糧隊（FB-255）
    if how == "hold" and not conquest.capturable(ctx.content, loc.id):
        note = "home"  # 自家的大本營、廣宗：不在爭奪之列（FB-532）
    elif how == "attack" and not conquest.capturable(ctx.content, loc.id):
        note = "convoy_out"  # 大本營、廣宗上攻的只有截糧的運糧隊（裁決 18）：只算截糧、沒有進度
    elif note == "attack" and conquest.holder(ctx.state.world, ctx.content, loc.id) is None:
        note = "open"  # 還沒人佔的中立地：不寫「這裡歸別人」（FB-533）
    # FB-552：被戰書凍結的那一塊，原因照那一場攻城在哪一步寫（已下戰書、集結中、開打中；conquest.push_problem 讀 siege_state）
    return howto.sortie_line(note, left, ctx.content, why is None, why)


def train_title(ctx: Game) -> str:
    """act:train 的紀錄標題：出陣開著時寫「出陣」，序章的雪恥寫「雪恥」；關著照舊「遊歷」。"""
    if not rules.on(ctx.content):
        return "遊歷"
    return rules.PROLOGUE_FIGHT if prologue_rules.active(ctx.state, ctx.content) else rules.NAME


def sorties_left(ctx: Game) -> int:
    """今天還能出陣幾次（Config.sortie.per_day；換日同回體丹，_pill_day）。約戰開著的季讀 jianfa_per_day（減法季批 3b）。"""
    if duel_actions.duel_on(ctx):
        return sortie_duel.left_today(ctx.state.player, ctx.content.config.sortie, ctx._pill_day())
    return rules.left_today(ctx.state.player, ctx.content, ctx._pill_day())


def sortie_foes(ctx: Game, loc: Location) -> list[str]:
    """出陣攻打的對手（設計 2.2；領地爭奪 conquest.sortie_foes），加上截糧軍令帶來的敵方運糧隊（orders.extra_enemies；
    自家地盤上有運糧隊時出陣就是去截它）。"""
    s, c = ctx.state, ctx.content
    own = ctx._side()  # 豪強分屬兩軍：依附的那一軍
    ids = conquest.sortie_foes(s.world, c, loc.id, own)  # 中立地打那裡的駐軍與流寇野獸，敵方的陣營區塊打控制方的兵
    extra = orders.extra_enemies(s, c, loc.id, own)
    return ids + [sid for sid in extra if sid not in ids]


def sortie_mode_of(ctx: Game, loc: Location) -> str | None:
    return rules.mode(ctx.content, ctx.state.world, ctx._side(), loc.id, bool(sortie_foes(ctx, loc)))


def sortie_mode(ctx: Game) -> str | None:
    """所在地此刻出陣是哪一種（假人照它挑，bot_policy）；在路上是 None。"""
    p = ctx.state.player
    return None if p.journey is not None else sortie_mode_of(ctx, ctx.content.locations[p.location])


def sortie_progress(ctx: Game, loc_id: str | None = None, how: str | None = None) -> float:
    """領地爭奪：在這個地點（預設所在地）出陣推（攻）或拉（守）進度的名目量（conquest.sortie_nominal；還沒打人數緩衝與集火）。
    開關關著、沒有出陣、這一塊此刻推不動（conquest.push_problem：大本營、不相連、冷卻、戰書凍結、守了也沒得拉）是 0。假人照它挑往哪裡走
    （bot_policy._train_value）。"""
    s, c = ctx.state, ctx.content
    loc = c.locations[loc_id or s.player.location]
    if not conquest.on(c, s.world) or ctx._side() is None:
        return 0.0
    how = how or sortie_mode_of(ctx, loc)
    if how is None or conquest.push_problem(s.world, c, ctx._side(), loc.id, how) is not None:
        return 0.0
    return conquest.sortie_nominal(c, loc.id, how)


def clash_target(ctx: Game, loc_id: str, how: str) -> Game | None:
    """這一下出陣撞得上的人（設計 4.3、第九章第 14 條）：自己這一下推得動（push_problem 是 None）；對面 clash_minutes 內在這一塊出陣過
    （conquest.clash_names，最近的先）、人此刻還站在這裡、不在路上；照截殺的保護——截殺開著（Config.raid.enabled）、季沒收、雙方過了新手期
    （roster.raid_newbie）、這一對兩個方向都過了 pair_cooldown_seconds（WorldState.raids，跟截殺同一本帳）、他沒在 shield_seconds 內被截過
    （raided）。城鎮也打（截殺「城裡不便動手」只管截殺）。沒有是 None。"""
    s, c = ctx.state, ctx.content
    w, me = s.world, s.player
    side = ctx._side()
    cfg = c.config.raid
    if not cfg.enabled or w.ended or side is None or roster.raid_newbie(s, c):
        return None
    if conquest.push_problem(w, c, side, loc_id, how) is not None:
        return None
    for name in conquest.clash_names(w, c, loc_id, side, me.name):
        last = max(w.raids.get(ctx._raid_key(me.name, name), -math.inf), w.raids.get(ctx._raid_key(name, me.name), -math.inf))
        if w.time - last < cfg.pair_cooldown_seconds:
            continue
        hit = w.raided.get(name_key(name))
        if hit is not None and w.time - hit < cfg.shield_seconds:
            continue
        other = ctx._load_kin(name)
        if other is None:
            continue
        o = other.state.player
        if o.location != loc_id or o.journey is not None or roster.raid_newbie(other.state, c):
            continue
        theirs = allied.side_of(other.state, c)
        if theirs is None or theirs == side:
            continue
        return other
    return None


def do_clash(ctx: Game, loc_id: str, how: str) -> tuple[list[str], str | None]:
    """混戰（設計 4.3【企劃者選 b】）：撞得上人（_clash_target）就打一場——本人對本人（_spar_power），亂數「混戰|地點|我|他|世界秒」（不碰 Game.rng）。
    贏：這一下推力 ×clash_scale（_clash_won，_push_progress 乘）；輸：這一下白跑；平手：照常出陣、不加成。沒有戰利品（不失銀兩、不扣氣血、
    不磨兵器防具、不記截殺的貢獻）；冷卻與護身記進截殺那一本（這一對兩個方向、他的護身）。雙方各一份戰報（kind melee）、他那一則紀錄
    這裡寫、存檔這裡寫回。回（要接在這一下前面的句子, "won"／"lost"／"draw"；沒撞上是 None）。"""
    other = clash_target(ctx, loc_id, how)
    if other is None:
        return [], None
    s, c = ctx.state, ctx.content
    w, me, them = s.world, s.player, other.state.player
    for key in (ctx._raid_key(me.name, them.name), ctx._raid_key(them.name, me.name)):
        w.raids[key] = w.clashes[key] = w.time
    w.raided[name_key(them.name)] = w.clashed[name_key(them.name)] = w.time  # 記下是混戰寫的：截殺的拒絕話照實寫（FB-607）
    ours, theirs = ctx._spar_power(ctx, other), ctx._spar_power(other, ctx)
    result = encounter.resolve_encounter(ours, theirs, random.Random(f"混戰|{loc_id}|{me.name}|{them.name}|{w.time}"))
    mirrored = ctx._spar_mirror(result, theirs)
    outcome = "won" if result.tier in team.WIN_TIERS else "lost" if mirrored.tier in team.WIN_TIERS else "draw"
    place = c.locations[loc_id].name
    side = c.scenario.faction_name(allied.side_of(other.state, c), "")
    opening = rules.CLASH_OPEN.format(rival=them.name, place=place, side=side)
    verdict = {"won": rules.CLASH_WON, "lost": rules.CLASH_LOST, "draw": rules.CLASH_DRAW}[outcome].format(rival=them.name)
    ctx.touched.add(them.name)
    him = gender.pronoun(s)
    # 被撞的那一方照**他自己的**勝負挑句子（FB-606：outcome 是出陣這一方的，出陣的贏＝他輸）；rules.CLASH_THEIRS_WON 是「被撞的人贏了」那一句
    theirs_outcome = {"won": "lost", "lost": "won", "draw": "draw"}[outcome]
    story = {"won": rules.CLASH_THEIRS_WON, "lost": rules.CLASH_THEIRS_LOST, "draw": rules.CLASH_THEIRS_DRAW}[theirs_outcome]
    melee_record(other, mirrored, me.name, ours, ctx, story.format(rival=me.name, place=place, him=him), rules.CLASH_HIT_TITLE)
    msgs = melee_record(ctx, result, them.name, theirs, other, f"{opening}{verdict}", None)
    ctx._save_kin(other)
    return msgs, outcome


def melee_record(
    ctx: Game, result: encounter.EncounterResult, rival: str, rival_power: float, rival_game: Game, story: str, title: str | None,
) -> list[str]:
    """混戰這一邊的戰報（kind melee；對手寫成一支只為這一場存在的隊伍，同截殺）。沒有得失、不磨兵器防具。title 給了（被撞的那一方）
    另起一則江湖紀錄；出陣的那一方接在這一下出陣的那一則裡。行狀兩邊各記一筆（交手）。"""
    s, c = ctx.state, ctx.content
    squad = Squad(
        id=f"melee:{rival}", name=rival, difficulty=rival_power,
        attribute=team.worn_attribute(rival_game.state, c, rival_game.world),
    )
    record = battlelog.new_record(s, c, ctx.world, squad, result, "melee")
    record.ours = record.ours[:1]
    record.notes.append(story)
    annals.note(s, c, annals.FIGHT, story, 2, keep=[rival])
    ctx._play_rounds(record, squad, result.tier, 0)
    line = ctx._file_battle(record, wear=False, armor_wear=False, team_exp=False)
    msgs = [line, story]
    if title is not None:
        ctx._write(title.format(rival=rival), msgs, tag=battlelog.outcome_text(record), battle_id=record.id)
    return msgs


def sortie_option(ctx: Game, loc: Location, cost: int, odds: bool) -> Option | None:
    """出陣的鈕（設計 2.2、2.3）：沒有出陣是 None；今天次數用完灰掉、寫什麼時候再來；攻照遊歷的寫法寫對手與勝算、必敗先問、
    大場面等模型（_train_option）；守寫零風險。標籤一律「出陣・攻／守（體力 N・今日還能 M 次・…）」。
    約戰開著的季（減法季批 3b）換成 _duel_option。"""
    if duel_actions.duel_on(ctx):
        return duel_actions.duel_option(ctx, loc)
    how = sortie_mode_of(ctx, loc)
    if how is None:
        return None
    name = f"{rules.NAME}・{rules.MODE_NAMES[how]}"
    left = ctx.sorties_left()
    if left <= 0:
        used = rules.USED_UP.format(n=ctx.content.config.sortie.per_day)
        return Option(id="act:train", label=f"{name}（{used}）", enabled=False)
    tail = rules.LEFT_NOTE.format(n=left)
    if how != "attack":
        return ctx._cost_option("act:train", name, cost, note=f"{tail}・零風險")
    return ctx._train_option(loc, cost, odds, name=name, tail=tail)


def sortie(ctx: Game) -> list[str]:
    """出陣（act:train；體力 _act 已經扣了）：記今天一次，照這裡此刻歸誰攻或守。不接戰後事件（搬到找素材，設計 2.4）。
    不論哪一種、有沒有替軍令記到功，都算入伍段的「出一次力」（note_action 對已經走過的步驟什麼都不做）。"""
    s, c = ctx.state, ctx.content
    loc = c.locations[s.player.location]
    how = sortie_mode_of(ctx, loc)
    rules.spend(s.player, ctx._pill_day())
    on = how in ("attack", "hold")
    # 領地爭奪（翻地與爭搶）：推得動的地方出陣，先看撞不撞得上對面正在推的人（混戰，輿圖簡化設計 4.3）；輸了這一下白跑
    side = ctx._side()
    why = conquest.push_problem(s.world, c, side, loc.id, how) if on else None
    pushable = on and why is None
    before = conquest.bars(s.world, loc.id) if on else {}
    clash, outcome = do_clash(ctx, loc.id, how) if pushable else ([], None)
    ctx._clash_won, ctx._sortie_marked = outcome == "won", False
    ctx._sortie_moved, ctx._sortie_flipped = 0.0, False
    try:
        if outcome == "lost":
            msgs = list(clash)
            ctx._outcome(rules.CLASH_LOST_TAG, clash[-1] if clash else "")
        elif how == "attack":
            squad = ctx._train_pick(loc) if ctx._big_trip(loc) else c.squads[ctx.rng.choice(sortie_foes(ctx, loc))]
            msgs = clash + ctx._squad_encounter(squad.id, as_sortie=True)
        else:
            msgs = clash + ctx._sortie_hold(loc, how)
        if pushable and not ctx._sortie_marked:  # 打輸守軍、混戰輸了：人確實在這裡推，記一筆 0（正在推的人、集火、混戰讀它）
            conquest.mark(s.world, c, loc.id, s.player.name, side, how, 0.0)
        if on and ctx._draft is not None:  # 出陣回報：「剛剛」卡片底下那一塊（企劃者 2026-10-23）
            ctx._draft.front = front_report(ctx, loc, how, before, why)
    finally:
        ctx._clash_won, ctx._sortie_marked = False, False
        ctx._sortie_moved, ctx._sortie_flipped = 0.0, False
    return msgs + ctx._guide(note_action(s, c, ctx.world, "order"))


def front_report(ctx: Game, loc: Location, how: str, before: dict[str, float], why: str | None) -> FrontReport:
    """出陣回報（rules.report）：這一下之後那一塊的進度、今天自己與全軍推了多少、這條戰線上攻（攻城）或守（守城）那一道軍令的進度。"""
    s, c = ctx.state, ctx.content
    w, side, day = s.world, ctx._side(), ctx._pill_day()
    line = conquest.line_of(w, c, loc.id)
    kinds = ("siege",) if how == "attack" else ("defend",)
    found = [
        (orders.KIND_NAMES[o.template], min(sum(o.progress.values()), o.quota), o.quota, o.done)
        for o in orders.current(s, c, side) if o.template in kinds and o.front == line
    ]
    return rules.report(
        c, w, loc.id, side, how, before=before, moved=ctx._sortie_moved, flipped=ctx._sortie_flipped, why=why,
        used=c.config.sortie.per_day - ctx.sorties_left(), mine_today=conquest.today_moved(w, day, side, s.player.name),
        side_today=conquest.today_moved(w, day, side), orders=found,
    )


def sortie_rewards(ctx: Game, squad: Squad, record) -> list[str]:
    """出陣攻打贏給自己的。一類一顆開著（正式季整合 2.6，第 4 批）：經驗、心得是對手的 reward_scale（兩倍，寶物與遊俠名號照乘，
    同練功打贏的算法再乘二），銀兩全額另加軍功賞（等級 × merit_silver_per_level），另擲稀有掉落（_sortie_rare）；關著照舊三成（_sortie_drill）。
    素材四階開著（10.1）：照對手的掉落表掉素材、寶物多掉一個也加上出陣（不擲兵器 3%）。經驗整隊一起拿（同遊歷）。"""
    s, c = ctx.state, ctx.content
    msgs = sortie_full(ctx, squad, record) if precise.on(c, s.world) else sortie_drill(ctx, squad, record)
    if four_tiers.on(c) and not prologue_rules.active(s, c):
        msgs[:0] = squad_drops(ctx, squad, record)
    if precise.on(c, s.world) and not prologue_rules.active(s, c):
        msgs += sortie_rare(ctx, record)
    return msgs


def squad_drops(ctx: Game, squad: Squad, record) -> list[str]:
    """照對手的掉落表掉素材（同遊歷，Game.rng），寶物「打贏多掉一個素材」另擲一個（自己的亂數）；寫進戰報的得失。"""
    got: list[str] = []
    msgs: list[str] = []
    cap = conquest.drop_cap(ctx.state.world, ctx.content, ctx.state.player.location)  # 領地爭奪：剛易手的中立地只掉一階（翻地與爭搶）
    for material_id, count in materials.roll_squad_drops(squad, ctx.content, ctx.rng, max_tier=cap):
        line = materials.grant(ctx.state, ctx.content, material_id, count)
        if line:
            got.append(material_id)
            materials.add_cell(record.materials, ctx.content, material_id, count)
            msgs.append(line)
    extra = treasures.extra_drop(ctx.state, ctx.content, got, ctx.world.get_season_number(), record.id)
    line = materials.grant(ctx.state, ctx.content, extra) if extra is not None else None
    if line:
        source = ctx.state.player.treasure.name if ctx.state.player.treasure is not None else "寶物"
        materials.add_cell(record.materials, ctx.content, extra, 1, source=source)
        msgs.append(materials.extra_line(ctx.content, extra, 1, source))
    return msgs


def sortie_full(ctx: Game, squad: Squad, record) -> list[str]:
    """一類一顆的出陣攻打贏（2.6）：對手經驗、心得 × reward_scale（寶物與遊俠名號同 _battle_rewards），銀兩全額＋軍功賞。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.sortie
    msgs: list[str] = []
    merit = p.member.level * cfg.merit_silver_per_level
    silver = squad.reward_silver + merit
    if silver:
        p.stats["silver"] = p.stats.get("silver", 0) + silver
        record.silver = silver
        msgs.append(f"銀兩 +{silver}")
        if merit:
            record.notes.append(rules.MERIT_LINE.format(silver=merit))
    xinde = round(squad.reward_xinde * cfg.reward_scale * (1 + treasures.amount(s, c, "win_xinde_pct")))
    if xinde:
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        record.xinde = xinde
        msgs.append(f"心得 +{xinde}")
    factor = ranger.exp_factor(s, c)
    exp = round(squad.exp * cfg.reward_scale * (1 + treasures.amount(s, c, "win_exp_pct")) * factor)
    msgs += ctx._record_exp(record, exp, "sortie")
    levels, record.levelups = team.grant_team_exp(s, c, ctx.world, exp, "sortie")
    record.notes += levels
    return msgs + levels


def sortie_rare(ctx: Game, record) -> list[str]:
    """出陣攻打贏的稀有掉落（2.6）：破境丹 rare_legend（自己的亂數）；寶物與良駒照 treasures.sortie_rare（各自一季的上限）。
    都寫進戰報的得失與江湖紀錄。"""
    s, c = ctx.state, ctx.content
    cfg, season = c.config.sortie, ctx.world.get_season_number()
    msgs: list[str] = []
    if random.Random(f"出陣稀有|{season}|{s.player.name}|{record.id}|破境丹").random() < cfg.rare_legend:
        s.player.legend_items += 1
        name = c.config.legend_item_name
        record.materials.append(f"{name} ×1")
        msgs += [f"獲得 【{name}】一枚——{c.config.legend_item_note}", f"{name} +1"]
    gear, gains, paid = treasures.sortie_rare(s, c, season, record.id)
    record.silver = (record.silver or 0) + paid  # 掉落池都有了換的銀兩也算進得失（FB-434）
    record.notes += gear
    record.materials += gains  # 得失那一格照挑戰本人寫「寶物【X】」「良駒【X】」（FB-430）
    return msgs + gear


def sortie_drill(ctx: Game, squad: Squad, record) -> list[str]:
    """一類一顆之前的出陣攻打贏（設計 2.4）：對手心得、經驗的 drill_reward_share（三成，同操練）。銀兩：素材與經濟設計第八節
    （Config.economy.sortie_silver）開著時加給對手銀兩的 sortie_silver_share（三成，四捨五入），關著不給。"""
    p, share = ctx.state.player, ctx.content.config.drill_reward_share
    msgs: list[str] = []
    econ = ctx.content.config.economy
    # 四捨五入照專案的寫法 int(x + 0.5)（同 economy.upgrade_cost）：round 逢 .5 取偶數，黃巾別部 15 兩的三成 4.5 會給 4（FB-271）
    silver = int(squad.reward_silver * econ.sortie_silver_share + 0.5) if econ.sortie_silver else 0
    if silver > 0:
        p.stats["silver"] = p.stats.get("silver", 0) + silver
        record.silver = silver
        msgs.append(f"銀兩 +{silver}")
    xinde = drill_share(squad.reward_xinde, share)
    if xinde:
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        record.xinde = xinde
        msgs.append(f"心得 +{xinde}")
    exp = drill_share(squad.exp, share)
    msgs += ctx._record_exp(record, exp, "sortie")
    levels, record.levelups = team.grant_team_exp(ctx.state, ctx.content, ctx.world, exp, "sortie")
    record.notes += levels
    return msgs + levels


def sortie_host(ctx: Game, loc: Location) -> Squad | None:
    """守拿誰的數字（設計 2.4「守用這個地點自己陣營那一路的數字」）：這裡自家陣營的隊伍，取經驗最高的一路、同分取先列的；
    沒有是 None（不給心得經驗，進度照拉）。"""
    s, c = ctx.state, ctx.content
    side = ctx._side()
    squads = [
        c.squads[sid] for sid in territory.squads_at(s.world, c, loc.id)
        if c.squads[sid].faction is not None and (side is None or c.squads[sid].faction == side)
    ]
    return max(squads, key=lambda q: q.exp) if squads else None


def sortie_hold(ctx: Game, loc: Location, how: str) -> list[str]:
    """守（設計 2.2）：不打、不會輸、不扣氣血、不磨兵器。給自己的照操練（_drill_gains，_sortie_host 那一路）；把這一塊的進度
    推回自己那一邊（_push_progress，量是攻的 hold_share；設計 3.7、4.4）；算一次守城（軍令文件 3.2，同巡哨、傳道）。"""
    s, c = ctx.state, ctx.content
    line = rules.HOLD_LINE.format(place=loc.name)
    msgs = [line]
    ctx._outcome(rules.MODE_NAMES[how], line)
    host = sortie_host(ctx, loc)
    if host is not None:
        msgs += ctx._drill_gains(host, hold_share(ctx))
    # 守城照拉之前的清單記（FB-608：拉到零的那一下，拉完那一塊沒有條，不在守的清單上）；那一句照舊排在最後
    credit = ctx._order_credit(kind="duty", location=loc.id, front=conquest.line_of(s.world, c, loc.id))
    msgs += ctx._push_progress(loc.id, conquest.sortie_nominal(c, loc.id, how), "sortie", how)
    return msgs + credit


def hold_share(ctx: Game) -> float | None:
    """守、守勢行動拿 _sortie_host 那一路的幾成：一類一顆開著是全額（正式季整合 2.6），關著照操練的三成（None）。"""
    return 1.0 if precise.on(ctx.content, ctx.state.world) else None
