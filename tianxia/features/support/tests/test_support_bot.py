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
    assert desk.post("/api/support/sweep", json={}, headers=h).json() == {"closed": []}  # 剛回的不結
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


def test_bot_replies_are_auto_for_player_and_staff(monkeypatch, support_isolated):
    c = player()
    tid = ticket(c).json()["id"]
    s = staffer(monkeypatch)
    desk, h = _desk(monkeypatch, support_isolated)
    desk.post("/api/support/answer", json={"id": tid, "body": "自動的", "then": "wait"}, headers=h)
    c.post("/api/support/reply", json={"id": tid, "body": "還是不行"})
    s.post("/api/support/answer", json={"id": tid, "body": "真人的", "then": "wait"})
    mine = c.get("/api/support/mine").json()["tickets"][0]["replies"]
    assert [(r["body"], r["staff"], r["auto"]) for r in mine] == [("自動的", True, True), ("還是不行", False, False), ("真人的", True, False)]
    one = s.get(f"/api/support/ticket/{tid}").json()["replies"]
    assert [(r["body"], r["auto"], r["system"]) for r in one] == [("自動的", True, False), ("還是不行", False, False), ("真人的", False, False)]
    monkeypatch.setattr(server.CONTENT.config.support, "bot_account", "")  # 沒設客服官：看不出哪一則是自動的
    assert [r["auto"] for r in c.get("/api/support/mine").json()["tickets"][0]["replies"]] == [False, False, False]


def test_relay_reply_is_not_auto_and_notes_who(monkeypatch, support_isolated):
    """客服官轉達真人的話（relay_from）：那一則玩家看不是自動的；客服頁多一則內部註記「轉達自 <ID>」；flags 記一列 relay；admin_flag 不動。
    cookie 身分帶 relay_from 一律不看。"""
    c = player()
    tid = ticket(c).json()["id"]
    s = staffer(monkeypatch)
    desk, h = _desk(monkeypatch, support_isolated)
    out = desk.post("/api/support/answer", json={"id": tid, "body": "真人說可以了", "then": "wait", "relay_from": " 4242 "}, headers=h).json()
    assert out["admin_flag"] is False
    # 轉達的那一則是真人的話（不是自動）；「轉達自」那則註記是客服官自己寫的（客服頁標自動）
    assert [(r["body"], r["internal"], r["auto"]) for r in out["replies"]] == [("真人說可以了", False, False), ("轉達自 4242", True, True)]
    mine = c.get("/api/support/mine").json()["tickets"][0]["replies"]
    assert [(r["body"], r["auto"]) for r in mine] == [("真人說可以了", False)]
    sc = store.open_store(support_kit.sidecar(), create=False)
    first = sc.replies(tid, internal=True)[0]
    assert [(f["kind"], f["ref"]) for f in sc.flags(tid)] == [("relay", first["id"])]
    assert sc.relayed(tid) == frozenset({first["id"]})
    out = s.post("/api/support/answer", json={"id": tid, "body": "我自己回", "then": "wait", "relay_from": "4242"}).json()
    assert [r["body"] for r in out["replies"]][-1] == "我自己回" and len(out["replies"]) == 3  # cookie 身分：沒有多一則註記
    assert [f["kind"] for f in sc.flags(tid)] == ["relay"] and out["admin_flag"] is False
    out = desk.post("/api/support/answer", json={"id": tid, "body": "x", "then": "wait", "relay_from": "  "}, headers=h).json()
    assert out["replies"][-1]["auto"] is True and len(sc.flags(tid)) == 1  # 空白當沒有


def test_bot_cannot_answer_a_ticket_waiting_for_a_human(monkeypatch, support_isolated):
    """T 波（PM）：玩家按了找真人，客服官（token）回覆並等、回覆並結單一律被拒、不寫任何東西；
    內部註記（then=admin）與帶 relay_from 的轉達照舊；cookie 的真人客服不受影響。"""
    from tianxia.features.support import rules
    c = player()
    tid = ticket(c).json()["id"]
    s = staffer(monkeypatch)
    desk, h = _desk(monkeypatch, support_isolated)
    assert c.post("/api/support/human", json={"id": tid}).status_code == 200
    sc = store.open_store(support_kit.sidecar(), create=False)
    before = (len(sc.replies(tid, internal=True)), sc.flags(tid))
    for then in ("wait", "close"):
        r = desk.post("/api/support/answer", json={"id": tid, "body": "我來回", "then": then}, headers=h)
        assert (r.status_code, r.json()) == (400, {"error": rules.HUMAN_WAITING})
    assert (len(sc.replies(tid, internal=True)), sc.flags(tid)) == before
    assert desk.post("/api/support/answer", json={"id": tid, "body": "請真人看", "then": "admin"}, headers=h).status_code == 200
    out = desk.post("/api/support/answer", json={"id": tid, "body": "真人說可以了", "then": "wait", "relay_from": "4242"}, headers=h)
    assert out.status_code == 200 and "真人說可以了" in [r["body"] for r in out.json()["replies"]]
    out = s.post("/api/support/answer", json={"id": tid, "body": "我是真人", "then": "close"})
    assert out.status_code == 200 and out.json()["replies"][-1]["body"] == "我是真人"


def test_bot_cannot_close_a_ticket_waiting_for_a_human(monkeypatch, support_isolated):
    """第 219 批：玩家按了找真人，客服官（token）結單也被拒、同一句 HUMAN_WAITING、什麼都不寫；
    cookie 的真人客服照舊結得了；沒按找真人的單客服官照舊結得了。"""
    from tianxia.features.support import rules
    c = player()
    tid = ticket(c).json()["id"]
    other = ticket(c, body="另一件事").json()["id"]
    s = staffer(monkeypatch)
    desk, h = _desk(monkeypatch, support_isolated)
    assert c.post("/api/support/human", json={"id": tid}).status_code == 200
    sc = store.open_store(support_kit.sidecar(), create=False)
    before = (sc.ticket(tid)["status"], len(sc.replies(tid, internal=True)), sc.flags(tid))
    assert before[0] != rules.CLOSED
    r = desk.post("/api/support/close", json={"id": tid}, headers=h)
    assert (r.status_code, r.json()) == (400, {"error": rules.HUMAN_WAITING})
    assert (sc.ticket(tid)["status"], len(sc.replies(tid, internal=True)), sc.flags(tid)) == before
    out = s.post("/api/support/close", json={"id": tid})
    assert out.status_code == 200 and sc.ticket(tid)["status"] == rules.CLOSED
    out = desk.post("/api/support/close", json={"id": other}, headers=h)
    assert out.status_code == 200 and sc.ticket(other)["status"] == rules.CLOSED


def test_support_json_never_contains_bot_word(monkeypatch, support_isolated):
    """假人看不出來：客服的每一條回應（清單、單、自己的單、找真人、自動結單、回覆）整串都沒有 bot 這個字（大小寫都不行）。"""
    c = player()
    tid = ticket(c).json()["id"]
    s = staffer(monkeypatch)
    desk, h = _desk(monkeypatch, support_isolated)
    bodies = [
        desk.post("/api/support/answer", json={"id": tid, "body": "自動的", "then": "wait", "relay_from": "77"}, headers=h),
        desk.post("/api/support/answer", json={"id": tid, "body": "再一則", "then": "wait"}, headers=h),
        desk.get("/api/support/queue", headers=h), s.get("/api/support/queue"), s.get(f"/api/support/ticket/{tid}"),
        c.get("/api/support/mine"), c.post("/api/support/human", json={"id": tid}), s.post("/api/support/sweep", json={}),
        desk.post("/api/support/sweep", json={}, headers=h), c.get("/api/main"), s.get("/api/main"),
    ]
    for r in bodies:
        assert r.status_code == 200, r.request.url
        assert b"bot" not in r.content.lower(), r.request.url


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
