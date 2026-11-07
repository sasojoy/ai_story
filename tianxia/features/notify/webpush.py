"""網頁推送（Web Push，減法季批 9）的加密、簽名與訂閱小檔（手機通知包 tianxia/features/notify/；全部拆包第 53 批從 server_push.py 下半段搬來）。

只用標準庫與 cryptography，沒有 tianxia 的 import；舊名 server_push 檔尾把這裡的十四個名字原樣再匯出（server.py、測試、same_behavior 從 server_push. 讀）。
cryptography 沒裝時 AVAILABLE 是 False，整段關著。"""
from __future__ import annotations

import base64
import contextlib
import json
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

try:  # 網頁推送（Web Push）的加密與簽名；主機沒裝 cryptography 時那一段整段關著（AVAILABLE），SSE 照常
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


# ── 網頁推送（Web Push；減法季整合設計第十章「回來的理由」，批 9）──
# 上面的 SSE 只叫醒開著的分頁；這一段是分頁關了、手機鎖著也跳得出來的通知：瀏覽器向它的推送服務（Chrome 是 FCM、
# Safari 是 Apple、Firefox 是 Mozilla）訂一個位址，交給伺服器；伺服器用 VAPID 金鑰簽名、照 RFC 8291 加密，POST 到那個位址。
# 加密與簽名自己寫（只用 cryptography），不裝 pywebpush：它帶的 http-ece 在這裡建不起來。cryptography 沒裝就整段關著
# （AVAILABLE 是 False，設定頁不畫那一顆），伺服器照常跑。
# 訂閱記在資料庫旁邊另一個小檔（PushStore），不進遊戲的資料庫結構：丟了只是大家要再按一次「開啟通知」。
RECORD_SIZE = 4096
VAPID_SECONDS = 12 * 3600  # 簽名的有效時間（推送服務最多收 24 小時）
TTL_SECONDS = 24 * 3600  # 手機關機時推送服務替我們留多久
# 只送到這幾家推送服務（訂閱的位址是瀏覽器給的，但經過玩家的手：不認得的主機一律不收，伺服器不會被拿去打別的網址）
PUSH_HOSTS = (
    "fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com",
    "web.push.apple.com", "notify.windows.com", "push.apple.com",
)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def push_host_ok(endpoint: str) -> bool:
    """訂閱的位址是 https、主機是認得的推送服務（PUSH_HOSTS 本身或它底下的子網域）。"""
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _public_bytes(key) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def encrypt(payload: bytes, p256dh: str, auth: str, *, salt: bytes | None = None, server_key=None) -> bytes:
    """RFC 8291（aes128gcm）：用瀏覽器給的公鑰 p256dh 與 auth 加密，回傳整個請求本文（標頭 + 一筆密文）。
    salt 與 server_key（這一次的臨時金鑰）只給測試固定用；平常每一則都新產。"""
    ua_public = unb64url(p256dh)
    auth_secret = unb64url(auth)
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _public_bytes(server_key)
    shared = server_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public))
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    if len(payload) + 1 + 16 > RECORD_SIZE:
        raise ValueError("推送的內容太長")
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public + body


class Vapid:
    """伺服器的 VAPID 金鑰（P-256）：第一次用時產生、存成 PEM（主機的 .local/，不進版控）。public 是給瀏覽器訂閱用的那一串。"""

    def __init__(self, path: Path, subject: str):
        self.path = Path(path)
        self.subject = subject
        if self.path.exists():
            self.key = serialization.load_pem_private_key(self.path.read_bytes(), password=None)
        else:
            self.key = ec.generate_private_key(ec.SECP256R1())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(self.key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        self.public = b64url(_public_bytes(self.key))

    def header(self, endpoint: str, now: float) -> str:
        """Authorization 標頭（RFC 8292）：對推送服務的來源簽一張 ES256 的 JWT。now 是牆上的時鐘（epoch 秒）。"""
        parts = urlsplit(endpoint)
        claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(now) + VAPID_SECONDS, "sub": self.subject}
        head = b64url(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
        body = b64url(json.dumps(claims, separators=(",", ":")).encode())
        signing = f"{head}.{body}".encode("ascii")
        r, s = decode_dss_signature(self.key.sign(signing, ec.ECDSA(hashes.SHA256())))
        jwt = f"{head}.{body}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
        return f"vapid t={jwt}, k={self.public}"


class PushStore:
    """訂閱的小檔（sqlite）：一台裝置一列，認帳號（account，accounts 的鍵），不認名號——改了名號照樣送得到。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS subs (endpoint TEXT PRIMARY KEY, account TEXT NOT NULL, "
                "p256dh TEXT NOT NULL, auth TEXT NOT NULL, created REAL NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS prefs (account TEXT PRIMARY KEY, off TEXT NOT NULL)")  # 關掉的那幾種（JSON 陣列）

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, account: str, endpoint: str, p256dh: str, auth: str, now: float, cap: int) -> None:
        """記一台裝置（同一個位址換帳號就改記到新帳號）；這個帳號超過 cap 台時丟掉最舊的。"""
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO subs VALUES (?, ?, ?, ?, ?)", (endpoint, account, p256dh, auth, now))
            rows = conn.execute("SELECT endpoint FROM subs WHERE account = ? ORDER BY created DESC", (account,)).fetchall()
            for row in rows[cap:]:
                conn.execute("DELETE FROM subs WHERE endpoint = ?", (row["endpoint"],))

    def remove(self, endpoint: str, account: str | None = None) -> bool:
        with contextlib.closing(self._conn()) as conn, conn:
            if account is None:
                cur = conn.execute("DELETE FROM subs WHERE endpoint = ?", (endpoint,))
            else:
                cur = conn.execute("DELETE FROM subs WHERE endpoint = ? AND account = ?", (endpoint, account))
            return cur.rowcount > 0

    def has(self, account: str, endpoint: str) -> bool:
        with contextlib.closing(self._conn()) as conn:
            return conn.execute("SELECT 1 FROM subs WHERE endpoint = ? AND account = ?", (endpoint, account)).fetchone() is not None

    def accounts(self) -> list[str]:
        with contextlib.closing(self._conn()) as conn:
            return [r["account"] for r in conn.execute("SELECT DISTINCT account FROM subs ORDER BY account")]

    def kinds_off(self, account: str) -> set[str]:
        """這個帳號關掉的通知種類（notices.KINDS 的鍵；預設全開，沒有這一列就是空的）。"""
        with contextlib.closing(self._conn()) as conn:
            row = conn.execute("SELECT off FROM prefs WHERE account = ?", (account,)).fetchone()
        return set(json.loads(row["off"])) if row is not None else set()

    def set_kind(self, account: str, kind: str, on: bool) -> set[str]:
        """開或關一種；回關掉的那幾種。"""
        off = self.kinds_off(account)
        (off.discard if on else off.add)(kind)
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO prefs VALUES (?, ?)", (account, json.dumps(sorted(off))))
        return off

    def devices(self, account: str) -> list[dict]:
        with contextlib.closing(self._conn()) as conn:
            rows = conn.execute("SELECT endpoint, p256dh, auth FROM subs WHERE account = ? ORDER BY created", (account,))
            return [dict(r) for r in rows]


class WebPush:
    """送通知：每一台裝置一個 POST（requests；timeout 秒）。推送服務回 404、410 是那台裝置退訂了（換瀏覽器、清了資料），
    當場從 PushStore 刪掉。回傳送成的台數。post 可以換掉（測試）。"""

    def __init__(self, store: PushStore, vapid: Vapid, post=None, timeout: float = 10.0):
        self.store, self.vapid, self.timeout = store, vapid, timeout
        if post is None:
            import requests  # noqa: PLC0415  只有真的送的時候才要
            post = requests.post
        self.post = post

    def send(self, account: str, title: str, body: str, *, tag: str = "", url: str = "/", now: float | None = None,
             endpoint: str | None = None) -> int:
        """送給這個帳號的每一台裝置（endpoint 給了就只送那一台）；回送成的台數。"""
        return sum(self.deliver(d, title, body, tag=tag, url=url, now=now) is None
                   for d in self.store.devices(account) if endpoint is None or d["endpoint"] == endpoint)

    def deliver(self, d: dict, title: str, body: str, *, tag: str = "", url: str = "/", now: float | None = None) -> str | None:
        """送一台（d 是 PushStore.devices 的一列）；送成回 None，不成回原因（設定頁「傳一則測試通知」照實寫給玩家看）。"""
        now = time.time() if now is None else now
        payload = json.dumps({"title": title, "body": body, "tag": tag, "url": url}, ensure_ascii=False).encode("utf-8")
        try:
            data = encrypt(payload, d["p256dh"], d["auth"])
            resp = self.post(d["endpoint"], data=data, timeout=self.timeout, headers={
                "Authorization": self.vapid.header(d["endpoint"], now), "TTL": str(TTL_SECONDS),
                "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "Urgency": "normal",
            })
        except Exception as e:  # noqa: BLE001  一台送不到不影響其他台；訂閱給的鑰匙壞了也一樣
            return f"連不上推送服務（{type(e).__name__}）"
        if resp.status_code in (404, 410):
            self.store.remove(d["endpoint"])
            return f"這台裝置的訂閱已經失效（推送服務回 {resp.status_code}），請把手機通知關掉再勾一次"
        if not 200 <= resp.status_code < 300:
            return f"推送服務不收（回 {resp.status_code}）"
        return None
