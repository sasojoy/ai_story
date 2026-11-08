"""客服（功能包；帳號與客服第 211 批「客服一」；設計 docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md 第六節，企劃者 2026-11-08 點頭第 2 版）。
這一包做什麼、旁檔、開關、客服名單的三個來源、另外要跑的：README.md。

- rules.py：純規則（類別白名單、長度、上限、狀態轉換、字）；不讀時鐘。
- store.py：旁檔 <db>-support.sqlite（tickets、replies）；關著不建檔。
- staff.py：客服名單（認帳號，不認名號）。
- accounts_view.py：唯讀查主檔的 accounts、logins（帳號一的 accounts.account_id 合進來之後換過去）。
- routes.py：/api/support/* 七條（第一行 _gate：先登入、再看開關）。

沒有選項前綴、沒有 PlayerState 欄位（不必 QUIET）、沒有內容檔。掛鉤：routes、on_own_turn（有客服回覆就寫一則「客服」紀錄）、status_slots（/api/main 的
support_unread、support_staff；關著不多鍵）。不在最上層 import routes：FEATURES 登記不拖進 fastapi。
"""
from __future__ import annotations

from tianxia.core.features import Feature, StatusHook

# 登入頁客服信箱那一行（設計 6.1；帳號一的 registerGateSlot 合進來後 PM 接，這一批沒人叫）。{mailbox} 照 Config.support.mailbox
GATE_LINE = "登不進去？寫信到客服信箱：{mailbox}（人工回信）"  # 待 joy 潤


class SupportFeature(Feature):
    name = "support"
    prefix = None  # 沒有選項：客服是設定抽屜與管理頁的事
    web: tuple[str, ...] = ()
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ()  # 不加存檔欄位：單與回覆都在旁檔
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return ctx.content.config.support.enabled  # 預設關（tianxia/core/tuning/support.py）

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只有殼掛路由時才 import（routes 要 fastapi）

        return routes.router(shell)

    def gate_slot(self, config) -> str:
        """登入頁那一行的字（關著回空字串）。帳號一開 registerGateSlot 之後由 PM 接上。"""
        return GATE_LINE.format(mailbox=config.support.mailbox) if config.support.enabled else ""

    def on_own_turn(self, ctx) -> None:
        """本人這一輪：客服回覆了，寫一則「客服」紀錄（一則回覆只寫一次）。假人第一行就跳過（假人沒有帳號、不開旁檔）。"""
        if ctx.state.player.bot is not None:
            return
        if not ctx.content.config.support.enabled:
            return
        from . import notes  # noqa: PLC0415

        notes.journal_replies(ctx)

    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """main 表的表外格（接在 STATUS_ORDER 尾）：關著回 {}；開著回 support_unread（本人帳號的未讀回覆，沒有帳號是 0），客服再加 support_staff。"""
        if self._status_slots is None:
            from . import notes  # noqa: PLC0415

            self._status_slots = (StatusHook("main", "support", lambda ctx, frame: notes.main_slot(ctx)),)
        return self._status_slots


FEATURE = SupportFeature()
