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


DAY = rules.DAY_SECONDS


def _sql(sql: str, args=()) -> None:
    with contextlib.closing(sqlite3.connect(sidecar(), isolation_level=None)) as conn:
        conn.execute(sql, args)


def _age(tid: int, days: float) -> None:
    """把這張單每一則回覆（與單）往前推 days 天。"""
    _sql("UPDATE replies SET created = created - ? WHERE ticket_id = ?", (days * DAY, tid))
    _sql("UPDATE tickets SET updated = updated - ? WHERE id = ?", (days * DAY, tid))


class _Push:
    def __init__(self):
        self.sent = []

    def send(self, *a, **k):
        self.sent.append(a)
        return 1


def test_sweep_closes_only_answered_older_than_days(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    push = _Push()
    a, b, d = (ticket(c).json()["id"] for _ in range(3))
    for tid in (a, b, d):
        s.post("/api/support/answer", json={"id": tid, "body": "試試看", "then": "wait"})
    _age(a, 4)  # answered、4 天：結
    _age(b, 2)  # answered、2 天：不結
    _sql("UPDATE tickets SET admin_flag = 1 WHERE id = ?", (d,))
    _age(d, 10)  # answered 但掛著請管理者、10 天：不結
    s.post("/api/support/close", json={"id": b})
    e = ticket(c).json()["id"]
    _age(e, 10)  # open（等客服）、10 天：不結
    _sql("UPDATE tickets SET status = 'answered' WHERE id = ?", (b,))
    monkeypatch.setattr(server, "WEB_PUSH", push)
    sc = _sc()
    owner = (sc.ticket(a)["account_id"], sc.ticket(a)["account_created"])
    before = sc.unread(*owner)
    got = s.post("/api/support/sweep", json={})
    assert got.status_code == 200 and got.json() == {"closed": [a]}
    assert push.sent == []  # 不推播
    assert [sc.ticket(t)["status"] for t in (a, b, d, e)] == ["closed", "answered", "answered", "open"]
    last = sc.replies(a, internal=True)[-1]
    assert (last["by_account_id"], last["staff"], last["internal"], last["seen"], last["journaled"]) == (rules.SYSTEM_ACCOUNT, 1, 0, 0, 1)
    assert last["body"] == rules.AUTO_CLOSED.format(days=3)
    assert sc.unread(*owner) == before + 1  # 紅點有
    assert all(r["id"] != last["id"] for r in sc.take_unjournaled(*owner, 1.0))  # 江湖紀錄沒有
    view = s.get(f"/api/support/ticket/{a}").json()
    assert (view["replies"][-1]["auto"], view["replies"][-1]["system"], view["last_by"], view["admin_flag"]) == (True, True, "system", False)
    assert c.get("/api/support/mine").json()["tickets"][-1]["replies"][-1]["auto"] is True
    assert s.post("/api/support/sweep", json={}).json() == {"closed": []}  # 再掃一次沒有了
    monkeypatch.setattr(server.CONTENT.config.support, "auto_close_days", 1)
    assert s.post("/api/support/sweep", json={}).json() == {"closed": [b]}  # 天數照設定
    assert sc.replies(b, internal=True)[-1]["body"] == rules.AUTO_CLOSED.format(days=1)


def test_sweep_rechecks_inside_the_write_lock(monkeypatch, tmp_path):
    """Review Focus 4：sweep 在 BEGIN IMMEDIATE 裡才讀要結哪幾張；別人先拿著寫入鎖、在鎖裡讓玩家回了一句（單回到處理中），sweep 等到鎖之後就不結它。"""
    import threading

    sc = store.SupportStore(tmp_path / "s.sqlite")
    tid = sc.add_ticket(account_id=1, account_created=1.0, login="x", character="x", version="v", category="account", body="b", now=100.0,
                        open_max=3, daily_max=5)
    sc.staff_reply(tid, 2, "試試看", "wait", 100.0)
    holder = sqlite3.connect(tmp_path / "s.sqlite", isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    out = {}
    worker = threading.Thread(target=lambda: out.setdefault("closed", sc.sweep(100.0 + 10 * DAY, 3 * DAY, "結了")))
    worker.start()
    worker.join(0.3)
    assert worker.is_alive()  # 等著鎖
    holder.execute("INSERT INTO replies (ticket_id, by_account_id, staff, internal, body, created) VALUES (?, 1, 0, 0, '還不行', ?)",
                   (tid, 100.0 + 10 * DAY))
    holder.execute("UPDATE tickets SET status = 'open' WHERE id = ?", (tid,))
    holder.execute("COMMIT")
    holder.close()
    worker.join(5)
    assert out["closed"] == [] and sc.ticket(tid)["status"] == "open"


def test_sweep_route_for_staff_and_token_not_players(monkeypatch, support_isolated):
    c = player()
    s = staffer(monkeypatch)
    player("desk_01", "青鸞")
    h = bot_setup(monkeypatch, support_isolated)
    from fastapi.testclient import TestClient  # noqa: PLC0415

    desk = TestClient(server.app, raise_server_exceptions=False)
    assert not sidecar().exists()
    assert s.post("/api/support/sweep", json={}).json() == {"closed": []}  # 旁檔不在
    assert desk.post("/api/support/sweep", json={}, headers=h).json() == {"closed": []}
    assert not sidecar().exists()  # 不建檔
    got = c.post("/api/support/sweep", json={})
    assert (got.status_code, got.json()) == (404, {"detail": "Not Found"})  # 玩家跟沒有這條路同一句
    tid = ticket(c).json()["id"]
    desk.post("/api/support/answer", json={"id": tid, "body": "自動的", "then": "wait"}, headers=h)
    _age(tid, 5)
    got = desk.post("/api/support/sweep", json={}, headers=h)
    assert (got.status_code, got.json()) == (200, {"closed": [tid]})


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
