"""帖友書信的小檔 <db>-mail.sqlite（設計稿 https://claude.ai/artifact/FhMZSwH6aqNsrnNAwHBznn 第四節，Joy 2026-11-07「其他按照建議」）。

照往來紀錄（companions/talk_log.py）的做法：不進角色存檔（角色那一整塊 JSON 每個動作都在行動鎖裡整份讀寫），一封一列，打開才分頁讀；
兩季以前的整批搬到 <db>-mail-archive.sqlite（照原本的 id 搬，翻舊信時主檔不夠才去那裡讀）。丟了這個檔只是看不到信，遊戲照玩。
名號一律存 name_key；易名帖改名時由核心 core/renames 叫 rename 換掉（這個檔不在資料庫交易裡，換名在交易 COMMIT 之後）。

表：
- letters：一封一列。dropped＝寄出那一刻收件人不收他的信（寄的人照樣看得到自己寫的，收件人永遠看不到）；hidden＝收件人檢舉後收起來；
  removed＝管理者撤下（兩邊都看不到）；read＝收件人看過了（只算未讀數，不給寄件人看：沒有「已讀」，假人永遠不讀信會露餡）。
- blocks：誰不收誰的信。mutes：管理者停誰寄信到什麼時候（現實時間）。reports：檢舉。
"""
from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path

PAGE = 30  # 往來一次讀幾封

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS letters (id INTEGER PRIMARY KEY AUTOINCREMENT, season INTEGER NOT NULL, at REAL NOT NULL, day INTEGER NOT NULL, "
    "stamp TEXT NOT NULL, place TEXT NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL, text TEXT NOT NULL, "
    "read INTEGER NOT NULL DEFAULT 0, dropped INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0, removed INTEGER NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS letters_to ON letters (recipient, read)",
    "CREATE INDEX IF NOT EXISTS letters_pair ON letters (sender, recipient, id)",
    "CREATE INDEX IF NOT EXISTS letters_day ON letters (sender, day)",
    "CREATE TABLE IF NOT EXISTS blocks (owner TEXT NOT NULL, blocked TEXT NOT NULL, PRIMARY KEY (owner, blocked))",
    "CREATE TABLE IF NOT EXISTS mutes (who TEXT PRIMARY KEY, until REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, letter INTEGER NOT NULL, reporter TEXT NOT NULL, "
    "at REAL NOT NULL, handled INTEGER NOT NULL DEFAULT 0, UNIQUE (letter, reporter))",
)
_COLS = "id, season, at, day, stamp, place, sender, recipient, text, read, dropped, hidden, removed"

_OPEN: dict[Path, MailStore] = {}
_OPEN_LOCK = threading.Lock()


def for_db(db_path: Path) -> MailStore:
    """資料庫檔旁邊那一份（<stem>-mail.sqlite）；同一個檔只開一次（建表只做一次）。"""
    db_path = Path(db_path)
    path = db_path.with_name(f"{db_path.stem}-mail.sqlite")
    with _OPEN_LOCK:
        store = _OPEN.get(path)
        if store is None:
            store = _OPEN[path] = MailStore(path)
        return store


class MailStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_path = self.path.with_name(self.path.name.replace(".sqlite", "-archive.sqlite"))
        self._swept = -1
        with contextlib.closing(self._conn(self.path)) as conn, conn:
            for sql in _SCHEMA:
                conn.execute(sql)

    @staticmethod
    def _conn(path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _read(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with contextlib.closing(self._conn(self.path)) as conn:
            return conn.execute(sql, args).fetchall()

    def _write(self, sql: str, args: tuple = ()) -> int:
        with contextlib.closing(self._conn(self.path)) as conn, conn:
            cur = conn.execute(sql, args)
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount

    # ── 寄 ──

    def add(self, *, season: int, at: float, day: int, stamp: str, place: str, sender: str, recipient: str, text: str,
            dropped: bool, keep: int) -> int:
        """寄一封；這一對人（不分誰寄誰）在主檔只留最近 keep 封。換了季的第一封順手把兩季以前的搬去封存檔。回傳這一封的 id。"""
        with contextlib.closing(self._conn(self.path)) as conn, conn:
            cur = conn.execute(
                "INSERT INTO letters (season, at, day, stamp, place, sender, recipient, text, dropped) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (season, at, day, stamp, place, sender, recipient, text, int(dropped)))
            lid = cur.lastrowid
            conn.execute(
                "DELETE FROM letters WHERE ((sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?)) AND id NOT IN "
                "(SELECT id FROM letters WHERE (sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?) ORDER BY id DESC LIMIT ?)",
                (sender, recipient, recipient, sender, sender, recipient, recipient, sender, keep))
        if self._swept != season:
            self._swept = season
            self.archive_before(season - 1)
        return lid

    def archive_before(self, season: int) -> int:
        """season 以前（不含）的整批搬到封存檔（照原本的 id）；回傳搬了幾封。"""
        old = self._read(f"SELECT {_COLS} FROM letters WHERE season < ?", (season,))
        if not old:
            return 0
        with contextlib.closing(self._conn(self.archive_path)) as arc, arc:
            for sql in _SCHEMA:
                arc.execute(sql)
            arc.executemany(f"INSERT OR REPLACE INTO letters ({_COLS}) VALUES ({', '.join('?' * 13)})", [tuple(r) for r in old])
        self._write("DELETE FROM letters WHERE season < ?", (season,))
        return len(old)

    def sent_on(self, sender: str, day: int) -> int:
        return self._read("SELECT COUNT(*) AS n FROM letters WHERE sender = ? AND day = ?", (sender, day))[0]["n"]

    def unanswered(self, sender: str, recipient: str) -> int:
        """他最後一次寫給你之後，你又連寫了幾封給他（被不收的也算：寄的人不知道）。"""
        rows = self._read("SELECT MAX(id) AS last FROM letters WHERE sender = ? AND recipient = ? AND dropped = 0 AND removed = 0",
                          (recipient, sender))
        last = rows[0]["last"] or 0
        return self._read("SELECT COUNT(*) AS n FROM letters WHERE sender = ? AND recipient = ? AND id > ?", (sender, recipient, last))[0]["n"]

    # ── 讀 ──

    def unread(self, me: str) -> int:
        return self._read("SELECT COUNT(*) AS n FROM letters WHERE recipient = ? AND read = 0 AND dropped = 0 AND hidden = 0 AND removed = 0",
                          (me,))[0]["n"]

    def threads(self, me: str) -> list[dict]:
        """我的信匣：每一位有往來的人一行（最新那一封、他寄給我還沒讀的幾封），新的在前。只看主檔（這一季與上一季）。"""
        rows = self._read(
            f"SELECT {_COLS} FROM letters WHERE removed = 0 AND ((sender = ?) OR (recipient = ? AND dropped = 0 AND hidden = 0)) ORDER BY id DESC",
            (me, me))
        out: dict[str, dict] = {}
        for r in rows:
            other = r["recipient"] if r["sender"] == me else r["sender"]
            row = out.get(other)
            if row is None:
                row = out[other] = {"other": other, "last": dict(r), "unread": 0}
            if r["recipient"] == me and not r["read"]:
                row["unread"] += 1
        return list(out.values())

    def page(self, me: str, other: str, before: int | None = None, limit: int = PAGE) -> tuple[list[dict], bool]:
        """我跟他的往來，新的在前，一次 limit 封；before 是上一頁最舊那一封的 id。主檔不夠就接著讀封存檔。"""
        where = ("removed = 0 AND ((sender = ? AND recipient = ?) OR (sender = ? AND recipient = ? AND dropped = 0 AND hidden = 0))"
                 + (" AND id < ?" if before else ""))
        args = (me, other, other, me, *((before,) if before else ()))
        sql = f"SELECT {_COLS} FROM letters WHERE {where} ORDER BY id DESC LIMIT ?"
        rows: list[dict] = []
        for path in (self.path, self.archive_path):
            if len(rows) > limit or not path.is_file():
                continue
            with contextlib.closing(self._conn(path)) as conn:
                try:
                    got = conn.execute(sql, (*args, limit + 1 - len(rows))).fetchall()
                except sqlite3.OperationalError:  # 封存檔還沒有這張表
                    got = []
            seen = {r["id"] for r in rows}
            rows += [dict(r) for r in got if r["id"] not in seen]
        return rows[:limit], len(rows) > limit

    def mark_read(self, me: str, other: str) -> int:
        return self._write("UPDATE letters SET read = 1 WHERE recipient = ? AND sender = ? AND read = 0", (me, other))

    def letter(self, lid: int) -> dict | None:
        for path in (self.path, self.archive_path):
            if not path.is_file():
                continue
            with contextlib.closing(self._conn(path)) as conn:
                try:
                    row = conn.execute(f"SELECT {_COLS} FROM letters WHERE id = ?", (lid,)).fetchone()
                except sqlite3.OperationalError:
                    row = None
            if row is not None:
                return dict(row)
        return None

    # ── 不收、停寄、檢舉 ──

    def blocked(self, owner: str) -> list[str]:
        return [r["blocked"] for r in self._read("SELECT blocked FROM blocks WHERE owner = ? ORDER BY blocked", (owner,))]

    def blocks(self, owner: str, other: str) -> bool:
        return bool(self._read("SELECT 1 FROM blocks WHERE owner = ? AND blocked = ?", (owner, other)))

    def block(self, owner: str, other: str) -> None:
        self._write("INSERT OR IGNORE INTO blocks (owner, blocked) VALUES (?, ?)", (owner, other))

    def unblock(self, owner: str, other: str) -> None:
        self._write("DELETE FROM blocks WHERE owner = ? AND blocked = ?", (owner, other))

    def muted_until(self, who: str, now: float) -> float | None:
        rows = self._read("SELECT until FROM mutes WHERE who = ?", (who,))
        return rows[0]["until"] if rows and rows[0]["until"] > now else None

    def mute(self, who: str, until: float) -> None:
        self._write("INSERT INTO mutes (who, until) VALUES (?, ?) ON CONFLICT (who) DO UPDATE SET until = excluded.until", (who, until))

    def unmute(self, who: str) -> None:
        self._write("DELETE FROM mutes WHERE who = ?", (who,))

    def report(self, lid: int, reporter: str, at: float) -> None:
        """收件人檢舉一封：從他的信匣收起來，記一筆給管理者看（同一封同一個人只記一次）。"""
        with contextlib.closing(self._conn(self.path)) as conn, conn:
            conn.execute("UPDATE letters SET hidden = 1 WHERE id = ? AND recipient = ?", (lid, reporter))
            conn.execute("INSERT OR IGNORE INTO reports (letter, reporter, at) VALUES (?, ?, ?)", (lid, reporter, at))

    def open_reports(self) -> list[dict]:
        rows = self._read("SELECT id, letter, reporter, at FROM reports WHERE handled = 0 ORDER BY id")
        out = []
        for r in rows:
            letter = self.letter(r["letter"])
            if letter is not None:
                out.append({"report": r["id"], "reporter": r["reporter"], "at": r["at"], "letter": letter})
        return out

    def settle(self, lid: int, *, remove: bool) -> int:
        """管理者處理一封信的檢舉：remove 撤下（兩邊都看不到），否則是看過沒事（收件人那裡照樣收著）。回傳結了幾筆檢舉。"""
        with contextlib.closing(self._conn(self.path)) as conn, conn:
            if remove:
                conn.execute("UPDATE letters SET removed = 1 WHERE id = ?", (lid,))
            return conn.execute("UPDATE reports SET handled = 1 WHERE letter = ? AND handled = 0", (lid,)).rowcount

    # ── 易名帖 ──

    def rename(self, old: str, new: str) -> None:
        """名號 key 從 old 換成 new（主檔與封存檔都換）。"""
        if old == new:
            return
        for path in (self.path, self.archive_path):
            if not path.is_file():
                continue
            with contextlib.closing(self._conn(path)) as conn, conn:
                try:
                    conn.execute("UPDATE letters SET sender = ? WHERE sender = ?", (new, old))
                    conn.execute("UPDATE letters SET recipient = ? WHERE recipient = ?", (new, old))
                    if path == self.path:
                        conn.execute("UPDATE OR IGNORE blocks SET owner = ? WHERE owner = ?", (new, old))
                        conn.execute("UPDATE OR IGNORE blocks SET blocked = ? WHERE blocked = ?", (new, old))
                        conn.execute("UPDATE OR IGNORE mutes SET who = ? WHERE who = ?", (new, old))
                        conn.execute("UPDATE reports SET reporter = ? WHERE reporter = ?", (new, old))
                except sqlite3.OperationalError:  # 封存檔沒有那幾張表
                    pass
