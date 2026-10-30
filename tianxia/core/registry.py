"""FEATURES：登記的功能包（有順序；開發規範手冊 3.3）。核心唯一 import 功能包的地方。

新的一包用 `scripts/new_feature.py <包名>` 生：它在下面兩個標記前面各加一行（import 與清單）。順序就是核心問的順序
（選項怎麼排、哪一包先接走選單）。搬一包進來時照它在 engine.py 裡原本的位置排，行為才一個字不變。
"""
from __future__ import annotations

from .features import Feature

# ── import（new_feature.py 接在這一行前面）──

FEATURES: list[Feature] = [
    # ── 清單（new_feature.py 接在這一行前面）──
]
