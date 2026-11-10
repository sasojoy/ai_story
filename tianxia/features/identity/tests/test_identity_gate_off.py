"""開關關著（帳號與客服第 204 批）：新路由登入了也 404、沒登入 401（先 401 再 gate）；/api/main 沒有 identity 格、登入不碰旁檔；
開著時沒登入一樣 401。開著與關著的 /、/api/me、/api/main 逐位元組比在 test_identity_server.py::test_switch_off_routes_404_and_pages_do_not_move。"""
from __future__ import annotations

from fastapi.testclient import TestClient
from test_identity_server import _turn_on, fresh_server, key_file  # noqa: F401
from test_identity_session import register

import server
from tianxia import database
from tianxia.features.identity import store as idstore

NEW_ROUTES = (
    ("GET", "/api/identity/me"), ("POST", "/api/identity/reauth"), ("POST", "/api/identity/unbind"),
    ("POST", "/api/identity/password/set"), ("POST", "/api/identity/password/reset"), ("POST", "/api/identity/code/release"),
    ("POST", "/api/identity/admin/accounts"), ("GET", "/api/identity/session"),  # 第 209 批
)


def _hit(c, method, path):
    return c.get(path) if method == "GET" else c.post(path, json={"provider": "phone", "login": "x", "new": "y", "again": "y"})


def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "g.db")
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "g.db"))


def test_every_new_route_404_when_off_logged_in(monkeypatch, key_file, tmp_path):  # noqa: F811
    _db(monkeypatch, tmp_path)
    c = TestClient(server.app)
    register(c, name="沈青衫")
    c.cookies.set("tx_recheck", "forged")
    c.cookies.set("tx_reset", "forged")
    assert {path: _hit(c, m, path).status_code for m, path in NEW_ROUTES} == {path: 404 for _m, path in NEW_ROUTES}
    for op in ("identity_view", "identity_unbind", "identity_delete"):
        assert c.post(f"/api/do/{op}", json={"target": "shen_01"}).status_code == 404
    assert b'"identity"' not in c.get("/api/main").content
    assert not idstore.default_side_path().exists()  # 關著登入、打這些路由都不建旁檔


def test_new_routes_401_without_login(monkeypatch, key_file, tmp_path):  # noqa: F811
    _db(monkeypatch, tmp_path)
    anon = TestClient(server.app)
    assert {path: _hit(anon, m, path).status_code for m, path in NEW_ROUTES} == {path: 401 for _m, path in NEW_ROUTES}
    _turn_on(monkeypatch)
    assert {path: _hit(anon, m, path).status_code for m, path in NEW_ROUTES} == {path: 401 for _m, path in NEW_ROUTES}
