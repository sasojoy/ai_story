"""綁定與解綁（帳號與客服第 204 批；設計 4.3）：近期驗證、bind 池與綁定那一份字、已綁其他帳號驗過碼才說、一種一列、
bound_at 與 verified_at、第三方的單綁帳號、解綁至少留一種（密碼算一種、不能解綁）、新綁 72 小時、30 天、雜湊永久留著、每次一則「帳號」紀錄。"""
from __future__ import annotations

from fastapi.testclient import TestClient
from test_identity_login import _callback, _fake_idp
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import (  # noqa: F401
    bind, clock, error, on, phone_account, register, send, side_rows, subj, token_of, verify,
)

import server
from tianxia import database
from tianxia.accounts import AccountStore
from tianxia.features.identity import binding, codes, senders
from tianxia.features.identity import store as idstore

PHONE = "0912345678"
PHONE_N = "+886912345678"
HOUR, DAY = 3600, 86400


def _pw(c, login="shen_01", name="沈青衫"):
    register(c, login, name=name)
    return AccountStore(database.open_database()).account_id(login)


def _kinds(key):
    return sorted(r["provider"] for r in AccountStore(database.open_database()).logins_of(key))


def _reauth(c, clock):
    clock.now += server.CONTENT.config.identity.recent_seconds + 1
    assert c.post("/api/identity/reauth", json={"password": "secret-pw"}).status_code == 200


def test_bind_phone_needs_recent_check(clock):
    c = TestClient(server.app)
    _pw(c)
    clock.now += server.CONTENT.config.identity.recent_seconds + 1
    assert error(send(c, purpose="bind")) == binding.NEED_RECENT
    assert senders.FAKES.sms.outbox == []
    anon = TestClient(server.app)
    assert send(anon, purpose="bind").status_code == 401  # 綁要登入


def test_bind_phone_uses_bind_pool_and_text(clock):
    c = TestClient(server.app)
    _pw(c)
    assert send(c, purpose="bind").status_code == 200
    assert "有人要把這支手機綁到遊戲帳號" in senders.FAKES.sms.outbox[-1][1]
    buckets = {r[0] for r in side_rows("SELECT bucket FROM counters")}
    assert "pool:phone:bind:hour" in buckets and not any(b.startswith("pool:phone:anon") for b in buckets)
    assert verify(c).json() == {"message": binding.BOUND}
    assert _kinds("shen_01") == ["password", "phone"]


def test_bind_taken_says_so_only_after_code(clock):
    other = TestClient(server.app)
    phone_account(other)
    c = TestClient(server.app)
    _pw(c, "li_02", "李白衣")
    clock.now += 61
    sent = send(c, purpose="bind")
    assert sent.status_code == 200 and sent.json()["message"] == codes.SENT  # 寄碼那一步跟沒綁的一樣
    assert error(verify(c)) == binding.BOUND_ELSEWHERE
    assert _kinds("li_02") == ["password"]


def test_bind_one_row_per_kind(clock):
    c = TestClient(server.app)
    _pw(c)
    assert bind(c).status_code == 200
    clock.now += 61
    assert error(send(c, to="0987654321", purpose="bind")) == binding.ALREADY_KIND
    assert _kinds("shen_01") == ["password", "phone"]


def test_bind_records_bound_and_verified_at(clock):
    c = TestClient(server.app)
    aid = _pw(c)
    bind(c)
    meta = idstore.IdentityStore().meta(aid)
    assert meta["phone"]["bound_at"] == meta["phone"]["verified_at"] == clock.now
    assert meta["phone"]["subject_hmac"] == subj("phone", PHONE_N)


def test_bind_oauth_ticket_tied_to_account(clock, monkeypatch):
    seen = _fake_idp(monkeypatch, sub="U-77")
    c = TestClient(server.app)
    aid = _pw(c)
    r = c.post("/api/identity/start", json={"provider": "line", "purpose": "bind"})
    assert r.status_code == 200
    rows = side_rows("SELECT purpose, account_id FROM oauth_tickets")
    assert rows == [("bind", aid)]
    from urllib.parse import parse_qs, urlsplit

    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["url"]).query).items()}
    seen["nonce"], seen["provider"] = q["nonce"], "line"
    other = TestClient(server.app)  # 別的瀏覽器拿這張單回來：不是開單的那個帳號
    _pw(other, "li_02", "李白衣")
    other.cookies.set("tx_oauth", c.cookies.get("tx_oauth"))
    assert other.get("/auth/line/callback", params={"state": q["state"], "code": "x"}, follow_redirects=False).headers["location"] == "/?auth=fail"
    r = c.post("/api/identity/start", json={"provider": "line", "purpose": "bind"})
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["url"]).query).items()}
    seen["nonce"] = q["nonce"]
    assert _callback(c, "line", state=q["state"], code="x").headers["location"] == "/?auth=bound"
    assert _kinds("shen_01") == ["line", "password"]
    assert idstore.IdentityStore().meta(aid)["line"]["bound_at"] == clock.now


def test_unbind_keeps_at_least_one(clock):
    c = TestClient(server.app)
    key = phone_account(c)
    assert error(c.post("/api/identity/unbind", json={"provider": "phone"})) == binding.KEEP_ONE
    assert _kinds(key) == ["phone"]


def test_unbind_password_refused(clock):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    assert error(c.post("/api/identity/unbind", json={"provider": "password"})) == binding.KEEP_PASSWORD
    assert error(c.post("/api/identity/unbind", json={"provider": "email"})) == binding.NO_SUCH_WAY
    assert c.post("/api/identity/unbind", json={"provider": "phone"}).json() == {"message": binding.UNBOUND}
    assert _kinds("shen_01") == ["password"]


def test_unbind_with_new_binding_refused_72h(clock):
    c = TestClient(server.app)
    key = phone_account(c)
    assert bind(c, "a@b.co", "email").status_code == 200  # 剛綁的 Email
    clock.now += server.CONTENT.config.identity.recent_seconds + 1
    assert send(c, "a@b.co", "email", purpose="reauth").status_code == 200 and verify(c, "email").status_code == 200  # 拿新綁的驗
    assert error(c.post("/api/identity/unbind", json={"provider": "phone"})) == binding.NEW_BINDING.format(hours=72)
    clock.now += 72 * HOUR
    assert send(c, "a@b.co", "email", purpose="reauth").status_code == 200 and verify(c, "email").status_code == 200
    assert c.post("/api/identity/unbind", json={"provider": "phone"}).status_code == 200
    assert _kinds(key) == ["email"]


def test_new_binding_and_rebind_wait_edges():
    """72 小時、30 天的邊界（L 波審查：改成 71 小時、29 天原本的測試照樣綠）：差一秒還算、滿了就不算。"""
    cfg = server.CONTENT.config.identity
    assert (cfg.new_binding_hours, cfg.rebind_days) == (72, 30)
    t0 = 1_800_000_000.0
    assert binding.is_new({"bound_at": t0}, t0 + 72 * HOUR - 1, cfg) and not binding.is_new({"bound_at": t0}, t0 + 72 * HOUR, cfg)
    assert binding.rebind_wait(t0, t0 + 30 * DAY - 1, cfg) and not binding.rebind_wait(t0, t0 + 30 * DAY, cfg)


def test_rebind_other_account_waits_30_days(clock):
    a = TestClient(server.app)
    _pw(a)
    bind(a)
    assert a.post("/api/identity/unbind", json={"provider": "phone"}).status_code == 200
    b = TestClient(server.app)
    _pw(b, "li_02", "李白衣")
    clock.now += 61
    assert error(bind(b)) == binding.REBIND_WAIT.format(days=30)
    clock.now += 30 * DAY
    _reauth(b, clock)
    assert bind(b).json() == {"message": binding.BOUND}


def test_rebind_same_account_ok(clock):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    assert c.post("/api/identity/unbind", json={"provider": "phone"}).status_code == 200
    clock.now += 61
    assert bind(c).json() == {"message": binding.BOUND}


def test_new_account_after_unbind_waits(clock):
    a = TestClient(server.app)
    _pw(a)
    bind(a)
    assert a.post("/api/identity/unbind", json={"provider": "phone"}).status_code == 200
    clock.now += 61
    anon = TestClient(server.app)
    assert send(anon).status_code == 200
    assert error(verify(anon)) == binding.REBIND_WAIT.format(days=30)
    assert side_rows("SELECT COUNT(*) FROM pending") == [(0,)]


def test_unbound_hash_kept_forever(clock):
    c = TestClient(server.app)
    aid = _pw(c)
    bind(c)
    c.post("/api/identity/unbind", json={"provider": "phone"})
    clock.now += 1000 * DAY
    _reauth(c, clock)
    bind(c, "0987654321")
    assert side_rows("SELECT subject_hmac, provider, account_id FROM unbound") == [(subj("phone", PHONE_N), "phone", aid)]


def test_every_change_writes_one_account_note(clock):
    c = TestClient(server.app)
    aid = _pw(c)
    bind(c)
    rows = side_rows("SELECT text, state FROM account_notes WHERE account_id = ?", (aid,))
    assert rows == [(binding.NOTE_BOUND.format(kind="手機"), idstore.NOTE_NEW)]
    assert c.get("/api/main").status_code == 200  # 寫進存檔、等下一輪確認
    assert side_rows("SELECT state FROM account_notes") == [(idstore.NOTE_PENDING,)]
    side_rows("UPDATE account_notes SET jtime = -1")  # 假裝上一輪沒存成：存檔裡找不到那一則
    assert c.get("/api/main").status_code == 200
    assert side_rows("SELECT state FROM account_notes") == [(idstore.NOTE_PENDING,)]  # 補寫一次
    assert c.get("/api/main").status_code == 200
    assert side_rows("SELECT state FROM account_notes") == [(idstore.NOTE_DONE,)]
    c.post("/api/identity/unbind", json={"provider": "phone"})
    assert [r[0] for r in side_rows("SELECT text FROM account_notes ORDER BY id")][-1] == binding.NOTE_UNBOUND.format(kind="手機")
