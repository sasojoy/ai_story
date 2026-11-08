"""補設密碼與忘記密碼（帳號與客服第 204 批；設計 4.4）：補設時取帳號名、鍵不變（id:<n> 照登，用帳號名登入也回 id:<n>）；
忘記密碼要用綁定的方式登入後 10 分鐘內（tx_reset）、其他裝置登出、新綁 72 小時內不行；/api/password 不動。"""
from __future__ import annotations

from fastapi.testclient import TestClient
from test_identity_bind import _pw
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import (  # noqa: F401
    bind, clock, error, on, phone_account, register, send, side_rows, subj, token_of, verify,
)

import server
from tianxia import accounts, database
from tianxia.accounts import AccountStore
from tianxia.features.identity import binding

HOUR = 3600


def _set(c, login="ray_77", new="new-secret", again=None):
    return c.post("/api/identity/password/set", json={"login": login, "new": new, "again": new if again is None else again})


def test_set_password_keeps_key(clock):
    c = TestClient(server.app)
    key = phone_account(c)
    token = token_of(c)
    assert _set(c, "Ray_77").json() == {"message": binding.PASSWORD_SET}
    store = AccountStore(database.open_database())
    assert server.SESSIONS.get(token) == key  # session 不換
    assert store.get(key).login == "Ray_77" and store.get("ray_77").key == key
    assert store.owner_of("沈青衫") == key and store.login_key("phone", subj("phone", "+886912345678")) == key
    assert store.find("ray_77") == key
    c.post("/api/logout")
    r = c.post("/api/login", json={"login": "RAY_77", "password": "new-secret"})
    assert r.status_code == 200 and r.json()["stage"] == "game"
    assert server.SESSIONS.get(token_of(c)) == key  # 密碼登入也回 id:<n>
    assert sorted(x["provider"] for x in store.logins_of(key)) == ["id", "password", "phone"]
    me = c.get("/api/identity/me").json()
    assert [k["provider"] for k in me["kinds"]] == ["password", "phone"] and me["has_password"] is True  # 記號列不算一種


def test_set_password_checks_login_and_taken(clock):
    TestClient(server.app).post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    c = TestClient(server.app)
    phone_account(c, name="李白衣")
    assert error(_set(c, "x")) == accounts.BAD_LOGIN
    assert error(_set(c, "SHEN_01")) == accounts.LOGIN_TAKEN
    assert error(_set(c, again="other-secret")) == accounts.PASSWORDS_DIFFER
    assert error(_set(c, new="123")) == accounts.SHORT_PASSWORD
    clock.now += server.CONTENT.config.identity.recent_seconds + 1
    assert error(_set(c)) == binding.NEED_RECENT


def test_set_password_refused_when_has_password(clock):
    c = TestClient(server.app)
    _pw(c)
    assert error(_set(c)) == binding.HAS_PASSWORD


def _phone_login(c):
    assert send(c, switch=True).status_code == 200  # 已登入的那一台：換帳號（同一個帳號也一樣先問）
    r = verify(c)
    assert r.status_code == 200 and r.json()["stage"] == "game", r.text
    return r


def test_reset_needs_cookie_within_10_minutes(clock):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    clock.now += 73 * HOUR
    d = TestClient(server.app)
    r = _phone_login(d)
    assert "tx_reset=" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    assert d.get("/api/identity/me").json()["reset"] == server.CONTENT.config.identity.reset_seconds
    clock.now += server.CONTENT.config.identity.reset_seconds + 1
    assert error(d.post("/api/identity/password/reset", json={"new": "brand-new", "again": "brand-new"})) == \
        binding.RESET_EXPIRED.format(minutes=10)
    nobody = TestClient(server.app)
    _pw(nobody, "li_02", "李白衣")
    assert error(nobody.post("/api/identity/password/reset", json={"new": "brand-new", "again": "brand-new"})) == \
        binding.RESET_EXPIRED.format(minutes=10)  # 沒有 tx_reset
    clock.now += 61
    _phone_login(d)
    assert d.post("/api/identity/password/reset", json={"new": "brand-new", "again": "brand-new"}).json() == \
        {"message": binding.PASSWORD_RESET}
    assert TestClient(server.app).post("/api/login", json={"login": "shen_01", "password": "brand-new"}).status_code == 200
    assert TestClient(server.app).post("/api/login", json={"login": "shen_01", "password": "secret-pw"}).status_code == 400
    texts = [r[0] for r in side_rows("SELECT text FROM account_notes ORDER BY id")]
    assert texts[-1] == binding.NOTE_PASSWORD_RESET.format(kind="手機")


def test_reset_logs_out_other_devices(clock):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    clock.now += 73 * HOUR
    d = TestClient(server.app)
    _phone_login(d)
    assert d.post("/api/identity/password/reset", json={"new": "brand-new", "again": "brand-new"}).status_code == 200
    assert c.get("/api/identity/me").status_code == 401  # 原本那一台登出
    assert d.get("/api/identity/me").status_code == 200  # 這一台留著


def test_reset_refused_for_new_binding(clock):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    clock.now += 61
    d = TestClient(server.app)
    _phone_login(d)
    assert error(d.post("/api/identity/password/reset", json={"new": "brand-new", "again": "brand-new"})) == \
        binding.NEW_BINDING.format(hours=72)


def test_api_password_unchanged(clock):
    c = TestClient(server.app)
    _pw(c)
    r = c.post("/api/password", json={"old": "secret-pw", "new": "other-pw", "again": "other-pw"})
    assert r.json() == {"message": "密碼已更新。"}
    assert TestClient(server.app).post("/api/login", json={"login": "shen_01", "password": "other-pw"}).status_code == 200


# ── M 波：名單上的帳號補設、忘記密碼也要 12 字（第 207 批的 check_password staff；routes 那兩條是第 208 批的範圍）──


def test_set_password_listed_needs_12(clock, monkeypatch):
    c = TestClient(server.app)
    phone_account(c)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
    assert error(_set(c, new="new-secret")) == accounts.STAFF_SHORT_PASSWORD
    assert _set(c, new="a-long-password").json() == {"message": binding.PASSWORD_SET}


def test_reset_listed_needs_12(clock, monkeypatch):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    clock.now += 73 * HOUR
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
    d = TestClient(server.app)
    _phone_login(d)
    assert error(d.post("/api/identity/password/reset", json={"new": "brand-new", "again": "brand-new"})) == \
        accounts.STAFF_SHORT_PASSWORD
    assert d.post("/api/identity/password/reset", json={"new": "a-long-password", "again": "a-long-password"}).json() == \
        {"message": binding.PASSWORD_RESET}
