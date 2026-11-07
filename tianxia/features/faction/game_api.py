"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import defect_actions, ending_actions, join_actions, lean_actions


TABLE = {
    # 本體在 tianxia/features/faction/lean_actions.py（全部拆包第 35 批：豪強改幫），這裡留一行委派
    "_join_lean": join_actions.join_lean,
    # 本體在 tianxia/features/faction/join_actions.py（全部拆包第 35 批：投靠的確認話），這裡留一行委派
    "_faction_prompt": join_actions.faction_prompt,
    # 叛投確認畫面的場景：本體在 defect_actions.scene（待確認那幾段的選單是 take/faction 那一格，core_seams）
    "_defect_scene": defect_actions.scene,
    # 本體在 tianxia/features/faction/ending_actions.py（全部拆包第 35 批），這裡留一行委派
    "_four_wins": ending_actions.four_wins,
    "ending_card": ending_actions.ending_card,
    "tier_hint": ending_actions.tier_hint,
    "sides_card": ending_actions.sides_card,
}
