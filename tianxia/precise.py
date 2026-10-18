"""一類一顆（docs/superpowers/specs/2026-10-17-正式季整合-design.md 第二章；正式季整合第 3 批）：每一顆行動鈕只給一類東西，
按了一定拿到那一類，運氣只決定拿到多少。找素材一定給、不打仗；練功（新）一定打一場；找事件寫這裡多半給哪一類；交友只談話；
靜心感悟選錯給心得、不鎖；應召不再換掉別的鈕。

開關 Config.precise_actions，照開季蓋章（WorldState.precise_actions）；探索三選一（Config.explore_modes）也開著時才生效——
找素材只存在於三選一裡（10.1）。關著時一個字都不變。這裡放不看引擎的純規則，engine.Game 接線。
"""
from __future__ import annotations

from . import explore_modes
from .models import Content
from .state import WorldState


def on(content: Content, world: WorldState | None) -> bool:
    """一類一顆開著沒：設定打開、這一季開季時也蓋了章、探索三選一開著。"""
    return (content.config.precise_actions and world is not None and world.precise_actions
            and explore_modes.on(content))
