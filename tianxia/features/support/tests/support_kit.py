"""客服包的測試共用：開關、客服名單、隔開這台機器的 .local/support.txt 與 TIANXIA_SUPPORT。
server_kit 的 autouse fixture 由各測試檔自己明列 import（少一個就會在沒有關排程、沒換雜湊參數之下跑：第 61 批）。"""
from __future__ import annotations

import pytest
import server
from fastapi.testclient import TestClient
from server_kit import _player

from tianxia import content as content_module
from tianxia.features.support import routes, staff


@pytest.fixture(autouse=True)
def support_isolated(monkeypatch, tmp_path):
    """名單的檔指到這個測試的暫存目錄、環境變數清掉、名單的快取清掉：這台機器的 .local/ 不影響測試，測試也不寫進去。"""
    local = tmp_path / "local"
    local.mkdir()
    monkeypatch.setattr(content_module, "LOCAL_DIR", local)
    monkeypatch.delenv(staff.ENV_VAR, raising=False)
    staff._cache.update(path=None, mtime=None, names=frozenset())
    yield local


@pytest.fixture
def support_on(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.support, "enabled", True)


def player(login="shen_01", name="沈青衫") -> TestClient:
    c = TestClient(server.app, raise_server_exceptions=False)
    _player(c, login=login, name=name)
    return c


def staffer(monkeypatch, login="kefu_01", name="青衣") -> TestClient:
    """名單上的客服（照登入名認）。"""
    monkeypatch.setattr(server.CONTENT.config.support, "staff", [login])
    return player(login, name)


def sidecar():
    return routes.sidecar_path()


def ticket(c: TestClient, body="帳號登不進去", category="account"):
    return c.post("/api/support/ticket", json={"category": category, "body": body})


ROUTES = (
    ("POST", "/api/support/ticket", {"category": "account", "body": "x"}),
    ("GET", "/api/support/mine", None),
    ("POST", "/api/support/reply", {"id": 1, "body": "x"}),
    ("GET", "/api/support/queue", None),
    ("GET", "/api/support/ticket/1", None),
    ("POST", "/api/support/answer", {"id": 1, "body": "x", "then": "wait"}),
    ("POST", "/api/support/close", {"id": 1}),
    ("POST", "/api/support/lookup", {"id": 1, "kind": "login", "text": "x"}),  # 第 212 批
)


def hit(c: TestClient, method: str, path: str, body):
    return c.request(method, path, json=body) if method == "POST" else c.get(path)
