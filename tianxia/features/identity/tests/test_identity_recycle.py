"""門號回收（帳號與客服第 204 批；設計 4.4，企劃者 180 天）：驗碼登入一律更新 verified_at；過期而帳號還有別種 → 不開 session、
給「這不是我的帳號」；只有這一種 → 進得了遊戲、7 天扣押；用密碼或第三方的人 180 天提醒一次、不擋遊戲。"""
from __future__ import annotations

from fastapi.testclient import TestClient
from test_identity_bind import _pw
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import (  # noqa: F401
    bind, clock, error, on, phone_account, register, send, side_rows, subj, token_of, verify,
)

import server
from tianxia import database
from tianxia.accounts import AccountStore
from tianxia.features.identity import binding, codes
from tianxia.features.identity import store as idstore

DAY = 86400
PHONE_N = "+886912345678"


def _kinds(key):
    return sorted(r["provider"] for r in AccountStore(database.open_database()).logins_of(key) if r["provider"] != "id")


def test_missing_meta_counts_as_fresh():
    cfg = server.CONTENT.config.identity
    assert binding.stale(None, 10 ** 9, cfg) is False
    assert binding.stale({"verified_at": None}, 10 ** 9, cfg) is False
    assert binding.stale({"verified_at": 0.0}, 180 * DAY, cfg) is False and binding.stale({"verified_at": 0.0}, 180 * DAY + 1, cfg)


def test_fresh_code_login_updates_verified_at(clock):
    c = TestClient(server.app)
    key = phone_account(c)
    aid = AccountStore(database.open_database()).account_id(key)
    c.post("/api/logout")
    clock.now += 100 * DAY
    assert send(c).status_code == 200 and verify(c).json()["stage"] == "game"
    assert idstore.IdentityStore().meta(aid)["phone"]["verified_at"] == clock.now


def _stale_with_password(clock):
    c = TestClient(server.app)
    key = phone_account(c)
    assert c.post("/api/identity/password/set", json={"login": "ray_77", "new": "new-secret-12", "again": "new-secret-12"}).status_code == 200
    c.post("/api/logout")
    clock.now += 181 * DAY
    return key


def test_stale_with_other_way_refuses_and_offers_not_mine(clock):
    key = _stale_with_password(clock)
    d = TestClient(server.app)
    assert send(d).status_code == 200
    r = verify(d)
    assert r.json() == {"stale": True, "message": binding.STALE_USE_OTHER, "ways": ["password"]}
    assert server.COOKIE not in d.cookies and d.cookies.get("tx_recheck")
    assert _kinds(key) == ["password", "phone"]


def test_not_mine_moves_number_to_new_account(clock):
    key = _stale_with_password(clock)
    old = AccountStore(database.open_database()).account_id(key)
    d = TestClient(server.app)
    send(d)
    verify(d)
    r = d.post("/api/identity/code/release")
    assert r.json() == {"stage": "create", "pending": True, "message": binding.NOT_MINE_DONE}
    assert _kinds(key) == ["password"]  # 從舊帳號拿掉
    made = d.post("/api/identity/character", json={"name": "新來的"})
    assert made.status_code == 200
    new_key = server.SESSIONS.get(token_of(d))
    assert new_key != key and _kinds(new_key) == ["phone"]
    assert side_rows("SELECT account_id, provider FROM unbound") == [(old, "phone")]
    texts = [r[0] for r in side_rows("SELECT text FROM account_notes WHERE account_id = ?", (old,))]
    assert binding.NOTE_RELEASED.format(kind="手機") in texts
    assert error(d.post("/api/identity/code/release")) == codes.BAD_CODE  # 單用過了、cookie 也刪了（登入著：過 gate 才說）
    assert TestClient(server.app).post("/api/identity/code/release").status_code == 401  # 什麼 cookie 都沒帶


def test_stale_only_way_logs_in_with_7_day_hold(clock):
    c = TestClient(server.app)
    key = phone_account(c)
    aid = AccountStore(database.open_database()).account_id(key)
    c.post("/api/logout")
    clock.now += 181 * DAY
    assert send(c).status_code == 200 and verify(c).json()["stage"] == "game"
    assert idstore.IdentityStore().hold_until(aid) == clock.now + 7 * DAY
    assert c.get("/api/identity/me").json()["hold"] is True
    r = c.post("/api/identity/password/set", json={"login": "ray_77", "new": "new-secret-12", "again": "new-secret-12"})
    assert error(r) == binding.ON_HOLD.format(days=7)
    clock.now += 7 * DAY
    c.post("/api/logout")
    clock.now += 61
    assert send(c).status_code == 200 and verify(c).json()["stage"] == "game"
    assert c.post("/api/identity/password/set", json={"login": "ray_77", "new": "new-secret-12", "again": "new-secret-12"}).status_code == 200


def test_reminder_once_per_180_days(clock):
    c = TestClient(server.app)
    aid = _pw(c)
    bind(c)
    def reminders():
        return [r for r in side_rows("SELECT text FROM account_notes WHERE account_id = ?", (aid,))
                if r[0] == binding.NOTE_REMIND.format(kind="手機")]
    assert c.get("/api/main").status_code == 200 and reminders() == []
    clock.now += 181 * DAY
    c.post("/api/identity/reauth", json={"password": "secret-pw-12"})
    assert c.get("/api/main").status_code == 200 and len(reminders()) == 1
    assert c.get("/api/main").status_code == 200 and len(reminders()) == 1  # 一次就好
    clock.now += 181 * DAY
    assert c.get("/api/main").status_code == 200 and len(reminders()) == 2
