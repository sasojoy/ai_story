"""travel 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from unittest import mock
import pytest
import server
from tianxia import atlas
from tianxia.characters import open_characters
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    DASH, HURRY, ME, _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory, game,
    model_breaker_closed, save_dir, scheduler_off, season_already_open, told,
)

pytestmark = pytest.mark.whole_content


def test_travel_sets_off_or_stays_on_the_map_and_says_why(client):
    _player(client)
    game = server.game_for("沈青衫")
    out = client.post("/api/travel", json={"place": game.state.player.location}).json()
    assert out["arrived"] is False and out["reason"] and out["map"]["selected"] == game.state.player.location
    nearby = [o["id"][5:] for o in client.get("/api/main").json()["options"] if o["id"].startswith("move:")]
    out = client.post("/api/travel", json={"place": nearby[0]}).json()
    assert out["arrived"] is True
    assert game.state.player.journey.path == [nearby[0]]  # 步行：在路上


def test_a_stale_travel_button_says_which_event_is_pending(client):
    """打開輿圖之後才冒出事件、按了舊的按鈕：留在輿圖，寫出原因，回傳的輿圖也帶 to_jianghu（FB-063）。"""
    _player(client)
    game = server.game_for("沈青衫")
    pending = server.CONTENT.events[next(iter(server.CONTENT.events))]
    game.state.pending_event = pending.id
    open_characters().save(game.state)  # 每次進鎖都從資料庫重讀角色，只改記憶體的話請求看不到
    out = client.post("/api/travel", json={"place": "yingshui"}).json()
    assert out["arrived"] is False and out["reason"] == f"先回江湖頁處理「{pending.title}」"
    assert out["map"]["travel"][0]["to_jianghu"] is True


def test_travel_dashes_when_asked(client):
    _player(client)
    game = server.game_for("沈青衫")
    minutes = atlas.routes(game.state, game.content)["yingshui"].minutes
    cost = atlas.travel_stamina(game.content, minutes, "dash", saving=0.0)  # 新角色沒騎馬
    assert client.post("/api/travel", json={"place": "yingshui", "mode": "dash"}).json()["arrived"] is True
    assert game.state.player.location == "yingshui"
    assert game.state.player.stamina == game.content.config.stamina_max - cost


def test_a_dash_departs_only_from_the_dash_menu(client):
    _player(client)
    game = server.game_for("沈青衫")
    start = game.state.player.location
    assert "move:yingshui:dash" in [o["id"] for o in client.get("/api/main", headers=DASH).json()["options"]]
    client.post("/api/choose", json={"id": "move:yingshui:dash"})  # 沒帶走法：步行的選單上沒有這個 id
    assert game.state.player.location == start and game.state.player.journey is None
    client.post("/api/choose", json={"id": "move:yingshui:hurry"}, headers=HURRY)  # 拿掉的走法：哪個選單上都沒有
    assert game.state.player.location == start and game.state.player.journey is None
    minutes = atlas.leg_minutes(game.content, start, "yingshui")
    client.post("/api/choose", json={"id": "move:yingshui:dash"}, headers=DASH)
    assert game.state.player.location == "yingshui" and game.state.player.journey is None  # 疾行立刻到
    cost = atlas.travel_stamina(game.content, minutes, "dash", saving=0.0)  # 新角色沒騎馬
    assert game.state.player.stamina == game.content.config.stamina_max - cost


# ── 路上（路上設計第三節）──────────────────────────────


def test_on_the_road_the_page_is_told_so_and_can_turn_back(client):
    _player(client)
    assert client.get("/api/main").json()["on_road"] is False
    client.post("/api/choose", json={"id": "move:yingshui"})
    main = client.get("/api/main").json()
    assert main["on_road"] is True  # 頁面照它放輿圖、修練、煉製三個捷徑
    assert "road:back" in [o["id"] for o in main["options"]]
    assert "路上可以折返" in main["scene"]
    with mock.patch("server.time.time", return_value=server.time.time() + 6 * 3600):  # 早就到了：捷徑收起來、回到平常的選單
        main = client.get("/api/main").json()
    assert main["on_road"] is False and "act:explore" in [o["id"] for o in main["options"]]


def test_turning_back_follows_the_move_mode_header(client):
    _player(client)
    game = server.game_for("沈青衫")
    start = game.state.player.location
    t0 = server.time.time()
    with mock.patch("server.time.time", return_value=t0):
        client.post("/api/choose", json={"id": "move:yingshui"})
    with mock.patch("server.time.time", return_value=t0 + 60):  # 走了一分鐘才掉頭：不是剛出發就折返（那種立刻回原地，FB-025）
        back = [o for o in client.get("/api/main", headers=DASH).json()["options"] if o["id"].startswith("road:back")]
        assert [o["id"] for o in back] == ["road:back:dash"] and "疾行" in back[0]["label"]
        client.post("/api/choose", json={"id": "road:back:dash"})  # 沒帶走法：步行的選單上沒有這個 id
        assert game.state.player.journey.path == ["yingshui"]
        client.post("/api/choose", json={"id": "road:back:dash"}, headers=DASH)
    assert game.state.player.journey is None and game.state.player.location == start


def test_the_map_arranges_travel_while_on_the_road(client):
    _player(client)
    game = server.game_for("沈青衫")
    start = game.state.player.location
    client.post("/api/choose", json={"id": "move:yingshui"})
    view = client.get(f"/api/map?place={start}").json()
    assert view["selected"] == start and view["travel"][0]["enabled"] is True  # 剛離開的那一站：就是折返
    assert view["travel"][0]["label"] == "步行（立刻到）"  # 剛出發：當下就回到原地（FB-025）
    out = client.post("/api/travel", json={"place": start}).json()
    assert out["arrived"] is True
    assert game.state.player.journey is None and game.state.player.location == start


def test_on_the_road_the_page_offers_the_road_tasks(client):
    _player(client)
    client.post("/api/choose", json={"id": "move:yingshui"})
    client.post("/api/choose", json={"id": "road:think"})
    main = client.get("/api/main").json()
    think = next(o for o in main["options"] if o["id"] == "road:think")
    assert think["enabled"] is False and think["label"] == "邊走邊想（想過了，到下一站再說）"
    assert main["status"]["xinde"] == server.CONTENT.config.start_stats["xinde"] + server.CONTENT.config.road_think_xinde


def test_the_other_action_endpoints_notify_once_each(client, told, monkeypatch):
    """/api/do、/api/menxia/*、/api/travel、/api/answer 做完也各通知一次（鎖已經放掉）。"""
    monkeypatch.setattr(server.CONTENT.config, "practice_injury_chance", 0.0)
    _player(client)
    game = server.game_for("沈青衫")
    nearby = next(o["id"][5:] for o in client.get("/api/main").json()["options"] if o["id"].startswith("move:"))
    for path, body in (("/api/do/anonymous", {"value": True}), ("/api/menxia/heal", {})):
        told.clear()
        assert client.post(path, json=body).status_code == 200, path
        assert told == [(ME, "self")], path
    from tianxia.models import FreeTextChoice

    event = next(iter(server.CONTENT.events.values()))
    monkeypatch.setattr(event, "free_text", FreeTextChoice(prompt="自己想辦法……", stat="str"))
    server.act(game, lambda g: setattr(g.state, "pending_event", event.id))
    told.clear()
    with mock.patch.object(server.event_llm, "judge_event_gamble", return_value=server.event_llm.EventVerdict(50)):
        assert client.post("/api/answer", json={"text": "大喊官兵來了"}).status_code == 200
    assert told == [(ME, "self")]  # 評分、擲骰、潤色分好幾次進鎖，但一個請求只通知一次
    server.act(game, lambda g: setattr(g.state, "pending_event", None))  # 事件沒選完的話，輿圖那顆按鈕是灰的
    told.clear()
    assert client.post("/api/travel", json={"place": nearby}).json()["arrived"] is True
    assert told == [(ME, "self")]


def test_a_travel_that_was_refused_does_not_notify(client, told):
    """按舊按鈕、走不成：什麼都沒變，其他分頁不必刷新。"""
    _player(client)
    told.clear()
    here = server.game_for("沈青衫").state.player.location
    assert client.post("/api/travel", json={"place": here}).json()["arrived"] is False
    assert told == []
