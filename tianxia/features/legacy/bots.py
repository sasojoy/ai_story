"""假人的分數（就像真人：季末會選、解封會解）。放進識海 30、解封 40、撞名挑第一個候選 50；不留了不按（bot_always）。"""
from __future__ import annotations


def score(option) -> float | None:
    if not option.enabled:
        return None
    if option.id.startswith("legacy:keep:"):
        return 30.0
    if option.id == "legacy:open":
        return 40.0
    if option.id == "legacy:name:0":
        return 50.0
    return None
