"""找真人與自動結單（客服自動受理第 216 批；設計 5.2、5.4、第七節，企劃者 2026-11-10「照計畫繼續」）：
旁檔的 flags 表、POST /api/support/human（主人、沒結、冪等、answered → open）、清單與單上的 human、last_by；
POST /api/support/sweep（answered、沒請管理者、最後一則早於 auto_close_days 天的單自動結掉，系統回覆一則）。"""
from __future__ import annotations

import contextlib
import sqlite3

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import bot_setup, player, sidecar, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.features.support import rules, store

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]


def _sc() -> store.SupportStore:
    return store.open_store(sidecar(), create=False)


def test_human_flag_owner_only_idempotent_and_reopens(monkeypatch):
    c = player()
    other = player("wang_03", "王小二")
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    s.post("/api/support/answer", json={"id": tid, "body": "試試重登", "then": "wait"})
    assert other.post("/api/support/human", json={"id": tid}).json() == {"detail": rules.NOT_FOUND}  # 別人的單
    assert other.post("/api/support/human", json={"id": tid}).status_code == 404
    assert c.post("/api/support/human", json={"id": tid + 9}).status_code == 404  # 不存在
    got = c.post("/api/support/human", json={"id": tid})
    assert got.status_code == 200
    one = got.json()
    assert one["id"] == tid and one["human"] is True and one["status"] == "open"  # answered → open
    assert c.post("/api/support/human", json={"id": tid}).json()["human"] is True  # 冪等
    assert [f["kind"] for f in _sc().flags(tid)] == ["human"]
    assert _sc().has_human(tid) and not _sc().has_human(tid + 9)
    assert c.get("/api/support/mine").json()["tickets"][0]["human"] is True
    s.post("/api/support/close", json={"id": tid})
    closed = c.post("/api/support/human", json={"id": tid})
    assert (closed.status_code, closed.json()) == (400, {"error": rules.CLOSED_ALREADY})
    later = ticket(c).json()["id"]
    assert c.get("/api/support/mine").json()["tickets"][0]["id"] == later
    assert c.get("/api/support/mine").json()["tickets"][0]["human"] is False
    assert rules.after_human(rules.ANSWERED) == rules.OPEN and rules.after_human(rules.OPEN) == rules.OPEN


def _system_reply(tid: int, body="結了") -> None:
    with contextlib.closing(sqlite3.connect(sidecar(), isolation_level=None)) as conn:
        conn.execute("INSERT INTO replies (ticket_id, by_account_id, staff, internal, body, created, journaled) VALUES (?, 0, 1, 0, ?, 1.0, 1)",
                     (tid, body))


def test_human_shows_in_queue_and_last_by(monkeypatch, support_isolated):
    c = player()
    s = staffer(monkeypatch)
    player("desk_01", "青鸞")
    h = bot_setup(monkeypatch, support_isolated)
    from fastapi.testclient import TestClient  # noqa: PLC0415

    desk = TestClient(server.app, raise_server_exceptions=False)
    a, b, d = (ticket(c).json()["id"] for _ in range(3))  # 一次最多三張沒結的：先結掉再開 e、f（一天五張）
    c.post("/api/support/reply", json={"id": a, "body": "補一句"})  # player
    s.post("/api/support/answer", json={"id": b, "body": "真人", "then": "wait"})  # staff
    desk.post("/api/support/answer", json={"id": d, "body": "自動", "then": "wait"}, headers=h)  # desk
    s.post("/api/support/answer", json={"id": d, "body": "記一下", "then": "admin"})  # 內部註記不算最後一則
    s.post("/api/support/close", json={"id": a})
    s.post("/api/support/close", json={"id": b})
    s.post("/api/support/close", json={"id": d})
    e, f = ticket(c).json()["id"], ticket(c).json()["id"]
    _system_reply(e)  # system
    c.post("/api/support/human", json={"id": f})  # 沒有回覆：None
    with contextlib.closing(sqlite3.connect(sidecar(), isolation_level=None)) as conn:
        conn.execute("UPDATE tickets SET status = 'open' WHERE id IN (?, ?, ?)", (a, b, d))
    q = s.get("/api/support/queue").json()["tickets"]
    by = {t["id"]: (t["last_by"], t["human"]) for t in q}
    assert by == {a: ("player", False), b: ("staff", False), d: ("desk", False), e: ("system", False), f: (None, True)}
    one = s.get(f"/api/support/ticket/{f}").json()
    assert (one["human"], one["last_by"]) == (True, None)
    assert s.get(f"/api/support/ticket/{d}").json()["last_by"] == "desk"
    monkeypatch.setattr(server.CONTENT.config.support, "bot_account", "")
    assert {t["id"]: t["last_by"] for t in s.get("/api/support/queue").json()["tickets"]}[d] == "staff"  # 沒設客服官就認不出自動的


def test_old_sidecar_without_flags_opens(monkeypatch):
    """第 215 批建的舊旁檔（沒有 flags 表）照讀：打開時補表、舊單 human 是 false。"""
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    with contextlib.closing(sqlite3.connect(sidecar(), isolation_level=None)) as conn:
        conn.execute("DROP TABLE flags")
    assert c.get("/api/support/mine").json()["tickets"][0]["human"] is False
    assert s.get(f"/api/support/ticket/{tid}").json()["human"] is False
    with contextlib.closing(sqlite3.connect(sidecar(), isolation_level=None)) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'flags'").fetchone() is not None
