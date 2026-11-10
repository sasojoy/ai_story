"""管理者的門（第二輪第 90 批）：五條路由與 13 個工具都打「不是管理者」（三條路由與 13 個工具同一條迴圈，reset_password 另一條），少一道都紅；管理者走得通的 accounts、reset_password 各一條。
權限檢查的字是從 server.py 照抄的，這裡逐字鎖；`/admin` 本來就不擋（資料都在 /api/admin* 那幾條）。"""
import pytest
import server
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content

TOOLS = ("open_season", "end_season", "next_season", "pause_clock", "resume_clock", "fast_forward", "fire", "push_trend", "schedule", "jump_next",
         "set_trend", "resolve_event", "clear_lock")
WRITTEN_ORDER = ["phase", "battles", "events", "trends", "timetable", "results", "locks", "season_one", "season21", "realign", "default_dates", "mandate_at",
                 "showdowns", "next_has_timetable", "fallen", "seal", "xingshi", "conquest", "mingtie", "divine_out", "llm_queue", "now"]


@pytest.mark.smoke
def test_the_admin_page_is_the_same_page_and_does_not_check_anyone(client):
    page = client.get("/admin")
    assert page.status_code == 200 and page.text == client.get("/").text


def test_every_admin_door_refuses_a_player(client):
    _player(client)
    assert client.get("/api/admin").status_code == 403, "/api/admin"
    assert client.post("/api/admin/player", json={"name": "沈青衫"}).status_code == 403, "/api/admin/player"
    assert client.post("/api/admin/accounts", json={"q": "shen"}).status_code == 403, "/api/admin/accounts"
    for op in TOOLS:
        out = client.post(f"/api/do/{op}", json={"id": "x", "key": "y", "at": 1.0, "hours": 1, "amount": 1, "value": 1})
        assert out.status_code == 400 and out.json() == {"error": "只有管理者能這麼做。"}, op


def test_reset_password_refuses_a_player_and_leaves_the_password_alone(client):
    _player(client)
    out = client.post("/api/admin/reset_password", json={"target": "shen_01", "temp": "temp-pass"})
    assert out.status_code == 200 and out.json() == {"message": "（只有管理者能重設密碼。）"}
    client.post("/api/logout")
    assert client.post("/api/login", json={"login": "shen_01", "password": "temp-pass"}).status_code != 200
    assert client.post("/api/login", json={"login": "shen_01", "password": "secret-pw"}).status_code == 200


def test_the_shell_table_is_gone():
    assert not hasattr(server, "ADMIN_ACTIONS")


def test_an_admin_searches_accounts(client, monkeypatch):
    _player(client)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
    out = client.post("/api/admin/accounts", json={"q": "shen"})
    assert out.status_code == 200 and out.json() == {"rows": [{"login": "shen_01", "character": "沈青衫"}]}


def test_an_admin_resets_a_password(client, monkeypatch):
    _player(client)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
    out = client.post("/api/admin/reset_password", json={"target": "沈青衫", "temp": "temp-pass"})
    assert out.json() == {"message": "已重設 shen_01 的密碼。"}
    client.post("/api/logout")
    assert client.post("/api/login", json={"login": "shen_01", "password": "temp-pass"}).status_code == 200


def test_an_admin_reads_the_keys_in_the_written_order(client, monkeypatch):
    """鍵的先後算行為：照 STATUS_ORDER["admin"]（timetable 那一格回三個鍵）。"""
    _player(client)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
    out = client.get("/api/admin")
    assert out.status_code == 200 and list(out.json()) == WRITTEN_ORDER
