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


def deliver_seat(ctx) -> list[str]:
    """sync.deliver 的 seat 那一格（core_seams，全部拆包第 55 批；照原位搬）：第四階席次：抄帳、補缺（正式版丁）。輪詢只同步、只存角色（server.poll_main → act_look），
    所以帳或名單變了要自己把共用賽季存回去，不然補上的缺、那一則陣營軍情都會丟掉，下一次輪詢又補一次、又寫一則紀錄。回的那幾句進同步的回話。"""
    watching = ctx.state.player.qualified or seats.on_the_books(ctx.state)  # 沒資格、帳上也沒有名字的人，同步不碰共用賽季
    ledger_before = ctx.state.world.model_dump(include={"seat_ledger", "seats"}) if watching else None
    seated = report_seat(ctx)
    if ledger_before is not None and ctx.state.world.model_dump(include={"seat_ledger", "seats"}) != ledger_before:
        ctx._save_season()
    if seated:
        ctx._write("席次", seated)  # 新寫，待 joy 潤：紀錄的標題
    return seated
