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


# ── 放手一搏的回話經 g._log（第 270 批；企劃者 2026-11-26「兩處都修 (Recommended)」）────────────


def _last_round_with_only_my_gamble_left(definition):
    """最後一回合：對面的黃巾真人已經出了招，只差這一位官軍的放手一搏，送出去就收掉決戰。"""
    def setup(b):
        b.round_number = battle_instance.total_rounds(definition) - 1
        battle_instance.submit_action(b, "乙玩家", battle_instance.safest_option_tag(b, definition, "乙玩家"))
    open_world().mutate_battle(setup)


def _one_short_of_the_first_fame_tier():
    """名望差一點就跨進「小有名氣」；這一季的段已經看過（不寫第一次的說明那一則）。"""
    from tianxia import renown
    from tianxia.state import RenownSeen
    s = server.game_for("沈青衫").state  # 同 _a_showdown_fighter：改伺服器手上那一份再存
    bar = renown.fame_bars(server.CONTENT, s.world)[0]
    s.player.stats["fame"] = bar - 1
    s.player.renown_seen = RenownSeen()
    s.player.renown_told = True
    open_characters().save(s)


def test_my_own_gamble_that_closes_the_showdown_gets_the_fame_gap_and_the_rank_up_in_the_same_entry(client, monkeypatch):
    """(a) 自己這一搏收掉決戰：決戰那一則的「名望 +N」後面接「（離「…」還差 M）」，升段的句子與金色籤在同一則，
    這一下的存檔就有、不必等下一次同步；回話也寫進 GameState.log。把 routes.py 的 g._log 拿掉這一條會紅。"""
    from tianxia import journal, renown
    definition = _a_showdown_fighter(client, started=True)
    client.post("/api/choose", json={"id": "battle:join_late"})
    _one_short_of_the_first_fame_tier()
    _last_round_with_only_my_gamble_left(definition)
    monkeypatch.setattr(battle_instance, "score_gamble", lambda *a, **k: 100)
    logged = len(open_characters().load("沈青衫").log)
    out = client.post("/api/do/battle_text", json={"text": "孤身闖陣，奪旗而還"}).json()
    assert open_world().get_battle().phase == "ended"
    saved = open_characters().load("沈青衫")  # 這一下的存檔（不再打 /api/main）
    entry = saved.journal[0]
    assert entry.title.startswith("黃巾決戰・")
    fame = [c for c in entry.changes if c.startswith("名望 +")]
    assert len(fame) == 1 and "（離「名動一方」還差 " in fame[0], entry.changes
    assert renown.UP_FAME.format(title="小有名氣") in entry.lines
    assert journal.renown_mark("小有名氣") in entry.changes
    # 新頁與舊頁畫的那兩格（/api/main 的 card、now）：差距在戰報卡的得失、升段與金色籤在「剛剛」的補充
    assert "還差" in out["main"]["card"]
    assert "小有名氣" in out["main"]["now"] and "名號傳開" in out["main"]["now"]
    assert len(saved.log) > logged and saved.log[-1] == journal.LOG_BREAK


def test_my_own_gamble_in_a_round_that_does_not_close_replies_the_same_and_is_logged(client):
    """(b) 沒收場的回合：回話一字不變（等待其他人），江湖紀錄不多，只多寫進 GameState.log。"""
    _a_showdown_fighter(client, started=True)
    client.post("/api/choose", json={"id": "battle:join_late"})
    before = _journal_titles()
    out = client.post("/api/do/battle_text", json={"text": "直取波才首級"}).json()
    assert out["message"] == "<p>你選擇了行動，等待其他人……</p>\n"
    assert _journal_titles() == before
    log = open_characters().load("沈青衫").log
    assert log[-2:] == ["你選擇了行動，等待其他人……", "\x1e"]


@pytest.mark.parametrize("battle, text, said", [
    (False, "直取波才首級", "（此刻無法這麼做。）"), (True, "   ", "（請先輸入你想做的事。）"),
])
def test_a_gamble_that_is_turned_away_says_the_same_line_and_adds_no_deed(client, battle, text, said):
    """(c) 被擋下（沒有決戰、空白字）：回的那一句照舊，行狀、江湖紀錄、GameState.log 都不多（A 段就回了，到不了 C 段）。"""
    if battle:
        _a_showdown_fighter(client, started=True)
        client.post("/api/choose", json={"id": "battle:join_late"})
    else:
        _player(client)
    before = open_characters().load("沈青衫")
    out = client.post("/api/do/battle_text", json={"text": text}).json()
    assert out["message"] == f"<p>{said}</p>\n"
    saved = open_characters().load("沈青衫")
    assert [e.title for e in saved.journal] == [e.title for e in before.journal]
    assert saved.player.annals == before.player.annals and saved.log == before.log


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
