"""帳號與密碼（帳號密碼登入設計，docs/superpowers/specs/2026-10-03-帳號密碼登入-design.md）。

帳號和名號分開：一個帳號一個角色，名號在建立角色時才綁上去。密碼用 scrypt 加鹽雜湊，只存鹽和雜湊值。
帳號存在資料庫（線上架構設計第三、六節）：`accounts` 表一個帳號一列，`logins` 表是帳號的登入方式——
現在只有 password（帳號密碼），線上版也是用它登入（server.py 只有 /api/register、/api/login，有網址的人都能註冊）；
線上架構設計原本定第 3 期在同一個帳號上加 line、google、封測的線上版關掉帳號密碼（企劃者 2026-10-03），那一條沒有做。
不 import 網頁框架；會改帳號的方法各自是一筆交易，呼叫端已經
開著交易（例如建立角色時一起綁帳號）就併進那一筆；scrypt 很慢，都在進交易之前先算好，不握著寫入權算。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .characters import name_key
from .database import Database

LOGIN_PATTERN = re.compile(r"[A-Za-z0-9_]{3,20}")
PASSWORD_MIN = 6
PASSWORD_MAX = 128
SCRYPT_PARAMS = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
SALT_BYTES = 16
MAX_FAILURES = 5
FAILURE_WINDOW = 600.0  # 秒：同一個帳號 10 分鐘內錯 5 次，就先不收它的登入
_THROTTLE_LOCK = threading.Lock()  # 擋猜密碼的紀錄由好幾個 AccountStore 共用（伺服器每次請求都建一個新的）：檢查與記帳要一起做
_DUMMY_SALT = bytes(SALT_BYTES)  # 不存在的帳號也算一次雜湊，花的時間跟密碼錯一樣，分不出帳號在不在
_INVALID_LOGIN = "\0invalid"  # 格式不對的帳號共用的擋猜密碼紀錄（不可能跟真的帳號撞名）

LOGIN_FAILED = "帳號或密碼不對。"
LOGIN_TAKEN = "這個帳號已有人使用。"
NAME_TAKEN = "這個名號已有人使用。"
PASSWORDS_DIFFER = "兩次輸入的密碼不一樣。"
TOO_MANY_TRIES = "嘗試太多次，請 10 分鐘後再試。"
BAD_LOGIN = "帳號只能用英文字母、數字、底線，3～20 字。"
SHORT_PASSWORD = f"密碼至少 {PASSWORD_MIN} 字。"
LONG_PASSWORD = f"密碼最多 {PASSWORD_MAX} 字。"
WRONG_OLD_PASSWORD = "舊密碼不對。"
HAS_CHARACTER = "這個帳號已經有角色了。"
NO_PASSWORD = "這個帳號沒有密碼，請他用綁定的方式登入。"  # 待 joy 潤（管理者重設密碼碰到沒有密碼的帳號；帳號與客服第 201 批）

# identity（帳號與客服第 201 批；設計 4.1）：沒有 password 列的帳號鍵是 id:<accounts.id>（終身不變）。帳號格式不收冒號，兩種鍵不會撞
ID_KEY = re.compile(r"id:([1-9][0-9]*)")
# 補設密碼（帳號與客服第 204 批；設計 4.4「鍵不變」）：沒密碼的帳號補設密碼時，logins 多一列 provider='id'、subject='id:<n>'、display=''
# 當記號，有這一列的帳號鍵一律是 id:<n>（用帳號名登入、owner_of、login_key 都回它）；沒有記號照舊。記號列不算一種登入方式。
# SQL 片段裡 a 是 accounts 的別名。沒有記號列的庫（identity 關著不會有）每一支的結果跟第 203 批一樣。
MARKER = "id"
_MARKED = f"EXISTS (SELECT 1 FROM logins m WHERE m.account_id = a.id AND m.provider = '{MARKER}')"

class AccountError(ValueError):
    """玩家看得到的錯誤：訊息就是畫面上要顯示的字。"""


@dataclass
class Account:
    login: str  # 註冊時打的寫法（顯示用）；資料庫裡的鍵是小寫。沒有密碼的帳號是 id:<n>
    salt: str | None  # hex；沒有密碼的帳號是 None
    hash: str | None  # hex；沒有密碼的帳號是 None
    character: str | None = None  # 綁定的角色名號；還沒建角色時是 None
    created: float = 0.0
    key: str = ""  # 帳號鍵（sessions、owner_of 用的那個）：有密碼是小寫帳號，沒有是 id:<n>
    id: int | None = None  # accounts.id


def normalize(login: str | None) -> str:
    """帳號不分大小寫：資料庫裡的鍵一律用小寫。"""
    return (login or "").strip().lower()


def _key(login: str | None) -> str:
    """AccountStore 認的鍵：照 normalize；只有 id: 開頭的照原樣（ID:1 不是 id:1，查不到）。"""
    key = normalize(login)
    return (login or "").strip() if key.startswith("id:") else key


def check_login(login: str | None) -> str:
    login = (login or "").strip()
    if not LOGIN_PATTERN.fullmatch(login):
        raise AccountError(BAD_LOGIN)
    return login


def check_password(password: str | None) -> str:
    password = password or ""
    if len(password) < PASSWORD_MIN:
        raise AccountError(SHORT_PASSWORD)
    if len(password) > PASSWORD_MAX:
        raise AccountError(LONG_PASSWORD)
    return password


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=salt, **SCRYPT_PARAMS).hex()


def _new_secret(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(SALT_BYTES)
    return salt.hex(), hash_password(password, salt)


def _matches(account: Account, password: str) -> bool:
    if not account.salt or not account.hash:  # 沒有密碼的帳號：照樣花一次雜湊的時間，回假（不 500）
        hash_password(password, _DUMMY_SALT)
        return False
    actual = hash_password(password, bytes.fromhex(account.salt))
    return hmac.compare_digest(bytes.fromhex(account.hash), bytes.fromhex(actual))


class AccountStore:
    """帳號的讀寫。failures 是擋猜密碼的紀錄（小寫帳號 → 最近幾次登入失敗的時間），只放在記憶體、
    重開就歸零；伺服器每次建新的 AccountStore 時傳同一個 dict 進來，讓它們共用。"""

    def __init__(
        self, db: Database, clock: Callable[[], float] = time.time,
        failures: dict[str, list[float]] | None = None,
    ):
        self.db = db
        self.clock = clock
        self.failures = {} if failures is None else failures

    # ── 查詢 ──────────────────────────────────────

    def _get(self, conn, key: str) -> Account | None:
        found = ID_KEY.fullmatch(key)
        if found is not None:  # id:<n> 只認沒有 password 列的帳號（有密碼的帳號鍵是小寫帳號，終身不變），或補設過密碼的（有記號列，第 204 批）
            row = conn.execute(
                "SELECT a.id, a.character, a.created, p.display, p.salt, p.hash FROM accounts a "
                "LEFT JOIN logins p ON p.account_id = a.id AND p.provider = 'password' "
                f"WHERE a.id = ? AND (p.subject IS NULL OR {_MARKED})",
                (int(found.group(1)),),
            ).fetchone()
            if row is None:
                return None
            return Account(
                login=row["display"] or key, salt=row["salt"], hash=row["hash"], character=row["character"], created=row["created"],
                key=key, id=row["id"],
            )
        row = conn.execute(
            f"SELECT l.display, l.salt, l.hash, a.character, a.created, a.id, {_MARKED} AS marked FROM logins l "
            "JOIN accounts a ON a.id = l.account_id WHERE l.provider = 'password' AND l.subject = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return Account(
            login=row["display"], salt=row["salt"], hash=row["hash"], character=row["character"], created=row["created"],
            key=f"id:{row['id']}" if row["marked"] else key, id=row["id"],
        )

    def _owner(self, conn, name: str) -> str | None:
        row = conn.execute(
            f"SELECT a.id, l.subject, {_MARKED} AS marked FROM accounts a "
            "LEFT JOIN logins l ON l.account_id = a.id AND l.provider = 'password' WHERE a.character_key = ?",
            (name_key(name),),
        ).fetchone()
        if row is None:
            return None
        return row["subject"] if row["subject"] is not None and not row["marked"] else f"id:{row['id']}"

    def get(self, login: str | None) -> Account | None:
        with self.db.snapshot() as conn:
            return self._get(conn, _key(login))

    def account_id(self, login: str | None) -> int | None:
        """這個帳號鍵（小寫帳號或 id:<n>）的 accounts.id；沒有就是 None。帳號層的新資料認這個（設計 4.1）。"""
        account = self.get(login)
        return None if account is None else account.id

    def owner_of(self, name: str) -> str | None:
        """綁定這個名號的帳號鍵（有密碼是小寫帳號，沒有是 id:<n>）；名號比對不分大小寫。沒有就是 None。"""
        with self.db.snapshot() as conn:
            return self._owner(conn, name)

    def find(self, login_or_name: str | None) -> str | None:
        """管理者重設密碼用：先照帳號找，找不到再照名號找；都沒有就是 None。"""
        text = (login_or_name or "").strip()
        if not text:
            return None
        account = self.get(text)
        if account is not None:
            return account.key  # 沒有記號列時就是 _key(text)；補設過密碼的是 id:<n>（第 204 批）
        return self.owner_of(text)

    def search(self, text: str | None, limit: int = 10, keys: bool = False) -> list[dict]:
        """管理頁重設密碼的搜尋：帳號或名號含這幾個字的（不分大小寫），最多 limit 筆 {login, character}；空字串回空的。
        以 accounts 為主、一個帳號一列（多綁幾種登入方式也一列）；沒有密碼的帳號 login 寫 id:<n>（find 認得）。
        只有密碼帳號的庫，結果跟第 201 批以前的查詢逐位元組一樣（排序鍵就是小寫帳號）。
        keys（第 204 批，identity 包的管理頁路由用）：每列多帶 key（帳號鍵）與 id（accounts.id）；預設不帶，輸出不變。"""
        q = (text or "").strip().lower()
        if not q:
            return []
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT COALESCE(l.display, 'id:' || a.id) AS shown, a.character, a.id, "
                f"CASE WHEN l.subject IS NULL OR {_MARKED} THEN 'id:' || a.id ELSE l.subject END AS account_key FROM accounts a "
                "LEFT JOIN logins l ON l.account_id = a.id AND l.provider = 'password' "
                "WHERE (COALESCE(l.subject, 'id:' || a.id) LIKE ? ESCAPE '\\' OR lower(COALESCE(a.character, '')) LIKE ? ESCAPE '\\') "
                "ORDER BY COALESCE(l.subject, 'id:' || a.id) LIMIT ?",
                (like, like, limit),
            ).fetchall()
        if keys:
            return [{"key": r["account_key"], "id": r["id"], "login": r["shown"], "character": r["character"] or ""} for r in rows]
        return [{"login": r["shown"], "character": r["character"] or ""} for r in rows]

    # ── 註冊、登入、角色 ──────────────────────────

    def register(self, login: str | None, password: str | None) -> Account:
        shown = check_login(login)
        check_password(password)
        key = normalize(shown)
        salt, digest = _new_secret(password)  # scrypt 很慢，先算好再進交易
        created = self.clock()
        with self.db.transaction() as conn:
            if self._get(conn, key) is not None:
                raise AccountError(LOGIN_TAKEN)
            account_id = conn.execute("INSERT INTO accounts (created) VALUES (?)", (created,)).lastrowid
            conn.execute(
                "INSERT INTO logins (provider, subject, account_id, display, salt, hash) "
                "VALUES ('password', ?, ?, ?, ?, ?)",
                (key, account_id, shown, salt, digest),
            )
        return Account(login=shown, salt=salt, hash=digest, created=created, key=key, id=account_id)

    def create_without_password(self, provider: str, subject: str, display: str) -> str:
        """第三方或驗證碼開的帳號（設計 4.1、4.2）：同一筆交易建 accounts 與 logins 一列，回帳號鍵 id:<n>。
        這個身分已經有帳號、或 provider 是 password，丟 ValueError（不是玩家看的字：第 202 批起由包翻成話）。"""
        if provider == "password":
            raise ValueError("password 帳號走 register")
        created = self.clock()
        with self.db.transaction() as conn:
            if conn.execute("SELECT 1 FROM logins WHERE provider = ? AND subject = ?", (provider, subject)).fetchone():
                raise ValueError("這個身分已經有帳號")
            account_id = conn.execute("INSERT INTO accounts (created) VALUES (?)", (created,)).lastrowid
            conn.execute(
                "INSERT INTO logins (provider, subject, account_id, display) VALUES (?, ?, ?, ?)",
                (provider, subject, account_id, display),
            )
        return f"id:{account_id}"

    def login_key(self, provider: str, subject: str) -> str | None:
        """第三方或驗證碼的身分對到哪個帳號（第 202 批）：有 password 列的帳號回小寫帳號，沒有的回 id:<n>；查無或 provider 是 password 回 None。
        subject 原樣比對（分大小寫，不過 normalize）。"""
        if provider == "password":
            return None
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT l.account_id, p.subject AS pw, EXISTS (SELECT 1 FROM logins m WHERE m.account_id = l.account_id "
                f"AND m.provider = '{MARKER}') AS marked FROM logins l LEFT JOIN logins p ON p.account_id = l.account_id "
                "AND p.provider = 'password' WHERE l.provider = ? AND l.subject = ?",
                (provider, subject),
            ).fetchone()
        if row is None:
            return None
        return row["pw"] if row["pw"] is not None and not row["marked"] else f"id:{row['account_id']}"

    def add_login(self, login: str | None, provider: str, subject: str, display: str) -> None:
        """綁一種登入方式到這個帳號（帳號鍵不變）：一個帳號每種只留一列、別人占著的不行、password 不走這裡，都丟 ValueError；
        帳號不在丟 KeyError。"""
        if provider == "password":
            raise ValueError("密碼不走 add_login")
        if provider == MARKER:
            raise ValueError("記號列不走 add_login")
        with self.db.transaction() as conn:
            account = self._get(conn, _key(login))
            if account is None:
                raise KeyError(login)
            if conn.execute("SELECT 1 FROM logins WHERE provider = ? AND subject = ?", (provider, subject)).fetchone():
                raise ValueError("這個身分已經綁在別的帳號")
            if conn.execute("SELECT 1 FROM logins WHERE account_id = ? AND provider = ?", (account.id, provider)).fetchone():
                raise ValueError("這個帳號已經有這一種")
            conn.execute(
                "INSERT INTO logins (provider, subject, account_id, display) VALUES (?, ?, ?, ?)",
                (provider, subject, account.id, display),
            )

    def remove_login(self, login: str | None, provider: str) -> None:
        """拿掉這個帳號的一種登入方式：最後一種不准拿、沒有這一種、password（鍵終身不變，這一批不拿）都丟 ValueError；帳號不在丟 KeyError。"""
        if provider == "password":
            raise ValueError("密碼列不拿")
        with self.db.transaction() as conn:
            account = self._get(conn, _key(login))
            if account is None:
                raise KeyError(login)
            kinds = [r["provider"] for r in conn.execute("SELECT provider FROM logins WHERE account_id = ?", (account.id,))
                     if r["provider"] != MARKER]  # 補設密碼的記號列不算一種（第 204 批）
            if provider not in kinds:
                raise ValueError("這個帳號沒有這一種")
            if len(kinds) <= 1:
                raise ValueError("最後一種登入方式不能拿掉")
            conn.execute("DELETE FROM logins WHERE account_id = ? AND provider = ?", (account.id, provider))

    def authenticate(self, login: str | None, password: str | None) -> Account:
        """帳號不存在和密碼錯是同一句話、花一樣的時間；10 分鐘內錯 5 次就先不收（不存在的帳號也照算）。
        先記一次失敗再比對密碼，比對成功才清掉：同時送來的猜測不會全部擠過檢查。
        不可能是帳號的字串（格式不對）共用一格紀錄，紀錄的鍵多長不由對方決定；太長的密碼也不整串雜湊。"""
        key = normalize(login)
        bucket = key if LOGIN_PATTERN.fullmatch(key) else _INVALID_LOGIN
        now = self.clock()
        with _THROTTLE_LOCK:
            recent = [t for t in self.failures.get(bucket, []) if now - t < FAILURE_WINDOW]
            if len(recent) >= MAX_FAILURES:
                self.failures[bucket] = recent
                raise AccountError(TOO_MANY_TRIES)
            self.failures[bucket] = recent + [now]
        password = password or ""
        if len(password) > PASSWORD_MAX:  # 不會有帳號的密碼這麼長：照樣花一次雜湊的時間，但只雜湊前面一段
            hash_password(password[:PASSWORD_MAX], _DUMMY_SALT)
            raise AccountError(LOGIN_FAILED)
        account = self.get(key) if bucket == key else None
        if account is None:
            hash_password(password, _DUMMY_SALT)
            raise AccountError(LOGIN_FAILED)
        if not _matches(account, password):
            raise AccountError(LOGIN_FAILED)
        with _THROTTLE_LOCK:
            self.failures.pop(bucket, None)
        return account

    def bind_character(self, login: str, name: str) -> None:
        key = _key(login)
        with self.db.transaction() as conn:
            account = self._get(conn, key)
            if account is None:
                raise KeyError(login)
            if self._owner(conn, name) not in (None, key):
                raise AccountError(NAME_TAKEN)
            if account.character not in (None, name):
                raise AccountError(HAS_CHARACTER)
            conn.execute(
                "UPDATE accounts SET character = ?, character_key = ? WHERE id = ?", (name, name_key(name), account.id),
            )

    # ── 密碼 ──────────────────────────────────────

    def _replace_secret(self, key: str, new: str, keep: str | None = None) -> None:
        """換密碼，同一筆交易裡把這個帳號的登入狀態（sessions）都清掉：別的裝置要用新密碼重登（PM 2026-10-31）。
        keep 是自己改密碼時正在用的那個 cookie，留著，不把改密碼的人自己踢出去。"""
        salt, digest = _new_secret(new)
        with self.db.transaction() as conn:
            # 第 204 批：照 account_id 改 password 列（補設過密碼的帳號鍵是 id:<n>，不等於 password 列的 subject）；
            # 登入狀態兩種鍵都清（管理者照帳號名找到的與 session 用的可能是同一個帳號的兩種寫法）。沒有記號列時跟以前同一個結果。
            account = self._get(conn, key)
            account_id = account.id if account is not None else -1
            conn.execute(
                "UPDATE logins SET salt = ?, hash = ? WHERE provider = 'password' AND account_id = ?", (salt, digest, account_id),
            )
            row = conn.execute("SELECT subject FROM logins WHERE provider = 'password' AND account_id = ?", (account_id,)).fetchone()
            conn.execute(
                "DELETE FROM sessions WHERE account IN (?, ?, ?) AND token_hash != ?",
                (key, account.key if account is not None else key, row["subject"] if row is not None else key,
                 _token_hash(keep) if keep else ""),
            )

    def change_password(self, login: str | None, old: str | None, new: str | None, keep: str | None = None) -> None:
        """自己改密碼：舊密碼要對；其他裝置的登入狀態清掉，keep（這個裝置的 cookie）留著。"""
        key = _key(login)
        account = self.get(key)
        if account is None or not _matches(account, old or ""):
            raise AccountError(WRONG_OLD_PASSWORD)
        check_password(new)
        self._replace_secret(key, new, keep)

    def set_password(self, login: str | None, new: str | None) -> None:
        """管理者重設、scripts/set_password.py 用：不必知道舊密碼；順便解除擋猜密碼，這個帳號所有裝置都登出。

        擋猜密碼的紀錄只在同一個程式的記憶體裡：從 scripts/set_password.py 重設，不會解除正在跑的伺服器裡的鎖定（最多再等 10 分鐘）；在遊戲裡由管理者重設才會。"""
        key = _key(login)
        account = self.get(key)
        if account is None:
            raise KeyError(login)
        if account.hash is None:  # 沒有密碼的帳號：不補設（第 204 批才有補設密碼），sessions 不清
            raise AccountError(NO_PASSWORD)
        check_password(new)
        self._replace_secret(key, new)
        with _THROTTLE_LOCK:
            self.failures.pop(key, None)

    # ── 補設密碼、忘記密碼、刪帳號（帳號與客服第 204 批；設計 4.4、6.4）──

    def add_password(self, key: str | None, login: str | None, password: str | None) -> str:
        """沒密碼的帳號補設密碼：帳號名過 check_login、別人用了丟 LOGIN_TAKEN；同一筆交易寫 password 列與記號列，鍵不變（回 id:<n>）。
        已經有密碼丟 ValueError（包先擋好，這裡不是玩家看的字）；帳號不在丟 KeyError。scrypt 在交易外算。"""
        shown = check_login(login)
        check_password(password)
        lower = normalize(shown)
        salt, digest = _new_secret(password)
        with self.db.transaction() as conn:
            account = self._get(conn, _key(key))
            if account is None:
                raise KeyError(key)
            if account.hash is not None or account.salt is not None:
                raise ValueError("這個帳號已經有密碼")
            if self._get(conn, lower) is not None:
                raise AccountError(LOGIN_TAKEN)
            conn.execute(
                "INSERT INTO logins (provider, subject, account_id, display, salt, hash) VALUES ('password', ?, ?, ?, ?, ?)",
                (lower, account.id, shown, salt, digest),
            )
            conn.execute(
                "INSERT INTO logins (provider, subject, account_id, display) VALUES (?, ?, ?, '')",
                (MARKER, f"id:{account.id}", account.id),
            )
        return f"id:{account.id}"

    def reset_password(self, key: str | None, new: str | None, keep: str | None = None) -> None:
        """忘記密碼（用綁定的方式登入後設新密碼）：不必知道舊密碼；其他裝置登出，keep（這個裝置的 cookie）留著；解除擋猜密碼。
        沒有密碼丟 AccountError(NO_PASSWORD)；帳號不在丟 KeyError。"""
        account = self.get(key)
        if account is None:
            raise KeyError(key)
        if account.hash is None:
            raise AccountError(NO_PASSWORD)
        check_password(new)
        self._replace_secret(account.key, new, keep)
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT subject FROM logins WHERE provider = 'password' AND account_id = ?", (account.id,)).fetchone()
        with _THROTTLE_LOCK:
            self.failures.pop(row["subject"] if row is not None else account.key, None)

    def logins_of(self, key: str | None) -> list[dict]:
        """這個帳號的每一列登入方式 {provider, subject, display}（記號列也在，呼叫端自己濾）；帳號不在回空的。"""
        with self.db.snapshot() as conn:
            account = self._get(conn, _key(key))
            if account is None:
                return []
            rows = conn.execute("SELECT provider, subject, display FROM logins WHERE account_id = ?", (account.id,)).fetchall()
        return [{"provider": r["provider"], "subject": r["subject"], "display": r["display"]} for r in rows]

    def delete_account(self, key: str | None) -> list[dict]:
        """管理者刪帳號（設計 6.4）：同一筆交易刪 logins、sessions、accounts 列；角色名號由存檔占住、錢包不動。回刪掉的登入列（包記解綁的雜湊）。
        帳號不在丟 KeyError。"""
        with self.db.transaction() as conn:
            account = self._get(conn, _key(key))
            if account is None:
                raise KeyError(key)
            rows = conn.execute("SELECT provider, subject, display FROM logins WHERE account_id = ?", (account.id,)).fetchall()
            gone = [{"provider": r["provider"], "subject": r["subject"], "display": r["display"]} for r in rows]
            keys = {account.key, _key(key)} | {r["subject"] for r in rows if r["provider"] == "password"}
            conn.executemany("DELETE FROM sessions WHERE account = ?", [(k,) for k in sorted(keys)])
            conn.execute("DELETE FROM logins WHERE account_id = ?", (account.id,))
            conn.execute("DELETE FROM accounts WHERE id = ?", (account.id,))
        return gone


# ── 登入狀態（審查 S-10）────────────────────────

SESSION_SECONDS = 30 * 86400  # 登入狀態認多久：跟 cookie 的 max_age 一樣（server._start_session）


def _token_hash(token: str) -> str:
    """cookie 的 SHA-256：token 是 32 位元組的亂數（secrets.token_urlsafe），不必加鹽或慢雜湊。"""
    return hashlib.sha256(token.encode("utf-8", "surrogatepass")).hexdigest()


class SessionStore:
    """登入狀態（cookie → 帳號）存在資料庫的 sessions 表（第 8 版），重開伺服器照樣認得；只存 cookie 的雜湊。
    過了 SESSION_SECONDS 就不認、順手刪掉。時鐘是注入的（引擎不讀時鐘；這裡跟 AccountStore 一樣由伺服器給）。"""

    def __init__(self, db: Database, clock: Callable[[], float] = time.time):
        self.db = db
        self.clock = clock

    def create(self, account_key: str) -> str:
        """開一個新的登入狀態，回傳要放進 cookie 的 token（只有這裡看得到原文）。順手清掉過期的。"""
        token = secrets.token_urlsafe(32)
        now = self.clock()
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM sessions WHERE created <= ?", (now - SESSION_SECONDS,))
            conn.execute(
                "INSERT INTO sessions (token_hash, account, created) VALUES (?, ?, ?)", (_token_hash(token), account_key, now),
            )
        return token

    def get(self, token: str | None) -> str | None:
        """這個 cookie 登入的帳號（normalize 過的）；沒有、或過期了是 None。"""
        if not token:
            return None
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT account, created FROM sessions WHERE token_hash = ?", (_token_hash(token),)).fetchone()
        if row is None or self.clock() - row["created"] >= SESSION_SECONDS:
            return None
        return row["account"]

    def created_at(self, token: str | None) -> float | None:
        """這個 cookie 的登入狀態是什麼時候開的（客服權限的 6 小時；帳號與客服第 204 批）；沒有、或過期了是 None。"""
        if not token:
            return None
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT created FROM sessions WHERE token_hash = ?", (_token_hash(token),)).fetchone()
        if row is None or self.clock() - row["created"] >= SESSION_SECONDS:
            return None
        return row["created"]

    def pop(self, token: str | None, default: str | None = None) -> str | None:
        """登出：刪掉這個登入狀態，回傳原本的帳號（沒有就是 default）。"""
        if not token:
            return default
        with self.db.transaction() as conn:
            row = conn.execute("SELECT account FROM sessions WHERE token_hash = ?", (_token_hash(token),)).fetchone()
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
        return default if row is None else row["account"]

    def clear(self) -> None:
        """全部登出（測試每次從空的開始；主機要全服強制登出也可以叫）。"""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM sessions")
