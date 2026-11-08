"""帳號綁定「別人也要讀」的那一半（帳號與客服第 201 批；設計 docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md 4.1、4.5、第七節）：
Email、手機的正規化與遮罩、加金鑰的雜湊、讀金鑰、開關（on）、綁手機才能用的功能問這裡（phone_ok）、名號擋不擋（blocked_name）。

純規則：不 import 功能包、不讀時鐘、不寫東西。只有 phone_ok 讀主資料庫的 accounts、logins 兩張表（經 ctx.world.db）。
金鑰在 .local/identity.json（不進版控）：讀不到、格式不對都當功能關著（on 回假）。
核心本體（tianxia/core/ 底下的檔），不進 MODULES。identity 包、server.py 的 name_taken、商城包的易名帖讀它。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from pathlib import Path

from ..characters import name_key
from .name_base import STAFF_NAMES

ROOT = Path(__file__).resolve().parent.parent.parent
KEY_FILE = ROOT / ".local" / "identity.json"  # {"key": "<至少 16 字>"}；不進版控
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


def phone_ok(ctx, feature_key: str) -> bool:
    """這個角色能不能用這個功能（設計 4.5；第 205 批才有人問）。關著、phone_gate 關、功能不在名單、假人、沒有帳號都回真
    （四者同值：看不出誰是假人）；否則看這個帳號有沒有綁手機。"""
    cfg = ctx.content.config.identity
    if not on(ctx.content) or not cfg.phone_gate or feature_key not in cfg.phone_required:
        return True
    player = ctx.state.player
    if player.bot is not None:
        return True
    with ctx.world.db.snapshot() as conn:
        row = conn.execute("SELECT id FROM accounts WHERE character_key = ?", (name_key(player.name),)).fetchone()
        if row is None:
            return True
        phone = conn.execute(
            "SELECT 1 FROM logins WHERE account_id = ? AND provider = 'phone'", (row["id"],),
        ).fetchone()
    return phone is not None


def blocked_name(name: str | None, content) -> bool:
    """開著時不准拿來當名號的：id: 開頭（跟帳號鍵撞）、客服與官方的字（name_base.STAFF_NAMES）。關著一律回假（行為不變）。"""
    if not on(content):
        return False
    text = (name or "").strip().casefold()
    return text.startswith(ID_PREFIX) or text in {n.casefold() for n in STAFF_NAMES}
