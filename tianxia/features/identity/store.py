"""帳號綁定的旁檔（設計 4.1「旁檔」；帳號與客服第 201 批）：遊戲資料庫旁邊、同名多「-identity.sqlite」（TIANXIA_DB 換了檔，它跟著換；
同手機通知的 -push.sqlite）。只有開關開著、有人叫到 IdentityStore 才建；scripts/sb/harness.py 的 _wipe_db 與每日備份都帶它。

主資料庫第 9 版不動：驗證紀錄、解綁留的雜湊、驗證碼、限制計數、這次登入的方式都放這裡，認 accounts.id（整數）。
第 202 批多兩張：oauth_tickets（第三方登入的一次性單）、pending（驗過、還沒建角色的身分）；都是 CREATE TABLE IF NOT EXISTS，舊旁檔開的時候補建。
SQLite WAL、isolation_level=None，寫一律 BEGIN IMMEDIATE；計數是「檢查並記一筆」同一筆交易。時間一律由呼叫端傳入（不讀時鐘）。
第 203 批：challenges 多 channel、subject_hmac、display 三欄（舊旁檔開檔時補）；多 trusted_devices、pending 兩表；check_all_and_record 多格全記或全不記。
第 204 批：建表一個路徑只跑一次（identity_base.ensure_schema）；session_auth 的 DDL 在核心一份；bindings_meta 多 bound_at、reminded_at，
oauth_tickets 多 account_id；多 resets、holds、account_notes、rechecks 四表。
第 208 批：bindings_meta、holds、account_notes 的 DDL 搬到核心 identity_base（字面不變；扣押期 hold_reason 也讀）；多 reset_holds（DDL 在核心）、
contacts（綁定通知用的加密號碼，contacts.py）、cap_alerts（全服池上限通知管理者，alerts.py）三表，challenges 多 contact 一欄。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from tianxia.core import identity_base
from tianxia.database import default_path

SUFFIX = identity_base.SIDE_SUFFIX
TABLES = (
    identity_base.META_DDL,  # 第 208 批：bindings_meta、holds、account_notes 的 DDL 搬到核心一份（扣押期 hold_reason 也讀），字面不變
    "CREATE TABLE IF NOT EXISTS unbound (subject_hmac TEXT NOT NULL, provider TEXT NOT NULL, at REAL NOT NULL, account_id INTEGER)",
    "CREATE INDEX IF NOT EXISTS unbound_subject ON unbound (subject_hmac, provider)",
    "CREATE TABLE IF NOT EXISTS challenges (id TEXT PRIMARY KEY, purpose TEXT NOT NULL, account_id INTEGER, code_hmac TEXT NOT NULL, "
    "tries INTEGER NOT NULL DEFAULT 0, expires REAL NOT NULL, created REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS counters (bucket TEXT NOT NULL, at REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS counters_bucket ON counters (bucket, at)",
    identity_base.SESSION_DDL,  # 第 204 批：DDL 在核心一份（殼的 _start_session 經 identity_base 寫）；第 201 批開的這一張補兩欄
    # 第 202 批：第三方登入的一次性單（state 的雜湊；browser_hash 是 tx_oauth cookie 的雜湊，擋登入 CSRF）
    "CREATE TABLE IF NOT EXISTS oauth_tickets (state_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, purpose TEXT NOT NULL, "
    "browser_hash TEXT NOT NULL, nonce TEXT NOT NULL, verifier TEXT NOT NULL, expires REAL NOT NULL, created REAL NOT NULL)",
    # 第 203 批：曾用這個身分成功登入過的瀏覽器（tx_dev 的 sha256）
    "CREATE TABLE IF NOT EXISTS trusted_devices (dev_hash TEXT NOT NULL, subject_hmac TEXT NOT NULL, at REAL NOT NULL, "
    "PRIMARY KEY (dev_hash, subject_hmac))",
    # 驗過、還沒開帳號的身分（tx_pending 的 sha256；第 202、203 批共用一張）：第三方的 subject 是對方給的 sub，
    # 驗證碼的 subject 是加金鑰的雜湊；display 是驗證碼那條遮罩過的號碼（第三方空字串）
    "CREATE TABLE IF NOT EXISTS pending (token_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, subject TEXT NOT NULL, "
    "display TEXT NOT NULL DEFAULT '', expires REAL NOT NULL, created REAL NOT NULL)",
    # 第 204 批：忘記密碼的短效證明（tx_reset 的 sha256）、只剩過期那一種的帳號的扣押、「帳號」紀錄（兩段式）、「這不是我的帳號」的單（tx_recheck）
    "CREATE TABLE IF NOT EXISTS resets (token_hash TEXT PRIMARY KEY, account_id INTEGER NOT NULL, provider TEXT NOT NULL, at REAL NOT NULL)",
    identity_base.HOLD_DDL,
    identity_base.NOTES_DDL,
    identity_base.NOTES_INDEX_DDL,
    "CREATE TABLE IF NOT EXISTS rechecks (token_hash TEXT PRIMARY KEY, account_id INTEGER NOT NULL, provider TEXT NOT NULL, "
    "subject_hmac TEXT NOT NULL, display TEXT NOT NULL DEFAULT '', at REAL NOT NULL)",
    # 第 208 批：管理者重設之後的扣押（DDL 在核心）、綁定通知用的加密號碼（contacts.py；跟 HMAC 分開、不進任何查詢與比對）、
    # 全服池上限通知管理者的「上次通知」（同一格一小時一次）
    identity_base.RESET_HOLD_DDL,
    "CREATE TABLE IF NOT EXISTS contacts (account_id INTEGER NOT NULL, provider TEXT NOT NULL, sealed BLOB NOT NULL, "
    "display TEXT NOT NULL DEFAULT '', PRIMARY KEY (account_id, provider))",
    "CREATE TABLE IF NOT EXISTS cap_alerts (bucket TEXT PRIMARY KEY, at REAL NOT NULL)",
)
# 補的欄（舊旁檔沒有）：開檔時缺哪一欄補哪一欄。第 203 批 challenges 三欄；第 204 批 session_auth 兩欄（identity_base.SESSION_COLUMNS）、
# bindings_meta 的 bound_at（NULL＝開帳號那一種或舊資料，不算新綁）與 reminded_at、oauth_tickets 的 account_id（綁定與重驗的單綁帳號）
ADDED_COLUMNS = (("challenges", "channel", "TEXT"), ("challenges", "subject_hmac", "TEXT"), ("challenges", "display", "TEXT"),
                 *identity_base.SESSION_COLUMNS, *identity_base.META_COLUMNS,
                 ("oauth_tickets", "account_id", "INTEGER"), ("challenges", "contact", "BLOB"),  # 第 208 批：綁定的單封存的號碼
                 ("pending", "contact", "BLOB"), ("rechecks", "contact", "BLOB"))  # 第 209 批：登入驗碼的號碼帶到建角色、「這不是我的帳號」
NOTE_NEW, NOTE_PENDING, NOTE_DONE = 0, 1, 2  # account_notes.state：還沒寫、寫進存檔等下一輪確認、確認過


def side_path(db: Path) -> Path:
    return Path(db).with_name(f"{Path(db).stem}-{SUFFIX}.sqlite")


def default_side_path() -> Path:
    """跟著 TIANXIA_DB（呼叫當下才讀）。"""
    return side_path(default_path())


class IdentityStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_side_path()
        # 第 204 批（K 波審查）：建表、補欄、WAL 一個路徑只跑一次（identity_base.ensure_schema；檔被刪了再跑）
        identity_base.ensure_schema(self.path, "store", TABLES, ADDED_COLUMNS)

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
                   expires: float, now: float, account_id: int | None = None) -> None:
        """account_id：綁定與重驗的單綁開單的那個帳號（第 204 批；登入的單是 None）。"""
        with self._write() as conn:
            conn.execute(
                "INSERT INTO oauth_tickets (state_hash, provider, purpose, browser_hash, nonce, verifier, expires, created, account_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (state_hash, provider, purpose, browser_hash, nonce, verifier, expires, now, account_id),
            )

    def take_ticket(self, state_hash: str, now: float) -> dict | None:
        """拿走這張單（讀完就刪，不能重放）；過期的當沒有。順手清掉所有過期的單。"""
        with self._write() as conn:
            row = conn.execute(
                "SELECT provider, purpose, browser_hash, nonce, verifier, expires, account_id FROM oauth_tickets WHERE state_hash = ?",
                (state_hash,),
            ).fetchone()
            conn.execute("DELETE FROM oauth_tickets WHERE state_hash = ? OR expires <= ?", (state_hash, now))
        if row is None or row[5] <= now:
            return None
        return {"provider": row[0], "purpose": row[1], "browser_hash": row[2], "nonce": row[3], "verifier": row[4], "account_id": row[6]}

    # ── 還沒開帳號的身分（第 202 批；建角色前不開帳號，設計 4.2；第 203 批驗證碼查無帳號也寫這裡）──

    def put_pending(self, token_hash: str, provider: str, subject: str, expires: float, now: float, display: str = "",
                    contact: bytes | None = None) -> None:
        """contact（第 209 批）：驗證碼那條單上封的號碼（contacts.sealer 封的），建角色時存進 contacts；第三方是 None。"""
        with self._write() as conn:
            conn.execute("DELETE FROM pending WHERE expires <= ?", (now,))
            conn.execute(
                "INSERT INTO pending (token_hash, provider, subject, display, expires, created, contact) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (token_hash) DO UPDATE SET provider = excluded.provider, subject = excluded.subject, "
                "display = excluded.display, expires = excluded.expires, created = excluded.created, contact = excluded.contact",
                (token_hash, provider, subject, display, expires, now, contact),
            )

    def pending_contact(self, token_hash: str) -> bytes | None:
        """第 209 批：待處理那一列封的號碼；沒有回 None。"""
        with self._conn() as conn:
            row = conn.execute("SELECT contact FROM pending WHERE token_hash = ?", (token_hash,)).fetchone()
        return row[0] if row is not None else None

    def pending_display(self, token_hash: str) -> str:
        """驗證碼那條留的遮罩號碼（建角色寫 logins.display 用）；沒有回空字串。"""
        with self._conn() as conn:
            row = conn.execute("SELECT display FROM pending WHERE token_hash = ?", (token_hash,)).fetchone()
        return row[0] if row is not None else ""

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
                      expires: float, now: float, account_id: int | None = None, contact: bytes | None = None) -> None:
        """開一張單；同一個身分（subject_hmac）同一種用途的舊單先刪（新碼作廢舊碼）。contact：綁定的單封好的號碼（第 208 批；contacts.sealer）。"""
        with self._write() as conn:
            conn.execute("DELETE FROM challenges WHERE subject_hmac = ? AND purpose = ?", (subject, purpose))
            conn.execute(
                "INSERT INTO challenges (id, purpose, account_id, code_hmac, tries, expires, created, channel, subject_hmac, display, contact) "
                "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)",
                (cid, purpose, account_id, code_hmac, expires, now, channel, subject, display, contact),
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

    def drop_challenge(self, cid: str) -> bool:
        """刪掉那張單；這一下真的刪到才回真（驗碼對了靠它判誰贏：同一張單同時兩個請求只有一個刪得到）。"""
        with self._write() as conn:
            return conn.execute("DELETE FROM challenges WHERE id = ?", (cid,)).rowcount == 1

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
    # 驗過、查無帳號的身分：第 203 批原本在這裡另寫一支 put_pending，合 K 波時併進上面第 202 批那一支（多 display）

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

    # ── 綁定（第 204 批）─────────────────────────────

    def mark_bound(self, account_id: int, provider: str, subject_hmac: str, at: float) -> None:
        """剛綁上去：verified_at、bound_at 都記這一下（72 小時從 bound_at 算）。"""
        with self._write() as conn:
            conn.execute(
                "INSERT INTO bindings_meta (account_id, provider, subject_hmac, verified_at, bound_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (account_id, provider) DO UPDATE SET subject_hmac = excluded.subject_hmac, "
                "verified_at = excluded.verified_at, bound_at = excluded.bound_at, reminded_at = NULL",
                (account_id, provider, subject_hmac, at, at),
            )

    def meta(self, account_id: int) -> dict[str, dict]:
        """這個帳號每一種的 {subject_hmac, verified_at, bound_at, reminded_at}（provider → 那一份）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT provider, subject_hmac, verified_at, bound_at, reminded_at FROM bindings_meta WHERE account_id = ?", (account_id,),
            ).fetchall()
        return {r[0]: {"subject_hmac": r[1], "verified_at": r[2], "bound_at": r[3], "reminded_at": r[4]} for r in rows}

    def drop_meta(self, account_id: int, provider: str | None = None) -> None:
        with self._write() as conn:
            if provider is None:
                conn.execute("DELETE FROM bindings_meta WHERE account_id = ?", (account_id,))
            else:
                conn.execute("DELETE FROM bindings_meta WHERE account_id = ? AND provider = ?", (account_id, provider))

    def set_reminded(self, account_id: int, provider: str, at: float) -> None:
        with self._write() as conn:
            conn.execute("UPDATE bindings_meta SET reminded_at = ? WHERE account_id = ? AND provider = ?", (at, account_id, provider))

    def unbound_elsewhere(self, subject_hmac: str, provider: str, account_id: int | None) -> float | None:
        """這個身分最近一次從「別的帳號」（不是 account_id）解綁或刪帳號的時間；沒有回 None。原帳號重綁不受 30 天限制。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MAX(at) FROM unbound WHERE subject_hmac = ? AND provider = ? AND (account_id IS NULL OR account_id != ?)",
                (subject_hmac, provider, -1 if account_id is None else account_id),
            ).fetchone()
        return row[0]

    # ── 忘記密碼、扣押、這不是我的帳號（第 204 批）───────

    def put_reset(self, token_hash: str, account_id: int, provider: str, at: float) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM resets WHERE account_id = ?", (account_id,))
            conn.execute("INSERT INTO resets (token_hash, account_id, provider, at) VALUES (?, ?, ?, ?)", (token_hash, account_id, provider, at))

    def get_reset(self, token_hash: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT account_id, provider, at FROM resets WHERE token_hash = ?", (token_hash,)).fetchone()
        return None if row is None else {"account_id": row[0], "provider": row[1], "at": row[2]}

    def drop_reset(self, token_hash: str) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM resets WHERE token_hash = ?", (token_hash,))

    def set_hold(self, account_id: int, until: float) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO holds (account_id, until) VALUES (?, ?) ON CONFLICT (account_id) DO UPDATE SET until = MAX(until, excluded.until)",
                (account_id, until),
            )

    def hold_until(self, account_id: int) -> float | None:
        with self._conn() as conn:
            row = conn.execute("SELECT until FROM holds WHERE account_id = ?", (account_id,)).fetchone()
        return None if row is None else row[0]

    def put_recheck(self, token_hash: str, account_id: int, provider: str, subject_hmac: str, display: str, at: float,
                    contact: bytes | None = None) -> None:
        """contact（第 209 批）：單上封的號碼，「這不是我的帳號」之後帶進 pending、建角色時存。"""
        with self._write() as conn:
            conn.execute(
                "INSERT INTO rechecks (token_hash, account_id, provider, subject_hmac, display, at, contact) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (token_hash) DO UPDATE SET account_id = excluded.account_id, provider = excluded.provider, "
                "subject_hmac = excluded.subject_hmac, display = excluded.display, at = excluded.at, contact = excluded.contact",
                (token_hash, account_id, provider, subject_hmac, display, at, contact),
            )

    def take_recheck(self, token_hash: str, now: float, ttl: float) -> dict | None:
        """拿走這張單（讀完就刪）；過了 ttl 秒當沒有。"""
        with self._write() as conn:
            row = conn.execute(
                "SELECT account_id, provider, subject_hmac, display, at, contact FROM rechecks WHERE token_hash = ?", (token_hash,),
            ).fetchone()
            conn.execute("DELETE FROM rechecks WHERE token_hash = ? OR at <= ?", (token_hash, now - ttl))
        if row is None or now - row[4] > ttl:
            return None
        return {"account_id": row[0], "provider": row[1], "subject_hmac": row[2], "display": row[3], "contact": row[5]}

    # ── 「帳號」紀錄（第 204 批；兩段式同客服包）──────────

    def add_note(self, account_id: int, text: str, at: float) -> None:
        with self._write() as conn:
            conn.execute("INSERT INTO account_notes (account_id, text, at) VALUES (?, ?, ?)", (account_id, text, at))

    def notes(self, account_id: int, state: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, text, at, jtime FROM account_notes WHERE account_id = ? AND state = ? ORDER BY id", (account_id, state),
            ).fetchall()
        return [{"id": r[0], "text": r[1], "at": r[2], "jtime": r[3]} for r in rows]

    def set_note_state(self, ids, state: int, jtime: float | None = None) -> None:
        if not ids:
            return
        with self._write() as conn:
            conn.executemany("UPDATE account_notes SET state = ?, jtime = ? WHERE id = ?", [(state, jtime, i) for i in ids])

    # ── 綁定通知用的加密號碼、全服池上限通知（第 208 批）──────

    def put_contact(self, account_id: int, provider: str, sealed: bytes, display: str) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO contacts (account_id, provider, sealed, display) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (account_id, provider) DO UPDATE SET sealed = excluded.sealed, display = excluded.display",
                (account_id, provider, sealed, display),
            )

    def contacts(self, account_id: int) -> list[dict]:
        """這個帳號存的每一個號碼 {provider, sealed, display}（照 provider 排）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT provider, sealed, display FROM contacts WHERE account_id = ? ORDER BY provider", (account_id,),
            ).fetchall()
        return [{"provider": r[0], "sealed": r[1], "display": r[2]} for r in rows]

    def drop_contacts(self, account_id: int, provider: str | None = None) -> None:
        with self._write() as conn:
            if provider is None:
                conn.execute("DELETE FROM contacts WHERE account_id = ?", (account_id,))
            else:
                conn.execute("DELETE FROM contacts WHERE account_id = ? AND provider = ?", (account_id, provider))

    def alert_due(self, bucket: str, now: float, every: float) -> bool:
        """這一格上次通知超過 every 秒（或沒通知過）就記這一下、回真；不然回假。檢查與記同一筆交易。"""
        with self._write() as conn:
            row = conn.execute("SELECT at FROM cap_alerts WHERE bucket = ?", (bucket,)).fetchone()
            if row is not None and now - row[0] < every:
                return False
            conn.execute("INSERT INTO cap_alerts (bucket, at) VALUES (?, ?) ON CONFLICT (bucket) DO UPDATE SET at = excluded.at",
                         (bucket, now))
        return True

    def alerts_since(self, t: float) -> list[tuple[str, float]]:
        """t 之後通知過的每一格 (桶名, 時間)，照時間排。"""
        with self._conn() as conn:
            return [(r[0], r[1]) for r in conn.execute("SELECT bucket, at FROM cap_alerts WHERE at >= ? ORDER BY at, bucket", (t,))]
