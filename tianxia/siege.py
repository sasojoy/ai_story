"""領地爭奪第二批：攻城戰（設計 3.6、4.4；計畫第四章 Task 10～11；裁決 8、14）——決戰引擎的縮小版。

每個有區塊的大區一筆範本（content/battles.json 的 siege_<大區>，BattleDef.siege）：一幕 5 回合、偏離中線 40 提前收場，戰局照決戰以官軍為
正向。這一場打哪一塊、誰攻、開集結那一刻誰佔著記在 BattleInstance.siege（battle_instance.SiegeInfo）；攻城另存一串
（SharedWorldState.sieges），跟時刻表決戰、別的攻城戰同時打。名字一律「攻城・地點」（title）。

- 開集結（open_waiting）：時程表上到了開集結時候的那幾場（world.advance_world_state 記成 waiting）。那一刻重新看誰佔著（Review Focus 3：
  同一天先打的那一場、時刻表指定、管理者改了主人，後打的照打新的主人）；攻方自己已經是主人就作罷。起點照進度偏（start_trend）。
- 誰能站哪一格（join_problem）：攻方站自己那一格；打的是誰的區塊，那一方站守的那一格；單方攻中立地時另一格是守將（guard_side），
  另一軍站不進去、散人可以投效助守（裁決 8）；兩軍同時搶同一塊中立地沒有守將。
- 留守（commanders）：守方是陣營時照龍頭上陣的挑法派那一區守方的大勢人物，沒有人物或中立地時是那裡最強的一路隊伍當守將（guard_squad）。
- 收場（verdict）：攻方贏（大勝或險勝）就易手；否則原主人留著（中立還是中立）。攻方一個人都沒到（集結結束時）作罷。
只 import models、state、battle_instance、generals、territory、conquest、conquest_day（作罷）、world_state 型別。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import atlas, battle_instance, conquest, conquest_day, generals, territory
from .battle_instance import Commander, SiegeInfo
from .models import BattleDef, Content
from .state import GameState, Rumor, SiegeSlot, WorldState

if TYPE_CHECKING:
    from .world_state import WorldStateStore

TITLE = "攻城・{place}"  # 待 joy 潤：畫面、戰報、天下大事一律走 title
MUSTER_LINE = "{title}：{who}的集結號角吹響了，開打前趕到{region}就能加入。"  # 待 joy 潤：開集結那一刻的天下大事
VOID_HELD = "{who}原定攻{place}，那裡已經是{who}的了，這一仗作罷。"  # 待 joy 潤：開集結那一刻攻方已經是主人（Review Focus 3）
VOID_ABSENT_NOTE = "攻方一個人都沒到，這一仗作罷，不算勝負。"  # 參戰者（守方、助守的人）那一則江湖紀錄
HELD_LINE = "{title}：{side}守住了{place}。"  # 待 joy 潤：攻方沒打下來的天下大事（打下來的照 territory 的「落入」那一句）
STALEMATE_LINE = "{title}：兩軍相持不下，{place}照舊沒人佔。"  # 待 joy 潤：兩軍同時搶同一塊中立地、戰局停在中線
TAKEN_TITLE = "{side}{margin}，拿下{place}"  # 待 joy 潤：戰報與紀錄的結果
HELD_TITLE = "{side}守住{place}"
STALEMATE_TITLE = "相持，{place}照舊"
GUARD_NAME = "{squad}（守將）"  # 待 joy 潤：中立地的守將（那裡最強的一路隊伍）
LATE_MUSTER_SECONDS = 600  # 【開發】開集結晚了（伺服器停過）：集結至少留這麼久，免得一開就截止、攻方來不及加入就作罷
SCENE_LINE = "{attackers}攻{place}；守方：{defender}。"  # 待 joy 潤：攻城戰的場景第二行


def title(content: Content, info: SiegeInfo) -> str:
    """這一場的名字（「攻城・淯水河畔」）。"""
    loc = content.locations.get(info.loc)
    return TITLE.format(place=loc.name if loc is not None else info.loc)


def template(content: Content, loc_id: str) -> BattleDef | None:
    """這一塊所在的大區的攻城範本（siege_<大區>）；沒有是 None（content.check_conquest_blocks 擋了搶得下來的每一塊都要有）。"""
    region = atlas.region_of(content, loc_id) if loc_id in content.locations else None
    definition = content.battles.get(f"siege_{region.id}") if region is not None else None
    return definition if definition is not None and definition.siege else None


def _other(side: str) -> str:
    return next(s for s in conquest.SIDES if s != side)


def info(slot: SiegeSlot, world: WorldState, content: Content) -> SiegeInfo:
    """開集結那一刻的這一場：此刻誰佔著（holder）、攻方（已經是主人的那一方不算攻方）、守將站哪一格。"""
    holder = conquest.holder(world, content, slot.loc)
    attackers = [a for a in slot.attackers if a != holder]
    guard = _other(attackers[0]) if len(attackers) == 1 and holder is None else None
    return SiegeInfo(slot_id=slot.id, loc=slot.loc, attackers=attackers, holder=holder, guard_side=guard)


def defender(info: SiegeInfo) -> str | None:
    """守的那一格：陣營佔著的是那一方，中立地是守將那一格；兩軍同時搶中立地沒有。"""
    return info.holder if info.holder in conquest.SIDES else info.guard_side


def start_trend(world: WorldState, content: Content, info: SiegeInfo) -> int:
    """起點（設計 4.4）：50 − 進度往黃巾偏的點數（戰局以官軍為正向）。"""
    return battle_instance.CENTER - conquest.progress_shift(world, content, info.loc)


def guard_squad(world: WorldState, content: Content, loc_id: str, side_slot: str) -> Commander | None:
    """那裡最強的一路隊伍當守將（站 side_slot 那一格；fid 是「squad:隊伍 id」，收場時 generals.after_battle 自然略過）：
    份量＝strength(難度) × 龍頭上陣主將的倍數，池子照主將。那裡沒有隊伍是 None。"""
    squads = [sid for sid in territory.squads_at(world, content, loc_id) if sid in content.squads]
    if not squads:
        return None
    best = max(squads, key=lambda sid: (content.squads[sid].difficulty, sid))
    gen = content.config.battle.generals
    rank, pool = (gen.ranks[0] if gen.ranks else 1.0), (gen.pool[0] if gen.pool else 1000.0)
    score = round(battle_instance.strength(content.config.battle, content.squads[best].difficulty) * rank, 1)
    return Commander(fid=f"squad:{best}", name=GUARD_NAME.format(squad=content.squads[best].name), faction=side_slot,
                     rank=0, score=score, neili=pool, neili_cap=pool)


def commanders(state: GameState, content: Content, info: SiegeInfo, definition: BattleDef) -> list[Commander]:
    """這一場的留守（不是參戰者：不佔人數、不等他、不拿軍餉）：守方是陣營時照龍頭上陣的挑法取那一區守方的大勢人物（開關開著時）；
    沒有人物、或中立地時是那裡最強的一路隊伍當守將。兩軍同時搶中立地沒有守將。"""
    side = defender(info)
    if side is None:
        return []
    if info.holder in conquest.SIDES and generals.on(content):
        rows = [c for c in generals.pick(state, content, definition) if c.faction == side]
        if rows:
            return rows
    guard = guard_squad(state.world, content, info.loc, side)
    return [guard] if guard is not None else []


JOIN_SIDE = "（這一仗是{who}攻{place}，你這一邊插不上手。）"  # 待 joy 潤
JOIN_OWN = "（你只能站在自己陣營這一邊。）"
WATCH_LINE = "這一仗是{who}攻{place}，你這一邊插不上手，照常行動就好。"  # 待 joy 潤：另一軍站在攻中立地的那一區時，場景上那一句


def watch_line(content: Content, info: SiegeInfo) -> str:
    """另一軍的人站在這一區、這一仗沒有他站得進去的格時，場景上那一句（取代「人要到了那裡才能加入」）。"""
    who = "、".join(content.scenario.faction_name(a, a) for a in info.attackers)
    return WATCH_LINE.format(who=who, place=content.locations[info.loc].name)


def slots(info: SiegeInfo, side: str | None) -> list[str]:
    """side（照 allied.side_of：豪強依附的那一軍；散人與不是兩軍的人是 None）站得進去的格：攻方站自己那一格；打的是誰的區塊，
    那一方站守的那一格；散人與不是兩軍的人臨時投效攻方或守的那一格（助守中立地的守將，裁決 8）；另一軍站不進守將那一格。"""
    if side in conquest.SIDES:
        return [side] if side in info.attackers or side == info.holder else []
    return [*info.attackers, *([d] if (d := defender(info)) is not None and d not in info.attackers else [])]


def join_problem(content: Content, info: SiegeInfo, side: str | None, slot: str) -> str | None:
    """side 的人站 slot 那一格不成的那一句（成是 None）。"""
    if slot in slots(info, side):
        return None
    if side in conquest.SIDES and slots(info, side):
        return JOIN_OWN
    who = "、".join(content.scenario.faction_name(a, a) for a in info.attackers)
    return JOIN_SIDE.format(who=who, place=content.locations[info.loc].name)


def verdict(info: SiegeInfo, battle: battle_instance.BattleInstance, definition: BattleDef) -> tuple[str | None, str, str]:
    """收場：（易手給誰〔None＝原主人留著〕, 戰場上贏的那一方, 大勝／險勝）。照 battle_instance.result_at 判（戰局剛好 50 算守方守住；
    兩軍同時搶中立地停在 50 是相持，誰都沒拿下）。"""
    side = defender(info)
    if side is None and battle.trend == battle_instance.CENTER:
        return None, "", ""
    winner, margin = battle_instance.result_at(battle.trend, definition, None, side or definition.factions[0].id)
    return (winner if winner in info.attackers else None), winner, margin


def outcome_title(content: Content, info: SiegeInfo, taken: str | None, winner: str, margin: str) -> str:
    place = content.locations[info.loc].name
    if taken is not None:
        return TAKEN_TITLE.format(side=content.scenario.faction_name(taken, taken), margin=margin, place=place)
    side = defender(info)
    if side is None or not winner:
        return STALEMATE_TITLE.format(place=place)
    holder = info.holder or side
    return HELD_TITLE.format(side=content.scenario.faction_name(holder, holder) if info.holder else "守將", place=place)


def scene_line(content: Content, info: SiegeInfo, battle: battle_instance.BattleInstance) -> str:
    """攻城戰的場景第二行：誰攻、守方是誰（陣營、守將、或兩軍相爭）。"""
    who = "、".join(content.scenario.faction_name(a, a) for a in info.attackers)
    if info.holder in conquest.SIDES:
        side = content.scenario.faction_name(info.holder, info.holder)
    else:
        guard = next((c.name for c in battle.commanders if c.fid.startswith("squad:")), "")
        side = guard or ("兩軍相爭" if defender(info) is None else "守將")
    return SCENE_LINE.format(attackers=who, place=content.locations[info.loc].name, defender=side)


def _rumor(world: WorldState, text: str, loc: str | None = None) -> None:
    world.rumors.append(Rumor(time=world.time, text=text, location=loc, layer="world"))


def mark_due(world: WorldState, content: Content) -> None:
    """時間到了開集結的（muster_at ≤ 此刻）記成 waiting（world.advance_world_state 每一步叫；開集結要 store，由 start_pending_battle 開）。"""
    if world.conquest is None or not conquest.on(content, world):
        return
    for slot in world.conquest.schedule:
        if slot.status == "planned" and slot.muster_at <= world.time:
            slot.status = "waiting"


def open_waiting(world: WorldStateStore, content: Content, now: float) -> list[str]:
    """開時間到了的攻城（world.start_pending_battle 叫；呼叫端不在任何 mutate 裡）：每一場照此刻誰佔著重算（info），攻方已經是主人就作罷；
    其餘開一場集結（store.start_siege），起點照進度偏，集結截止＝開打的那一刻（開晚了至少留 LATE_MUSTER_SECONDS），派留守、一句天下大事。
    回寫進天下大事的那幾句。開關關著、季收了、沒有在等的什麼都不做。"""
    from .world import _season_vehicle  # noqa: PLC0415  world → siege：延後 import

    season = world.get_season()
    if season.ended or season.conquest is None or not conquest.on(content, season):
        return []
    waiting = [slot for slot in season.conquest.schedule if slot.status == "waiting"]
    if not waiting:
        return []
    msgs: list[str] = []
    opened: dict[str, int] = {}
    voided: dict[str, str] = {}
    scale = content.config.time_scale
    for slot in waiting:
        definition = template(content, slot.loc)
        here = info(slot, season, content)
        name = title(content, here)
        if definition is None or not here.attackers:
            who = "、".join(content.scenario.faction_name(a, a) for a in slot.attackers)
            voided[slot.id] = VOID_HELD.format(who=who, place=content.locations[slot.loc].name)
            continue
        battle = world.start_siege(definition, now, start_trend(season, content, here), here)
        floor = min(LATE_MUSTER_SECONDS, content.config.conquest.muster_minutes * 60)  # 開晚了（伺服器停過）至少留這麼久
        deadline = now + max((slot.at - season.time) / scale, floor)
        rows = commanders(_season_vehicle(content, season), content, here, definition.model_copy(update={"name": name}))

        def _snap(b: battle_instance.BattleInstance, deadline=deadline, rows=rows) -> None:
            b.muster_deadline_real = deadline
            b.commanders = [c.model_copy() for c in rows]

        world.mutate_siege(battle.record_id, _snap)
        opened[slot.id] = battle.record_id
        region = atlas.region_of(content, slot.loc)
        who = "、".join(content.scenario.faction_name(a, a) for a in here.attackers)
        msgs.append(MUSTER_LINE.format(title=name, who=who, region=region.name if region is not None else ""))

    def _apply(s: WorldState) -> None:
        for slot in s.conquest.schedule:
            if slot.id in opened:
                slot.status, slot.record_id = "open", opened[slot.id]
            elif slot.id in voided:
                conquest_day.void(s, content, slot, voided[slot.id])
        for line in msgs:
            _rumor(s, line)

    world.mutate_season(_apply)
    return [f"🛡️ 【全服戰報】{line}" for line in msgs] + list(voided.values())


def void_absent(content: Content, battle: battle_instance.BattleInstance) -> bool:
    """集結剛結束（_advance_battle_round 收集結那一下呼叫，在 mutate 裡）：攻方一個參戰者都沒有就作罷——標成收場、不算勝負
    （unfinished，參戰者照季終收兵補一則交代、不發軍餉），SiegeInfo.void 記原因。回作罷了沒。"""
    if battle.siege is None or battle.phase != "active":
        return False
    if any(p.faction in battle.siege.attackers for p in battle.participants.values()):
        return False
    battle.phase, battle.unfinished, battle.unfinished_text = "ended", True, VOID_ABSENT_NOTE
    battle.outcome_title = battle_instance.UNFINISHED_TITLE
    battle.siege.void = "absent"
    return True


def settle(world: WorldState, content: Content, battle: battle_instance.BattleInstance, definition: BattleDef) -> dict:
    """收場那一下改季（Game._settle_siege 在 mutate_season 裡叫）：易手（conquest.set_control 發「落入／收復」）或守住各一句
    天下大事、進度歸 50、時程表那一場記 done（winner）或 void；作罷不發天下大事，攻方沒人到的另記一筆 day_log（裁決 19）。
    回 {"taken", "winner", "margin", "title"} 給戰鬥那一列寫結果。"""
    info_ = battle.siege
    name = title(content, info_)
    place = content.locations[info_.loc].name
    slot = next((s for s in world.conquest.schedule if s.id == info_.slot_id), None) if world.conquest is not None else None
    if info_.void or battle.unfinished:
        # 作罷不發天下大事（攻方沒人到：人少的服每天空轉會洗版，PM 裁決 19）：時程表記 void（公告卡照常寫），沒人到的另記一筆 day_log
        if slot is not None:
            conquest_day.void(world, content, slot)
            if info_.void == "absent":
                conquest_day.note_void(world, slot, "absent")
        elif world.conquest is not None:
            world.conquest.progress.pop(info_.loc, None)
        return {"taken": None, "winner": "", "margin": "", "title": battle.outcome_title or battle_instance.UNFINISHED_TITLE}
    taken, winner, margin = verdict(info_, battle, definition)
    if taken is not None:
        conquest.set_control(world, content, info_.loc, taken)
    elif winner and defender(info_) is not None:
        holder = info_.holder
        side = content.scenario.faction_name(holder, holder) if holder else "守將"
        _rumor(world, HELD_LINE.format(title=name, side=side, place=place), info_.loc)
    else:
        _rumor(world, STALEMATE_LINE.format(title=name, place=place), info_.loc)
    if world.conquest is not None:
        world.conquest.progress.pop(info_.loc, None)
    if slot is not None:
        slot.status, slot.winner = "done", taken
    return {"taken": taken, "winner": winner, "margin": margin, "title": outcome_title(content, info_, taken, winner, margin)}
