"""/api/main 的 identity 格（帳號與客服第 204 批）：只給本人、有帳號才有；假人與沒帳號的同一個樣子（{}）；phone_missing 只在 phone_gate 開著。"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from test_identity_bind import _pw
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import bind, clock, on, phone_account  # noqa: F401

import server
from tianxia import database
from tianxia.features.identity import FEATURE, notes
from tianxia.features.identity import store as idstore


def test_status_only_for_own_account(clock):
    c = TestClient(server.app)
    _pw(c)
    assert c.get("/api/main").json()["identity"] == {"kinds": ["password"], "has_password": True, "phone_missing": False}
    bind(c)
    assert c.get("/api/main").json()["identity"]["kinds"] == ["password", "phone"]


def test_bot_and_no_account_get_nothing(clock):
    def ctx(name, bot=None):
        return SimpleNamespace(content=server.CONTENT, now=clock.now, world=SimpleNamespace(db=database.open_database()),
                               state=SimpleNamespace(player=SimpleNamespace(name=name, bot=bot), journal=[]))

    assert notes.main_slot(ctx("無人")) == {} == notes.main_slot(ctx(""))  # 沒有帳號：跟假人同一個樣子
    side = idstore.default_side_path()
    FEATURE.on_own_turn(ctx("假的", bot=object()))  # 假人第一行就跳過：不開旁檔
    assert not side.exists()


def test_phone_missing_only_with_gate(clock, monkeypatch):
    c = TestClient(server.app)
    _pw(c)
    assert c.get("/api/main").json()["identity"]["phone_missing"] is False
    monkeypatch.setattr(server.CONTENT.config.identity, "phone_gate", True)
    assert c.get("/api/main").json()["identity"]["phone_missing"] is True
    bind(c)
    assert c.get("/api/main").json()["identity"]["phone_missing"] is False


def test_others_never_see_bindings(clock):
    a = TestClient(server.app)
    _pw(a)
    bind(a)
    b = TestClient(server.app)
    _pw(b, "li_02", "李白衣")
    main = b.get("/api/main")
    assert main.json()["identity"]["kinds"] == ["password"]  # 自己的
    assert b"09*****678" not in main.content and "沈青衫" not in main.json()["identity"].__repr__()
    assert b.get("/api/identity/me").json()["kinds"][0]["shown"] == "li_02"
