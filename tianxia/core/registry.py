"""FEATURES：登記的功能包（有順序；開發規範手冊 3.3）。核心唯一 import 功能包的地方。

新的一包用 `scripts/new_feature.py <包名>` 生：它在下面兩個標記前面各加一行（import 與清單）。順序就是核心問的順序
（選項怎麼排、哪一包先接走選單）。搬一包進來時照它在 engine.py 裡原本的位置排，行為才一個字不變。
"""
from __future__ import annotations

from .features import Feature

# explore
from ..features import explore  # 探索（走一趟、探索一顆）：主動搬六包第 3＋4 批（沒有選項、選單、狀態，排在哪裡結果都一樣）
from ..features import feast, mall  # 商城（萬寶閣）：第 1 階搬進來的示範；宴客：第 1 階多搬的有按鈕的小包（3.10）
# tavern
from ..features import tavern  # 酒肆：主動搬六包第 10 批（只接 tavern:* 的 choose 與假人分數，都照前綴認，排在哪裡結果都一樣）
from ..features import sortie  # 出陣：主動搬六包第 1 批（沒有選項、選單、狀態，排在哪裡結果都一樣）
# battle
from ..features import battle  # 全服決戰：主動搬六包第 5 批（「看」那一半；沒有選項、選單、狀態，排在哪裡結果都一樣）
# ── import（new_feature.py 接在這一行前面）──

FEATURES: list[Feature] = [
    # explore（排最前面不是排最後：同時在拆的別條線都在標記前面接自己的一行，各佔各的行合併才不撞；這一包只有 check_content，
    # 其餘掛鉤都是預設的，順序唯一的影響是 content.validate 裡探索的錯誤排在商城前面——審查修正，不是「忘了排最後」）
    explore.FEATURE,
    mall.FEATURE,
    feast.FEATURE,
    # tavern
    tavern.FEATURE,
    sortie.FEATURE,
    # battle
    battle.FEATURE,
    # ── 清單（new_feature.py 接在這一行前面）──
]
