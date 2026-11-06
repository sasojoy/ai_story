"""全服決戰「打」那一半之二：集結、加入、晚到、臨時投效、改投、挑同伴（隨你出陣）、在不在場、假人趕路、出招的分派（全部拆包第 7 批；計畫
docs/superpowers/plans/2026-11-01-決戰包-第3批.md）。原本 Game 上的 29 個方法，本體照抄、self 換成 ctx（第一階 ctx 就是 Game，開發規範手冊 3.3）；
名字去掉前導底線。Game 留 13 個一行委派（核心原位與別的功能在叫、測試直接叫或換掉的），其餘 16 個只有這裡叫。

- 選單與分派：battle_menu（同一個大區兩場以上時每一場一組，鈕 id 帶 @流水號）、battle_options、battle_choose（照 @流水號定看的那一場）、
  battle_choose_in（加入、晚到、臨時投效、挑同伴、出招）、join_refusal、submit_battle_action
- 臨時投效：free_agent、own_side_name、enlist_options、enlist_sides、enlist；選邊之後集結名單跟著換邊：ally_follows_battle（FB-273）
- 挑同伴（歷史武將同行第五、六節）：escort_choices、escort_of、escort_carry、escort_options、escort_step、escort_home、settle_partings
- 在不在場：at_battle、in_battle_region、battle_region_name、absent_reason、sync_battle_presence；我在哪幾場打得進去：joinable、in_region
- 假人趕路：rally_region、rally_any（bot_policy、bot_runner 照舊叫 Game.rally_region）

留在 Game 的經 ctx：「打」那一半被測試換掉的 _battle_status、_apply_battle_outcome（第 8 批的本體在 progress.py，照舊經 Game：換掉的才打得到）、
戰力快照（核心的單打服務：_battle_scores〔測試換掉〕、_battle_power〔測試換掉〕、_battle_gear、_battle_marks、_battle_role、_battle_road、
_battle_neili_cap）、玉璽的 _mandate_weight（總表裁定歸玉璽）、_side、_conquest_side、_write，與 Game 上的暫時旗標 _battle_ref、_escort_picked、
_escort_now（寄放）。這一包自己的（view.round_wait、sieges.sieges、sieges.definition_of、escorts、第 8 批的 progress〔battle_for_me、battle_now、
watching_battle、battles_now、mutate_battle_of、mutate_battle_now、advance_battle_round、backfill_battle_scores：第 7 批時還在 Game、經 ctx 叫〕、
這一檔互相叫）直接叫函式：測試只是直接叫 Game 上的委派、沒有換掉它們（手冊第十五節 PM 11/01）。
"""
from __future__ import annotations

import math

from tianxia import allied, atlas, battle_instance, roster, siege  # 共用規則層（豪強依附、輿圖的大區與路線 atlas〔第 50 批收進〕、戰鬥規則核心、同伴、攻城）
from tianxia import attrset, journal, team
from tianxia.core.option import Option
from tianxia.models import BattleDef
from tianxia.state import JournalEntry

from . import escorts, progress, rules, sieges, view  # progress：推進與結算（第 8 批；它也 import 這一檔，都在函式裡用）


def ally_follows_battle(ctx) -> list[str]:
    """選邊的那一刻（豪強分屬兩軍），人已經在這一場決戰的參戰名單上、站的是另一邊（先臨時投效了，FB-273）：集結時照新選的
    那一邊換過去（同改選：份量照這一刻重新快照），開打了照決戰的規則不能改投（同 _enlist），這一場照舊站原來那一邊；兩種都說一句。
    沒有決戰、不在名單上、本來就站這一邊，什麼都不做。"""
    status = progress.battle_for_me(ctx, tick=False)
    if status is None:
        return []
    battle, definition = status
    name, side, camps = ctx.state.player.name, ctx._side(), sides(ctx, definition)
    me = battle.participants.get(name)
    if me is None or me.faction == side or side not in camps:
        return []
    if battle.phase != "muster":
        return [allied.ALLY_STAYS.format(battle=definition.name, ally=camps[side], old=camps.get(me.faction, me.faction))]
    scores = ctx._mandate_weight(definition, ctx._battle_scores())
    gear, marks = ctx._battle_gear(), ctx._battle_marks()
    progress.mutate_battle_of(
        ctx, battle,
        lambda b: battle_instance.join_faction(
            b, name, side, ctx._battle_neili_cap(), ctx._battle_power(), scores=scores, attribute=ctx._battle_road(),
            role=ctx._battle_role(), **gear, **marks,
        ),
    )
    return [allied.ALLY_REJOINED.format(battle=definition.name, ally=camps[side])]


def escort_choices(ctx) -> list[str]:
    """加入決戰時挑得到的同伴：名下的（歷史武將同行第五節）。開關關著是空的（照舊一下就加入）。"""
    if not roster.on(ctx.content, ctx.state.world):
        return []
    return [cid for cid in roster.owned_companions(ctx.world, ctx.state.player.name) if cid in ctx.content.characters]


def escort_of(ctx, cid: str) -> battle_instance.Escort:
    """派他上陣的那一刻快照（第五節【預設】）：份量＝strength(他的威力) × escort_share（不吃你的職位、坐騎、部下），
    池子是他的氣血上限，戰法是他自己身上的兩門。"""
    s, c, w = ctx.state, ctx.content, ctx.world
    pool = team.mate_pool(s, c, w, cid)
    score = battle_instance.strength(c.config.battle, team.mate_power(s, c, w, cid)) * c.config.battle.generals.escort_share
    return battle_instance.Escort(
        cid=cid, name=c.characters[cid].name, score=round(score, 1), neili=pool, neili_cap=pool, kit=team.mate_side(s, c, w, cid),
    )


def escort_carry(ctx) -> battle_instance.Escort | None:
    """這一次加入要帶的同伴：剛在挑的那一位（_escort_step）；不然是已經在參戰名單上的那一位（集結時改選、依附那一軍重新快照，照舊跟著）。"""
    if ctx._escort_picked:
        return ctx._escort_now
    battle = progress.battle_now(ctx)
    me = battle.participants.get(ctx.state.player.name) if battle is not None else None
    return me.escort if me is not None else None


def escort_options(ctx) -> list[Option]:
    """按了加入、還在挑誰隨你上陣：名下每一位一顆（寫份量與氣血），加上「不派」「再想想」。"""
    out = []
    for cid in escort_choices(ctx):
        e = escort_of(ctx, cid)
        out.append(Option(id=f"battle:escort:{cid}", label=rules.ESCORT_OPTION.format(name=e.name, score=round(e.score), pool=round(e.neili_cap))))
    return out + [Option(id="battle:escort:none", label=rules.ESCORT_NONE), Option(id="battle:escort:back", label=rules.ESCORT_BACK)]


def escort_step(ctx, battle: battle_instance.BattleInstance, arg: str) -> list[str]:
    """挑好了（battle:escort:<id>／none）或「再想想」（back）：照記下的那一下（PlayerState.escort_pick）加入，帶著挑的那一位。
    集結時按的、挑的時候已經開打了，改成晚到（join_late）。"""
    p = ctx.state.player
    pick, p.escort_pick = p.escort_pick, ""
    if not pick:
        return ["（此刻無法這麼做。）"]
    if arg == "back":
        return [rules.ESCORT_BACK_LINE]
    if arg != "none" and arg not in escort_choices(ctx):
        return ["（此刻無法這麼做。）"]
    pick, at, ref = pick.partition("@")  # 同一個大區兩場以上時記著是哪一場（領地爭奪第二批）
    kind, _, rest = pick.partition(":")
    if kind == "join" and battle.phase != "muster":
        kind, rest = "join_late", ""
    ctx._escort_picked, ctx._escort_now = True, (escort_of(ctx, arg) if arg != "none" else None)
    try:
        return battle_choose(ctx, f"{kind}:{rest}{at}{ref}")
    finally:
        ctx._escort_picked, ctx._escort_now = False, None


def escort_home(ctx, e: battle_instance.Escort) -> list[str]:
    """補這一場戰報時（_file_showdown）：他回江湖了——拿出出戰隊伍、寫一句，情誼照 _settle_partings 減半（同一則紀錄裡說）。"""
    team.remove_from_team(ctx.state, e.cid)
    line = (escorts.FELL_RETURN_LINE if e.fallen_round is not None else escorts.RETURN_LINE).format(name=e.name)
    return [line] + settle_partings(ctx, write=False)


def settle_partings(ctx, write: bool = True) -> list[str]:
    """歷史武將同行 9.6：決戰收場時從你身邊回江湖的人（CompanionProgress.parted_from 有你的名號），情誼乘 parted_keep（無條件捨去）。
    同步、按招募之前與補戰報時叫；write 時另起一則「同伴回江湖」紀錄（補戰報時併進那一則，不另寫）。開關關著什麼都不做。
    全服的記號不在減半那一下清（FB-361）：減了記進 PlayerState.parted_done，記號留到之後再叫到這裡、看到這一份角色已經減過才清
    （同一次同步裡補戰報先減、後面那一次清；收場在輪詢組畫面時發生、角色沒存的話，下一次同步照存檔裡沒減過的那一份再減一次）。"""
    c, p = ctx.content, ctx.state.player
    if not roster.on(c):
        return []
    keep = c.config.companions.parted_keep
    lines = []
    marked = set()
    for cid, progress in ctx.world.companions().items():
        if cid not in c.characters or not any(roster.owns(n, p.name) for n in progress.parted_from):
            continue
        marked.add(cid)
        if cid in p.parted_done:  # 這一份角色已經減過：清記號
            ctx.world.update_companion(
                cid, lambda pr: setattr(pr, "parted_from", [n for n in pr.parted_from if not roster.owns(n, p.name)]),
            )
            p.parted_done.remove(cid)
            continue
        p.parted_done.append(cid)
        before = p.affinities.get(cid, 0)
        after = math.floor(before * keep)
        p.affinities[cid] = after
        if after != before:
            lines.append(escorts.PARTED_LINE.format(name=c.characters[cid].name, before=before, after=after))
    p.parted_done = [cid for cid in p.parted_done if cid in marked]  # 記號已經不在的（換季清掉了）不留
    if write and lines:
        journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=escorts.PARTED_TITLE, tag="", lines=lines))
    return lines


def in_region(ctx, battles: list[battle_instance.BattleInstance]) -> list[battle_instance.BattleInstance]:
    """這幾場裡，人此刻所在（在路上看最後一站）的大區就是它的大區的；不限地點的那一場也算。"""
    loc = ctx.state.player.location
    found = atlas.region_of(ctx.content, loc) if loc in ctx.content.locations else None
    out = []
    for b in battles:
        d = sieges.definition_of(ctx, b)
        if d is not None and (d.region is None or (found is not None and found.id == d.region)):
            out.append(b)
    return out


def joinable(ctx) -> list[battle_instance.BattleInstance]:
    """自己大區裡集結中或開打、加得進去的那幾場（決戰在前）：自己已經在某一場的名單上、或沒有攻城戰時是空的。"""
    live_sieges = sieges.sieges(ctx)
    if not live_sieges:
        return []
    showdown = ctx.world.get_battle()
    live = ([showdown] if showdown is not None and showdown.phase != "ended" else []) + live_sieges
    name = ctx.state.player.name
    if any(name in b.participants for b in live):
        return []
    out = []
    for b in live:
        d = sieges.definition_of(ctx, b)
        if d is not None and at_battle(ctx, d) and not progress.watching_battle(ctx, b, d):
            out.append(b)
    return out


def sides(ctx, definition: BattleDef) -> dict[str, str]:
    """這場決戰能站的每一方（id → 名字）：交戰的兩軍。"""
    return {f.id: f.name for f in definition.factions}


def free_agent(ctx, definition: BattleDef) -> bool:
    """劇本分陣營、自己不是交戰兩軍的人（散人、地方豪強）：決戰時可以臨時投效交戰的兩軍之一，只算這一場
    （散人：試玩回饋 2026-10-08；豪強：Joy 2026-10-13「豪強在大決戰還是要加入某一陣營，主軸還是官兵跟黃巾」）——
    不寫進投靠名冊、不改自己的陣營、不算叛投、不記貢獻。
    豪強分屬兩軍的季（企劃者 2026-10-15），豪強是依附那一軍的人（_side），跟兩軍的人一樣加入，不是臨時投效；
    拜入曹氏莊院還沒挑一邊（allied.needs_ally）也不給臨時投效，先挑一邊（FB-273）。"""
    if allied.needs_ally(ctx.state, ctx.content):
        return False
    return bool(ctx.content.scenario.factions) and ctx._side() not in sides(ctx, definition)


def own_side_name(ctx) -> str:
    """臨時投效的人打完照樣是誰：散人，或自己陣營的名字（豪強）。"""
    faction = ctx.state.player.faction
    return "散人" if faction is None else f"{ctx.content.scenario.faction_name(faction, faction)}的人"


def enlist_options(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[Option]:
    """散人的臨時投效按鈕（兩軍各一顆）：集結時已經投效的那一邊是灰的「已投效」、還能改投另一邊；開打了還沒參戰的照樣能投效。
    單方攻中立地時守將那一格（battle_instance.neutral_guard）寫「助守【守軍】」，不寫那一格的陣營（FB-540；鈕 id 照舊是那一格的 id）。"""
    me = battle.participants.get(ctx.state.player.name)
    guard, names = battle_instance.neutral_guard(battle), battle_instance.side_names(battle, definition)
    out = []
    for fid in battle_instance.fields(battle, definition):  # 三方混戰（裁決 22）多一顆助守【守軍】（GUARD）
        done = me is not None and me.faction == fid
        if fid == guard:
            label = (siege.HELPED_GUARD if done else siege.HELP_GUARD).format(side=names[fid])
        else:
            label = f"已臨時投效【{names[fid]}】" if done else f"臨時投效【{names[fid]}】（只算這一場）"
        out.append(Option(id=f"battle:enlist:{fid}", label=label, enabled=not done))
    return out


def enlist_sides(ctx, battle: battle_instance.BattleInstance | None, definition: BattleDef) -> dict[str, str]:
    """臨時投效站得了的格（id → 名字）：交戰的兩軍，三方混戰再加助守【守軍】（GUARD，裁決 22）。"""
    camps = sides(ctx, definition)
    if battle is not None and battle_instance.melee(battle):
        camps[battle_instance.GUARD] = battle_instance.GUARD_SIDE
    return camps


def at_battle(ctx, definition: BattleDef) -> bool:
    """人在這場決戰的大區、而且不在路上，才算到了戰場（地圖擴充設計第六節）；決戰不限地點時只看在不在路上。
    這是「加入」的條件，也是還沒參戰的人算不算在場；已經參戰的人看 _in_battle_region。"""
    if ctx.state.player.journey is not None:
        return False
    if definition.region is None:
        return True
    region = atlas.region_of(ctx.content, ctx.state.player.location)
    return region is not None and region.id == definition.region


def in_battle_region(ctx, definition: BattleDef) -> bool:
    """參戰者還算不算在戰場（地圖擴充設計第六節：只有「離開大區」才讓人這回合不出手）：決戰不限地點時
    一律算在場；有大區時，所在地和這一趟還沒走到的站都在那個大區才算——在區內站與站之間走動仍在場上，
    要走出區外的路一出發就算離開。"""
    if definition.region is None:
        return True
    j = ctx.state.player.journey
    stops = [ctx.state.player.location] + ([] if j is None else j.path[j.reached:j.last + 1])
    return all(
        (region := atlas.region_of(ctx.content, stop)) is not None and region.id == definition.region for stop in stops
    )


def battle_region_name(ctx, definition: BattleDef) -> str:
    return next((r.name for r in ctx.content.map.regions if r.id == definition.region), "戰場")


def absent_reason(ctx, definition: BattleDef) -> str:
    """還沒到戰場、不能加入的原因（不含括號與句號）。"""
    if definition.region is None:
        return "你還在路上，到了才能加入戰局"
    return f"這場決戰在{battle_region_name(ctx, definition)}，人要到了那裡、不在路上才能加入"


def sync_battle_presence(ctx) -> None:
    """參戰者出發或抵達時，把「人還在不在決戰的大區」記到戰鬥上：離開大區的這回合不出手。"""
    status = ctx._battle_status(tick=False)
    if status is None:
        return
    battle, definition = status
    name = ctx.state.player.name
    me = battle.participants.get(name)
    if me is None:
        return
    away = not in_battle_region(ctx, definition)
    if me.away != away:
        progress.mutate_battle_of(ctx, battle, lambda b: battle_instance.set_away(b, name, away))


def rally_region(ctx) -> str | None:
    """自己這一方正在集結或開打的全服決戰、而自己人不在現場時，回傳那場決戰的大區 id，給伺服器假人決定要不要
    趕路（地圖擴充設計 3.4）。不在現場的意思：還沒參戰的人不在那個大區或在路上；參戰者離開了大區
    （見 _in_battle_region）。沒有這種決戰、決戰不限地點、打不了這場、已經在場上或倒下了，都是 None。
    有攻城戰時（領地爭奪第二批）每一場都看（決戰在前、再照開集結的先後）：攻城認自己那一邊的攻方、守方（守將那一格不算，裁決 8）。"""
    if sieges.sieges(ctx):
        return rally_any(ctx)
    status = ctx._battle_status(tick=False)
    if status is None:
        return None
    battle, definition = status
    if definition.region is None:
        return None
    me = battle.participants.get(ctx.state.player.name)
    if me is None and ctx.state.player.faction is None and free_agent(ctx, definition):
        # 散人沒有自己的一方：不會為了投效趕過去，投效了才算自己這一方。豪強照樣趕過去臨時投效（bot.enlist_pick）
        return None
    if me is not None:
        return definition.region if me.away and not me.eliminated else None
    return None if at_battle(ctx, definition) else definition.region


def rally_any(ctx) -> str | None:
    """rally_region 在有攻城戰時：自己已經在某一場的名單上就只看那一場（離開了大區、還沒倒下才回它的大區）；不然照先後找第一場
    自己這一方打得進去、自己人又不在現場的那一場的大區。散人不為了投效趕過去（同決戰）；攻城戰另照 siege.slots。"""
    name = ctx.state.player.name
    showdown = ctx.world.get_battle()
    live = ([showdown] if showdown is not None and showdown.phase != "ended" else []) + sieges.sieges(ctx)
    mine = next((b for b in live if name in b.participants), None)
    if mine is not None:
        d = sieges.definition_of(ctx, mine)
        me = mine.participants[name]
        return d.region if d is not None and d.region is not None and me.away and not me.eliminated else None
    for b in live:
        d = sieges.definition_of(ctx, b)
        if d is None or d.region is None:
            continue
        if ctx.state.player.faction is None and free_agent(ctx, d):
            continue  # 散人沒有自己的一方：不會為了投效趕過去
        if b.siege is not None and not siege.slots(b.siege, ctx._conquest_side()):
            continue
        if not at_battle(ctx, d):
            return d.region
    return None


def battle_menu(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[Option]:
    """戰鬥那一段選單：自己大區裡打得進去的只有一場（或已經在名單上、在挑同伴）照舊（_battle_options，鈕 id 一字不變）；
    兩場以上（攻城戰與決戰、或兩場攻城，領地爭奪第二批 Review Focus 4）每一場各一組加入鈕，id 帶「@流水號」、字前面寫是哪一場。"""
    found = joinable(ctx)
    if len(found) < 2 or ctx.state.player.escort_pick:
        return battle_options(ctx, battle, definition)
    out = []
    for b in found:
        d = sieges.definition_of(ctx, b)
        for o in battle_options(ctx, b, d):
            out.append(o.model_copy(update={"id": f"{o.id}@{b.record_id}", "label": f"{d.name}：{o.label}"}))
    return out


def battle_options(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[Option]:
    """打得了這場仗的人的戰鬥選項（只能觀戰的人不會走到這裡，見 _watching_battle）。"""
    name = ctx.state.player.name
    p = battle.participants.get(name)
    if p is None and allied.needs_ally(ctx.state, ctx.content):  # 拜入曹氏莊院還沒挑一邊（FB-273）：先挑一邊，不給加入也不給投效
        return []
    if p is None and ctx.state.player.escort_pick and escort_choices(ctx):  # 按了加入、在挑誰隨你上陣（歷史武將同行）
        return escort_options(ctx)
    if free_agent(ctx, definition):  # 散人、豪強：集結時、或開打了還沒參戰，給臨時投效的兩顆
        if battle.phase == "muster" or p is None:
            return enlist_options(ctx, battle, definition)
    if battle.phase == "muster":
        camps = list(sides(ctx, definition).items())  # 兩軍（id, 名字）
        if ctx.content.scenario.factions:  # 劇本分陣營：只能站在自己陣營那邊
            camps = [(fid, fname) for fid, fname in camps if fid == ctx._side()]  # 豪強分屬兩軍：依附那一軍
        return [  # 已經加入的那一邊換成灰的「已加入」；不分陣營的劇本集結時還能換到另一邊
            Option(id=f"battle:join:{fid}", label=f"已加入【{fname}】", enabled=False)
            if p is not None and p.faction == fid else Option(id=f"battle:join:{fid}", label=f"加入【{fname}】")
            for fid, fname in camps
        ]
    if p is None:
        return [Option(id="battle:join_late", label="加入戰局")]
    if p.eliminated:
        return [Option(id="battle:spectate", label="（觀戰中，無法行動）", enabled=False)]
    if name in battle.round.pending_actions:
        return [Option(id="battle:waiting", label=f"（已選擇，等其他人：{view.round_wait(ctx, battle, definition)}）", enabled=False)]
    out = []
    for o in battle_instance.options_for(battle, definition, name):
        if o.free_text:
            continue
        label = o.text
        ordered = o.move is not None and o.move == battle.orders.get(p.faction) and battle_instance.caller(battle, p.faction) is not None
        if p.faction == battle_instance.GUARD and o.move is not None:  # 三方混戰助守的人：份量不推戰線，不寫分數與將令（裁決 22）
            label = f"{o.text}（{o.move}）"
        elif o.move is not None and p.scores:  # 三招：寫招與這個人現在的份量（設計 3.4：按鈕上直接寫）
            score = p.scores.get(o.move, 0.0) * battle_instance.condition(p)
            if ordered:  # 照將令出招（龍頭上陣）：份量照算進去
                score *= 1 + ctx.content.config.battle.generals.order_bonus
            label = f"{o.text}（{o.move}・{round(score)} 分{battle_instance.ORDER_MARK if ordered else ''}）"
        elif o.move is not None:  # 還沒有份量快照（上線前就在場上、下一次同步才補）：不寫「0 分」，那是假的
            label = f"{o.text}（{o.move}）"
        out.append(Option(id=f"battle:act:{o.tag}", label=label))
    return out


def battle_choose(ctx, arg: str) -> list[str]:
    """choose() 分派進這裡之前，已經透過自己開頭那次 Game.options(odds=False) 呼叫
    推進過一次了（options() 內部會 tick），這裡用 tick=False 只讀，避免同一次請求裡
    重複推進兩次。序章裡一律擋下（_battle_for_me，FB-113）：選單上本來就沒有，直接送也不行。
    鈕 id 帶「@流水號」（同一個大區有兩場以上打得進去，領地爭奪第二批 Review Focus 4）：這一下照那一場；已經在別場的名單上不收。"""
    arg, at, ref = arg.partition("@")
    if not at:
        return battle_choose_in(ctx, arg)
    if not ref.isdigit():
        return ["（此刻無法這麼做。）"]
    name = ctx.state.player.name
    if any(name in b.participants and b.record_id != int(ref) for b in progress.battles_now(ctx) if b.phase != "ended"):
        return ["（你已經在另一場戰局裡。）"]
    ctx._battle_ref = int(ref)
    try:
        return battle_choose_in(ctx, arg)
    finally:
        ctx._battle_ref = None


def battle_choose_in(ctx, arg: str) -> list[str]:
    """_battle_choose 的本體（看的那一場已經照 @流水號 定好）。"""
    status = progress.battle_for_me(ctx, tick=False)
    if status is None:
        return ["（此刻無法這麼做。）"]
    battle, definition = status
    name = ctx.state.player.name
    kind, _, rest = arg.partition(":")
    # 已經報名的人在區內走動時改選陣營不是「加入」，不用再驗人在不在戰場（_at_battle 在路上一律是否）
    changing_sides = kind == "join" and name in battle.participants
    if kind == "enlist":
        changing_sides = name in battle.participants
    if kind in ("join", "join_late", "enlist") and not changing_sides and not at_battle(ctx, definition):
        return [f"（{absent_reason(ctx, definition)}。）"]
    if kind == "escort":
        return escort_step(ctx, battle, rest)
    guarding = kind == "enlist" and rest.partition("@")[0] == battle_instance.GUARD  # 三方混戰助守：同伴只在兩軍那兩格上陣（裁決 22）
    if (kind in ("join", "join_late", "enlist") and not changing_sides and not ctx._escort_picked and not guarding
            and escort_choices(ctx)):
        # 名下有同伴：先挑誰隨你上陣（或不派），挑了才加入（歷史武將同行 9.3：沒有預設值）
        refusal = join_refusal(ctx, kind, rest, definition, battle)
        if refusal is not None:
            return refusal
        ctx.state.player.escort_pick = f"{kind}:{rest}" + (f"@{ctx._battle_ref}" if ctx._battle_ref is not None else "")
        return [rules.ESCORT_PICK]
    if kind == "enlist":
        return enlist(ctx, battle, definition, rest, changing_sides)
    if kind == "join":
        if ctx.content.scenario.factions and rest != ctx._side():
            return ["（你只能站在自己陣營這一邊。）"]
        if battle.siege is not None and (problem := siege.join_problem(ctx.content, battle.siege, ctx._conquest_side(), rest)):
            return [problem]
        scores = ctx._mandate_weight(definition, ctx._battle_scores())  # 在 mutate_battle 之前算好：快照的是加入這一刻、這個玩家自己的份量
        gear, marks = ctx._battle_gear(), ctx._battle_marks()
        progress.mutate_battle_of(
            ctx, battle,
            lambda b: battle_instance.join_faction(
                b, name, rest, ctx._battle_neili_cap(), ctx._battle_power(), scores=scores, attribute=ctx._battle_road(),
                role=ctx._battle_role(), **gear, **marks,
            ),
        )
        msgs = ["你加入了這場戰局。"]
        side = sides(ctx, definition).get(rest, rest)
        ctx._write(f"{definition.name}・{'改選' if changing_sides else '加入'}{side}", msgs)  # 加入與改選各留一則（FB-030）
        return msgs
    if kind == "join_late":
        own = ctx._side() if ctx.content.scenario.factions else None
        if battle.siege is not None and (problem := siege.join_problem(ctx.content, battle.siege, ctx._conquest_side(), own or "")):
            return [problem]
        scores = ctx._mandate_weight(definition, ctx._battle_scores())
        gear, marks = ctx._battle_gear(), ctx._battle_marks()
        progress.mutate_battle_of(
            ctx, battle,
            lambda b: battle_instance.auto_assign_latecomer(
                b, definition, name, ctx._battle_neili_cap(), ctx.rng, ctx._battle_power(), faction=own,
                scores=scores, attribute=ctx._battle_road(), role=ctx._battle_role(), **gear, **marks,
            ),
        )
        msgs = ["你趕到了戰場，這一回合就能出手。"]  # 晚到的人當回合就能出招（FB-028）
        ctx._write(f"{definition.name}・趕到戰場", msgs)  # 趕到也留一則（FB-030）；每回合的出招不寫，太吵
        return msgs
    if kind == "act":
        progress.backfill_battle_scores(ctx)  # 還沒有份量快照的自己，出招之前先補（結算要讀）
        return submit_battle_action(ctx, name, definition, rest)
    return ["（此刻無法這麼做。）"]


def join_refusal(
    ctx, kind: str, rest: str, definition: BattleDef, battle: battle_instance.BattleInstance | None = None,
) -> list[str] | None:
    """加入、臨時投效這一下本身就不成的那一句（同 _battle_choose、_enlist 的擋法）：挑同伴之前先擋，免得挑完了才說不行。
    攻城戰（領地爭奪第二批）另照 siege.join_problem（另一軍站不進守將那一格）。"""
    if kind == "join" and ctx.content.scenario.factions and rest != ctx._side():
        return ["（你只能站在自己陣營這一邊。）"]
    if kind == "enlist" and (not free_agent(ctx, definition) or rest not in enlist_sides(ctx, battle, definition)):
        return ["（此刻無法這麼做。）"]
    if battle is not None and battle.siege is not None:
        slot = rest if kind != "join_late" else (ctx._side() or "")
        problem = siege.join_problem(ctx.content, battle.siege, ctx._conquest_side(), slot)
        if problem is not None:
            return [problem]
    return None


def enlist(
    ctx, battle: battle_instance.BattleInstance, definition: BattleDef, side: str, changing_sides: bool,
) -> list[str]:
    """散人、豪強臨時投效交戰的一方（_free_agent）：集結時跟加入一樣（還能改投另一邊），開打了照晚到的人算、當回合就能出手。
    參戰名單上記投效的那一方，自己的陣營照舊（散人照舊是散人、豪強照舊是豪強）。"""
    name = ctx.state.player.name
    armies = enlist_sides(ctx, battle, definition)  # 三方混戰多一格助守【守軍】（裁決 22）
    if not free_agent(ctx, definition) or side not in armies:
        return ["（此刻無法這麼做。）"]
    if battle.siege is not None and (problem := siege.join_problem(ctx.content, battle.siege, ctx._conquest_side(), side)):
        return [problem]
    if changing_sides and battle.phase != "muster":
        return ["（開打之後就不能改投了。）"]
    scores, cap, power, road = ctx._mandate_weight(definition, ctx._battle_scores()), ctx._battle_neili_cap(), ctx._battle_power(), ctx._battle_road()
    role = ctx._battle_role()
    gear, marks = ctx._battle_gear(), ctx._battle_marks()
    if side == battle_instance.GUARD:  # 三方混戰助守：同伴只在兩軍那兩格上陣，這一場不帶（裁決 22）
        marks["escort"] = None
    if battle.phase == "muster":
        progress.mutate_battle_of(
            ctx, battle,
            lambda b: battle_instance.join_faction(
                b, name, side, cap, power, scores=scores, attribute=road, role=role, **gear, **marks,
            ),
        )
        msgs = [f"你臨時投效了{armies[side]}，只算這一場：打完你照樣是{own_side_name(ctx)}。"]
    else:
        progress.mutate_battle_of(
            ctx, battle,
            lambda b: battle_instance.auto_assign_latecomer(
                b, definition, name, cap, ctx.rng, power, faction=side, scores=scores, attribute=road, role=role,
                **gear, **marks,
            ),
        )
        msgs = [f"你臨時投效了{armies[side]}，趕到了戰場，這一回合就能出手；打完你照樣是{own_side_name(ctx)}。"]
    if side == battle_instance.neutral_guard(battle):  # 助守中立地的守將：不寫那一格的陣營（FB-540）
        place = ctx.content.locations[battle.siege.loc].name
        line = siege.HELP_GUARD_LINE if battle.phase == "muster" else siege.HELP_GUARD_LATE
        msgs = [line.format(place=place, own=own_side_name(ctx))]
        ctx._write(f"{definition.name}・{siege.HELP_GUARD_SWITCH if changing_sides else siege.HELP_GUARD_TITLE}", msgs)
        return msgs
    ctx._write(f"{definition.name}・{'改投' if changing_sides else '臨時投效'}{armies[side]}", msgs)
    return msgs


def submit_battle_action(
    ctx, name: str, definition: BattleDef, tag: str, text: str | None = None, success_rate: int | None = None,
    stories: tuple[str, str] | None = None, sex: str | None = None,
) -> list[str]:
    """送出一個行動（按鈕選的固定 tag，或自訂輸入框的 free_text 選項，連同 LLM 先評好
    的成功率）並嘗試結算這回合；呼叫端已經確認過戰鬥還在進行（還沒結束），所以這裡
    如果結算完變成 ended，一定是這次送出的行動剛好造成的，不用再跟「結算前是不是
    已經 ended」比對。"""
    captured: dict[str, list[str]] = {"msgs": []}
    if success_rate is not None and name == ctx.state.player.name:  # 魅力略為提高放手一搏（五項屬性的季；企劃者 2026-11-04）
        success_rate = int(success_rate) + round(attrset.charm(ctx.state, ctx.content, "gamble"))
    ult = ctx._battle_ult() if success_rate is not None and name == ctx.state.player.name else None  # 回合首功用（looks）

    def _apply(b: battle_instance.BattleInstance) -> None:
        battle_instance.submit_action(b, name, tag, text, success_rate, stories, sex=sex)
        if ult and name in b.round.success_rates:  # 這一搏真的送進去了，記下身上的絕招
            b.round.ults[name] = ult
        captured["msgs"] = progress.advance_battle_round(ctx, b, definition)

    battle = progress.mutate_battle_now(ctx, _apply)  # 有攻城戰時是自己參戰的那一場（領地爭奪第二批）
    if battle is not None and battle.phase == "ended":
        ctx._apply_battle_outcome(battle)
    return captured["msgs"] or ["你選擇了行動，等待其他人……"]
