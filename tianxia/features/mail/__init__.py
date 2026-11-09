"""帖友書信（功能包；開發規範手冊 3.2）：交換過名帖的兩個人互相寄信。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

- store.py：信件小檔 <db>-mail.sqlite（不進角色存檔；兩季以前的搬去封存檔）
- actions.py：信匣、往來、寄（三段式的 A、C 段）、不收、檢舉、管理者看檢舉、撤下、停寄
- routes.py：/api/mail、/api/mail/thread、/api/mail/{op}；管理者工具 mail_remove、mail_keep、mail_mute
- 易名帖改名時信上的名號跟著換：載入這一包就登記到核心 core/renames（sqlite_world.rename_character 交易 COMMIT 之後叫）
沒有選項、不認領 PlayerState 欄位；假人不寄信（bots 不碰這一包）。
"""
from __future__ import annotations

from tianxia.core import renames
from tianxia.core.features import Feature, StatusHook


def _rename(db_path, old: str, new: str) -> None:
    from . import store  # noqa: PLC0415

    path = db_path.with_name(f"{db_path.stem}-mail.sqlite")
    if path.is_file():
        store.for_db(db_path).rename(old, new)


renames.register(_rename)


class MailFeature(Feature):
    name = "mail"
    prefix = "mail"  # 沒有選項；前綴留著（核心只把這個前綴的 id 交給這一包）
    web: tuple[str, ...] = ("mail.js", "mail.css")
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ()  # 信在小檔裡，不認領欄位
    carried: tuple[str, ...] = ()
    _status_slots: tuple[StatusHook, ...] | None = None

    def enabled(self, ctx) -> bool:
        return ctx.content.config.mail.enabled  # 數字在 tianxia/core/tuning/mail.py（Config.mail）

    def status(self, ctx) -> dict:
        from . import actions  # noqa: PLC0415

        return actions.status(ctx)  # main.mail：信匣幾封沒看（見聞的紅點）

    def status_slots(self) -> tuple[StatusHook, ...]:
        """管理頁「書信檢舉」（admin 表的表外格，接在表尾）。核心不問 enabled：關著這裡回 {}（沒有這個鍵，管理頁一個位元組都不變）。"""
        if self._status_slots is None:
            from . import actions  # noqa: PLC0415

            self._status_slots = (StatusHook("admin", "mail", lambda ctx, frame: {"mail": actions.admin_reports(ctx)} if actions.on(ctx) else {}),)
        return self._status_slots

    def admin_tools(self, shell) -> dict:
        from . import routes  # noqa: PLC0415

        return routes.admin_tools(shell)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415

        return routes.router(shell)


FEATURE = MailFeature()
