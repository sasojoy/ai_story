"""客服單的旁檔（帳號與客服第 211 批；設計 6.1、第七節）：遊戲資料庫旁邊、同名多「-support.sqlite」（TIANXIA_DB 換了檔，它跟著換；
同 notify 包的 push_store_path）。不進資料庫第 9 版、沒有存檔欄位。開關關著時沒有人建這個檔（open_store(create=False) 不建）。

四張表：
- tickets：一張單。account_id、account_created、login、character、version 是送單那一下伺服器填的（不收客戶端的）。
- replies：單上的每一則（玩家再回一句、客服回覆、請管理者處理的內部註記）。seen：玩家看過了沒；journaled：確定存進存檔的「客服」紀錄了沒。
- lookups（第 212 批）：客服查帳號與看單帶出帳號卡，每一次一列（含查無、超過次數）。只有 INSERT，沒有任何路由改或刪（客服改不到）。
  shown：帳號存正規化後的，Email、手機只存遮好的字（不存明碼、不存雜湊）。counted 1 才算進每小時的次數（看單帶卡、超過次數那一下是 0）。
- pending_notes（第 212 批）：寫進存檔、還沒確定存成的「客服」紀錄（reply_id、ticket_id、at＝寫進去那一下的遊戲時間）；notes.py 下一輪對存檔確認。
純 sqlite3；「檢查並記一筆」在同一筆 BEGIN IMMEDIATE 裡（兩個分頁同時送單也不會超過上限）。時間一律由呼叫端傳進來。"""
from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Callable
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
    # 第 212 批（CREATE IF NOT EXISTS：第 211 批建的舊檔打開時補上，舊的兩張表不 ALTER）
    "CREATE TABLE IF NOT EXISTS lookups (id INTEGER PRIMARY KEY, staff_account_id INTEGER NOT NULL, ticket_id INTEGER NOT NULL, "
    "kind TEXT NOT NULL, shown TEXT NOT NULL, found_account_id INTEGER, outcome TEXT NOT NULL, counted INTEGER NOT NULL, created REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS lookups_staff ON lookups (staff_account_id, created)",
    "CREATE TABLE IF NOT EXISTS pending_notes (reply_id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, at REAL NOT NULL)",
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

    def take_unjournaled(self, account_id: int, account_created: float, at: float) -> list[dict]:
        """還沒寫過「客服」紀錄、也不在 pending 的客服回覆（玩家看得到的那種），取出來就記進 pending（at＝這一下寫進存檔的遊戲時間；
        同一筆交易）。第 212 批起不在這裡標 journaled：要等下一輪 settle 在存檔裡看到那一則才標（先存檔成功再標）。"""
        with self._write() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT r.id, r.ticket_id FROM replies r JOIN tickets t ON t.id = r.ticket_id WHERE t.account_id = ? AND t.account_created = ? "
                "AND r.staff = 1 AND r.internal = 0 AND r.journaled = 0 AND r.id NOT IN (SELECT reply_id FROM pending_notes) ORDER BY r.id",
                (account_id, account_created))]
            for r in rows:
                conn.execute("INSERT INTO pending_notes (reply_id, ticket_id, at) VALUES (?, ?, ?)", (r["id"], r["ticket_id"], at))
        return rows

    def pending(self, account_id: int, account_created: float) -> list[dict]:
        """這個帳號寫進存檔、還沒確定存成的紀錄（reply_id、ticket_id、at）。"""
        with contextlib.closing(self._conn()) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT p.reply_id, p.ticket_id, p.at FROM pending_notes p JOIN tickets t ON t.id = p.ticket_id "
                "WHERE t.account_id = ? AND t.account_created = ? ORDER BY p.reply_id", (account_id, account_created))]

    def settle(self, saved: list[int], lost: list[int]) -> None:
        """saved：存檔裡看到了 → journaled=1、拿掉 pending；lost：存檔裡沒有（那一輪沒存成）→ 只拿掉 pending，回到沒寫（這一輪補寫）。"""
        if not saved and not lost:
            return
        with self._write() as conn:
            for rid in saved:
                conn.execute("UPDATE replies SET journaled = 1 WHERE id = ?", (rid,))
            for rid in saved + lost:
                conn.execute("DELETE FROM pending_notes WHERE reply_id = ?", (rid,))

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

    # ── 查帳號（第 212 批）──

    @staticmethod
    def _used(conn, staff_account_id: int, now: float) -> int:
        return int(conn.execute("SELECT COUNT(*) FROM lookups WHERE staff_account_id = ? AND counted = 1 AND created > ?",
                                (staff_account_id, rules.hour_start(now))).fetchone()[0])

    @staticmethod
    def _log(conn, staff_account_id: int, ticket_id: int, kind: str, shown: str, found: int | None, outcome: str, counted: int, now: float) -> None:
        conn.execute("INSERT INTO lookups (staff_account_id, ticket_id, kind, shown, found_account_id, outcome, counted, created) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (staff_account_id, ticket_id, kind, shown, found, outcome, counted, now))

    def lookup(self, *, staff_account_id: int, ticket_id: int, kind: str, shown: str, now: float, hourly: int,
               find: Callable[[], int | None]) -> tuple[str, int | None, int]:
        """數這位客服這一小時算過的次數、查、記一筆，同一筆 BEGIN IMMEDIATE（兩個分頁同時查也不會超過）。find 是唯讀查主檔（另一個庫，很短）。
        回 (outcome, 查到的帳號 id, 這一小時還剩幾次)：滿了記一筆 limit（不算次數）、不叫 find；否則記 found／none（算一次）。"""
        with self._write() as conn:
            used = self._used(conn, staff_account_id, now)
            if used >= hourly:
                self._log(conn, staff_account_id, ticket_id, kind, shown, None, "limit", 0, now)
                return "limit", None, 0
            found = find()
            self._log(conn, staff_account_id, ticket_id, kind, shown, found, "found" if found is not None else "none", 1, now)
            return ("found" if found is not None else "none"), found, hourly - used - 1

    def log_card(self, *, staff_account_id: int, ticket_id: int, shown: str, found: int | None, now: float) -> None:
        """看單時帶出帳號卡：不算次數，照樣記一筆（帳號對得上 card，對不上 gone）。"""
        with self._write() as conn:
            self._log(conn, staff_account_id, ticket_id, "card", shown, found, "card" if found is not None else "gone", 0, now)

    def lookups_left(self, staff_account_id: int, now: float, hourly: int) -> int:
        with contextlib.closing(self._conn()) as conn:
            return max(0, hourly - self._used(conn, staff_account_id, now))

    def close(self, ticket_id: int, now: float) -> None:
        with self._write() as conn:
            t = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if t is None:
                raise Refused(rules.NOT_FOUND)
            conn.execute("UPDATE tickets SET status = ?, updated = ? WHERE id = ?", (rules.CLOSED, now, ticket_id))
