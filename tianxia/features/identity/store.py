"""帳號綁定的旁檔（設計 4.1「旁檔」；帳號與客服第 201 批）：遊戲資料庫旁邊、同名多「-identity.sqlite」（TIANXIA_DB 換了檔，它跟著換；
同手機通知的 -push.sqlite）。只有開關開著、有人叫到 IdentityStore 才建；scripts/sb/harness.py 的 _wipe_db 與每日備份都帶它。

主資料庫第 9 版不動：驗證紀錄、解綁留的雜湊、驗證碼、限制計數、這次登入的方式都放這裡，認 accounts.id（整數）。
SQLite WAL、isolation_level=None，寫一律 BEGIN IMMEDIATE；計數是「檢查並記一筆」同一筆交易。時間一律由呼叫端傳入（不讀時鐘）。
第 203 批：challenges 多 channel、subject_hmac、display 三欄（舊旁檔開檔時補）；多 trusted_devices、pending 兩表；check_all_and_record 多格全記或全不記。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from tianxia.database import default_path

SUFFIX = "identity"
TABLES = (
    "CREATE TABLE IF NOT EXISTS bindings_meta (account_id INTEGER NOT NULL, provider TEXT NOT NULL, subject_hmac TEXT NOT NULL, "
    "verified_at REAL NOT NULL, PRIMARY KEY (account_id, provider))",
    "CREATE TABLE IF NOT EXISTS unbound (subject_hmac TEXT NOT NULL, provider TEXT NOT NULL, at REAL NOT NULL, account_id INTEGER)",
    "CREATE INDEX IF NOT EXISTS unbound_subject ON unbound (subject_hmac, provider)",
    "CREATE TABLE IF NOT EXISTS challenges (id TEXT PRIMARY KEY, purpose TEXT NOT NULL, account_id INTEGER, code_hmac TEXT NOT NULL, "
    "tries INTEGER NOT NULL DEFAULT 0, expires REAL NOT NULL, created REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS counters (bucket TEXT NOT NULL, at REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS counters_bucket ON counters (bucket, at)",
    "CREATE TABLE IF NOT EXISTS session_auth (token_hash TEXT PRIMARY KEY, method TEXT NOT NULL, at REAL NOT NULL)",
    # 第 203 批：曾用這個身分成功登入過的瀏覽器（tx_dev 的 sha256）、驗過但查無帳號的待處理身分（tx_pending 的 sha256）
    "CREATE TABLE IF NOT EXISTS trusted_devices (dev_hash TEXT NOT NULL, subject_hmac TEXT NOT NULL, at REAL NOT NULL, "
    "PRIMARY KEY (dev_hash, subject_hmac))",
    "CREATE TABLE IF NOT EXISTS pending (token_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, subject_hmac TEXT NOT NULL, "
    "display TEXT NOT NULL, expires REAL NOT NULL)",
)
# 第 203 批補的欄（第 201 批開的旁檔沒有）：開檔時缺哪一欄補哪一欄
ADDED_COLUMNS = (("challenges", "channel", "TEXT"), ("challenges", "subject_hmac", "TEXT"), ("challenges", "display", "TEXT"))


def side_path(db: Path) -> Path:
    return Path(db).with_name(f"{Path(db).stem}-{SUFFIX}.sqlite")


def default_side_path() -> Path:
    """跟著 TIANXIA_DB（呼叫當下才讀）。"""
    return side_path(default_path())


class IdentityStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_side_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            for sql in TABLES:
                conn.execute(sql)
            for table, column, kind in ADDED_COLUMNS:
                have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                if column not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self):
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    # ── 綁定的驗證時間 ─────────────────────────────

    def record_verified(self, account_id: int, provider: str, subject_hmac: str, at: float) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO bindings_meta (account_id, provider, subject_hmac, verified_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (account_id, provider) DO UPDATE SET subject_hmac = excluded.subject_hmac, verified_at = excluded.verified_at",
                (account_id, provider, subject_hmac, at),
            )

    def verified_at(self, account_id: int, provider: str) -> float | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT verified_at FROM bindings_meta WHERE account_id = ? AND provider = ?", (account_id, provider),
            ).fetchone()
        return None if row is None else row[0]

    # ── 解綁留的雜湊 ───────────────────────────────

    def record_unbound(self, subject_hmac: str, provider: str, account_id: int | None, at: float) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO unbound (subject_hmac, provider, at, account_id) VALUES (?, ?, ?, ?)",
                (subject_hmac, provider, at, account_id),
            )

    def unbound_since(self, subject_hmac: str, provider: str) -> float | None:
        """這個身分最近一次被解綁的時間；沒有就是 None。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MAX(at) FROM unbound WHERE subject_hmac = ? AND provider = ?", (subject_hmac, provider),
            ).fetchone()
        return row[0]

    # ── 限制計數 ───────────────────────────────────

    def count_and_record(self, bucket: str, window: float, limit: int, now: float) -> bool:
        """這個桶在 window 秒內還不到 limit 筆就記一筆、回真；到了不記、回假。檢查與記帳同一筆交易（BEGIN IMMEDIATE）。"""
        with self._write() as conn:
            conn.execute("DELETE FROM counters WHERE bucket = ? AND at <= ?", (bucket, now - window))
            used = conn.execute("SELECT COUNT(*) FROM counters WHERE bucket = ?", (bucket,)).fetchone()[0]
            if used >= limit:
                return False
            conn.execute("INSERT INTO counters (bucket, at) VALUES (?, ?)", (bucket, now))
        return True

    def check_all_and_record(self, buckets, now: float) -> str | None:
        """buckets 是 (桶名, window 秒, limit)：一筆 BEGIN IMMEDIATE 裡每一格都還沒滿才每格各記一筆、回 None；
        有一格滿了一筆都不記、回第一個滿的桶名（第 203 批：驗證碼的一號、每日、來源、全服池同一筆交易）。"""
        with self._write() as conn:
            for bucket, window, limit in buckets:
                conn.execute("DELETE FROM counters WHERE bucket = ? AND at <= ?", (bucket, now - window))
                used = conn.execute("SELECT COUNT(*) FROM counters WHERE bucket = ?", (bucket,)).fetchone()[0]
                if used >= limit:
                    return bucket
            conn.executemany("INSERT INTO counters (bucket, at) VALUES (?, ?)", [(b, now) for b, _w, _l in buckets])
        return None

    # ── 驗證碼的單（第 203 批）─────────────────────

    def put_challenge(self, cid: str, purpose: str, channel: str, subject: str, display: str, code_hmac: str,
                      expires: float, now: float, account_id: int | None = None) -> None:
        """開一張單；同一個身分（subject_hmac）同一種用途的舊單先刪（新碼作廢舊碼）。"""
        with self._write() as conn:
            conn.execute("DELETE FROM challenges WHERE subject_hmac = ? AND purpose = ?", (subject, purpose))
            conn.execute(
                "INSERT INTO challenges (id, purpose, account_id, code_hmac, tries, expires, created, channel, subject_hmac, display) "
                "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
                (cid, purpose, account_id, code_hmac, expires, now, channel, subject, display),
            )

    def challenge(self, cid: str) -> dict | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM challenges WHERE id = ?", (cid,)).fetchone()
        return None if row is None else dict(row)

    def bump_tries(self, cid: str, cap: int) -> int | None:
        """錯一次：tries 加一，到 cap 刪單；回加完的次數，單不在回 None。"""
        with self._write() as conn:
            row = conn.execute("SELECT tries FROM challenges WHERE id = ?", (cid,)).fetchone()
            if row is None:
                return None
            tries = row[0] + 1
            if tries >= cap:
                conn.execute("DELETE FROM challenges WHERE id = ?", (cid,))
            else:
                conn.execute("UPDATE challenges SET tries = ? WHERE id = ?", (tries, cid))
        return tries

    def drop_challenge(self, cid: str) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM challenges WHERE id = ?", (cid,))

    # ── 信任的瀏覽器與待處理的身分（第 203 批）──────

    def trust_device(self, dev_hash: str, subject: str, at: float) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO trusted_devices (dev_hash, subject_hmac, at) VALUES (?, ?, ?) "
                "ON CONFLICT (dev_hash, subject_hmac) DO UPDATE SET at = excluded.at",
                (dev_hash, subject, at),
            )

    def is_trusted(self, dev_hash: str, subject: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM trusted_devices WHERE dev_hash = ? AND subject_hmac = ?", (dev_hash, subject),
            ).fetchone()
        return row is not None

    def put_pending(self, token_hash: str, provider: str, subject: str, display: str, expires: float) -> None:
        """驗過、查無帳號的身分（建角色之前不開帳號，設計 4.2）；第 202 批的建角色流程讀它。"""
        with self._write() as conn:
            conn.execute(
                "INSERT INTO pending (token_hash, provider, subject_hmac, display, expires) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (token_hash) DO UPDATE SET provider = excluded.provider, subject_hmac = excluded.subject_hmac, "
                "display = excluded.display, expires = excluded.expires",
                (token_hash, provider, subject, display, expires),
            )

    # ── 這次登入的方式 ─────────────────────────────

    def set_session_auth(self, token_hash: str, method: str, at: float) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO session_auth (token_hash, method, at) VALUES (?, ?, ?) "
                "ON CONFLICT (token_hash) DO UPDATE SET method = excluded.method, at = excluded.at",
                (token_hash, method, at),
            )

    def session_auth(self, token_hash: str) -> tuple[str, float] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT method, at FROM session_auth WHERE token_hash = ?", (token_hash,)).fetchone()
        return None if row is None else (row[0], row[1])
