"""客服查帳號（帳號與客服第 212 批；設計 6.3）：唯讀查主資料庫的 accounts、logins，元寶帳本讀核心的 Wallet.ledger。
- find：完整帳號（AccountStore.account_id；id:<n> 不收）、完整 Email、完整手機（正規化後算 HMAC，identity_base.account_key_for 找帳號；
  identity 關著或金鑰讀不到就查無）。不收名號、不做模糊搜尋。
- card：帳號卡（帳號、名號、建帳號日、綁了哪幾種〔只有 Email、手機帶遮好的顯示字〕、餘額、帳本最近幾筆）。
假人沒有帳號：怎麼查都查無，卡永遠不會是假人。不寫任何東西、不讀時鐘。"""
from __future__ import annotations

from tianxia.accounts import AccountStore
from tianxia.characters import name_key
from tianxia.core import identity_base
from tianxia.database import Database
from tianxia.wallet import Wallet

from . import rules


def find(db: Database, content, kind: str, value: str) -> int | None:
    """value 是 rules.lookup_value 正規化過的。查到回 accounts.id，查無回 None。"""
    if kind == "login":
        if value.startswith(identity_base.ID_PREFIX):
            return None  # id:<n> 是內部的鍵，不是帳號名
        return AccountStore(db).account_id(value)
    if kind not in ("email", "phone") or not identity_base.on(content):
        return None
    key = identity_base.read_key()
    if key is None:
        return None
    account_key = identity_base.account_key_for(db, kind, identity_base.subject_hmac(key, kind, value))
    return None if account_key is None else AccountStore(db).account_id(account_key)


def card(db: Database, account_id: int, *, ledger_rows: int, created_must: float | None = None) -> dict:
    """帳號卡；帳號不在、或 created_must 給了而建帳號的時間對不上（主檔退回舊時間點之後 id 被新帳號拿到）回 {"gone": True}。"""
    with db.snapshot() as conn:
        a = conn.execute("SELECT id, created, character FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if a is None or (created_must is not None and float(a["created"]) != float(created_must)):
            return {"gone": True}
        rows = conn.execute("SELECT provider, display FROM logins WHERE account_id = ?", (account_id,)).fetchall()
    order = list(rules.PROVIDER_NAMES)
    rows = sorted(rows, key=lambda r: (order.index(r["provider"]) if r["provider"] in order else len(order), r["provider"]))
    login = next((r["display"] for r in rows if r["provider"] == "password"), None) or f"{identity_base.ID_PREFIX}{a['id']}"
    binds = [{"provider": r["provider"], "name": rules.PROVIDER_NAMES.get(r["provider"], r["provider"]),
              "shown": (r["display"] or "") if r["provider"] in rules.SHOWN_PROVIDERS else ""} for r in rows]
    character = a["character"]
    wallet = Wallet(db)
    owner = name_key(character) if character else None
    ledger = [] if owner is None else [
        {"time": e.time, "delta": e.delta, "reason": rules.LEDGER_REASONS.get(e.reason, e.reason), "note": e.note}
        for e in wallet.ledger(owner, limit=ledger_rows)]
    return {"id": int(a["id"]), "login": login, "character": character, "created": float(a["created"]), "binds": binds,
            "balance": 0 if owner is None else wallet.balance(owner), "ledger": ledger}
