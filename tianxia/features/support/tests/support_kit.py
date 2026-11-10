"""客服包的測試共用：開關、客服名單、隔開這台機器的 .local/support.txt 與 TIANXIA_SUPPORT。
server_kit 的 autouse fixture 由各測試檔自己明列 import（少一個就會在沒有關排程、沒換雜湊參數之下跑：第 61 批）。"""
from __future__ import annotations

import json

import pytest
import server
from fastapi.testclient import TestClient
from server_kit import _player

from tianxia import content as content_module
from tianxia.core import identity_base
from tianxia.features.support import routes, staff


@pytest.fixture(autouse=True)
def support_isolated(monkeypatch, tmp_path):
    """名單的檔指到這個測試的暫存目錄、環境變數清掉、名單的快取清掉：這台機器的 .local/ 不影響測試，測試也不寫進去。"""
    local = tmp_path / "local"
    local.mkdir()
    monkeypatch.setattr(content_module, "LOCAL_DIR", local)
    monkeypatch.delenv(staff.ENV_VAR, raising=False)
    staff._cache.update(path=None, mtime=None, names=frozenset())
    identity_base._support_bot_cache.update(path=None, mtime=None, token=None)
    yield local


@pytest.fixture
def support_on(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.support, "enabled", True)


def player(login="shen_01", name="沈青衫") -> TestClient:
    c = TestClient(server.app, raise_server_exceptions=False)
    _player(c, login=login, name=name, password="secret-pw-12")  # identity 開著全體 12 字（第 209 批），這裡測的不是密碼
    return c


def staffer(monkeypatch, login="kefu_01", name="青衣") -> TestClient:
    """名單上的客服（照登入名認）。建好帳號才列（第 207 批：identity 開著時名單上的帳號註冊要 12 字，這裡測的不是密碼）。"""
    c = player(login, name)
    monkeypatch.setattr(server.CONTENT.config.support, "staff", [login])
    return c


FAKE_TOKEN = "test-desk-token-" + "0123456789abcdef01234567"  # 測試自造的 40 字假 token（不是真的金鑰）


def bot_setup(monkeypatch, local, login="desk_01", *, token=FAKE_TOKEN) -> dict:
    """客服官（第 216 批）：暫存的 .local/support.json 寫假 token、設 bot_account、清 token 的快取；回帶 Bearer 的標頭。
    login 那個帳號要測試自己建（player(login, ...)）；token=None 不寫金鑰檔。"""
    if token is not None:
        (local / identity_base.SUPPORT_BOT_FILE).write_text(json.dumps({"bot_token": token}), encoding="utf-8")
    monkeypatch.setattr(server.CONTENT.config.support, "bot_account", login)
    identity_base._support_bot_cache.update(path=None, mtime=None, token=None)
    return {"Authorization": f"Bearer {FAKE_TOKEN}"}


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
    ("GET", "/api/support/file/1/1", None),  # 第 215 批：看圖
)
# 第 215 批：截圖上傳的內文是位元組、不解 JSON（gate 測試的「壞 JSON 422」不走它，「關著 404」「沒登入 401」走）
RAW_POSTS = (("POST", "/api/support/file?id=1", b"x"),)


def hit(c: TestClient, method: str, path: str, body):
    if isinstance(body, bytes):
        return c.request(method, path, content=body)
    return c.request(method, path, json=body) if method == "POST" else c.get(path)
