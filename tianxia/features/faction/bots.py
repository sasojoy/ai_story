"""假人看到陣營的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 defect／sect 兩段）。
假人不叛投（計畫甲）、不拜門派（一類一顆從交友搬出來的一顆，同不叛投）；faction: 這幾顆（投靠、確認、選邊、改幫）原本落到 score 最後的 None：
投靠與確認走 bot_policy._toward_faction，不經 score。三個前綴一律回 None（不是 0.0）。"""
from __future__ import annotations

from tianxia.core.option import Option


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按（defect:、sect:、faction:）。"""
    return None
