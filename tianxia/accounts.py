"""帳號與密碼（帳號密碼登入設計，docs/superpowers/specs/2026-10-03-帳號密碼登入-design.md）。

帳號和名號分開：一個帳號一個角色，名號在建立角色時才綁上去。密碼用 scrypt 加鹽雜湊，只存鹽和雜湊值。
這裡只管帳號檔（saves/accounts/accounts.json）的讀寫，不 import gradio；會改帳號檔的動作由呼叫端包在
WorldStateStore.action_lock() 裡（設計第六節）。之後接 LINE／Google 時，是在同一個帳號上多一種登入方式。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .fileio import retry_sharing

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


class AccountError(ValueError):
    """玩家看得到的錯誤：訊息就是畫面上要顯示的字。"""


@dataclass
class Account:
    login: str  # 註冊時打的寫法（顯示用）；檔案裡的鍵是小寫
    salt: str  # hex
    hash: str  # hex
    character: str | None = None  # 綁定的角色名號；還沒建角色時是 None
    created: float = 0.0


def normalize(login: str | None) -> str:
    """帳號不分大小寫：檔案裡的鍵一律用小寫。"""
    return (login or "").strip().lower()


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
    actual = hash_password(password, bytes.fromhex(account.salt))
    return hmac.compare_digest(bytes.fromhex(account.hash), bytes.fromhex(actual))


class AccountStore:
    """帳號檔的讀寫。failures 是擋猜密碼的紀錄（小寫帳號 → 最近幾次登入失敗的時間），只放在記憶體、
    重開就歸零；伺服器每次建新的 AccountStore 時傳同一個 dict 進來，讓它們共用。"""

    def __init__(
        self, path: Path, clock: Callable[[], float] = time.time,
        failures: dict[str, list[float]] | None = None,
    ):
        self.path = Path(path)
        self.clock = clock
        self.failures = {} if failures is None else failures

    # ── 檔案 ──────────────────────────────────────

    def _load(self) -> dict[str, Account]:
        """讀帳號檔；看不懂的檔案（版本不對、形狀不對）直接丟錯，不當成空的——不然下一次寫入會把它蓋掉。
        紀錄裡多出來、這一版不認得的欄位略過（例如之後才加的 LINE／Google 綁定）。"""
        if not self.path.exists():
            return {}
        raw = json.loads(retry_sharing(lambda: self.path.read_text(encoding="utf-8")))
        if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("accounts"), dict):
            raise ValueError(f"看不懂的帳號檔：{self.path}")
        known = {f.name for f in fields(Account)}
        return {
            key: Account(**{k: v for k, v in data.items() if k in known})
            for key, data in raw["accounts"].items()
        }

    def _save(self, accounts: dict[str, Account]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "accounts": {key: asdict(a) for key, a in accounts.items()}}
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        retry_sharing(lambda: tmp.replace(self.path))

    # ── 查詢 ──────────────────────────────────────

    def get(self, login: str | None) -> Account | None:
        return self._load().get(normalize(login))

    def owner_of(self, name: str) -> str | None:
        """綁定這個名號的帳號（小寫鍵）；名號比對不分大小寫。沒有就是 None。"""
        wanted = (name or "").strip().casefold()
        for key, account in self._load().items():
            if account.character is not None and account.character.casefold() == wanted:
                return key
        return None

    def find(self, login_or_name: str | None) -> str | None:
        """管理者重設密碼用：先照帳號找，找不到再照名號找；都沒有就是 None。"""
        text = (login_or_name or "").strip()
        if not text:
            return None
        if normalize(text) in self._load():
            return normalize(text)
        return self.owner_of(text)

    # ── 註冊、登入、角色 ──────────────────────────

    def register(self, login: str | None, password: str | None) -> Account:
        shown = check_login(login)
        check_password(password)
        accounts = self._load()
        key = normalize(shown)
        if key in accounts:
            raise AccountError(LOGIN_TAKEN)
        salt, digest = _new_secret(password)
        account = Account(login=shown, salt=salt, hash=digest, created=self.clock())
        accounts[key] = account
        self._save(accounts)
        return account

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
        account = self._load().get(key) if bucket == key else None
        if account is None:
            hash_password(password, _DUMMY_SALT)
            raise AccountError(LOGIN_FAILED)
        if not _matches(account, password):
            raise AccountError(LOGIN_FAILED)
        with _THROTTLE_LOCK:
            self.failures.pop(bucket, None)
        return account

    def bind_character(self, login: str, name: str) -> None:
        accounts = self._load()
        key = normalize(login)
        account = accounts.get(key)
        if account is None:
            raise KeyError(login)
        if self.owner_of(name) not in (None, key):
            raise AccountError(NAME_TAKEN)
        if account.character not in (None, name):
            raise AccountError(HAS_CHARACTER)
        account.character = name
        self._save(accounts)

    # ── 密碼 ──────────────────────────────────────

    def change_password(self, login: str | None, old: str | None, new: str | None) -> None:
        accounts = self._load()
        account = accounts.get(normalize(login))
        if account is None or not _matches(account, old or ""):
            raise AccountError(WRONG_OLD_PASSWORD)
        check_password(new)
        account.salt, account.hash = _new_secret(new)
        self._save(accounts)

    def set_password(self, login: str | None, new: str | None) -> None:
        """管理者重設、scripts/set_password.py 用：不必知道舊密碼；順便解除擋猜密碼。

        擋猜密碼的紀錄只在同一個程式的記憶體裡：從 scripts/set_password.py 重設，不會解除正在跑的伺服器裡的鎖定（最多再等 10 分鐘）；在遊戲裡由管理者重設才會。"""
        accounts = self._load()
        key = normalize(login)
        account = accounts.get(key)
        if account is None:
            raise KeyError(login)
        check_password(new)
        account.salt, account.hash = _new_secret(new)
        self._save(accounts)
        with _THROTTLE_LOCK:
            self.failures.pop(key, None)
