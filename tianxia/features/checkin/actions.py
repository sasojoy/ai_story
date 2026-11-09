"""簽到包的動作（全部拆包第 30 批：原本 Game 上的 3 個方法，計畫 docs/superpowers/plans/2026-11-04-一條線簽到-第30批.md 1.1）。
Game 留 3 個一行委派（server 的 MAIN_ACTIONS["checkin"]、假人 bot.check_in、核心原位 sync 與 status_data 在叫的；check_in 的裝飾器 @_not_while_preparing 留在委派上）。
第一個參數 ctx 是 Game（手冊 3.3）；叫回 Game 的只用 tianxia/core/services_list.md 那張清單上的。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import journal  # 核心
from tianxia import prologue as prologue_rules  # 共用規則層（序章草廬：序章裡不簽）
from tianxia.state import JournalEntry

from . import checkin

if TYPE_CHECKING:
    from tianxia.engine import Game


def check_in(ctx: Game, attribute: str = "") -> list[str]:
    """每日簽到（21 天季，正式季整合 6.2；checkin.py）：領今天的份，四階的日子帶 attribute（剛柔快慢）。草廬序章裡不簽
    （同回體丹）；關著、簽過了、沒挑或挑錯四階都只回一句、什麼都不動。成了寫一則「簽到」江湖紀錄（數值變化寫丹、銀兩、素材）。"""
    s, c = ctx.state, ctx.content
    if checkin.on(c, s.world) and ctx._opening_pending():  # 開局第一分鐘：三選一還沒選，福利之後寫進紀錄、不當第一張卡
        return ctx._log([ctx._opening_gate()])
    if checkin.on(c, s.world) and prologue_rules.active(s, c):
        return ctx._log([checkin.HUT])
    result = checkin.claim(s, c, s.world, attribute)
    if isinstance(result, str):
        return ctx._log([result])
    lines, changes = result
    journal.add_entry(s, JournalEntry(time=s.world.time, title=checkin.TITLE, lines=lines, changes=changes))
    return ctx._log(lines + changes)


def auto_checkin(ctx: Game) -> None:
    """每日簽到自動領（減法季批 1；Joy 2026-10-24 挑了江湖頁乙案：簽到不放鈕）：每天第一次同步時，今天的份不必挑的就直接領、
    寫一則「簽到」江湖紀錄（同 check_in，「剛剛」那一行會寫出來）；要挑四階的日子不動，江湖頁冒一張挑屬性的小卡（status.checkin.pick），
    挑了才領（check_in）。草廬序章裡不簽（同 check_in）。假人照舊在 bot.check_in 自己簽，先同步到的這裡順手領了也只是同一份。"""
    s, c = ctx.state, ctx.content
    if prologue_rules.active(s, c) or ctx._opening_pending():
        return
    day = checkin.due(s, c, s.world)
    if day is None or checkin.needs_pick(c, day):
        return
    result = checkin.claim(s, c, s.world)
    if isinstance(result, str):
        return
    lines, changes = result
    journal.add_entry(s, JournalEntry(time=s.world.time, title=checkin.TITLE, lines=lines, changes=changes))


def checkin_view(ctx: Game) -> dict | None:
    """江湖頁「簽到」小標的資料（checkin.view）：簽到關著、草廬序章裡、過了這一季最後一天（管理者把季末往後排）是 None。"""
    s, c = ctx.state, ctx.content
    if not checkin.on(c, s.world) or not checkin.in_season(c, s.world) or prologue_rules.active(s, c) or ctx._opening_pending():
        return None
    return checkin.view(s, c, s.world)
