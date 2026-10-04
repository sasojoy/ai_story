"""陣營裡的階級（計畫 T5、第一季設計 5.2、5.3）：頭銜、召見、晉升、部下、每日彙整。

只有第一季的規則開著（rules.season_one）才有這些；開關關著時狀態列照舊寫「門派・陣營」。"""
from __future__ import annotations

from .models import Content
from .rules import season_one
from .state import GameState

# 第一季設計 5.2【定】：0 號是空字串（散人沒有階），1～4 是各陣營的頭銜
TITLES: dict[str, list[str]] = {
    "guan": ["", "鄉勇", "屯長", "軍司馬", "校尉"],
    "huang": ["", "信眾", "小帥", "小方渠帥", "大方渠帥"],
    "haoqiang": ["", "鄉里子弟", "宗族頭人", "地方豪強", "一方之主"],
}


def rank_of(state: GameState) -> int:
    """此刻的階：散人 0；投靠了就至少第 1 階（存檔裡記的是晉升過的階，投靠本身不寫）。"""
    p = state.player
    return 0 if p.faction is None else max(p.rank, 1)


def title(content: Content, state: GameState) -> str | None:
    """狀態列陣營後面的頭銜；第一季的規則沒開、散人、或陣營沒有頭銜表時是 None。"""
    if not season_one(content, state.world):
        return None
    titles = TITLES.get(state.player.faction or "")
    if not titles:
        return None
    return titles[min(rank_of(state), len(titles) - 1)] or None
