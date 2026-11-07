"""guide 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import time
import pytest
import server
from tianxia.characters import open_characters
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory, game,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


# ── 引導小改版（新手引導重做設計第八節）─────────────────────────


def test_main_view_sends_the_guide_box_and_skipping_hides_it(client):
    """全新角色走序章：遇險的事件在眼前時沒有對話框；拜師之後 /api/main 帶著師父第 2 步的話（不用點開任何東西）；
    略過新手引導後就沒有了。"""
    main = _player(client, prologue=True)["main"]
    assert main["guide"] is None  # 還沒遇到師父
    for option in ("choice:0", "choice:0"):  # 遇險、拜師
        main = client.post("/api/choose", json={"id": option}).json()["main"]
    tutorial = server.CONTENT.tutorial
    step = tutorial.steps[1]
    assert main["guide"] == {
        "speaker": tutorial.speaker, "key": step.id, "scene": "", "text": step.text, "line": step.line,
        "done": main["guide"]["done"], "end": False, "pending": False, "glow": [],
    }  # glow：入伍段「出一次力」那一步才有東西（FB-093）。key 是這一步的 id：網頁記收起記它；pending 標這一句是不是「先把眼前的「…」了結」，網頁預設把它收成一行（FB-076）
    assert tutorial.speaker == "師父" and step.id == "p2_apprentice"
    client.post("/api/do/skip_tutorial", json={})
    assert client.get("/api/main").json()["guide"] is None


def test_guide_ack_closes_the_outro(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.tutorial, "outro", "去闖吧。")  # 正式內容的結語是空的（新手引導計畫三換成碰到才說）
    _player(client, prologue=True)
    game = server.game_for("沈青衫")
    game.state.player.location = server.CONTENT.scenario.start_location
    game.state.pending_event = None
    game.state.player.tutorial_step = len(server.CONTENT.tutorial.steps)
    game.state.player.guide_outro = True
    open_characters().save(game.state)
    assert client.get("/api/main").json()["guide"]["end"] is True
    client.post("/api/do/guide_ack", json={})
    assert client.get("/api/main").json()["guide"] is None


def test_a_hint_goes_out_in_the_guide_box_and_guide_ack_closes_it(client, monkeypatch):
    """碰到才說（新手引導計畫三）：排著的提示就是 /api/main 的 guide（end 的框、key 是那一條的 id），按「知道了」收掉。
    正式內容還沒有提示表：這裡給一條。"""
    from tianxia.models import HintDef, Hints

    monkeypatch.setattr(server.CONTENT, "hints", Hints(hints=[HintDef(id="h_merge", by="mentor", text="意境可以合。")]))
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.tutorial_step = len(server.CONTENT.tutorial.steps)
    game._hint("h_merge")
    open_characters().save(game.state)
    box = client.get("/api/main").json()["guide"]
    assert (box["speaker"], box["text"], box["key"], box["end"]) == ("想起師父說過", "意境可以合。", "h_merge", True)
    client.post("/api/do/guide_ack", json={})
    assert client.get("/api/main").json()["guide"] is None
    assert open_characters().load("沈青衫").player.hints_seen == {"h_merge"}


def test_hints_off_toggles_from_the_settings_even_while_the_clock_is_paused(client):
    """設定頁的「不再提示」（新手引導計畫三，F8）：狀態帶 hints_off；賽季時鐘暫停中也照做（跟匿名一樣是畫面設定），不然勾了被擋下、
    勾選框卻已經打勾。"""
    _player(client)
    assert "hints_off" in server.MAIN_ACTIONS and "hints_off" in server.PAUSE_OK_ACTIONS
    assert client.get("/api/main").json()["status"]["hints_off"] is False
    out = client.post("/api/do/hints_off", json={"value": True}).json()
    assert out["main"]["status"]["hints_off"] is True
    assert open_characters().load("沈青衫").player.hints_off is True
    assert server.game_for("沈青衫").world.pause_clock(time.time())
    out = client.post("/api/do/hints_off", json={"value": False})
    assert out.status_code == 200 and out.json()["main"]["status"]["hints_off"] is False
    assert open_characters().load("沈青衫").player.hints_off is False


def test_view_orders_is_accepted_and_leaves_a_new_players_box_alone(client):
    """入伍段第一步的「軍令卡出現在畫面上」（新手引導計畫二）：網頁送 /api/do/view_orders。還沒投靠的人送了什麼也不會發生，框照舊。"""
    main = _player(client)["main"]
    posted = client.post("/api/do/view_orders", json={})
    assert posted.status_code == 200
    assert posted.json()["main"]["guide"] == main["guide"] == client.get("/api/main").json()["guide"]
