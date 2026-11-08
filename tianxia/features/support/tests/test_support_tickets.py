"""玩家那一側（帳號與客服第 211 批；設計 6.1）：送單、看單、再回一句、上限與拒絕的話、別人的單一律 404 同一句、內部註記看不到。"""
from __future__ import annotations

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import player, sidecar, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.features.support import rules, store

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]


def test_filing_a_ticket_fills_account_name_time_and_version_on_the_server():
    c = player()
    out = ticket(c, body="  儲值沒到帳  ", category="mall")
    assert out.status_code == 200
    tid = out.json()["id"]
    t = store.open_store(sidecar(), create=False).ticket(tid)
    assert (t["account_id"], t["login"], t["character"], t["category"], t["body"], t["status"]) == (1, "shen_01", "沈青衫", "mall", "儲值沒到帳", "open")
    notes = server.patch_notes()
    assert t["version"] == (notes[0]["date"] if notes else "")
    assert t["account_created"] > 0 and t["created"] > 0


def test_client_supplied_name_and_version_are_ignored():
    c = player()
    tid = c.post("/api/support/ticket", json={"category": "game", "body": "卡住了", "character": "假名", "login": "x", "version": "1999",
                                              "account_id": 99, "status": "closed"}).json()["id"]
    t = store.open_store(sidecar(), create=False).ticket(tid)
    assert (t["character"], t["login"], t["account_id"], t["status"]) == ("沈青衫", "shen_01", 1, "open")
    assert t["version"] != "1999"


@pytest.mark.parametrize("category", ["", "admin", "帳號", "constructor"])
def test_category_must_be_on_the_whitelist(category):
    out = ticket(player(), category=category)
    assert out.status_code == 400 and out.json()["error"] == rules.BAD_CATEGORY


def test_body_at_most_1000_characters_and_not_empty():
    c = player()
    assert ticket(c, body="字" * 1000).status_code == 200
    long = ticket(c, body="字" * 1001)
    assert long.status_code == 400 and long.json()["error"] == "太長了：一則最多 1000 個字。"
    empty = ticket(c, body="   ")
    assert empty.status_code == 400 and empty.json()["error"] == rules.EMPTY


def test_three_open_tickets_at_most():
    c = player()
    for _ in range(3):
        assert ticket(c).status_code == 200
    out = ticket(c)
    assert out.status_code == 400 and out.json()["error"] == "已經有 3 張還沒結的單，等客服回覆或結單之後再送。"


def test_five_tickets_a_day_at_most(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    for _ in range(5):
        tid = ticket(c).json()["id"]
        assert s.post("/api/support/close", json={"id": tid}).status_code == 200
    out = ticket(c)
    assert out.status_code == 400 and out.json()["error"] == "一天最多送 5 張單，明天再送。"
    monkeypatch.setattr(server.time, "time", lambda real=server.time.time: real() + rules.DAY_SECONDS + 1)
    assert ticket(c).status_code == 200


def test_mine_lists_my_tickets_newest_first():
    c = player()
    ticket(c, body="第一張")
    ticket(c, body="第二張", category="other")
    mine = c.get("/api/support/mine").json()
    assert [t["body"] for t in mine["tickets"]] == ["第二張", "第一張"]
    assert mine["tickets"][0]["category_name"] == "其他" and mine["tickets"][0]["status"] == "open"
    assert list(mine["categories"]) == ["account", "mall", "game", "other"] and mine["body_max"] == 1000


def test_other_players_ticket_is_404():
    """別人的單號、不存在的單號、建帳號時間對不上的單：三種回同一句、同一個狀態碼。"""
    a = player()
    b = player("li_02", "李白衣")
    tid = ticket(a).json()["id"]
    theirs = b.post("/api/support/reply", json={"id": tid, "body": "偷看"})
    missing = b.post("/api/support/reply", json={"id": 999, "body": "偷看"})
    assert ticket(b).status_code == 200
    mine_b = b.get("/api/support/mine").json()["tickets"]
    assert [t["body"] for t in mine_b] == ["帳號登不進去"] and all(t["id"] != tid for t in mine_b)
    s = store.open_store(sidecar(), create=False)
    with s._write() as conn:  # 主檔退回舊時間點之後同一個 id 被新帳號拿到：建帳號的時間對不上
        conn.execute("UPDATE tickets SET account_created = account_created - 1 WHERE id = ?", (tid,))
    stale = a.post("/api/support/reply", json={"id": tid, "body": "還是我"})
    assert theirs.status_code == missing.status_code == stale.status_code == 404
    assert theirs.json() == missing.json() == stale.json()
    assert all(t["id"] != tid for t in a.get("/api/support/mine").json()["tickets"])


def test_replying_again_moves_the_ticket_back_to_open(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    s.post("/api/support/answer", json={"id": tid, "body": "請說明是哪一台裝置", "then": "wait"})
    assert c.get("/api/support/mine").json()["tickets"][0]["status"] == "answered"
    out = c.post("/api/support/reply", json={"id": tid, "body": "手機"})
    assert out.status_code == 200
    t = out.json()["mine"]["tickets"][0]
    assert t["status"] == "open" and [(r["staff"], r["body"]) for r in t["replies"]] == [(True, "請說明是哪一台裝置"), (False, "手機")]


def test_closed_tickets_take_no_reply(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    s.post("/api/support/close", json={"id": tid})
    out = c.post("/api/support/reply", json={"id": tid, "body": "還沒好"})
    assert out.status_code == 400 and out.json()["error"] == rules.CLOSED_ALREADY


def test_internal_notes_never_reach_the_player(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    s.post("/api/support/answer", json={"id": tid, "body": "內部：請管理者補發", "then": "admin"})
    t = c.get("/api/support/mine").json()["tickets"][0]
    assert t["replies"] == [] and "內部" not in str(t) and "admin_flag" not in t
    assert c.get("/api/main").json()["support_unread"] == 0


def test_unread_counts_staff_replies_until_the_player_looks(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    assert c.get("/api/main").json()["support_unread"] == 0
    s.post("/api/support/answer", json={"id": tid, "body": "好了", "then": "wait"})
    assert c.get("/api/main").json()["support_unread"] == 1
    c.get("/api/support/mine")
    assert c.get("/api/main").json()["support_unread"] == 0
