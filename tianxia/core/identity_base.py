"""帳號綁定「別人也要讀」的那一半（帳號與客服第 201 批；設計 docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md 4.1、4.5、第七節）：
Email、手機的正規化與遮罩、加金鑰的雜湊、讀金鑰、開關（on）、綁手機才能用的功能問這裡（phone_ok、phone_subject、被擋的那一句 PHONE_NEEDED；
第 205 批接上九個入口：截殺、掛通緝、玩家單的揭與交、贈物、切磋與論武的發起與答應、市集上架與買、商城買、封測發放）、名號擋不擋（blocked_name）。

純規則：不 import 功能包、不讀時鐘、不寫東西。只有 phone_ok、phone_subject 讀主資料庫的 accounts、logins 兩張表（經 ctx.world.db），
account_key_for（第 203 批）只讀 logins。
客服名單也在這（第 212 批從 support 包搬來：商城的易名帖要問「這個名號是不是客服」；support_staff_name 只讀 accounts、logins，
名單的 .local/support.txt 只讀不寫）。
金鑰在 .local/identity.json（不進版控）：讀不到、格式不對都當功能關著（on 回假）。
核心本體（tianxia/core/ 底下的檔），不進 MODULES。identity 包、server.py 的 name_taken、商城包的易名帖讀它。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import unicodedata
from pathlib import Path

from ..accounts import normalize
from ..characters import name_key
from .name_base import STAFF_NAMES

_REPO = Path(__file__).resolve().parent.parent.parent
KEY_FILE = _REPO / ".local" / "identity.json"  # {"key": "<至少 16 字>"}；不進版控
KEY_MIN = 16
ID_PREFIX = "id:"  # 沒有密碼的帳號的鍵（accounts.id）；名號不准以它開頭

_PHONE_JUNK = re.compile(r"[\s\-()]")
_TW_LOCAL = re.compile(r"09\d{8}")
_TW_INTL = re.compile(r"\+8869\d{8}")
_GMAIL = frozenset(("gmail.com", "googlemail.com"))


def normalize_phone(text: str | None) -> str | None:
    """台灣手機門號轉成 +8869XXXXXXXX（NFKC、去空白與連字號、括號）；不是台灣手機門號回 None。"""
    raw = _PHONE_JUNK.sub("", unicodedata.normalize("NFKC", text or ""))
    if _TW_LOCAL.fullmatch(raw):
        return "+886" + raw[1:]
    if _TW_INTL.fullmatch(raw):
        return raw
    return None


def normalize_email(text: str | None) -> str | None:
    """Email 小寫；Gmail 去掉點與 + 之後的部分，其他網域去掉 + 之後。不像 Email 回 None。"""
    raw = unicodedata.normalize("NFKC", text or "").strip().lower()
    if raw.count("@") != 1:
        return None
    local, domain = raw.split("@")
    local = local.split("+", 1)[0]
    if domain in _GMAIL:
        local = local.replace(".", "")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith(".") or re.search(r"\s", raw):
        return None
    return f"{local}@{domain}"


def mask_phone(phone: str) -> str:
    """正規化後的門號 → 09*****678（只留開頭兩碼與最後三碼）。"""
    local = "0" + phone[4:] if phone.startswith("+886") else phone
    return local[:2] + "*" * 5 + local[-3:]


def mask_email(email: str) -> str:
    """正規化後的 Email → r*@gmail.com（只留首字與網域；星號不照長度，看不出幾個字）。"""
    local, domain = email.split("@", 1)
    return f"{local[:1]}*@{domain}"


def read_key(path: Path | None = None) -> bytes | None:
    """金鑰；檔案不在、讀不了、不是 {"key": "<至少 16 字>"} 都回 None。"""
    try:
        data = json.loads(Path(path or KEY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    key = data.get("key") if isinstance(data, dict) else None
    if not isinstance(key, str) or len(key) < KEY_MIN:
        return None
    return key.encode("utf-8")


def subject_hmac(key: bytes, provider: str, value: str) -> str:
    """logins.subject 存的值（email、phone）：HMAC-SHA256(金鑰, provider|正規化後的值) 的 hex。"""
    return hmac.new(key, f"{provider}|{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def on(content) -> bool:
    """開關開著、金鑰讀得到，這一包才算開著。"""
    return bool(content.config.identity.enabled) and read_key() is not None


# 綁手機才能用的功能被擋時的回話與灰鈕的 note（同一句；四包共用，包之間不能互相 import，所以放核心；第 205 批）
PHONE_NEEDED = "要先在設定裡綁定手機，才能這麼做。"  # 待 joy 潤


def _account_phone(ctx, feature_key: str) -> tuple[bool, str | None]:
    """phone_ok 與 phone_subject 共用的判斷（設計 4.5 的順序）：(要不要問, 綁的那一列 phone 的 subject 或 None)。
    identity 關或 phone_gate 關 → 不問；鍵不在 phone_required → 不問；假人（state.player.bot 不是 None）→ 不問；
    其餘查這個名號的帳號：查不到、或帳號沒有 provider='phone' 的列 → (真, None)。只問動手的這一個人（ctx 自己）。"""
    cfg = ctx.content.config.identity
    if not cfg.enabled or not cfg.phone_gate or feature_key not in cfg.phone_required or not on(ctx.content):
        return False, None
    player = ctx.state.player
    if player.bot is not None:
        return False, None
    with ctx.world.db.snapshot() as conn:
        row = conn.execute("SELECT id FROM accounts WHERE character_key = ?", (name_key(player.name),)).fetchone()
        if row is None:
            return True, None
        phone = conn.execute(
            "SELECT subject FROM logins WHERE account_id = ? AND provider = 'phone'", (row["id"],),
        ).fetchone()
    return True, (phone["subject"] if phone is not None else None)


def phone_ok(ctx, feature_key: str) -> bool:
    """這個角色能不能用這個功能（設計 4.5；第 205 批接上九個入口）。identity 關、phone_gate 關、功能不在名單、假人都回真；
    不是假人又查不到帳號回假；其餘看這個帳號有沒有綁手機（logins 有沒有 provider='phone'）。"""
    asked, subject = _account_phone(ctx, feature_key)
    return not asked or subject is not None


def phone_subject(ctx, feature_key: str) -> str | None:
    """綁的那支手機的 logins.subject（加金鑰的雜湊 hex）：只有 phone_ok 走到「有 phone 列」才回，其餘（關著、不在名單、假人、沒綁）一律 None。
    封測發放記「同一支手機一輩子一次」用（第 205 批）。"""
    return _account_phone(ctx, feature_key)[1]


def account_key_for(db, provider: str, subject: str) -> str | None:
    """這個身分（logins 的 provider、subject）綁在哪個帳號：有 password 列回小寫帳號（鍵終身不變），沒有回 id:<n>；查無回 None。
    只讀（第 203 批驗證碼登入用；設計第七節「查 logins」）。"""
    with db.snapshot() as conn:
        row = conn.execute("SELECT account_id FROM logins WHERE provider = ? AND subject = ?", (provider, subject)).fetchone()
        if row is None:
            return None
        pw = conn.execute(
            "SELECT subject FROM logins WHERE account_id = ? AND provider = 'password'", (row["account_id"],),
        ).fetchone()
    return pw["subject"] if pw is not None else f"{ID_PREFIX}{row['account_id']}"


def blocked_name(name: str | None, content) -> bool:
    """開著時不准拿來當名號的：id: 開頭（跟帳號鍵撞）、客服與官方的字（name_base.STAFF_NAMES）。關著一律回假（行為不變）。"""
    if not on(content):
        return False
    text = (name or "").strip().casefold()
    return text.startswith(ID_PREFIX) or text in {n.casefold() for n in STAFF_NAMES}


# ── 客服名單（帳號與客服第 212 批從 features/support/staff.py 搬來：商城的易名帖也要問，包不能 import 別包）──
# 認帳號，不認名號（設計 6.2）。三個來源合起來：Config.support.staff、.local/support.txt（一行一個，# 開頭是註解；照檔的修改時間重讀）、
# 環境變數 TIANXIA_SUPPORT（逗號分開）。每一筆是 accounts.id 的數字，或登入名（accounts.normalize：不分大小寫）。
SUPPORT_ENV = "TIANXIA_SUPPORT"
SUPPORT_FILE = "support.txt"

_support_cache: dict = {"path": None, "mtime": None, "names": frozenset()}  # support/staff.py 的 _cache 是同一個 dict


def support_file() -> Path:
    from tianxia import content as content_module  # noqa: PLC0415  content 在 import 時讀設定檔：放函式裡免循環（測試換 LOCAL_DIR 當下看得到）

    return content_module.LOCAL_DIR / SUPPORT_FILE


def _support_file_names(path: Path) -> frozenset[str]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return frozenset()
    if _support_cache["path"] == path and _support_cache["mtime"] == mtime:
        return _support_cache["names"]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return frozenset()
    names = frozenset(normalize(line) for line in lines if line.strip() and not line.strip().startswith("#"))
    _support_cache.update(path=path, mtime=mtime, names=names)
    return names


def support_names(config) -> frozenset[str]:
    """名單上每一筆（小寫、去空白）。"""
    listed = {normalize(x) for x in config.support.staff}
    listed |= {normalize(x) for x in os.environ.get(SUPPORT_ENV, "").split(",")}
    listed |= _support_file_names(support_file())
    listed.discard("")
    return frozenset(listed)


def support_staff(config, account_id: int, login: str) -> bool:
    """這個帳號（accounts.id、密碼列的登入名，沒有是空字串）在不在名單上。名單上全是數字的一筆只當 id：
    登入名可以全是數字、註冊又是開放的，不然搶註冊登入名 777 就頂了 id 777 的客服（第 J 波審查）。"""
    listed = support_names(config)
    key = normalize(login) if login else ""
    return str(account_id) in listed or (bool(key) and not key.isdigit() and key in listed)


def support_staff_name(db, config, name: str | None) -> bool:
    """這個名號綁著的帳號是不是客服（商城的易名帖問：客服也不能改名，同管理者）。客服開關關著、名號沒綁帳號（假人、還沒綁的）都回假。
    只讀主資料庫的 accounts、logins。"""
    if not config.support.enabled or not name:
        return False
    with db.snapshot() as conn:
        row = conn.execute(
            "SELECT a.id, l.display FROM accounts a LEFT JOIN logins l ON l.account_id = a.id AND l.provider = 'password' "
            "WHERE a.character_key = ?", (name_key(name),),
        ).fetchone()
    return row is not None and support_staff(config, int(row["id"]), row["display"] or "")
