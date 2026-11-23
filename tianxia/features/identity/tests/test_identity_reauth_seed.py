"""帳號綁定第 259 批：identity 打開之前就登入的 session（旁檔 session_auth 沒有那一列），重新驗證要真的記上。
密碼重驗沒有那一列時補一列（method=password），第三方與驗證碼的重驗補的是這次驗的那一種；本來就有那一列的照舊。"""
from __future__ import annotations

from fastapi.testclient import TestClient
from test_identity_server import fresh_server, key_file  # noqa: F401  fresh_server 是 autouse
from test_identity_session import (  # noqa: F401
    bind, clock, error, on, register, send, side_rows, token_of, verify,
)

import server
from tianxia import accounts
from tianxia.core import identity_base
from tianxia.features.identity import binding

BOSS = "段青山"
PW = "secret-pw-12"


def _off_then_on(monkeypatch, name="沈青衫", login="shen_01"):
    """identity 關著時註冊（密碼登入、旁檔沒有那一列），再打開；回同一台 client。"""
    monkeypatch.setattr(server.CONTENT.config.identity, "enabled", False)
    c = TestClient(server.app)
    register(c, login, PW, name=name)
    monkeypatch.setattr(server.CONTENT.config.identity, "enabled", True)
    assert identity_base.session_auth(token_of(c)) is None
    return c


def _reauth(c, password=PW):
    return c.post("/api/identity/reauth", json={"password": password})


# ── (a) 關著登入 → 打開 → 同一個 session 密碼重驗 → 綁得下去、解綁也走得下去 ──

def test_a_pre_identity_session_password_reauth_unlocks_binding(clock, monkeypatch):
    c = _off_then_on(monkeypatch)
    assert error(send(c, purpose="bind")) == binding.NEED_RECENT  # 照舊：沒重驗前被擋
    r = _reauth(c)
    assert r.status_code == 200 and "驗證好了" in r.json()["message"]
    auth = identity_base.session_auth(token_of(c))
    assert auth == {"method": "password", "at": clock.now, "verified": clock.now, "verified_by": "password"}
    assert bind(c).status_code == 200
    assert bind(c, "a1@example.com", "email").status_code == 200
    assert c.post("/api/identity/unbind", json={"provider": "phone"}).status_code == 200


# ── (b) 打錯密碼：不補列、照舊算一次猜錯 ──

def test_b_wrong_password_seeds_nothing_and_counts(clock, monkeypatch):
    c = _off_then_on(monkeypatch)
    for _ in range(accounts.MAX_FAILURES):
        assert error(_reauth(c, "wrong-pw")) == accounts.LOGIN_FAILED
        assert identity_base.session_auth(token_of(c)) is None
    assert error(_reauth(c)) == accounts.TOO_MANY_TRIES  # 同一套擋猜
    assert identity_base.session_auth(token_of(c)) is None
    assert error(send(c, purpose="bind")) == binding.NEED_RECENT


# ── (c) 管理者：重驗前 admin_session_ok 假（設計 4.4 照舊），密碼重驗補 password 之後真 ──

def test_c_admin_session_after_password_reauth(clock, monkeypatch):
    c = _off_then_on(monkeypatch, name=BOSS, login="boss_01")
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS])  # 建好角色才列（玩家不能取管理者的名號）
    token = token_of(c)
    assert identity_base.admin_session_ok(server.CONTENT, token, lambda: clock.now) is False
    assert c.get("/api/identity/session").json() == {"relogin": True}
    assert _reauth(c).status_code == 200
    assert identity_base.admin_session_ok(server.CONTENT, token, lambda: clock.now) is True
    assert identity_base.staff_session_ok(None, server.CONTENT, token, clock.now) is True
    assert c.get("/api/identity/session").json() == {"relogin": False}


# ── (d) 驗證碼重驗補的列是那一種（不是 password）：客服、管理者權限照舊假；新綁的不能拿來解綁別的 ──

def test_d_code_reauth_seeds_its_own_kind(clock, monkeypatch):
    c = TestClient(server.app)
    register(c, name="沈青衫")
    assert bind(c).status_code == 200
    side_rows("DELETE FROM session_auth")  # 旁檔漏了這一列（打開之前登入、或旁檔不見）
    token = token_of(c)
    assert identity_base.session_auth(token) is None
    assert send(c, purpose="reauth").status_code == 200
    assert verify(c).status_code == 200
    auth = identity_base.session_auth(token)
    assert auth == {"method": "phone", "at": clock.now, "verified": clock.now, "verified_by": "phone"}
    assert identity_base.staff_session_ok(None, server.CONTENT, token, clock.now) is False
    assert identity_base.admin_session_ok(server.CONTENT, token, lambda: clock.now) is False
    assert bind(c, "d1@example.com", "email").status_code == 200
    hours = server.CONTENT.config.identity.new_binding_hours
    assert error(c.post("/api/identity/unbind", json={"provider": "email"})) == binding.NEW_BINDING.format(hours=hours)


# ── (e) 本來就有那一列：重驗只改 verified 兩欄，method、at 一個字不變 ──

def test_e_existing_row_is_untouched_but_verified(clock, monkeypatch):
    c = TestClient(server.app)
    register(c, name="沈青衫")
    token = token_of(c)
    start = identity_base.session_auth(token)
    assert start["method"] == "password" and start["verified"] is None
    assert bind(c).status_code == 200
    clock.now += 60
    assert send(c, purpose="reauth").status_code == 200
    assert verify(c).status_code == 200
    after = identity_base.session_auth(token)
    assert after == {"method": "password", "at": start["at"], "verified": clock.now, "verified_by": "phone"}
    clock.now += 60
    assert _reauth(c).status_code == 200
    assert identity_base.session_auth(token) == {"method": "password", "at": start["at"],
                                                 "verified": clock.now, "verified_by": "password"}
