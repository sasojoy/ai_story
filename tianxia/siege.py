"""領地爭奪第二批：攻城戰（設計 3.6、4.4；計畫第四章 Task 10～11；裁決 8、14）——決戰引擎的縮小版。共用規則層這一半：開集結與留守。

第二輪第 97 批切兩半：世界層代叫與別包要讀的（開集結、留守、這一場的名字、誰佔著、內容驗證）留這裡；只有決戰包讀的（誰站哪一格、開打那一下、
收場、場景字）在 tianxia/features/battle/siege_rules.py。共用層不 import 包，這一半一處都不讀它；它讀這裡的 defender、title、MELEE_MIN_HEADS 與
_guard_pool、_other、_rumor。

每個有區塊的大區一筆範本（content/battles.json 的 siege_<大區>，BattleDef.siege）：一幕 5 回合、偏離中線 40 提前收場，戰局照決戰以官軍為
正向。這一場打哪一塊、誰攻、開集結那一刻誰佔著記在 BattleInstance.siege（battle_instance.SiegeInfo）；攻城另存一串
（SharedWorldState.sieges），跟時刻表決戰、別的攻城戰同時打。名字一律「攻城・地點」（title）。

- 時程表上的那幾場是第 4 階的人下戰書排的（翻地與爭搶，輿圖簡化設計 4.4；conquest_day.place_letter），投票與 22:00 的結算拿掉了。
- 開集結（open_waiting）：時程表上到了開集結時候的那幾場（world.advance_world_state 記成 waiting）。那一刻重新看誰佔著（Review Focus 3：
  同一天先打的那一場、時刻表指定、管理者改了主人，後打的照打新的主人）；攻方自己已經是主人就作罷。起點照進度偏（start_trend）。
- 留守（commanders）：守方是陣營時照龍頭上陣的挑法派那一區守方的大勢人物，沒有人物或中立地時是那裡最強的一路隊伍當守將（guard_squad）。
只 import models、state、battle_instance、chiefs（龍頭上陣的挑法：全部拆包第 8 批 generals 進決戰包時留在共用規則層的那一塊）、territory、
conquest（作罷）、world_state 型別。

內容驗證 check_siege_templates 也在這個檔（core_content 第二輪第 96 批，content.validate 在函式內叫）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import atlas, chiefs, conquest, territory
from .core import battle_base as battle_instance
from .core.battle_base import GUARD, Commander, SiegeInfo
from .models import BattleDef, Content
from .state import GameState, Rumor, SiegeSlot, WorldState

if TYPE_CHECKING:
    from .world_state import WorldStateStore

TITLE = "攻城・{place}"  # 待 joy 潤：畫面、戰報、天下大事一律走 title
MUSTER_LINE = "{title}：{who}的集結號角吹響了，開打前趕到{region}就能加入。"  # 待 joy 潤：開集結那一刻的天下大事
VOID_HELD = "{who}原定攻{place}，那裡已經是{who}的了，這一仗作罷。"  # 待 joy 潤：開集結那一刻攻方已經是主人（Review Focus 3）
MELEE_MIN_HEADS = 2  # 【開發】三方混戰守將的池子至少照幾個人算（一軍只到一個人也不會一碰就倒）
GUARD_NAME = "{squad}" + battle_instance.GUARD_SUFFIX  # 待 joy 潤：中立地的守將（那裡最強的一路隊伍）
LATE_MUSTER_SECONDS = 600  # 【開發】開集結晚了（伺服器停過）：集結至少留這麼久，免得一開就截止、攻方來不及加入就作罷


def title(content: Content, info: SiegeInfo) -> str:
    """這一場的名字（「攻城・淯水河畔」）。"""
    loc = content.locations.get(info.loc)
    return TITLE.format(place=loc.name if loc is not None else info.loc)


def template(content: Content, loc_id: str) -> BattleDef | None:
    """這一塊所在的大區的攻城範本（siege_<大區>）；沒有是 None（conquest.check_conquest_blocks 擋了搶得下來的每一塊都要有）。"""
    region = atlas.region_of(content, loc_id) if loc_id in content.locations else None
    definition = content.battles.get(f"siege_{region.id}") if region is not None else None
    return definition if definition is not None and definition.siege else None


def _other(side: str) -> str:
    return next(s for s in conquest.SIDES if s != side)


def _squads(world: WorldState, content: Content, loc_id: str) -> list[str]:
    return [sid for sid in territory.squads_at(world, content, loc_id) if sid in content.squads]


def info(slot: SiegeSlot, world: WorldState, content: Content) -> SiegeInfo:
    """開集結那一刻的這一場：此刻誰佔著（holder）、攻方（已經是主人的那一方不算攻方）、守將站哪一格。
    兩軍同時攻同一塊中立地、那裡有隊伍當守將：三方混戰，守將站 GUARD（裁決 22）；那裡沒有隊伍（開季中立的每一塊都有）退回兩軍正面打。"""
    holder = conquest.holder(world, content, slot.loc)
    attackers = [a for a in slot.attackers if a != holder]
    if holder is None and len(attackers) == 1:
        guard = _other(attackers[0])
    elif holder is None and len(attackers) == 2 and _squads(world, content, slot.loc):
        guard = GUARD
    else:
        guard = None
    return SiegeInfo(slot_id=slot.id, loc=slot.loc, attackers=attackers, holder=holder, guard_side=guard)


def defender(info: SiegeInfo) -> str | None:
    """守的那一格：陣營佔著的是那一方，中立地是守將那一格（三方混戰是 GUARD）；兩軍同時搶沒有守將的中立地沒有。"""
    return info.holder if info.holder in conquest.SIDES else info.guard_side


def start_trend(world: WorldState, content: Content, info: SiegeInfo) -> int:
    """起點（設計 4.4）：50 − 進度往黃巾偏的點數（戰局以官軍為正向）；只有一個攻方時照他那一條進度偏（翻地與爭搶：戰書要到 60 才下得了）。"""
    return battle_instance.CENTER - conquest.progress_shift(world, content, info.loc, info.attackers)


def _guard_pool(content: Content) -> float:
    """單方攻中立地時守將的池子：同龍頭上陣的主將（Config.battle.generals.pool 第一個）。"""
    pool = content.config.battle.generals.pool
    return pool[0] if pool else 1000.0


def guard_squad(world: WorldState, content: Content, loc_id: str, side_slot: str) -> Commander | None:
    """那裡最強的一路隊伍當守將（站 side_slot 那一格；fid 是「squad:隊伍 id」，收場時 generals.after_battle 自然略過）：
    份量＝strength(難度) × 龍頭上陣主將的倍數，池子照主將（三方混戰站 GUARD 時先照 MELEE_MIN_HEADS 個人算，集結結束再照到場的人數定，
    size_melee_guard）。那裡沒有隊伍是 None。"""
    squads = _squads(world, content, loc_id)
    if not squads:
        return None
    best = max(squads, key=lambda sid: (content.squads[sid].difficulty, sid))
    gen = content.config.battle.generals
    rank, pool = (gen.ranks[0] if gen.ranks else 1.0), _guard_pool(content)
    if side_slot == GUARD:
        pool = content.config.conquest.melee_pool_per_head * MELEE_MIN_HEADS
    score = round(battle_instance.strength(content.config.battle, content.squads[best].difficulty) * rank, 1)
    return Commander(fid=f"squad:{best}", name=GUARD_NAME.format(squad=content.squads[best].name), faction=side_slot,
                     rank=0, score=score, neili=pool, neili_cap=pool)


def commanders(state: GameState, content: Content, info: SiegeInfo, definition: BattleDef) -> list[Commander]:
    """這一場的留守（不是參戰者：不佔人數、不等他、不拿軍餉）：守方是陣營時照龍頭上陣的挑法取那一區守方的大勢人物（開關開著時）；
    沒有人物、或中立地時是那裡最強的一路隊伍當守將（三方混戰站 GUARD，裁決 22）。兩軍同時搶沒有隊伍的中立地沒有守將。"""
    side = defender(info)
    if side is None:
        return []
    if info.holder in conquest.SIDES and chiefs.on(content):
        rows = [c for c in chiefs.pick(state, content, definition) if c.faction == side]
        if rows:
            return rows
    guard = guard_squad(state.world, content, info.loc, side)
    return [guard] if guard is not None else []



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
                conquest.void(s, content, slot, voided[slot.id])
        for line in msgs:
            _rumor(s, line)

    world.mutate_season(_apply)
    return [f"🛡️ 【全服戰報】{line}" for line in msgs] + list(voided.values())



# ── 內容驗證（第二輪第 96 批）──
def check_siege_templates(c: Content, need) -> None:
    """攻城範本（BattleDef.siege，領地爭奪第二批）：id 是 siege_<大區>、寫了大區、兩軍依序是官軍與黃巾（戰局以官軍為正向）、不是時刻表決戰。"""
    for battle in c.battles.values():
        if not battle.siege:
            continue
        where = f"攻城範本 {battle.id}"
        need(battle.region is not None and battle.id == f"siege_{battle.region}", f"{where}：id 要是 siege_<大區>、要寫 region")
        need([f.id for f in battle.factions] == ["guan", "huang"], f"{where}：陣營要依序是 guan、huang")
        need(battle.timetable_event is None and battle.version is None, f"{where}：攻城範本不是時刻表決戰")
