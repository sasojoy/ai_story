"""客服官的 token 身分（客服自動受理第 216 批；設計 5.2、5.3、第八節，企劃者 2026-11-10「照計畫繼續」）：
Authorization: Bearer 只在客服的路由認；錯的、沒設的一律 404 同一句；token 不能查帳號；別的路由 Bearer 不認。"""
from __future__ import annotations

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
import re

import support_kit
from fastapi.testclient import TestClient
from support_kit import bot_setup, player, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.database import open_database
from tianxia.features.support import accounts_view, staff, store

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]


def test_bot_account_id_by_id_or_login(monkeypatch):
    player("desk_01", "青鸞")
    db, config = open_database(), server.CONTENT.config
    me = accounts_view.by_key(db, "desk_01")
    monkeypatch.setattr(config.support, "bot_account", "")
    assert staff.bot_account_id(config, db) is None  # 空
    monkeypatch.setattr(config.support, "bot_account", "  ")
    assert staff.bot_account_id(config, db) is None
    monkeypatch.setattr(config.support, "bot_account", str(me.id))
    assert staff.bot_account_id(config, db) == me.id  # id
    monkeypatch.setattr(config.support, "bot_account", " DESK_01 ")
    assert staff.bot_account_id(config, db) == me.id  # 登入名，不分大小寫
    monkeypatch.setattr(config.support, "bot_account", "nobody_9")
    assert staff.bot_account_id(config, db) is None  # 不存在
    monkeypatch.setattr(config.support, "bot_account", "999")
    assert staff.bot_account_id(config, db) is None  # id 不在
    monkeypatch.setattr(config.support, "bot_account", "青鸞")
    assert staff.bot_account_id(config, db) is None  # 名號不認


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _desk(monkeypatch, support_isolated) -> tuple[TestClient, dict]:
    """客服官的帳號（desk_01，不在客服名單上）＋只帶 Bearer、沒有 cookie 的 client。"""
    player("desk_01", "青鸞")
    headers = bot_setup(monkeypatch, support_isolated)
    return TestClient(server.app, raise_server_exceptions=False), headers


def test_bearer_token_is_staff_on_support_routes(monkeypatch, support_isolated):
    c = player()
    tid = ticket(c).json()["id"]
    assert c.post(f"/api/support/file?id={tid}", content=PNG, headers={"Content-Type": "image/png"}).status_code == 200
    desk, h = _desk(monkeypatch, support_isolated)
    q = desk.get("/api/support/queue", headers=h)
    assert q.status_code == 200 and [t["id"] for t in q.json()["tickets"]] == [tid]
    one = desk.get(f"/api/support/ticket/{tid}", headers=h)
    assert one.status_code == 200 and one.json()["card"]["login"] == "shen_01"
    pic = desk.get(f"/api/support/file/{tid}/1", headers=h)
    assert pic.status_code == 200 and pic.content == PNG
    out = desk.post("/api/support/answer", json={"id": tid, "body": "已收到", "then": "wait"}, headers=h)
    assert out.status_code == 200 and out.json()["status"] == "answered"
    me = accounts_view.by_key(open_database(), "desk_01")
    replies = store.open_store(support_kit.sidecar(), create=False).replies(tid, internal=True)
    assert [r["by_account_id"] for r in replies] == [me.id]  # 記在客服官的帳號上


def _nobody_404() -> bytes:
    got = player("wang_03", "王小二").get("/api/support/queue")
    assert got.status_code == 404
    return got.content


def test_bad_or_missing_token_is_404_like_nobody(monkeypatch, support_isolated):
    c = player()
    tid = ticket(c).json()["id"]
    nobody = _nobody_404()
    desk, h = _desk(monkeypatch, support_isolated)
    assert desk.get("/api/support/queue", headers=h).status_code == 200
    cases = {
        "wrong": {"Authorization": "Bearer " + "z" * 40},
        "non_ascii": {"Authorization": ("Bearer " + "青鸞" * 20).encode("utf-8")},
        "empty": {"Authorization": "Bearer "},
    }
    got = {k: desk.get("/api/support/queue", headers=v) for k, v in cases.items()}
    monkeypatch.setattr(server.CONTENT.config.support, "bot_account", "")
    got["no_account"] = desk.get("/api/support/queue", headers=h)
    monkeypatch.setattr(server.CONTENT.config.support, "bot_account", "nobody_9")
    got["account_gone"] = desk.get("/api/support/queue", headers=h)
    monkeypatch.setattr(server.CONTENT.config.support, "bot_account", "desk_01")
    (support_isolated / "support.json").unlink()
    got["no_file"] = desk.get("/api/support/queue", headers=h)
    got["no_file_answer"] = desk.post("/api/support/answer", json={"id": tid, "body": "x", "then": "wait"}, headers=h)
    for k, r in got.items():
        assert (r.status_code, r.content) == (404, nobody), k


def test_token_cannot_lookup(monkeypatch, support_isolated):
    c = player()
    tid = ticket(c).json()["id"]
    desk, h = _desk(monkeypatch, support_isolated)

    def count():
        conn = store.open_store(support_kit.sidecar(), create=False)._conn()
        try:
            return conn.execute("SELECT COUNT(*) FROM lookups").fetchone()[0]
        finally:
            conn.close()

    before = count()
    got = desk.post("/api/support/lookup", json={"id": tid, "kind": "login", "text": "shen_01"}, headers=h)
    assert (got.status_code, got.json()) == (404, {"detail": "Not Found"})
    assert count() == before


def test_bearer_wins_on_support_and_is_ignored_elsewhere(monkeypatch, support_isolated):
    """Review Focus 3：客服的路由有 Bearer 就以它為準（客服 cookie＋錯的 token 照樣 404）；別的路由不看 Bearer（玩家 cookie＋對的 token 打 /api/me 是玩家自己）。"""
    s = staffer(monkeypatch)
    assert s.get("/api/support/queue").status_code == 200
    player("desk_01", "青鸞")
    h = bot_setup(monkeypatch, support_isolated)
    assert s.get("/api/support/queue", headers={"Authorization": "Bearer " + "z" * 40}).json() == {"detail": "Not Found"}
    assert s.get("/api/support/queue", headers={"Authorization": "Bearer " + "z" * 40}).status_code == 404
    c = player()
    me = c.get("/api/me", headers=h).json()
    assert me == c.get("/api/me").json() and me.get("stage") != "login"


def _admin_paths() -> list[tuple[str, str]]:
    out = []
    for path, methods in server.app.openapi()["paths"].items():
        if path.startswith("/api/admin"):
            out += [(m.upper(), re.sub(r"\{[^}]+\}", "1", path)) for m in methods]
    return out


def test_bot_token_rejected_by_every_admin_api_and_the_shell(monkeypatch, support_isolated):
    """契約（設計第八節）：只帶客服官的 Bearer、沒有 cookie：每個管理者 op 的 /api/do/<op>、每條 /api/admin*、/api/main、/api/do/rest 全部不是 2xx；
    /api/me 回的是沒登入的那一份（第一段量到：沒登入照舊 200 {"stage":"login"}）。照 test_staff_rejected_by_every_admin_api 的掃法。"""
    desk, h = _desk(monkeypatch, support_isolated)
    assert desk.get("/api/support/queue", headers=h).status_code == 200  # token 真的對
    ops = sorted(set(server.FEATURE_ADMIN_ACTIONS) | set(server.PLAYER_ADMIN_ACTIONS))
    paths = _admin_paths()
    assert len(server.FEATURE_ADMIN_ACTIONS) >= 10 and len(paths) >= 4, "掃法壞了"
    passed = {}
    for op in ops + ["rest"]:
        got = desk.post(f"/api/do/{op}", json={"name": "沈青衫"}, headers=h)
        if 200 <= got.status_code < 300:
            passed[f"/api/do/{op}"] = got.status_code
    for method, path in paths:
        got = desk.request(method, path, json={} if method == "POST" else None, headers=h)
        if 200 <= got.status_code < 300:
            passed[path] = got.status_code
    got = desk.get("/api/main", headers=h)
    if 200 <= got.status_code < 300:
        passed["/api/main"] = got.status_code
    assert not passed
    anon = TestClient(server.app, raise_server_exceptions=False)
    assert desk.get("/api/me", headers=h).content == anon.get("/api/me").content
    assert desk.get("/api/me", headers=h).json().get("stage") == "login"
