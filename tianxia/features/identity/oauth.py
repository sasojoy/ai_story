"""LINE、Google 登入的規則（帳號與客服第 202 批；設計 4.2）：兩家的設定表、PKCE、授權網址、換 token、驗 id_token 的欄位。

- 只拿使用者編號（sub）：scope 只有 openid，不要 email 與個人資料。
- 回呼網址寫死設定值（Config.identity.redirect_base），不照請求的網域拼。
- 不驗 id_token 的簽章：id_token 是我們自己在伺服器上經 TLS 直接向對方的 token 端點拿的（OpenID Connect Core 1.0 3.1.3.7 第 6 項：
  這種情況可以用 TLS 驗發行者代替驗簽章），所以只驗 iss、aud、exp、nonce、sub。
- 時間一律由參數傳入（不讀時鐘）；HTTP 經模組層的 HTTP（測試換成假的），逾時 TIMEOUT 秒，出錯一律當沒換到。
- client_id、client_secret 在 .local/identity.json（identity_base.KEY_FILE；不進版控）：{"key": ..., "line": {"client_id", "client_secret"}, "google": {...}}。
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets as _rand
from urllib.parse import urlencode

import requests

from tianxia.core import identity_base

PROVIDERS = {
    "line": {
        "authorize": "https://access.line.me/oauth2/v2.1/authorize",
        "token": "https://api.line.me/oauth2/v2.1/token",
        "iss": ("https://access.line.me",),
    },
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "iss": ("https://accounts.google.com", "accounts.google.com"),
    },
}
DISPLAY = {"line": "LINE", "google": "Google"}  # logins.display；不是新字（品牌名）
SCOPE = "openid"
SUB_MAX = 255
TIMEOUT = 10
HTTP = requests.post


def secrets(provider: str) -> dict | None:
    """這一家的 client_id、client_secret（兩欄都要是不空的字串）；檔案讀不到、格式不對、少一欄都回 None。"""
    try:
        data = json.loads(identity_base.KEY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    got = data.get(provider) if isinstance(data, dict) else None
    if not isinstance(got, dict):
        return None
    cid, secret = got.get("client_id"), got.get("client_secret")
    if not isinstance(cid, str) or not isinstance(secret, str) or not cid or not secret:
        return None
    return {"client_id": cid, "client_secret": secret}


def ready(content, provider: str) -> bool:
    """這一家能不能按：認得、在 ways 裡、金鑰兩欄都有、redirect_base 不空。不看總開關（呼叫端先過 gate）。"""
    cfg = content.config.identity
    return provider in PROVIDERS and provider in cfg.ways and bool(cfg.redirect_base.strip()) and secrets(provider) is not None


def redirect_uri(content, provider: str) -> str:
    return content.config.identity.redirect_base.strip().rstrip("/") + f"/auth/{provider}/callback"


def new_ticket() -> dict:
    """一次性單上的三樣隨機值（secrets.token_urlsafe）。"""
    return {"state": _rand.token_urlsafe(32), "nonce": _rand.token_urlsafe(32), "verifier": _rand.token_urlsafe(48)}


def code_challenge(verifier: str) -> str:
    """PKCE S256：base64url(sha256(verifier))，不補等號。"""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def authorize_url(provider: str, client_id: str, redirect: str, state: str, nonce: str, verifier: str) -> str:
    query = {
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect, "scope": SCOPE,
        "state": state, "nonce": nonce, "code_challenge": code_challenge(verifier), "code_challenge_method": "S256",
    }
    return PROVIDERS[provider]["authorize"] + "?" + urlencode(query)


def exchange(provider: str, code: str, verifier: str, redirect: str, client_id: str, client_secret: str) -> str | None:
    """拿授權碼向對方換 id_token；連不上、逾時、不是 200、回的不是 JSON 或沒有 id_token 都回 None。"""
    data = {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
        "client_id": client_id, "client_secret": client_secret, "code_verifier": verifier,
    }
    try:
        resp = HTTP(PROVIDERS[provider]["token"], data=data, timeout=TIMEOUT)
        if resp.status_code != 200:
            return None
        token = resp.json().get("id_token")
    except Exception:  # noqa: BLE001  對方出什麼錯都只是「沒登入成功」
        return None
    return token if isinstance(token, str) and token else None


def claims(id_token: str | None) -> dict | None:
    """只解 id_token 的中段（base64url 的 JSON）；格式不對回 None。不驗簽章（見模組說明）。"""
    parts = (id_token or "").split(".")
    if len(parts) != 3:
        return None
    body = parts[1]
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def check(got: dict | None, provider: str, client_id: str, nonce: str, now: float) -> str | None:
    """iss 是這一家的、aud 是我們的 client_id（字串或含它的清單）、exp 還沒到、nonce 是單上的、sub 不空且不超過 255 字：回 sub；
    有一樣不對回 None。"""
    if not isinstance(got, dict) or provider not in PROVIDERS:
        return None
    if got.get("iss") not in PROVIDERS[provider]["iss"]:
        return None
    aud = got.get("aud")
    if not (aud == client_id or (isinstance(aud, list) and client_id in aud)):
        return None
    exp = got.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)) or exp <= now:
        return None
    if not nonce or got.get("nonce") != nonce:
        return None
    sub = got.get("sub")
    if not isinstance(sub, str) or not sub or len(sub) > SUB_MAX:
        return None
    return sub
