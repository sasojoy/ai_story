"""客服單的旁檔（帳號與客服第 211 批；設計 6.1、第七節）：遊戲資料庫旁邊、同名多「-support.sqlite」（TIANXIA_DB 換了檔，它跟著換；
同 notify 包的 push_store_path）。不進資料庫第 9 版、沒有存檔欄位。開關關著時沒有人建這個檔（open_store(create=False) 不建）。

兩張表：
- tickets：一張單。account_id、account_created、login、character、version 是送單那一下伺服器填的（不收客戶端的）。
- replies：單上的每一則（玩家再回一句、客服回覆、請管理者處理的內部註記）。seen：玩家看過了沒；journaled：寫過「客服」紀錄沒。
純 sqlite3；「檢查並記一筆」在同一筆 BEGIN IMMEDIATE 裡（兩個分頁同時送單也不會超過上限）。時間一律由呼叫端傳進來。"""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from . import rules

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, account_created REAL NOT NULL, "
    "login TEXT NOT NULL, character TEXT NOT NULL, version TEXT NOT NULL, category TEXT NOT NULL, body TEXT NOT NULL, "
    "status TEXT NOT NULL, admin_flag INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS tickets_status ON tickets (account_id, status)",
    "CREATE INDEX IF NOT EXISTS tickets_created ON tickets (account_id, created)",
    "CREATE TABLE IF NOT EXISTS replies (id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, by_account_id INTEGER NOT NULL, "
    "staff INTEGER NOT NULL, internal INTEGER NOT NULL, body TEXT NOT NULL, created REAL NOT NULL, "
    "seen INTEGER NOT NULL DEFAULT 0, journaled INTEGER NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS replies_ticket ON replies (ticket_id)",
)


class Refused(ValueError):
    """玩家看得到的拒絕：訊息就是畫面上的字（routes 換成殼的 GameError）。"""


def store_path(db_path: Path) -> Path:
    db = Path(db_path)
    return db.with_name(f"{db.stem}-support.sqlite")


def open_store(path: Path, create: bool) -> SupportStore | None:
    """create=False：檔不在就回 None（只讀的地方：關著、沒人送過單都不建檔）。"""
    path = Path(path)
    if not create and not path.exists():
        return None
    return SupportStore(path)


def _row(row: sqlite3.Row | None) -> dict | None:
    return None if row is None else dict(row)


class SupportStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(self._conn()) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            for sql in SCHEMA:
                conn.execute(sql)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    @contextlib.contextmanager
    def _write(self):
        with contextlib.closing(self._conn()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    # ── 玩家 ──

    def add_ticket(self, *, account_id: int, account_created: float, login: str, character: str, version: str, category: str, body: str,
                   now: float, open_max: int, daily_max: int) -> int:
        """數沒結的單與 24 小時內送的單、沒超過才記一張（同一筆交易）。超過丟 Refused。"""
        with self._write() as conn:
            open_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE account_id = ? AND account_created = ? AND status != ?",
                                      (account_id, account_created, rules.CLOSED)).fetchone()[0]
            recent = conn.execute("SELECT COUNT(*) FROM tickets WHERE account_id = ? AND account_created = ? AND created > ?",
                                  (account_id, account_created, rules.day_start(now))).fetchone()[0]
            why = rules.quota_problem(open_count, recent, open_max, daily_max)
            if why is not None:
                raise Refused(why)
            cur = conn.execute(
                "INSERT INTO tickets (account_id, account_created, login, character, version, category, body, status, admin_flag, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (account_id, account_created, login, character, version, category, body, rules.OPEN, now, now))
            return int(cur.lastrowid)

    def ticket(self, ticket_id: int) -> dict | None:
        with contextlib.closing(self._conn()) as conn:
            return _row(conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone())

    def replies(self, ticket_id: int, *, internal: bool) -> list[dict]:
        """一張單的回覆（舊的在前）；internal=False 不含內部註記。"""
        sql = "SELECT * FROM replies WHERE ticket_id = ?" + ("" if internal else " AND internal = 0") + " ORDER BY id"
        with contextlib.closing(self._conn()) as conn:
            return [dict(r) for r in conn.execute(sql, (ticket_id,))]

    def mine(self, account_id: int, account_created: float) -> list[dict]:
        """這個帳號的單（新的在前）；只認 id 加建帳號的時間都對的。"""
        with contextlib.closing(self._conn()) as conn:
            rows = conn.execute("SELECT * FROM tickets WHERE account_id = ? AND account_created = ? ORDER BY id DESC",
                                (account_id, account_created)).fetchall()
        return [dict(r) for r in rows]

    def mark_seen(self, account_id: int, account_created: float) -> None:
        """玩家看過自己的單：客服的回覆都記成看過（紅點消掉）。"""
        with self._write() as conn:
            conn.execute("UPDATE replies SET seen = 1 WHERE seen = 0 AND staff = 1 AND internal = 0 AND ticket_id IN "
                         "(SELECT id FROM tickets WHERE account_id = ? AND account_created = ?)", (account_id, account_created))

    def unread(self, account_id: int, account_created: float) -> int:
        with contextlib.closing(self._conn()) as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM replies r JOIN tickets t ON t.id = r.ticket_id WHERE t.account_id = ? AND t.account_created = ? "
                "AND r.staff = 1 AND r.internal = 0 AND r.seen = 0", (account_id, account_created)).fetchone()[0])

    def take_unjournaled(self, account_id: int, account_created: float) -> list[dict]:
        """還沒寫過「客服」紀錄的客服回覆（玩家看得到的那種），取出來就記成寫過（同一筆交易：同一則只寫一次）。"""
        with self._write() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT r.id, r.ticket_id FROM replies r JOIN tickets t ON t.id = r.ticket_id WHERE t.account_id = ? AND t.account_created = ? "
                "AND r.staff = 1 AND r.internal = 0 AND r.journaled = 0 ORDER BY r.id", (account_id, account_created))]
            for r in rows:
                conn.execute("UPDATE replies SET journaled = 1 WHERE id = ?", (r["id"],))
        return rows

    def player_reply(self, ticket_id: int, account_id: int, account_created: float, body: str, now: float) -> None:
        """玩家再回一句：單號加帳號（id 與建帳號時間）都對才行，不然丟 Refused(NOT_FOUND)；結了的丟 Refused(CLOSED_ALREADY)。"""
        with self._write() as conn:
            t = _row(conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone())
            if t is None or not rules.owns(t, account_id, account_created):
                raise Refused(rules.NOT_FOUND)
            if t["status"] == rules.CLOSED:
                raise Refused(rules.CLOSED_ALREADY)
            conn.execute("INSERT INTO replies (ticket_id, by_account_id, staff, internal, body, created) VALUES (?, ?, 0, 0, ?, ?)",
                         (ticket_id, account_id, body, now))
            conn.execute("UPDATE tickets SET status = ?, updated = ? WHERE id = ?", (rules.after_player_reply(t["status"]), now, ticket_id))

    # ── 客服 ──

    def queue(self, now: float) -> dict:
        """客服頁的清單：沒結的單（處理中的在前、各自舊的在前），三個數：沒回的、等玩家、24 小時內的新單。"""
        with contextlib.closing(self._conn()) as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM tickets WHERE status != ? ORDER BY CASE status WHEN ? THEN 0 ELSE 1 END, updated", (rules.CLOSED, rules.OPEN))]
            fresh = conn.execute("SELECT COUNT(*) FROM tickets WHERE created > ?", (rules.day_start(now),)).fetchone()[0]
        return {
            "open": sum(1 for r in rows if r["status"] == rules.OPEN),
            "waiting": sum(1 for r in rows if r["status"] == rules.ANSWERED),
            "fresh": int(fresh),
            "tickets": rows,
        }

    def staff_reply(self, ticket_id: int, by_account_id: int, body: str, then: str, now: float) -> dict:
        """客服回一則：then 是 wait（回覆並等玩家）、close（回覆並結單）、admin（請管理者處理：內部註記、單上記一個旗）。回更新後的單。"""
        internal = then == "admin"
        with self._write() as conn:
            t = _row(conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone())
            if t is None:
                raise Refused(rules.NOT_FOUND)
            if t["status"] == rules.CLOSED:
                raise Refused(rules.CLOSED_ALREADY)
            conn.execute("INSERT INTO replies (ticket_id, by_account_id, staff, internal, body, created) VALUES (?, ?, 1, ?, ?, ?)",
                         (ticket_id, by_account_id, int(internal), body, now))
            status = rules.after_staff(then, t["status"])
            conn.execute("UPDATE tickets SET status = ?, admin_flag = MAX(admin_flag, ?), updated = ? WHERE id = ?",
                         (status, int(internal), now, ticket_id))
            return _row(conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone())

    def close(self, ticket_id: int, now: float) -> None:
        with self._write() as conn:
            t = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if t is None:
                raise Refused(rules.NOT_FOUND)
            conn.execute("UPDATE tickets SET status = ?, updated = ? WHERE id = ?", (rules.CLOSED, now, ticket_id))
