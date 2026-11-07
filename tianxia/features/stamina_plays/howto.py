"""體力玩法包：玩法說明設伏那一行（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia.core.howto_base import tenth as _tenth
from tianxia.models import Content

from . import ambush_rules as ambush


def ambush_lines(content: Content) -> list[str]:
    """設伏劫道（Config.ambush，Joy 2026-10-30 打開）：開著才寫一行；數字讀設定。待 joy 潤"""
    if not ambush.on(content):
        return []
    a = content.config.ambush
    return [
        f"- **設伏**（體力 {a.stamina}）：投靠了陣營、過了新手期，在兩頭都不是城鎮的路上守 {a.hours:g} 小時，敵對的人走過那一段"
        f"（步行、疾行都算，下線也照守）就打一場：贏的搶走輸的{_tenth(a.silver_share)}銀兩（最多 {a.silver_cap} 兩）與 {a.materials} 個素材，"
        "輸的扣氣血；伏兵輸了，埋伏就散了。守著的時候不能移動，可以隨時收伏。散人只劫得了自己揭了通緝的人。",
    ]
