"""帳號在遊戲裡露出來的兩處（帳號與客服第 204 批；設計 4.3「每次綁、解綁、設密碼都寫一則帳號遊戲紀錄」、4.4、4.5）：
「帳號」紀錄（on_own_turn）與 /api/main 的 identity 格（status_slots；只給本人、有帳號才有）。

紀錄是兩段式（同客服包 notes.py）：路由先把一句記進旁檔 account_notes（還沒寫）；本人下一輪 on_own_turn 寫進存檔、標「寫進存檔等確認」並記那一則
的遊戲時間；再下一輪在重讀的存檔找到那一則才標確認過，找不到（上一輪沒存成）退回還沒寫、補寫一次。
180 天提醒（用密碼或第三方登入、綁的手機或 Email 過期了）也在這裡記一次、記 reminded_at，不擋遊戲。
旁檔不在就什麼都不讀、不建（開著但還沒有人綁過）。紀錄的時間用遊戲裡的 ctx.state.world.time；提醒比的現實時間用 ctx.now（Game.sync 給的），不讀時鐘。
"""
from __future__ import annotations

from tianxia import journal
from tianxia.accounts import AccountStore
from tianxia.state import JournalEntry

from . import binding, store


def side() -> store.IdentityStore | None:
    path = store.default_side_path()
    return store.IdentityStore(path) if path.exists() else None


def account_of(ctx) -> tuple[int, str] | None:
    """本人的 (accounts.id, 帳號鍵)；名號沒綁帳號（假人、還沒綁的）回 None。"""
    name = ctx.state.player.name
    if not name:
        return None
    accounts = AccountStore(ctx.world.db)
    key = accounts.owner_of(name)
    account_id = accounts.account_id(key) if key is not None else None
    return None if account_id is None else (account_id, key)


def add(sidecar: store.IdentityStore, account_id: int, text: str, now: float) -> None:
    sidecar.add_note(account_id, text, now)


def _in_save(ctx, text: str, at: float | None) -> bool:
    return any(e.title == binding.JOURNAL_TITLE and e.time == at and text in e.lines for e in ctx.state.journal)


def journal_notes(ctx) -> None:
    """本人這一輪：先確認上一輪寫的、再把還沒寫的寫進存檔，最後看要不要提醒一次。"""
    sidecar = side()
    if sidecar is None:
        return
    found = account_of(ctx)
    if found is None:
        return
    account_id, _key = found
    pending = sidecar.notes(account_id, store.NOTE_PENDING)
    saved = [n["id"] for n in pending if _in_save(ctx, n["text"], n["jtime"])]
    lost = [n["id"] for n in pending if n["id"] not in saved]
    sidecar.set_note_state(saved, store.NOTE_DONE, None)
    sidecar.set_note_state(lost, store.NOTE_NEW, None)
    _remind(ctx, sidecar, account_id)
    fresh = sidecar.notes(account_id, store.NOTE_NEW)
    if not fresh:
        return
    at = ctx.state.world.time
    for note in fresh:
        journal.add_entry(ctx.state, JournalEntry(time=at, title=binding.JOURNAL_TITLE, tag=binding.JOURNAL_TAG, lines=[note["text"]]))
    sidecar.set_note_state([n["id"] for n in fresh], store.NOTE_PENDING, at)


def _remind(ctx, sidecar: store.IdentityStore, account_id: int) -> None:
    """用密碼或第三方登入的玩家：綁的 Email、手機過期了，fresh_days 提醒一次（記 reminded_at）。用驗證碼登入的人每次都更新 verified_at，不會過期。"""
    now = ctx.now
    if not now:
        return
    cfg = ctx.content.config.identity
    for provider, row in sorted(sidecar.meta(account_id).items()):
        if provider in ("email", "phone") and binding.remind_due(row, now, cfg):
            sidecar.add_note(account_id, binding.NOTE_REMIND.format(kind=binding.kind_name(provider)), now)
            sidecar.set_reminded(account_id, provider, now)


def main_slot(ctx) -> dict:
    """/api/main 的 identity 格：關著、名號沒綁帳號（假人與還沒綁的同一個樣子）回 {}；有帳號回本人的
    {kinds, has_password, phone_missing}（phone_missing 只在 phone_gate 開著、沒綁手機時真）。別人看的玩家卡、榜單不經這裡。"""
    from tianxia.core import identity_base  # noqa: PLC0415

    if not identity_base.on(ctx.content):
        return {}
    found = account_of(ctx)
    if found is None:
        return {}
    with ctx.world.db.snapshot() as conn:
        rows = conn.execute("SELECT provider FROM logins WHERE account_id = ?", (found[0],)).fetchall()
    kinds = binding.kinds_of(r["provider"] for r in rows)
    cfg = ctx.content.config.identity
    return {"identity": {"kinds": kinds, "has_password": "password" in kinds,
                         "phone_missing": bool(cfg.phone_gate) and "phone" not in kinds}}
