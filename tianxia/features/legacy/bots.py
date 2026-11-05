"""假人的分數（就像真人：開季會封、解封會解）。封進識海第一份 60（開季第一件事）、解封 40、撞名挑第一個候選 50；
這一季不帶不按（bot_always）。"""
from __future__ import annotations


def score(option) -> float | None:
    if not option.enabled:
        return None
    if option.id == "legacy:seal:0":
        return 60.0
    if option.id == "legacy:open":
        return 40.0
    if option.id == "legacy:name:0":
        return 50.0
    return None
