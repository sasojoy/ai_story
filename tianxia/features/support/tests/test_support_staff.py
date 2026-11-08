"""客服身分（帳號與客服第 211 批；設計 6.2）：名單認帳號（id 或登入名）不認名號，三個來源；客服的四條路由；不是客服 404；
契約：客服身分打所有管理者工具與 /api/admin* 全部被拒；/api/main 只有客服有 support_staff。"""
from __future__ import annotations

import re

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import player, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.features.support import accounts_view, staff
from tianxia.database import open_database

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]

STAFF_ROUTES = (
    ("GET", "/api/support/queue", None),
    ("GET", "/api/support/ticket/1", None),
    ("POST", "/api/support/answer", {"id": 1, "body": "x", "then": "wait"}),
    ("POST", "/api/support/close", {"id": 1}),
)


def _who(login):
    return accounts_view.by_key(open_database(), login)


def test_the_list_takes_ids_and_logins_from_three_sources(monkeypatch, support_isolated):
    player("shen_01", "沈青衫")
    player("Li_02", "李白衣")
    player("wang_03", "王小二")
    config = server.CONTENT.config
    shen, li, wang = _who("shen_01"), _who("li_02"), _who("wang_03")
    assert not any(staff.is_staff(config, w) for w in (shen, li, wang))
    monkeypatch.setattr(config.support, "staff", [str(shen.id)])  # 設定：認 id
    (support_isolated / "support.txt").write_text("# 客服\nLI_02\n", encoding="utf-8")  # .local/support.txt：認登入名、不分大小寫
    monkeypatch.setenv(staff.ENV_VAR, " wang_03 ,")  # 環境變數：逗號分開
    assert all(staff.is_staff(config, w) for w in (shen, li, wang))


def test_the_list_does_not_take_character_names(monkeypatch, support_isolated):
    player()
    config = server.CONTENT.config
    monkeypatch.setattr(config.support, "staff", ["沈青衫"])
    (support_isolated / "support.txt").write_text("沈青衫\n", encoding="utf-8")
    monkeypatch.setenv(staff.ENV_VAR, "沈青衫")
    assert not staff.is_staff(config, _who("shen_01"))
    assert not staff.is_staff(config, None)


def test_a_number_on_the_list_is_only_an_id(monkeypatch, support_isolated):
    """名單寫 id 的數字：登入名取成同一個數字的人不算客服（不然搶註冊登入名就頂了那個 id）。"""
    player("shen_01", "沈青衫")
    player("777", "李白衣")
    config = server.CONTENT.config
    shen, digits = _who("shen_01"), _who("777")
    assert digits.id != 777
    monkeypatch.setattr(config.support, "staff", ["777", str(shen.id)])
    assert staff.is_staff(config, shen) and not staff.is_staff(config, digits)
    monkeypatch.setattr(config.support, "staff", [str(digits.id)])
    assert staff.is_staff(config, digits)


def test_the_file_is_reread_when_it_changes(support_isolated):
    player()
    config = server.CONTENT.config
    path = support_isolated / "support.txt"
    path.write_text("nobody\n", encoding="utf-8")
    assert not staff.is_staff(config, _who("shen_01"))
    path.write_text("nobody\nshen_01\n", encoding="utf-8")
    import os  # noqa: PLC0415

    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 5))
    assert staff.is_staff(config, _who("shen_01"))


def test_staff_sees_queue_and_answers(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c, body="<b>登不進去</b>").json()["id"]
    q = s.get("/api/support/queue").json()
    assert (q["open"], q["waiting"], q["fresh"]) == (1, 0, 1)
    assert [(t["id"], t["character"], t["login"], t["body"]) for t in q["tickets"]] == [(tid, "沈青衫", "shen_01", "<b>登不進去</b>")]
    one = s.get(f"/api/support/ticket/{tid}").json()
    assert one["account"]["login"] == "shen_01" and one["account"]["character"] == "沈青衫" and one["account"]["id"] == 1
    out = s.post("/api/support/answer", json={"id": tid, "body": "已處理", "then": "wait"}).json()
    assert out["status"] == "answered" and [(r["staff"], r["internal"], r["body"]) for r in out["replies"]] == [(True, False, "已處理")]
    q = s.get("/api/support/queue").json()
    assert (q["open"], q["waiting"]) == (0, 1)


def test_staff_closes_and_answer_close(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    a, b = ticket(c).json()["id"], ticket(c).json()["id"]
    assert s.post("/api/support/close", json={"id": a}).json()["status"] == "closed"
    assert s.post("/api/support/answer", json={"id": b, "body": "好了", "then": "close"}).json()["status"] == "closed"
    assert s.get("/api/support/queue").json()["tickets"] == []
    again = s.post("/api/support/answer", json={"id": b, "body": "補一句", "then": "wait"})
    assert again.status_code == 400
    assert s.post("/api/support/close", json={"id": 999}).status_code == 404


def test_staff_asks_an_admin(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    out = s.post("/api/support/answer", json={"id": tid, "body": "請補發 100 元寶", "then": "admin"}).json()
    assert out["admin_flag"] is True and out["status"] == "open" and out["replies"][0]["internal"] is True


def test_answer_refuses_a_bad_then_and_an_empty_body(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    assert s.post("/api/support/answer", json={"id": tid, "body": "x", "then": "delete"}).status_code == 400
    assert s.post("/api/support/answer", json={"id": tid, "body": " ", "then": "wait"}).status_code == 400


def test_non_staff_gets_404_on_staff_routes():
    c = player()
    ticket(c)
    for method, path, body in STAFF_ROUTES:
        got = c.request(method, path, json=body) if method == "POST" else c.get(path)
        assert got.status_code == 404, path
        assert got.json() == {"detail": "Not Found"}


def _admin_paths() -> list[tuple[str, str]]:
    out = []
    for path, methods in server.app.openapi()["paths"].items():
        if path.startswith("/api/admin"):
            out += [(m.upper(), re.sub(r"\{[^}]+\}", "1", path)) for m in methods]
    return out


def test_staff_rejected_by_every_admin_api(monkeypatch):
    """契約（設計 6.2）：客服身分打管理者工具（FEATURE_ADMIN_ACTIONS 每一個 op 的 /api/do/<op>）、動別人存檔的那幾個（PLAYER_ADMIN_ACTIONS）、
    app 上每一條 /api/admin*：全部不是 2xx。"""
    s = staffer(monkeypatch)
    assert s.get("/api/support/queue").status_code == 200  # 真的是客服
    ops = sorted(set(server.FEATURE_ADMIN_ACTIONS) | set(server.PLAYER_ADMIN_ACTIONS))
    paths = _admin_paths()
    assert len(server.FEATURE_ADMIN_ACTIONS) >= 10 and len(paths) >= 4, "掃法壞了"
    passed = {}
    for op in ops:
        got = s.post(f"/api/do/{op}", json={"name": "沈青衫"})
        if 200 <= got.status_code < 300:
            passed[f"/api/do/{op}"] = got.status_code
    for method, path in paths:
        got = s.request(method, path, json=ADMIN_BODIES.get(path, {}) if method == "POST" else None)
        if 200 <= got.status_code < 300 and got.json() != REFUSED_200.get(path):
            passed[path] = got.status_code
    assert not passed


# 拒絕時照舊回 200 的（管理者包原本的寫法，不改）：回的就是拒絕那一句才算被拒
ADMIN_BODIES = {"/api/admin/reset_password": {"target": "kefu_01", "temp": "temp-pass-123"}}
REFUSED_200 = {"/api/admin/reset_password": {"message": "（只有管理者能重設密碼。）"}}


def test_support_staff_only_for_staff(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    assert "support_staff" not in c.get("/api/main").json()
    main = s.get("/api/main").json()
    assert main["support_staff"] is True and main["support_unread"] == 0
    assert main["admin"] is False


def test_staff_needs_password_session(monkeypatch):
    """設計 6.2／4.4（第 204 批拿掉 xfail）：客服權限要這次 session 6 小時內登入或驗過；identity 關著看 session 建立的時間。
    原本 patch 不存在的 SESSIONS.clock，改 patch server.time.time 往後 7 小時（shell.time.time 讀它）。"""
    s = staffer(monkeypatch)
    assert s.get("/api/support/queue").status_code == 200
    real = server.time.time
    monkeypatch.setattr(server.time, "time", lambda: real() + 7 * 3600)  # 7 小時前登入的 session
    assert s.get("/api/support/queue").status_code == 404
