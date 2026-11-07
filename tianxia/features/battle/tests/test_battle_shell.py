"""battle 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import random
from unittest import mock
import pytest
import server
from conftest import at
from tianxia.features.battle import instance as battle_instance
from tianxia.characters import open_characters
from tianxia.sqlite_world import open_world
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _a_showdown_fighter, _journal_titles, _no_landing, _no_preset_recipes, _player, cheap_password_hashing,
    client, fresh_server_memory, game, model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


# ── 全服即時戰鬥：自訂行動 ────────────────────────────────


def test_battle_free_text_shows_and_submits(game):
    definition = server.CONTENT.battles["huangjin_showdown"]
    game.state.player.faction = "guan"  # 劇本分陣營：散人只能觀戰，要先投靠才有得加入
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=320.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        assert server.look(game, server.main_view)["free_text"] == game.battle_free_text_prompt()
        with mock.patch("server.time.time", return_value=after_muster):
            server.battle_text(game, "直取波才首級")
    assert any("直取波才首級" in line for line in game.world.get_battle().narrative_log)


def test_joining_the_muster_tells_the_page_and_is_journaled(client):
    _a_showdown_fighter(client)
    before = _journal_titles()
    out = client.post("/api/choose", json={"id": "battle:join:guan"}).json()
    assert "你加入了這場戰局。" in out["message"]
    assert "黃巾決戰・加入官軍" in out["main"]["latest"]
    assert _journal_titles() == ["黃巾決戰・加入官軍"] + before


def test_joining_late_shows_the_line_on_the_page_data_and_journals_it(client):
    """FB-028 的驗收：「你趕到了戰場，這一回合就能出手。」要在畫面資料裡找得到（回話與江湖紀錄兩處）。"""
    _a_showdown_fighter(client, started=True)
    before = _journal_titles()
    out = client.post("/api/choose", json={"id": "battle:join_late"}).json()
    line = "你趕到了戰場，這一回合就能出手。"
    assert line in out["message"]
    main = client.get("/api/main").json()
    assert line in main["latest"] and line in out["main"]["latest"]
    assert _journal_titles() == ["黃巾決戰・趕到戰場"] + before


def test_a_rounds_action_replies_but_is_not_journaled(client):
    _a_showdown_fighter(client, started=True)
    client.post("/api/choose", json={"id": "battle:join_late"})
    before = _journal_titles()
    options = client.get("/api/main").json()["options"]
    act_id = next(o["id"] for o in options if o["id"].startswith("battle:act:"))
    out = client.post("/api/choose", json={"id": act_id}).json()
    assert "等待其他人" in out["message"]
    assert _journal_titles() == before


def test_the_free_text_action_already_replies_and_is_not_journaled(client):
    """放手一搏走 /api/do/battle_text，回話本來就從 api_do 的 message 回來、前端的 doMain 也會跳出來；不寫江湖紀錄。"""
    _a_showdown_fighter(client, started=True)
    client.post("/api/choose", json={"id": "battle:join_late"})
    before = _journal_titles()
    assert client.get("/api/main").json()["free_text"]
    assert "重傷的是你自己" in client.get("/api/main").json()["free_text_note"]
    out = client.post("/api/do/battle_text", json={"text": "直取波才首級"}).json()
    assert "等待其他人" in out["message"]
    assert _journal_titles() == before


def test_the_free_text_action_is_rated_outside_the_action_lock(client, monkeypatch):
    """試玩回饋 2026-10-08：放手一搏的成功率以前在行動鎖裡評，最多等 in_lock_model_timeout 秒，全服跟著等。現在鎖外評，
    評好的分照樣送進這一回合。"""
    _a_showdown_fighter(client, started=True)
    client.post("/api/choose", json={"id": "battle:join_late"})
    seen = []

    def rate(c, act, faction_name, text, name, target="", sex="男"):
        seen.append((open_world().db.writing(), faction_name, text, name))
        return 73

    monkeypatch.setattr(battle_instance, "score_gamble", rate)
    client.post("/api/do/battle_text", json={"text": "火燒糧草"})
    assert seen == [(False, "官軍", "火燒糧草", "沈青衫")]
    battle = open_world().get_battle()
    assert battle.round.success_rates == {"沈青衫": 73}
    # 只評成功率（Joy 2026-10-13）：劇情等回合結算後一整批寫（narrate_battle），送出時沒有劇情
    assert battle.round.stories == {} and battle.round.sexes == {"沈青衫": "男"}


def test_a_showdown_option_that_is_no_longer_there_still_says_so(client):
    _a_showdown_fighter(client)
    out = client.post("/api/choose", json={"id": "battle:act:safe"}).json()
    assert "此刻無法" in out["message"]


def test_a_fighter_sees_the_finished_showdown_on_the_main_page(client):
    """FB-027：決戰在這個帳號沒連線時收場（只動了資料庫裡的戰鬥），下一次打 /api/main 就補進江湖紀錄與戰報、
    「剛剛」放這一場的卡片，而且存進了角色。"""
    _player(client)
    definition = server.CONTENT.battles["huangjin_showdown"]
    world = open_world()
    world.start_battle(definition, now=0.0)

    def fight(b):
        battle_instance.join_faction(b, "沈青衫", "guan", neili_cap=320.0)
        battle_instance.close_muster(b, definition, random.Random(0))
        while b.phase == "active":
            battle_instance.submit_action(b, "沈青衫", battle_instance.safest_option_tag(b, definition, "沈青衫"))
            battle_instance.resolve_round(b, definition, random.Random(0))

    world.mutate_battle(fight)
    main = client.get("/api/main").json()
    assert main["card"] is not None and "決戰：黃巾決戰" in main["card"] and "你站在官軍" in main["card"]
    assert main["card_id"] is not None
    saved = open_characters().load("沈青衫")
    assert saved.journal[0].title.startswith("黃巾決戰・") and saved.journal[0].battle_id == main["card_id"]
    report = client.get(f"/api/reports?id={main['card_id']}").json()
    assert report["list"][0]["id"] == main["card_id"] and "你站在官軍" in report["detail"]


def test_main_view_drops_the_battle_scene_when_its_own_poll_settles_the_battle():
    """U-06（手機介面自檢 2026-10-31）：場景先讀、選單才把決戰推到收場——以前「剛剛」已經寫了結果，場景還停在最後一回合
    「已送出 0／在場 0」。現在同一次回的場景就回到地點；U-08：上過陣的人全倒下了，這一下就收場，不等回合逾時。"""
    from jianfa_kit import jianfa_game, ready

    game = ready(jianfa_game("week7", name="Rayal"), side="guan", loc="changshe", level=20)
    game.now = 1000.0
    game.admin_start_showdown("changshe_fire", game.now)
    game.choose("battle:join:guan")
    game.now = game.world.get_battle().muster_deadline_real + 1
    game.options()
    assert game.world.get_battle().phase == "active"

    def fall(battle):
        for p in battle.participants.values():
            p.eliminated = True
    game.world.mutate_battle(fall)
    game.now += 5  # 遠不到回合逾時
    view = server.main_view(game)
    assert game.world.get_battle().phase == "ended"
    assert "回合" not in view["scene"] and "在場" not in view["scene"]
    assert "長社" in view["scene"]  # 回到地點描述；結果在「剛剛」與戰報
