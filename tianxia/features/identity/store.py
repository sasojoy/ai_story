"""帳號綁定的旁檔（設計 4.1「旁檔」；帳號與客服第 201 批）：遊戲資料庫旁邊、同名多「-identity.sqlite」（TIANXIA_DB 換了檔，它跟著換；
同手機通知的 -push.sqlite）。只有開關開著、有人叫到 IdentityStore 才建；scripts/sb/harness.py 的 _wipe_db 與每日備份都帶它。

主資料庫第 9 版不動：驗證紀錄、解綁留的雜湊、驗證碼、限制計數、這次登入的方式都放這裡，認 accounts.id（整數）。
第 202 批多兩張：oauth_tickets（第三方登入的一次性單）、pending（驗過、還沒建角色的身分）；都是 CREATE TABLE IF NOT EXISTS，舊旁檔開的時候補建。
SQLite WAL、isolation_level=None，寫一律 BEGIN IMMEDIATE；計數是「檢查並記一筆」同一筆交易。時間一律由呼叫端傳入（不讀時鐘）。
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
    # 第 202 批：第三方登入的一次性單（state 的雜湊；browser_hash 是 tx_oauth cookie 的雜湊，擋登入 CSRF）、還沒開帳號的身分
    "CREATE TABLE IF NOT EXISTS oauth_tickets (state_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, purpose TEXT NOT NULL, "
    "browser_hash TEXT NOT NULL, nonce TEXT NOT NULL, verifier TEXT NOT NULL, expires REAL NOT NULL, created REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS pending (token_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, subject TEXT NOT NULL, "
    "expires REAL NOT NULL, created REAL NOT NULL)",
)


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

    # ── 第三方登入的一次性單（第 202 批）──────────────

    def put_ticket(self, state_hash: str, provider: str, purpose: str, browser_hash: str, nonce: str, verifier: str,
                   expires: float, now: float) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO oauth_tickets (state_hash, provider, purpose, browser_hash, nonce, verifier, expires, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (state_hash, provider, purpose, browser_hash, nonce, verifier, expires, now),
            )

    def take_ticket(self, state_hash: str, now: float) -> dict | None:
        """拿走這張單（讀完就刪，不能重放）；過期的當沒有。順手清掉所有過期的單。"""
        with self._write() as conn:
            row = conn.execute(
                "SELECT provider, purpose, browser_hash, nonce, verifier, expires FROM oauth_tickets WHERE state_hash = ?",
                (state_hash,),
            ).fetchone()
            conn.execute("DELETE FROM oauth_tickets WHERE state_hash = ? OR expires <= ?", (state_hash, now))
        if row is None or row[5] <= now:
            return None
        return {"provider": row[0], "purpose": row[1], "browser_hash": row[2], "nonce": row[3], "verifier": row[4]}

    # ── 還沒開帳號的身分（第 202 批；建角色前不開帳號，設計 4.2）──

    def put_pending(self, token_hash: str, provider: str, subject: str, expires: float, now: float) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM pending WHERE expires <= ?", (now,))
            conn.execute(
                "INSERT INTO pending (token_hash, provider, subject, expires, created) VALUES (?, ?, ?, ?, ?)",
                (token_hash, provider, subject, expires, now),
            )

    def get_pending(self, token_hash: str, now: float) -> tuple[str, str] | None:
        """(provider, subject)；過期或沒有回 None。讀不刪（建角色名號不合格可以再試）。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT provider, subject, expires FROM pending WHERE token_hash = ?", (token_hash,),
            ).fetchone()
        if row is None or row[2] <= now:
            return None
        return (row[0], row[1])

    def drop_pending(self, token_hash: str) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM pending WHERE token_hash = ?", (token_hash,))

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
