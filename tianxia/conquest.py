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
    t = content.scenario.territory
    return dict(t.blocks) if t is not None else {}
