"""客服在遊戲裡露出來的兩處（帳號與客服第 211 批；設計 6.6）：「客服」紀錄（on_own_turn）與 /api/main 的格（status_slots）。
旁檔不在就什麼都不讀、不建（開著但還沒有人送過單）。時間用遊戲裡的 ctx.state.world.time（不讀時鐘）。"""
from __future__ import annotations

from tianxia import journal
from tianxia.database import default_path, open_database
from tianxia.state import JournalEntry

from . import accounts_view, rules, staff, store


def _sidecar() -> store.SupportStore | None:
    return store.open_store(store.store_path(default_path()), create=False)


def _in_save(ctx, ticket_id: int, at: float) -> bool:
    line = rules.JOURNAL_LINE.format(id=ticket_id)
    return any(e.title == rules.JOURNAL_TITLE and e.time == at and line in e.lines for e in ctx.state.journal)


def journal_replies(ctx) -> None:
    """有還沒寫過的客服回覆：一張單寫一則「客服」（同一張單好幾則回覆併成一則）。先存檔成功再標（第 212 批）：
    ① 上一輪寫進去、記在 pending 的，到這一份存檔（伺服器每次進鎖從資料庫重讀）找那一則：找到就標 journaled，找不到（上一輪沒存成）
    就拿掉 pending、回到沒寫；② 沒寫、也不在 pending 的照舊寫進存檔、記進 pending。兩輪之間那一則被擠出 journal.MAX_ENTRIES 的話會補寫一次。"""
    sidecar = _sidecar()
    if sidecar is None or not ctx.state.player.name:
        return
    who = accounts_view.by_character(open_database(), ctx.state.player.name)
    if who is None:
        return
    saved, lost = [], []
    for p in sidecar.pending(who.id, who.created):
        (saved if _in_save(ctx, p["ticket_id"], p["at"]) else lost).append(p["reply_id"])
    sidecar.settle(saved, lost)
    taken = sidecar.take_unjournaled(who.id, who.created, ctx.state.world.time)
    for tid in dict.fromkeys(r["ticket_id"] for r in taken):
        journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=rules.JOURNAL_TITLE, tag=rules.JOURNAL_TAG,
                                                  lines=[rules.JOURNAL_LINE.format(id=tid)]))


def main_slot(ctx) -> dict:
    """關著 {}；開著 {support_unread: n}（沒有帳號、沒有旁檔都是 0：真人假人同一個樣子），名單上的客服再加 support_staff: True。"""
    config = ctx.content.config
    if not config.support.enabled:
        return {}
    who = accounts_view.by_character(open_database(), ctx.state.player.name) if ctx.state.player.name else None
    sidecar = _sidecar() if who is not None else None
    out: dict = {"support_unread": sidecar.unread(who.id, who.created) if sidecar is not None else 0}
    if staff.is_staff(config, who):
        out["support_staff"] = True
    return out
