"""手機通知（減法季整合設計第十章「回來的理由」，批 9）：Web Push 的加密與簽名（server_push）、五種事（tianxia/notices.py）、
09:00 來信（letters.mail_day、Game.morning_mail）、伺服器的訂閱 API 與看守（server.notice_round）。"""
from __future__ import annotations

import json
import os

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi.testclient import TestClient

import server
import server_push
from conftest import real_content
from tianxia import letters, notices
from tianxia.battle_instance import BattleInstance
from tianxia.characters import open_characters
from tianxia.state import GameState, JournalEntry, Letter, PlayerState, XingshiEssay
from tianxia.world_state import fresh_season

HOUR = 3600


# ── 加密與簽名 ──

def test_encryption_matches_the_rfc_8291_example():
    """RFC 8291 附錄 A 的例子：同一把臨時金鑰、同一個 salt，加密出來一個位元組都不差。"""
    key = ec.derive_private_key(int.from_bytes(server_push.unb64url("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
    body = server_push.encrypt(
        b"When I grow up, I want to be a watermelon",
        "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4", "BTBZMqHH6r4Tts7J_aSIgg",
        salt=server_push.unb64url("DGv6ra1nlYgDCS1FRnbzlw"), server_key=key,
    )
    assert server_push.b64url(body) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_"
        "yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


class Phone:
    """一台假的手機：自己的一把金鑰與 auth，收到的本文照 RFC 8291 解開。"""

    def __init__(self, endpoint="https://fcm.googleapis.com/fcm/send/abc"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.endpoint = endpoint
        self.p256dh = server_push.b64url(server_push._public_bytes(self.key))

    def subscription(self) -> dict:
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": server_push.b64url(self.auth)}}

    def open(self, body: bytes) -> dict:
        salt, idlen = body[:16], body[20]
        as_public = body[21:21 + idlen]
        shared = self.key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
        ua = server_push.unb64url(self.p256dh)
        ikm = HKDF(hashes.SHA256(), 32, self.auth, b"WebPush: info\x00" + ua + as_public).derive(shared)
        cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
        nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
        plain = AESGCM(cek).decrypt(nonce, body[21 + idlen:], None)
        assert plain.endswith(b"\x02")
        return json.loads(plain[:-1].decode("utf-8"))


def test_vapid_header_is_a_signed_jwt_for_the_push_service(tmp_path):
    vapid = server_push.Vapid(tmp_path / "v.pem", "https://tianxiadashi.com")
    again = server_push.Vapid(tmp_path / "v.pem", "https://tianxiadashi.com")
    assert again.public == vapid.public and len(server_push.unb64url(vapid.public)) == 65  # 存了檔，重開照舊那一把
    header = vapid.header("https://fcm.googleapis.com/fcm/send/abc", 1_000_000)
    t, k = header.removeprefix("vapid t=").split(", k=")
    assert k == vapid.public
    head, body, sig = t.split(".")
    claims = json.loads(server_push.unb64url(body))
    assert claims == {"aud": "https://fcm.googleapis.com", "exp": 1_000_000 + server_push.VAPID_SECONDS, "sub": "https://tianxiadashi.com"}
    raw = server_push.unb64url(sig)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    vapid.key.public_key().verify(der, f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))  # 簽錯會丟例外


def test_only_known_push_services_are_accepted():
    ok = server_push.push_host_ok
    assert ok("https://fcm.googleapis.com/fcm/send/x") and ok("https://web.push.apple.com/abc")
    assert ok("https://updates.push.services.mozilla.com/wpush/v2/x") and ok("https://wns2-db5p.notify.windows.com/w/?token=x")
    assert not ok("http://fcm.googleapis.com/x") and not ok("https://evil.example/fcm.googleapis.com")
    assert not ok("https://fcm.googleapis.com.evil.example/x") and not ok("https://127.0.0.1/x") and not ok("not a url")


class Post:
    def __init__(self, status=201):
        self.calls, self.status = [], status

    def __call__(self, url, data, timeout, headers):
        self.calls.append((url, data, headers))
        return type("R", (), {"status_code": self.status})()


def test_send_encrypts_for_each_device_and_drops_gone_ones(tmp_path):
    store = server_push.PushStore(tmp_path / "p.sqlite")
    phone, other = Phone(), Phone("https://web.push.apple.com/zzz")
    for p in (phone, other):
        s = p.subscription()
        store.add("acc", s["endpoint"], s["keys"]["p256dh"], s["keys"]["auth"], 1.0, 5)
    post = Post()
    push = server_push.WebPush(store, server_push.Vapid(tmp_path / "v.pem", "https://x.example"), post=post)
    assert push.send("acc", "天下大勢", "某某派人送來一封信。", tag="letter", now=100) == 2
    url, data, headers = post.calls[0]
    assert headers["Content-Encoding"] == "aes128gcm" and headers["Authorization"].startswith("vapid t=")
    assert phone.open(data) == {"title": "天下大勢", "body": "某某派人送來一封信。", "tag": "letter", "url": "/"}
    push.post = Post(410)
    assert push.send("acc", "天下大勢", "x", now=100) == 0
    assert store.devices("acc") == [] and store.accounts() == []  # 410：那台退訂了，當場刪掉


def test_store_keeps_at_most_cap_devices_per_account(tmp_path):
    store = server_push.PushStore(tmp_path / "p.sqlite")
    for i in range(4):
        store.add("acc", f"https://fcm.googleapis.com/{i}", "k", "a", float(i), 3)
    assert [d["endpoint"][-1] for d in store.devices("acc")] == ["1", "2", "3"]  # 最舊的丟掉
    assert not store.remove("https://fcm.googleapis.com/1", "別人")  # 別人的刪不掉
    assert store.remove("https://fcm.googleapis.com/1", "acc") and store.has("acc", "https://fcm.googleapis.com/2")


# ── 五種事 ──

@pytest.fixture
def c():
    return real_content()


def _state(c) -> GameState:
    return GameState(player=PlayerState(name="沈青衫", location=c.scenario.start_location, stats={}, stamina=0), world=fresh_season(c))


def test_the_five_kinds(c):
    s = _state(c)
    assert notices.current(s, c) == []
    s.player.letters += [Letter(id=1, kind="道賀", sender="qinjie", at=0, text="…"),
                         Letter(id=2, kind="條件", sender="qinjie", at=0, text="…", read=False),
                         Letter(id=3, kind="道賀", sender="qinjie", at=0, text="…", read=True)]
    s.journal.append(JournalEntry(time=5, title="遭某甲截殺", tag="敗退"))
    s.journal.append(JournalEntry(time=6, title="截殺・某乙"))  # 自己去截別人：不跳
    bid = next(iter(c.battles))
    battle = BattleInstance(battle_id=bid, muster_deadline_real=123.0)
    s.world.xingshi.append(XingshiEssay(key=1, time=0, n=4, essay="潁川一帶，沈青衫連日奔走。", line="是日：…"))
    got = {n.kind: n for n in notices.current(s, c, battle)}
    assert set(got) == {"letter", "raid", "rally", "xingshi"}
    assert got["letter"].text == "秦頡派人送來一封信。" and got["letter"].key == f"letter:{s.player.season_number}:1"
    assert got["raid"].text == "遭某甲截殺（敗退）。"
    assert got["rally"].text == f"{c.battles[bid].name}開始集結，速來參戰。"
    assert got["xingshi"].text == "〈天下形勢〉第 4 篇提到了你。"
    battle.phase = "active"
    s.world.xingshi.append(XingshiEssay(key=2, time=1, n=5, essay="別人的事。", line="是日：…"))  # 最新一篇沒寫到你
    assert {n.kind for n in notices.current(s, c, battle)} == {"letter", "raid"}


def test_duel_sources_hook(c, monkeypatch):
    """約戰是批 3b 的：它在 DUEL_SOURCES 登記一個來源，這裡就照收。"""
    s = _state(c)
    monkeypatch.setattr(notices, "DUEL_SOURCES", [lambda st, ct: [notices.Notice(key="duel:1", kind="duel", text="有人向你約戰。")]])
    assert [n.key for n in notices.current(s, c)] == ["duel:1"]


# ── 09:00 來信 ──

def _jianfa(c, s):
    c.config.jianfa.enabled = True
    s.world.jianfa_on = True


def test_mail_day_turns_at_nine_local(c):
    s = _state(c)
    offset = c.config.pill_day_utc_offset_hours
    nine = 20_000 * 86400 + (9 - offset) * HOUR  # 某一天當地 09:00 的 epoch 秒
    assert letters.mail_day(c, s.world, nine) is None  # 減法季沒開：照舊用遊戲日
    _jianfa(c, s)
    assert letters.mail_day(c, s.world, nine - 60) == letters.mail_day(c, s.world, nine) - 1
    assert letters.mail_day(c, s.world, nine + 23 * HOUR) == letters.mail_day(c, s.world, nine)
    c.config.jianfa.morning_mail = False
    assert letters.mail_day(c, s.world, nine) is None


def test_letters_wait_for_nine_oclock(c):
    from tianxia import figures

    s = _state(c)
    _jianfa(c, s)
    figures._ensure(s, c, "qinjie").prestige = 1  # 焦慮：寫信求援
    s.player.affinities["qinjie"] = 40
    nine = 20_000 * 86400 + (9 - c.config.pill_day_utc_offset_hours) * HOUR
    s.player.letter_day = letters.mail_day(c, s.world, nine - 60)  # 昨天的信已經收了
    assert letters.deliver(s, c, nine - 60) == [] and s.player.letters == []  # 08:59：還沒到
    assert letters.deliver(s, c, nine) and s.player.letters[-1].sender == "qinjie"  # 09:00 送到


# ── 伺服器 ──

@pytest.fixture
def push(tmp_path, monkeypatch):
    for store in (server.SESSIONS, server.GAMES, server.NOTICE_SENT, server.MAIL_DONE):
        store.clear()
    post = Post()
    web = server_push.WebPush(server_push.PushStore(tmp_path / "p.sqlite"), server_push.Vapid(tmp_path / "v.pem", "https://x.example"), post=post)
    monkeypatch.setattr(server, "WEB_PUSH", web)
    monkeypatch.setattr(server.threading, "Thread", _Inline)  # 「開了」那一則當場送，不開執行緒
    yield web, post
    for store in (server.SESSIONS, server.GAMES, server.NOTICE_SENT, server.MAIL_DONE):
        store.clear()


class _Inline:
    def __init__(self, target, args=(), kwargs=None, **_):
        self.run = lambda: target(*args, **(kwargs or {}))

    def start(self):
        self.run()


def _login(client, login="shen_01", name="沈青衫"):
    client.post("/api/register", json={"login": login, "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": name})
    return client.post("/api/do/skip_tutorial", json={}).json()


def test_push_api_is_404_when_off():
    client = TestClient(server.app)
    _login(client)
    assert server.WEB_PUSH is None
    assert client.get("/api/push").status_code == 404
    assert client.post("/api/push/subscribe", json={}).status_code == 404
    assert client.get("/api/main").json()["web_push"] is False


def test_subscribe_sends_a_welcome_and_then_only_new_things(push):
    web, post = push
    client = TestClient(server.app)
    _login(client)
    assert client.get("/api/main").json()["web_push"] is True
    assert client.get("/api/push").json()["key"] == web.vapid.public
    phone = Phone()
    assert client.post("/api/push/subscribe", json={"endpoint": "https://evil.example/x", "keys": phone.subscription()["keys"]}).status_code == 400
    assert client.post("/api/push/subscribe", json=phone.subscription()).json() == {"on": True}
    assert phone.open(post.calls[-1][1])["body"] == server.PUSH_WELCOME  # 開了當場跳一則：手機上看得到通不通
    post.calls.clear()
    later = lambda: server.time.time() + 3600  # noqa: E731  一小時沒碰遊戲（分頁關著）
    assert server.notice_round(later) == 0  # 開的那一刻身上已經有的事不跳
    characters = open_characters()
    state = characters.load("沈青衫")
    state.player.letters.append(Letter(id=99, kind="道賀", sender="qinjie", at=0, text="…"))
    characters.save(state)
    assert server.notice_round(later) == 1
    assert phone.open(post.calls[-1][1]) == {"title": "天下大勢", "body": "秦頡派人送來一封信。", "tag": "letter", "url": "/"}
    assert server.notice_round(later) == 0  # 同一件不跳第二次
    client.post("/api/push/unsubscribe", json={"endpoint": phone.endpoint})
    assert web.store.accounts() == []


def test_no_push_while_the_player_is_on_the_page(push):
    web, post = push
    client = TestClient(server.app)
    _login(client)
    phone = Phone()
    client.post("/api/push/subscribe", json={**phone.subscription(), "quiet": True})
    assert post.calls == []  # quiet：不送「開了」
    characters = open_characters()
    state = characters.load("沈青衫")
    state.player.letters.append(Letter(id=99, kind="道賀", sender="qinjie", at=0, text="…"))
    characters.save(state)
    client.get("/api/main")  # 正開著遊戲：畫面上就看得到那封信
    assert server.notice_round() == 0 and post.calls == []
    assert server.notice_round(lambda: server.time.time() + 3600) == 0  # 記成看過了，之後也不補跳


def test_morning_mail_is_delivered_by_the_watcher(push, monkeypatch):
    """09:00 一到，看守替開了通知的人送今天的信（不必等他上線），接著跳「某某派人送來一封信」。"""
    web, post = push
    content = server.CONTENT
    monkeypatch.setattr(content.config.jianfa, "enabled", True)
    client = TestClient(server.app)
    _login(client)
    phone = Phone()
    client.post("/api/push/subscribe", json={**phone.subscription(), "quiet": True})
    world = server.open_world()
    world.mutate(lambda st: setattr(st.season, "jianfa_on", True))
    characters = open_characters()
    state = characters.load("沈青衫")
    state.player.affinities["qinjie"] = 40
    state.player.cheers = ["qinjie|在潁川打退了黃巾"]  # 他欣賞你剛做的事：寫道賀
    characters.save(state)
    later = lambda: server.time.time() + 3600  # noqa: E731
    assert server.notice_round(later) == 1
    assert phone.open(post.calls[-1][1])["body"] == "秦頡派人送來一封信。"
    state = characters.load("沈青衫")
    assert state.player.letters[-1].kind == "道賀" and state.player.letter_day == letters.mail_day(content, world.get_season(), later())


def test_service_worker_and_manifest_are_served():
    client = TestClient(server.app)
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "showNotification" in sw.text and "javascript" in sw.headers["content-type"]
    assert client.get("/manifest.webmanifest").json()["start_url"] == "/"
    assert 'rel="manifest"' in client.get("/").text


def test_home_screen_icons_are_linked_and_really_that_size():
    """加入主畫面的圖示（Joy 2026-10-26）：iPhone 不吃 manifest 的 SVG，index.html 要 apple-touch-icon 的 PNG（180、滿版）與
    apple-mobile-web-app-title；manifest 的 icons 補 192／512 的 PNG 與一張 maskable；每一張都在 web/、尺寸跟寫的一樣、拿得到。"""
    import io
    import re

    from PIL import Image

    client = TestClient(server.app)
    page = client.get("/").text
    assert '<meta name="apple-mobile-web-app-title" content="天下大勢">' in page
    touch = re.search(r'<link rel="apple-touch-icon" href="(/static/icon-180\.png\?v=[^"]+)">', page)
    assert touch, page[:600]
    r = client.get(touch[1])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    im = Image.open(io.BytesIO(r.content))
    assert im.size == (180, 180) and im.getpixel((0, 0))[3] == 255  # 滿版：iOS 自己切圓角，透明的角會變黑
    icons = client.get("/manifest.webmanifest").json()["icons"]
    assert [(i["sizes"], i["purpose"]) for i in icons if i["type"] == "image/png"] == [("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")]
    for icon in icons:
        if icon["type"] != "image/png":
            continue
        r = client.get(icon["src"])
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        size = int(icon["sizes"].split("x")[0])
        im = Image.open(io.BytesIO(r.content))
        assert im.size == (size, size)
        assert (im.getpixel((0, 0))[3] == 255) == (icon["purpose"] == "maskable")  # maskable 滿版；any 的跟 icon.svg 一樣圓角
