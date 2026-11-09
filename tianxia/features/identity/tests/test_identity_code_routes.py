"""驗證碼的兩條路由（POST /api/identity/code/send、/api/identity/code/verify；帳號與客服第 203 批，設計 4.2、4.6）：
關著 404、對外同一句、碼綁 cookie、有帳號直接登入並記登入方式、查無帳號只寫待處理不開帳號、看不出誰是假人。寄送與 Turnstile 一律假的。"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

import pytest
from fastapi.testclient import TestClient
from test_identity_server import _turn_on, fresh_server, key_file  # noqa: F401  同一份伺服器 fixture
from test_server_bots import leaks

import server
from tianxia import accounts, database
from tianxia.accounts import AccountStore
from tianxia.core import identity_base
from tianxia.features.identity import codes, senders
from tianxia.features.identity import store as idstore

SEND = "/api/identity/code/send"
VERIFY = "/api/identity/code/verify"
KEY = b"k" * 32  # key_file 寫的那一把


@pytest.fixture
def on(monkeypatch, key_file, tmp_path):  # noqa: F811
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "g.db"))
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "g.db")
    _turn_on(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config.identity, "fake_services", True)
    for box in (senders.FAKES.sms.outbox, senders.FAKES.mail.outbox, senders.FAKES.mail.subjects):
        box.clear()
    senders.FAKES.sms.fail = senders.FAKES.mail.fail = False
    return tmp_path


def _send(c, to="0912345678", channel="phone", token="ok", ip=None):
    headers = {"cf-connecting-ip": ip} if ip else {}
    return c.post(SEND, json={"channel": channel, "to": to, "turnstile": token}, headers=headers)


def _code(channel="phone") -> str:
    box = senders.FAKES.sms.outbox if channel == "phone" else senders.FAKES.mail.outbox
    return re.search(r"\d{6}", box[-1][1]).group(0)


def _subj(channel, value):
    return identity_base.subject_hmac(KEY, channel, value)


def _side(tmp_path):
    return idstore.side_path(tmp_path / "g.db")


def test_code_routes_404_while_closed(monkeypatch, key_file, tmp_path):  # noqa: F811
    c = TestClient(server.app)
    body = {"channel": "phone", "to": "0912345678", "turnstile": "ok"}
    assert c.post(SEND, json=body).status_code == 404 and c.post(VERIFY, json={"code": "1"}).status_code == 404  # 開關關著
    _turn_on(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config.identity, "fake_services", True)
    monkeypatch.setattr(identity_base, "KEY_FILE", tmp_path / "missing.json")
    assert c.post(SEND, json=body).status_code == 404 and c.post(VERIFY, json={"code": "1"}).status_code == 404  # 沒金鑰
    monkeypatch.setattr(identity_base, "KEY_FILE", key_file)
    monkeypatch.setattr(server.CONTENT.config.identity, "ways", ["line", "google", "email"])
    assert c.post(SEND, json=body).status_code == 404  # phone 不在 ways
    assert c.post(SEND, json={**body, "channel": "fax"}).status_code == 404
    monkeypatch.setattr(server.CONTENT.config.identity, "ways", ["line"])
    assert c.post(SEND, json={**body, "channel": "email", "to": "a@b.co"}).status_code == 404
    assert c.post(VERIFY, json={"code": "1"}).status_code == 404  # email、phone 都不在


def test_verify_404_when_the_channel_was_taken_out_of_ways(on, monkeypatch):
    c = TestClient(server.app)
    assert _send(c).status_code == 200
    monkeypatch.setattr(server.CONTENT.config.identity, "ways", ["email"])
    assert c.post(VERIFY, json={"code": _code()}).status_code == 404


def test_send_reply_identical_bound_unbound_and_capped(on):
    AccountStore(database.open_database()).create_without_password("phone", _subj("phone", "+886922222222"), "09*****222")
    c = TestClient(server.app)
    unbound = _send(c, ip="198.51.100.1")
    bound = _send(c, to="0922222222", ip="198.51.100.2")
    capped = _send(c, ip="198.51.100.3")  # 同號 60 秒內
    assert unbound.status_code == bound.status_code == capped.status_code == 200
    assert unbound.content == bound.content == capped.content
    assert unbound.json() == {"message": codes.SENT, "notice": codes.NOTICE, "privacy": "/privacy"}
    assert len(senders.FAKES.sms.outbox) == 2
    assert "tx_code=" in unbound.headers.get("set-cookie", "") and "httponly" in unbound.headers["set-cookie"].lower()
    assert "set-cookie" not in capped.headers  # 滿了不開新單，舊的 cookie 照舊能用


def test_send_errors_say_their_own_line(on, monkeypatch):
    c = TestClient(server.app)
    assert _send(c, to="+14155550100").json() == {"error": codes.BAD_PHONE}
    assert _send(c, to="nope", channel="email").json() == {"error": codes.BAD_EMAIL}
    monkeypatch.setattr(senders.FAKES.turnstile, "fail", True)
    assert _send(c).json() == {"error": codes.NEED_HUMAN}
    monkeypatch.setattr(senders.FAKES.turnstile, "fail", False)
    senders.FAKES.sms.fail = True
    r = _send(c)
    assert (r.status_code, r.json()) == (400, {"error": codes.CANNOT_SEND})
    assert senders.FAKES.sms.outbox == []


def test_fake_turnstile_passes_without_a_site_key(on):
    """假的就是假的（L 波 PM 定）：沒設網站金鑰時表單送空字串，fake_services 開著照樣寄得出去。"""
    c = TestClient(server.app)
    assert _send(c, token="").status_code == 200
    assert len(senders.FAKES.sms.outbox) == 1


def test_challenge_bound_to_cookie(on):
    mine, other = TestClient(server.app), TestClient(server.app)
    _send(mine)
    code = _code()
    assert other.post(VERIFY, json={"code": code}).json() == {"error": codes.BAD_CODE}  # 別的瀏覽器拿不到你的單
    other.cookies.set("tx_code", "forged")
    for _ in range(6):
        assert other.post(VERIFY, json={"code": "000000"}).json() == {"error": codes.BAD_CODE}  # 別人猜錯不影響你的單
    assert mine.post(VERIFY, json={"code": code}).json()["stage"] == "create"


def test_verify_logs_in_bound_account(on, monkeypatch):
    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    db = database.open_database()
    store = AccountStore(db)
    store.register("shen_01", "secret-pw-12")
    store.add_login("shen_01", "phone", _subj("phone", "+886912345678"), "09*****678")
    c = TestClient(server.app)
    _send(c)
    r = c.post(VERIFY, json={"code": _code()})
    assert r.status_code == 200 and r.json() == {"stage": "create"}  # 還沒角色：照 _entry
    assert identity_base.account_key_for(db, "phone", _subj("phone", "+886912345678")) == "shen_01"
    token = c.cookies.get(server.COOKIE)
    assert token and server.SESSIONS.get(token) == "shen_01"
    side = idstore.IdentityStore(_side(on))
    assert side.session_auth(accounts._token_hash(token))[0] == "phone"
    account_id = store.get("shen_01").id
    assert side.verified_at(account_id, "phone") is not None
    dev = c.cookies.get("tx_dev")
    assert dev and side.is_trusted(hashlib.sha256(dev.encode()).hexdigest(), _subj("phone", "+886912345678"))
    assert c.get("/api/me").json() == {"stage": "create", "identity": True}  # 第 202 批：開著 /api/me 帶旗標
    assert c.post(VERIFY, json={"code": _code()}).json() == {"error": codes.BAD_CODE}  # 同一碼不能用第二次


def test_verify_unknown_makes_pending_not_account(on):
    db = database.open_database()
    with db.snapshot() as conn:
        before = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    c = TestClient(server.app)
    _send(c, to="Ray.Lin@Gmail.com", channel="email")
    r = c.post(VERIFY, json={"code": _code("email")})
    assert r.json() == {"stage": "create", "pending": True}
    assert c.cookies.get("tx_pending") and c.cookies.get(server.COOKIE) is None
    with db.snapshot() as conn:
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == before
    with sqlite3.connect(_side(on)) as conn:
        rows = conn.execute("SELECT provider, subject, display FROM pending").fetchall()
    assert rows == [("email", _subj("email", "raylin@gmail.com"), "r*@gmail.com")]
    assert c.get("/api/me").json() == {"stage": "login", "identity": True}  # 沒開 session（第 202 批：開著帶旗標）


def test_code_pending_becomes_an_account_at_character(on):
    """合 K 波：驗證碼查無帳號留的 pending，走第 202 批的建角色那一條開帳號；logins 寫 email、雜湊、遮罩，下次驗碼直接登入。"""
    c = TestClient(server.app)
    _send(c, to="Ray.Lin@Gmail.com", channel="email")
    assert c.post(VERIFY, json={"code": _code("email")}).json() == {"stage": "create", "pending": True}
    r = c.post("/api/identity/character", json={"name": "林驗碼"})
    assert r.status_code == 200 and c.cookies.get(server.COOKIE)
    db = database.open_database()
    with db.snapshot() as conn:
        rows = conn.execute("SELECT provider, subject, display FROM logins WHERE provider = 'email'").fetchall()
    assert [tuple(row) for row in rows] == [("email", _subj("email", "raylin@gmail.com"), "r*@gmail.com")]
    with sqlite3.connect(_side(on)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending").fetchone()[0] == 0
    assert identity_base.account_key_for(db, "email", _subj("email", "raylin@gmail.com")) is not None  # 下次驗碼查得到


def test_bots_cannot_be_told_apart(on):
    """假人沒有帳號：拿假人的名號當 Email、門號都不認（同一句），跟真人沒帳號的回應一樣；回應裡掃不到假人字樣。"""
    c = TestClient(server.app)
    out = [_send(c, to="趙子龍", channel="email"), _send(c, to="趙子龍"), _send(c, to="bot@bot", channel="email")]
    assert [r.json() for r in out] == [{"error": codes.BAD_EMAIL}, {"error": codes.BAD_PHONE}, {"error": codes.BAD_EMAIL}]
    nobody = _send(c, to="0977777777", ip="198.51.100.9")
    assert nobody.json()["message"] == codes.SENT
    texts = [r.text for r in out + [nobody]] + [c.post(VERIFY, json={"code": "000000"}).text]
    texts += [v for v in vars(codes).values() if isinstance(v, str)]
    assert not [leaks(t) for t in texts if leaks(t)]


def test_texts_ride_on_the_send_reply(on):
    c = TestClient(server.app)
    reply = _send(c, to="a@b.co", channel="email").json()
    assert reply["notice"] == codes.NOTICE and reply["privacy"] == server.CONTENT.config.identity.privacy_url
    assert senders.FAKES.mail.subjects[-1] == codes.MAIL_SUBJECT and "客服不會跟你要驗證碼" in senders.FAKES.mail.outbox[-1][1]
    assert json.dumps(reply, ensure_ascii=False).count("隱私權") == 1
