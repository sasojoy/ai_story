"""管理者的帳號工具（帳號與客服第 204 批；設計 4.3、6.4、6.5）：identity_view／identity_unbind／identity_delete 關著 404、
不是管理者拒；解綁寫紀錄、雜湊留著；刪帳號名號仍占住、錢包留著、不能刪自己；重設密碼對沒密碼的回那一句；管理頁搜尋帶帳號鍵與綁定。"""
from __future__ import annotations

import re

from fastapi.testclient import TestClient
from test_identity_bind import _pw
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import (  # noqa: F401
    bind, clock, error, on, phone_account, register, send, side_rows, subj, token_of, verify,
)

import server
from tianxia import accounts, database
from tianxia.accounts import AccountStore
from tianxia.features.identity import admin, binding

PHONE_N = "+886912345678"


def _admin(monkeypatch):
    c = TestClient(server.app)
    _pw(c, "boss_01", "段青山")
    monkeypatch.setattr(server.CONTENT.config, "admins", ["段青山"])  # 建好角色才列（玩家不能取管理者的名號）
    return c


def _say(r) -> str:
    """/api/do 回的 message 是 md 轉過的 HTML：拿掉標籤。"""
    return re.sub(r"<[^>]+>", "", r.json()["message"]).strip()


def _do(c, op, **body):
    return c.post(f"/api/do/{op}", json=body)


def test_admin_tools_refuse_non_admin(clock):
    c = TestClient(server.app)
    _pw(c)
    for op in ("identity_view", "identity_unbind", "identity_delete"):
        assert error(_do(c, op, target="shen_01", provider="phone")) == "只有管理者能這麼做。"
    assert c.post("/api/identity/admin/accounts", json={"q": "shen"}).status_code == 403


def test_admin_unbind_and_view(clock, monkeypatch):
    boss = _admin(monkeypatch)
    c = TestClient(server.app)
    aid = _pw(c)
    bind(c)
    view = _say(_do(boss, "identity_view", target="沈青衫"))
    assert view.splitlines()[0] == admin.ADMIN_VIEW_HEAD.format(who="shen_01")
    assert "手機：09*****678（綁定 " in view and "密碼：shen_01（綁定 開帳號時，上次驗證 —）" in view
    assert _say(_do(boss, "identity_unbind", target="shen_01", provider="password")) == admin.ADMIN_NO_WAY
    r = _do(boss, "identity_unbind", target="shen_01", provider="phone")
    assert _say(r) == admin.ADMIN_UNBOUND.format(who="shen_01", kind="手機")
    assert [x["provider"] for x in AccountStore(database.open_database()).logins_of("shen_01")] == ["password"]
    assert side_rows("SELECT subject_hmac, account_id FROM unbound") == [(subj("phone", PHONE_N), aid)]
    texts = [r[0] for r in side_rows("SELECT text FROM account_notes WHERE account_id = ?", (aid,))]
    assert texts[-1] == binding.NOTE_ADMIN_UNBOUND.format(kind="手機")
    assert _say(_do(boss, "identity_view", target="nobody")) == admin.NOT_FOUND


def test_admin_delete_keeps_name_and_wallet(clock, monkeypatch):
    from tianxia.characters import name_key
    from tianxia.wallet import Wallet

    boss = _admin(monkeypatch)
    c = TestClient(server.app)
    key = phone_account(c)
    db = database.open_database()
    before = Wallet(db).balance(name_key("沈青衫"))
    assert _say(_do(boss, "identity_delete", target="boss_01")) == admin.ADMIN_SELF
    r = _do(boss, "identity_delete", target="沈青衫")
    assert _say(r) == admin.ADMIN_DELETED.format(who=key)
    store = AccountStore(db)
    assert store.get(key) is None and store.owner_of("沈青衫") is None and server.SESSIONS.get(token_of(c)) is None
    assert side_rows("SELECT provider FROM unbound") == [("phone",)]  # 雜湊永久留著
    assert Wallet(db).balance(name_key("沈青衫")) == before
    other = TestClient(server.app)
    register(other, "li_02")
    taken = other.post("/api/character", json={"name": "沈青衫"})
    assert taken.status_code == 400 and taken.json()["error"] == accounts.NAME_TAKEN  # 名號仍被存檔占住


def test_admin_reset_no_password_says_so(clock, monkeypatch):
    boss = _admin(monkeypatch)
    key = phone_account(TestClient(server.app))
    r = boss.post("/api/admin/reset_password", json={"target": key, "temp": "temp-pass-1"})
    assert r.json()["message"] == accounts.NO_PASSWORD == "這個帳號沒有密碼，請他用綁定的方式登入。"


def test_admin_accounts_route_gives_keys(clock, monkeypatch):
    boss = _admin(monkeypatch)
    c = TestClient(server.app)
    key = phone_account(c)
    assert c.post("/api/identity/password/set", json={"login": "ray_77", "new": "new-secret-12", "again": "new-secret-12"}).status_code == 200
    rows = boss.post("/api/identity/admin/accounts", json={"q": "ray"}).json()["rows"]
    assert [(r["key"], r["login"], r["character"]) for r in rows] == [(key, "ray_77", "沈青衫")]
    assert [b["provider"] for b in rows[0]["binds"]] == ["password", "phone"]
    plain = boss.post("/api/admin/accounts", json={"q": "ray"}).json()["rows"]
    assert plain == [{"login": "ray_77", "character": "沈青衫"}]  # 管理者包原本那一條輸出不變
    assert boss.post("/api/admin/reset_password", json={"target": "ray_77", "temp": "temp-pass-123"}).json()["message"] == \
        "已重設 ray_77 的密碼。"
