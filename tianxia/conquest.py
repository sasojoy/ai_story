"""領地爭奪（第 38 項改版；設計 docs/superpowers/specs/2026-10-20-領地爭奪-design.md，計畫 docs/superpowers/plans/2026-10-20-領地爭奪.md）。

第一季的地圖分成三種區塊（Scenario.territory.blocks，一塊＝一個地點）：中立（高階獎勵，兩軍爭奪）、官軍與黃巾各自的陣營領地。
- 開季蓋章（WorldState.conquest_on，world_state.stamp_season）；判斷開沒開一律走 on(content, world)，不要只看設定。
- 開著時控制方只照佔領（攻城戰的結果、時刻表指定、管理者改），不拔河、不割據；此刻的控制方照舊記在 TerritoryState.control
  （所以讀控制方的地方都不用改），開季中立而沒人佔的區塊不在裡面（controller 回 None）。
- 三條戰線的值＝佔領的基準＋其他來源累積的偏移，夾在 0～100（設計 4.7）；值照舊存在 world.trends[戰線]，讀線的地方都不用改。
  別處直接改了線（rules.change_trend、決戰收場、管理者），下一次 reweigh 照上一次的基準重錨偏移（推進牆的部分丟掉，同以前）。
- 出陣不推線、推攻城目標的進度（ConquestState.progress，第一批任何可奪的區塊都記）。
只讀寫 WorldState；天下大事與江湖史照 territory._announce。territory 反過來在函式裡延後 import 這裡。"""
from __future__ import annotations

import math

from . import rules, territory
from .models import BlockDef, Content
from .state import ConquestState, GameState, TerritoryState, WorldState

SIDES = ("guan", "huang")  # 交戰兩軍（設計 4.1：豪強不佔地）；戰線往 100 是黃巾、往 0 是官軍（劇本的 goals）
NEUTRAL = "neutral"


def eligible(content: Content) -> bool:
    """這份內容與設定開得了領地爭奪（不看季）：劇本有官軍與黃巾、寫了區塊；劇本有要依附的陣營（豪強）時豪強分屬兩軍也開著（設計 4.1、4.10）。"""
    scen = content.scenario
    ids = {f.id for f in scen.factions}
    if not set(SIDES) <= ids or scen.territory is None or not scen.territory.blocks:
        return False
    if any(f.allies for f in scen.factions) and not content.config.haoqiang_allied:
        return False
    return True


def on(content: Content, world: WorldState | None) -> bool:
    """這一季照領地爭奪的規則：主機的開關開著、這一季開季時蓋了章、地盤本身開著（territory.on）。world 是 None 一律是假。"""
    return bool(world is not None and content.config.conquest.enabled and world.conquest_on and territory.on(content))


def blocks(content: Content) -> dict[str, BlockDef]:
    """地點 → 區塊（Scenario.territory.blocks）；劇本沒寫是空的。"""
    t = content.scenario.territory
    return dict(t.blocks) if t is not None else {}


def start_kind(world: WorldState | None, content: Content, loc_id: str) -> str | None:
    """這個區塊開季那一刻的種類（neutral／guan／huang）：這一季算過就讀抄下來的（之後內容改了不跟著動），沒算過照內容；不是區塊是 None。"""
    if world is not None and world.conquest is not None and loc_id in world.conquest.start:
        return world.conquest.start[loc_id]
    block = blocks(content).get(loc_id)
    return block.kind if block is not None else None


def line_of(world: WorldState | None, content: Content, loc_id: str) -> str | None:
    """這個區塊算進哪一條戰線（BlockDef.line）；不是區塊、或不算進任何一條是 None。"""
    block = blocks(content).get(loc_id)
    return block.line if block is not None else None


def capturable(content: Content, loc_id: str) -> bool:
    """搶得下來的區塊：是區塊、不是大本營（投靠點，設計 3.2）、不是 fixed（廣宗只照廣宗決戰易手）。"""
    t = content.scenario.territory
    return loc_id in blocks(content) and loc_id not in territory.bases(content) and (t is None or loc_id not in t.fixed)


def adjacent(content: Content, loc_id: str) -> list[str]:
    """跟這一塊有路直通的區塊（設計 3.2「輿圖上有路直通」）：照 Location.connections（兩個方向都算），不穿過不是區塊的地點；照內容順序。"""
    table = blocks(content)
    loc = content.locations.get(loc_id)
    if loc is None:
        return []
    near = {str(x) for x in loc.connections}
    near |= {other for other, place in content.locations.items() if loc_id in {str(x) for x in place.connections}}
    return [other for other in table if other in near and other != loc_id]


def holder(world: WorldState | None, content: Content, loc_id: str) -> str | None:
    """這一塊此刻歸誰（中立而沒人佔是 None）：這一季算過照 TerritoryState.control，還沒算過照開季的種類。"""
    t = world.territory if world is not None else None
    if world is not None and world.conquest is not None and t is not None:
        return t.control.get(loc_id)
    kind = start_kind(world, content, loc_id)
    return kind if kind in SIDES else None


def _opened(world: WorldState, content: Content, loc_id: str) -> bool:
    """劇情開放了（同 atlas.is_unlocked，但不看人站在哪裡）：不是序章專屬、unlock_flag 立了或第一季直接開放的地點。"""
    loc = content.locations[loc_id]
    if loc.prologue_only:
        return False
    if loc_id in rules.season_one_off(content, world, "unlocks"):
        return True
    return not loc.unlock_flag or loc.unlock_flag in world.flags


def targets(world: WorldState, content: Content, side: str) -> list[str]:
    """side 此刻能挑成目標的區塊（設計 3.2）：搶得下來、此刻不是 side 的、跟 side 此刻控制的某一塊直通、劇情開放了；照內容順序。"""
    mine = {loc for loc in blocks(content) if holder(world, content, loc) == side}
    return [
        loc for loc in blocks(content)
        if capturable(content, loc) and holder(world, content, loc) != side and _opened(world, content, loc)
        and any(x in mine for x in adjacent(content, loc))
    ]
