"""客服包自己唯讀查主檔的 accounts、logins（帳號與客服第 211 批）：帳號鍵 → 帳號、名號 → 帳號、帳號 id → 推播用的帳號鍵。
只讀（db.snapshot()），不改 accounts.py；帳號一的 accounts.account_id(key) 合進來之後換過去（計畫第一節）。假人沒有帳號：名號查不到就是 None。"""
from __future__ import annotations

from dataclasses import dataclass

from tianxia.characters import name_key
from tianxia.database import Database


@dataclass(frozen=True)
class Who:
    id: int
    created: float
    login: str  # 登入名的顯示寫法（logins.display）；沒有密碼列時是空字串
    key: str  # 推播與登入狀態認的帳號鍵（password 列的 subject）；沒有密碼列時是 id:<n>
    character: str | None


_SELECT = ("SELECT a.id, a.created, a.character, l.subject, l.display FROM accounts a "
           "LEFT JOIN logins l ON l.account_id = a.id AND l.provider = 'password' ")


def _who(row) -> Who | None:
    if row is None:
        return None
    key = row["subject"] if row["subject"] is not None else f"id:{row['id']}"
    return Who(id=int(row["id"]), created=float(row["created"]), login=row["display"] or "", key=key, character=row["character"])


def by_key(db: Database, key: str) -> Who | None:
    """登入狀態認的帳號鍵（server._account 回的那個，小寫登入名）。"""
    with db.snapshot() as conn:
        return _who(conn.execute(_SELECT + "WHERE a.id = (SELECT account_id FROM logins WHERE provider = 'password' AND subject = ?)",
                                 (key,)).fetchone())


def by_character(db: Database, name: str) -> Who | None:
    """綁著這個名號的帳號（名號不分大小寫）；假人、還沒綁的都是 None。"""
    with db.snapshot() as conn:
        return _who(conn.execute(_SELECT + "WHERE a.character_key = ?", (name_key(name),)).fetchone())


def by_id(db: Database, account_id: int) -> Who | None:
    with db.snapshot() as conn:
        return _who(conn.execute(_SELECT + "WHERE a.id = ?", (account_id,)).fetchone())
