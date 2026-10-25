"""伺服器主動通知（線上架構設計 5.3）：用 SSE（Server-Sent Events）告訴開著的分頁「有東西變了」，分頁再去抓 /api/main。

兩種通知：
- self：某個角色自己做完一個動作，他其他開著的分頁該刷新了；
- world：大家都看得到的世界變了（大事、江湖史、天下大事傳聞、決戰的階段與回合、大勢人物、已浮現的大勢線），每個分頁都刷新。
  由背景的看守（watch_world）每隔幾秒比一次「公開的世界指紋」，變了才發，而且兩次 world 之間至少隔 min_interval 秒。

另有一種不算通知的 ping：連線上沒事時每隔幾秒送一個，頁面靠它分辨「連線還活著」與「半開的死連線」（SSE 的註解行到不了
頁面的 JS，所以心跳要寫成事件）。

指紋只看大家本來就看得到的東西：鎖定、搶輸、豪強、伏筆、軍令、隱藏的大勢線、陣營軍情、地方傳聞與個人線索，還有
決戰裡誰加入了、這一回合出手了幾個，都不算——不然「什麼都沒變卻收到刷新」會洩漏誰在什麼時候做了看不見的事
（伏筆鎖定看不出來；決戰的人數是跟著假人的節奏變的，算了就等於把假人的作息廣播出去）。

放在專案根目錄、不在 tianxia/：要用執行緒、事件迴圈與時鐘。只送「哪一種變了」，不送內容，所以不會把誰的資料推給別人。

下半段是網頁推送（Web Push，減法季批 9）：分頁關著也跳得出來的手機通知；送的是一句話，只給那個人自己的裝置。"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable
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

SELF, WORLD, PING = "self", "world", "ping"


class PushHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def subscribe(self, name: str, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subs.setdefault(name, set()).add((loop, queue))

    def unsubscribe(self, name: str, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subs.get(name)
            if subs is not None:
                subs.discard((loop, queue))
                if not subs:
                    del self._subs[name]

    def notify(self, name: str, kind: str = SELF) -> int:
        """通知這個角色開著的每個分頁；回傳送了幾個。可以從任何執行緒呼叫。"""
        with self._lock:
            targets = list(self._subs.get(name, ()))
        return sum(_deliver(loop, queue, kind) for loop, queue in targets)

    def broadcast(self, kind: str = WORLD) -> int:
        with self._lock:
            targets = [t for subs in self._subs.values() for t in subs]
        return sum(_deliver(loop, queue, kind) for loop, queue in targets)

    def close(self) -> None:
        """叫每一條連線結束（測試與關伺服器用）：送 None，串流收到就停。"""
        with self._lock:
            targets = [t for subs in self._subs.values() for t in subs]
        for loop, queue in targets:
            _deliver(loop, queue, None)

    def count(self) -> int:
        with self._lock:
            return sum(len(subs) for subs in self._subs.values())


def _deliver(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, item) -> bool:
    try:
        loop.call_soon_threadsafe(queue.put_nowait, item)
        return True
    except RuntimeError:  # 那條連線的事件迴圈已經關了
        return False


def world_fingerprint(
    season_number: int, phase: str, season, battle, *, rumor_id: int | None = None, chronicle_count: int | None = None,
    paused: bool = False, progress: tuple[int, int] | None = None, seal: list | None = None,
    sieges: list | None = None,
) -> str:
    """大家都看得到的世界部分的指紋。時間本身不算（時鐘一直在走，靠慢速輪詢更新）。
    paused 是賽季時鐘有沒有暫停（SharedWorldState.paused_at 是不是 None）：暫停中每個人的選單都只剩一顆灰的，這是全服看得到的
    變化，要算；停了幾分鐘不算（畫面上的分鐘數每分鐘都在變，不能每分鐘叫醒一次全服）。
    決戰只看階段、第幾回合與戰局（每個人的畫面都不一樣的那幾樣），加上 progress：兩軍這一回合（已送出, 在場）的人數
    （battle_instance.round_progress，呼叫端照內容算好給；畫面寫「已送出 X／在場 Y」，試玩回饋 2026-10-08）。豪強也算在裡面
    （Joy 2026-10-13：以前兩軍的數字不算豪強，全員送出了還在等豪強，倒數一直跳）。
    rumor_id（最大的天下大事傳聞流水號）與 chronicle_count（江湖史則數）不給就從 season.rumors、season.chronicle 算；
    伺服器的看守給資料庫數好的（SqliteWorldStore.fingerprint_parts），不必把每一則讀回來。兩種給法算出同一個指紋。
    seal 是 SharedWorldState.seal_duels（奪璽單挑，玉璽碎片設計 5.10）；空的清單跟 None 算同一個指紋。
    sieges 是攻城戰（領地爭奪第二批）：[(那一場, 這一回合的（已送出, 在場）或 None)]，每一場算同決戰那幾樣；空的跟 None 同一個指紋。"""
    if rumor_id is None:
        rumor_id = max((r.id or 0 for r in season.rumors if r.layer == "world"), default=0)
    if chronicle_count is None:
        chronicle_count = len(season.chronicle)
    public = {
        "season": season_number,
        "phase": phase,
        "paused": paused,
        "trends": {k: v for k, v in sorted(season.trends.items()) if k in season.revealed},
        "ending": season.ending_title,
        "act": [season.storyline, season.act],
        "timeline": sorted(season.timeline),
        "opened": sorted(season.showdowns_opened),
        "figures": {k: v.model_dump() for k, v in sorted(season.figures.items())},
        "rumor": rumor_id,
        "chronicle": chronicle_count,
        # tales：等著補劇情的放手一搏有幾筆（Joy 2026-10-13：劇情回合結算後才寫好，補上的那一下場景的字變了，開著的分頁要更新）
        "battle": None if battle is None else [
            battle.battle_id, battle.phase, battle.round_number, battle.trend, progress, len(battle.tales),
        ],
        # 奪璽單挑（玉璽碎片設計 5.10）：全服觀戰。只算 id、階段、回合、氣勢與親自送出了幾手；last_seen 不算（每 15 秒就可能動一次）
        "seal": [[d.id, d.phase, d.round, round(d.edge, 1), sorted(d.pending)] for d in seal] if seal else None,
    }
    if sieges:  # 沒有攻城戰時不放這個鍵：關著的季指紋一個字都不變
        public["sieges"] = [[b.record_id, b.phase, b.round_number, b.trend, p, len(b.tales)] for b, p in sieges]
    blob = json.dumps(public, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def watch_world(
    hub: PushHub, fingerprint: Callable[[], str], stop: threading.Event, interval: float, min_interval: float,
    clock: Callable[[], float] = time.monotonic,
    on_error: Callable[[BaseException], None] | None = None, on_round: Callable[[], None] | None = None,
) -> None:
    """看守：每 interval 秒算一次指紋，跟上次發出去的不同、而且離上次 world 至少 min_interval 秒，就廣播 world。
    還沒到 min_interval 的變化不記下來，下一輪照樣看得出來、時間到了再發。算指紋出錯就跳過這一輪。
    出錯時這裡什麼都不印，只把例外交給 on_error：例外的訊息常夾著名號（含假人的），伺服器視窗不該看得出來，
    怎麼記由呼叫端決定（server.py 只寫例外的類別、同一個錯只數次數）。on_round 每一輪（成敗都算）叫一次，給呼叫端定時印累計用。
    兩個回呼自己出錯也吞掉：記錄不能讓看守停下來。clock 只用來算 min_interval，所以是 monotonic，不是世界的時間。"""
    sent = None
    last = float("-inf")
    while not stop.wait(interval):
        try:
            now_fp = fingerprint()
            if sent is None:
                sent = now_fp
            else:
                now = clock()
                if now_fp != sent and now - last >= min_interval:
                    hub.broadcast(WORLD)
                    sent, last = now_fp, now
        except Exception as e:  # noqa: BLE001  看守不能因為一次讀不到就停
            if on_error is not None:
                with contextlib.suppress(Exception):
                    on_error(e)
        if on_round is not None:
            with contextlib.suppress(Exception):
                on_round()


async def sse_stream(hub: PushHub, name: str, heartbeat: float = 15.0):
    """一條 SSE 連線：訂閱 name、把通知寫成 SSE 的格式；每 heartbeat 秒沒事就送一個 ping 事件，代理才不會當它斷了、
    頁面也才認得出死連線；收到 None（hub.close）就結束；不論怎麼結束（含分頁關掉、連線被切）都退訂。"""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    hub.subscribe(name, loop, queue)
    try:
        yield "retry: 5000\n\n"
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            except TimeoutError:
                yield f"event: {PING}\ndata: {{}}\n\n"
                continue
            if item is None:
                break
            yield f"event: {item}\ndata: {{}}\n\n"
    finally:
        hub.unsubscribe(name, loop, queue)


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

    def send(self, account: str, title: str, body: str, *, tag: str = "", url: str = "/", now: float | None = None) -> int:
        now = time.time() if now is None else now
        payload = json.dumps({"title": title, "body": body, "tag": tag, "url": url}, ensure_ascii=False).encode("utf-8")
        sent = 0
        for d in self.store.devices(account):
            try:
                data = encrypt(payload, d["p256dh"], d["auth"])
                resp = self.post(d["endpoint"], data=data, timeout=self.timeout, headers={
                    "Authorization": self.vapid.header(d["endpoint"], now), "TTL": str(TTL_SECONDS),
                    "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "Urgency": "normal",
                })
            except Exception:  # noqa: BLE001  一台送不到不影響其他台；訂閱給的鑰匙壞了也一樣
                continue
            if resp.status_code in (404, 410):
                self.store.remove(d["endpoint"])
            elif 200 <= resp.status_code < 300:
                sent += 1
        return sent
