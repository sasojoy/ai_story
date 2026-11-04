"""第四階席次的抄帳（功能包 military；全部拆包第 33 批；正式版丁）。原本 Game 上的 1 個方法（_report_seat）；第一個參數是 ctx。會改狀態（抄帳、補缺、發軍情）。
席次的規則在 tianxia/seats.py（共用規則層）。被叫在 sync、choose、travel 與事件檢定（隨口應對）之後，Game 與事件檢定都留一行委派。
"""
from __future__ import annotations

from tianxia import seats


def report_seat(ctx) -> list[str]:
    """第四階席次的抄帳與補缺（seats.report）：賽季時鐘暫停中不做（丁 N5 的裁決：暫停凍結世界的變化，
    不補缺、不發軍情、帳也不抄；繼續之後的第一次同步補上，只補一次）。暫停時畫面照常可看、同步照常走，所以這裡要自己擋。"""
    if ctx.world.paused_at() is not None:
        return []
    return seats.report(ctx.state, ctx.content)
