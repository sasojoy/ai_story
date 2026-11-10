import os
import ast
import contextlib
import hashlib
import io
import json
import random
import re
import sys
import threading
import time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import llm_queue
import server
import server_push
import webharness
from conftest import at, old_explore, real_content, season_one_events
from tianxia import atlas
from tianxia.features.battle import instance as battle_instance
from tianxia import calendar
from tianxia.features.companions import companion_agent
from tianxia import database, fight_llm, journal, naming
from tianxia.features.cultivation import art_view
from tianxia import sqlite_world
from tianxia.features.tale import tale
from tianxia import team
from tianxia.accounts import NAME_TAKEN
from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.features.admin import routes as admin_routes
from tianxia.journal import WORLD_NEWS
from tianxia.martial_arts import MartialArt
from tianxia.ollama_client import OllamaClient
from tianxia.sqlite_world import SqliteWorldStore, open_world
from tianxia.state import BotProfile, FigureState, Lock, Rumor, TimelineResult, WorldState
from tianxia.world_state import SharedWorldState, season_length_days
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    DASH, DIALOGUE_TURN, FENG_HUO, HURRY, ME, _ScriptedQueue, _a_player_with_insights, _a_showdown_fighter,
    _ended_showdown, _forger, _js_function, _model, _no_landing, _no_preset_recipes, _nobody_holds_the_lock, _player,
    _seal_duel, _season_one_now, _stand_by_a_figure, _stand_in_a_hall, _tale_store, breaker_clock, cheap_password_hashing,
    client, fresh_server_memory, game, lock_events, model_breaker_closed, save_dir, scheduler_off, season_already_open,
    told,
)

REAL_CHAT_STRUCTURED = OllamaClient.chat_structured  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」，重問的測試要真的


# ── 畫面資料 ────────────────────────────────────────────


def _fixed(event_id: str, week: int, day: float = 0):
    from tianxia.models import TimetableEvent, TimetableOutcome

    return TimetableEvent(id=event_id, week=week, day=day, title=f"{event_id}事", kind="fixed",
                          outcomes={"fixed": TimetableOutcome(text=f"{event_id}事的公告。")})


def test_main_view_bulletin_this_week(monkeypatch):
    """江湖頁那排小標「大事」點開的本週大事：這一週已經發生的大事（Markdown 轉成 HTML），最多 3 則、新的在前。"""
    content = server.CONTENT
    monkeypatch.setattr(content.config, "season_one", True)
    monkeypatch.setattr(content.config, "season_days", 2.5)
    monkeypatch.setattr(content, "timetable", [_fixed("甲", 1), *(_fixed(x, 2, day) for x, day in (("乙", 0), ("丙", 1), ("丁", 2), ("戊", 3)))])
    game = Game.new(content, "測試")
    assert server.main_view(game)["bulletin"] == []
    hour = calendar.cal_hour_seconds(content)
    game.advance(hour)
    bulletin = server.main_view(game)["bulletin"]
    assert len(bulletin) == 1 and "<strong>甲事</strong>" in bulletin[0] and "甲事的公告。" in bulletin[0]
    game.advance(calendar.week_start(2, content) + 3 * 86400 / 33.6 + hour - game.state.world.time)
    bulletin = server.main_view(game)["bulletin"]
    assert [re.search(r"<strong>(.)事</strong>", b).group(1) for b in bulletin] == ["戊", "丁", "丙"]  # 上一週的甲不在


def test_now_card_does_not_repeat_the_big_event_on_the_bulletin(monkeypatch):
    """FB-046：時刻表大事補進江湖紀錄那一則，全文本週大事上已經有了，江湖頁的「剛剛」（now）不再寫一次，
    改放再前面那一則（這裡是開場那一則）；江湖紀錄頁（latest＋journal＋older）照舊從最新一則列起。"""
    content = server.CONTENT
    monkeypatch.setattr(content.config, "season_one", True)
    monkeypatch.setattr(content.config, "season_days", 2.5)
    monkeypatch.setattr(content, "timetable", [_fixed("甲", 1)])
    old_explore(content.config, monkeypatch.setattr)  # 舊探索當手段（同 classic_rules）
    game = Game.new(content, "測試")
    view = server.main_view(game)
    assert "賽季開始" in view["now"] and view["now"] == view["latest"]
    game.advance(calendar.cal_hour_seconds(content))
    assert game.state.journal[0].title == WORLD_NEWS
    view = server.main_view(game)
    assert "甲事的公告。" in view["bulletin"][0]
    assert "甲事的公告。" not in view["now"] and "賽季開始" in view["now"]
    assert "甲事的公告。" in view["latest"]  # 江湖紀錄頁照舊
    game.choose("act:explore")
    view = server.main_view(game)
    assert "探索" in view["now"] and view["now"] == view["latest"]


def test_season_one_off_changes_nothing(game, monkeypatch):
    """開關關著（現在的試玩伺服器）：推進一週，時刻表不跑、狀態列沒有季曆、本週大事是空的。"""
    monkeypatch.setattr(server.CONTENT, "timetable", season_one_events())
    assert server.CONTENT.config.season_one is False
    game.advance(7 * 86400)
    assert game.state.world.timeline == {} and game.state.world.schedule == {}
    view = server.main_view(game)
    assert "calendar" not in view["status"] and "next_event" not in view["status"]
    assert view["bulletin"] == []


@pytest.mark.smoke
def test_main_view_has_everything_the_page_draws(game):
    view = server.look(game, server.main_view)
    assert view["status"]["name"] == "測試"
    assert view["status"]["stamina"] == view["status"]["stamina_max"]
    assert "主線" in view["quest"]
    assert view["scene"].startswith("<p>")
    assert {"id", "label", "enabled"} <= set(view["options"][0])
    assert view["free_text"] is None
    assert view["free_text_note"] is None
    assert view["card"] is None
    assert "minimap" not in view  # 網頁不畫了，不送（全面自檢 S-07）
    assert view["admin"] is False


def test_markdown_from_the_engine_cannot_inject_html():
    assert server.md("**名號** <script>x</script>") == "<p><strong>名號</strong> &lt;script&gt;x&lt;/script&gt;</p>\n"


def test_main_view_sends_the_fronts_only_with_the_switch_on(game, monkeypatch):
    assert "fronts" not in server.look(game, server.main_view)  # 開關關著：江湖頁照舊
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    assert "fronts" not in server.look(game, server.main_view)  # 這一季沒蓋「開」的章：照舊
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))
    view = server.look(game, server.main_view)
    assert [(f["name"], f["value"]) for f in view["fronts"]] == [("潁川汝南", 40), ("南陽", 35), ("冀州", 55)]
    assert view["status"]["stances"] == {"guan": 55, "huang": 45}  # 豪強依附兩軍之一，沒有自己的態勢（割據 2026-10-31 拿掉）


def test_main_view_carries_the_chaos_band_and_which_fronts_are_in_it(game, monkeypatch):
    """FB-065：圖卡要畫亂局帶（兩端讀設定、不寫死在前端）、標出在亂局裡的戰線，態勢那一行的說法也由伺服器給。"""
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    game.world.mutate_season(lambda season: (setattr(season, "season_one", True),
                                             season.trends.update(yingru=35, nanyang=65, jizhou=66)))
    view = server.look(game, server.main_view)
    assert view["status"]["chaos_band"] == {"low": 35, "high": 65}
    assert [(f["name"], f["value"], f["chaos"]) for f in view["fronts"]] == [
        ("潁川汝南", 35, True), ("南陽", 65, True), ("冀州", 66, False)]  # 35 與 65 剛好在邊上：算在亂局裡
    assert view["status"]["stance_notes"] == {"sum": "三條戰線合計"}  # 割據那一句 2026-10-31 拿掉
    assert "割據" not in view["trends"]
    game.world.mutate_season(lambda season: season.trends.update(yingru=34, nanyang=66, jizhou=66))
    view = server.look(game, server.main_view)
    assert [f["chaos"] for f in view["fronts"]] == [False, False, False]


def test_main_view_has_no_chaos_data_with_the_switch_off(game):
    status = server.look(game, server.main_view)["status"]
    assert "chaos_band" not in status and "stance_notes" not in status


def test_admin_choices_follow_the_switch(game, monkeypatch):
    """管理者推大勢的下拉選單：開關關著跟 beta 一樣；開關打開但這一季沒蓋章也一樣；這一季蓋了「開」的章時
    列三條戰線，不列黃巾聲勢（由戰線合成；割據 2026-10-31 拿掉）。"""
    def listed():
        return [t["id"] for t in server.look(game, lambda g: admin_routes.admin_choices(server, g))["trends"]]

    assert listed() == ["huangjin", "yuxi"]
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    assert listed() == ["huangjin", "yuxi"]
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))
    assert listed() == ["yingru", "nanyang", "jizhou", "yuxi"]


def test_admin_choices_leave_out_the_beta_battle_and_thresholds_in_season_one(game, monkeypatch):
    """計畫 T8：開戰與觸發大事的下拉選單照 Game.admin_battles／admin_fires——這一季蓋了「開」的章時，
    beta 那場決戰、四個黃巾聲勢門檻與舊玉璽鏈不列；開關關著照舊。"""
    def listed(kind):
        return [x["id"] for x in server.look(game, lambda g: admin_routes.admin_choices(server, g))[kind]]

    assert "huangjin_showdown" in listed("battles") and "huangjin_60" in listed("events")
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))
    assert listed("battles") == ["changshe_fire", "guangzong"]  # 三場大戲；宛城要等第 3 週結算才知道開哪一版，先不列（PM 2026-10-05）
    assert not {"huangjin_50", "huangjin_60", "huangjin_80", "huangjin_10"} & set(listed("events"))
    # 玉璽一：舊玉璽鏈的門檻與董卓奪璽第一季也關掉（玉璽碎片設計 11.2 第 1 條），開關關著時照舊列（上面第一行）
    assert not {"yuxi_50", "yuxi_100", "dongzhuo_takes_shard"} & set(listed("events"))


def test_menxia_view_falls_back_to_no_person_for_an_unknown_one(game):
    view = server.look(game, lambda g: server.menxia_view(g, "沒這個人"))
    assert view["person"] is None and view["person_card"] is None
    assert view["roster"][0]["key"] == "player"
    assert "forge_line" in view and "per_craft" not in view and "craft_line" not in view
    assert "materials" not in view and "arts" not in view  # 煉製頁不再列素材、修練頁不再從舊功法庫畫（改畫 owned_arts）


def _clue_items(game):
    return server.look(game, server.menxia_view)["clue_items"]


def test_menxia_view_lists_the_foreshadow_items_in_the_content_order(monkeypatch):
    """煉製頁素材旁的「伏筆物品」（T7b）：開關開著、這一季蓋了章、手上有的才列；每樣名字加數量，照 foreshadows.json 的順序，
    不列數量 0 的。沒有說明句：兩份文件都沒寫，不自己編。"""
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    game = Game.new(server.CONTENT, "測試")  # 開關開著時開的季：蓋了章
    assert _clue_items(game) == []  # 手上什麼都沒有：整塊不出現
    game.state.player.clue_items = {"fs_oil": 1, "fs_reeds": 3, "fs_ash": 0}
    assert _clue_items(game) == [
        {"id": "fs_reeds", "name": "葦束", "count": 3},
        {"id": "fs_oil", "name": "膏油", "count": 1},
    ]


def test_menxia_view_hides_the_foreshadow_items_when_the_switch_is_off(game, monkeypatch):
    """開關關著（現在的試玩伺服器）：就算手上有東西也是空的。開關是後來才開的：這一季沒蓋章，一樣是空的。"""
    game.state.player.clue_items = {"fs_oil": 1}
    assert not server.CONTENT.config.season_one and _clue_items(game) == []
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)  # 這一季開季時開關是關的：不會跑
    assert _clue_items(game) == []


def test_menxia_endpoint_carries_the_foreshadow_items(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    _player(client)
    game = server.game_for("沈青衫")
    assert client.get("/api/menxia").json()["clue_items"] == []
    game.state.player.clue_items = {"fs_witness": 1}
    open_characters().save(game.state)  # 資料庫是唯一的真實來源：進鎖先重讀
    assert client.get("/api/menxia").json()["clue_items"] == [{"id": "fs_witness", "name": "宮中的證人", "count": 1}]
    monkeypatch.setattr(server.CONTENT.config, "season_one", False)
    assert client.get("/api/menxia").json()["clue_items"] == []


def test_map_view_selects_your_location_by_default(game):
    view = server.look(game, lambda g: server.map_view(g, "沒這層", None))
    assert view["layer"] == server.DEFAULT_LAYER
    assert view["selected"] == game.state.player.location
    assert 'data-loc="' in view["svg"]


def test_reports_view_is_empty_with_no_battles(game):
    view = server.look(game, lambda g: server.reports_view(g, None))
    assert view["list"] == [] and view["selected"] is None
    assert "還沒有戰報" in view["detail"]
    assert view["tale_id"] is None  # 不是決戰（這裡一場都沒有）就沒有戰記
    assert server.tale_view(1) == {"status": "none"}  # 沒這一場：網頁不畫那一顆


def test_the_tale_cover_falls_back_until_the_art_arrives(tmp_path, monkeypatch):
    """封面：那一場自己的圖 > 攻城共用 > 通用 > 那一區的地點圖 > 事件插圖。"""
    battles = server.CONTENT.battles
    assert server.tale_cover(battles["wancheng_yi"]) == "/static/img/tale/wancheng.webp"  # 企劃者的圖：宛城甲乙共用一張
    assert server.tale_cover(battles["siege_luoyang"]) == "/static/img/tale/siege.webp"
    monkeypatch.setattr(server, "TALE_COVER_DIR", tmp_path)
    assert server.tale_cover(battles["changshe_fire"]) == "/static/img/places/yingru.webp"
    assert server.tale_cover(None) == "/static/img/events/tale.webp"
    (tmp_path / "siege.webp").write_bytes(b"x")
    assert server.tale_cover(battles["siege_jizhou"]) == "/static/img/tale/siege.webp"
    (tmp_path / "default.webp").write_bytes(b"x")
    assert server.tale_cover(battles["changshe_fire"]) == "/static/img/tale/default.webp"
    (tmp_path / "changshe_fire.webp").write_bytes(b"x")
    assert server.tale_cover(battles["changshe_fire"]) == "/static/img/tale/changshe_fire.webp"


def test_the_chronicle_index_waits_for_the_switch(client, tmp_path, monkeypatch):
    """江湖史最上面那排戰記：TALES_IN_CHRONICLE 關著一律空的（誰看得到等 Joy 定）；開了就一場一筆、新的在前。"""
    _player(client)
    _tale_store(tmp_path, monkeypatch)
    first = _ended_showdown(open_world())
    assert server.tale_round() == first
    assert client.get("/api/main").json()["tales"] == []
    monkeypatch.setattr(server, "TALES_IN_CHRONICLE", True)
    listed = client.get("/api/main").json()["tales"]
    assert listed == [{"battle_id": first, "title": "黃巾決戰", "season": open_world().get_season_number(),
                       "result": "黃巾大勝"}]


def test_status_text_still_reads_the_same(game):
    text = game.status_text()
    assert text.startswith("### 測試　·　散人　第1級")
    assert "⚡ 體力 250/250" in text


# ── 開局、讀檔 ────────────────────────────────────────────


def test_open_game_creates_a_new_character_when_no_save_exists():
    assert server.open_game("新玩家").state.player.name == "新玩家"


def test_open_game_loads_an_existing_save():
    g = server.open_game("新玩家")
    g.state.player.stamina = 42.0
    open_characters().save(g.state)
    assert server.open_game("新玩家").state.player.stamina == 42.0


def test_open_game_backs_up_a_corrupt_save_and_starts_fresh(save_dir):
    characters = open_characters()
    with characters.db.transaction() as conn:
        conn.execute(
            "INSERT INTO characters (key, name, is_bot, faction, data) VALUES ('壞掉的', '壞掉的', 0, NULL, '{not json')"
        )
    g = server.open_game("壞掉的")
    assert g.state.player.name == "壞掉的"
    with characters.db.snapshot() as conn:
        assert conn.execute("SELECT COUNT(*) FROM character_backups").fetchone()[0] == 1
    assert any("已備份" in line for line in g.state.log)


def test_open_game_refuses_a_name_that_belongs_to_a_server_bot(save_dir):
    g = server.open_game("周泰安")
    g.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    open_characters().save(g.state)
    with pytest.raises(server.GameError, match="這個名號已有人使用"):
        server.open_game("周泰安")
    with open_characters().db.snapshot() as conn:  # 假人的存檔不能被當成壞檔備份走
        assert conn.execute("SELECT COUNT(*) FROM character_backups").fetchone()[0] == 0


def test_one_character_has_one_game_however_many_times_it_logs_in():
    assert server.game_for("沈青衫") is server.game_for("沈青衫")


# ── 行動鎖 ────────────────────────────────────────────


def test_every_action_takes_the_cross_program_action_lock(game, monkeypatch):
    """伺服器假人設計第九節：伺服器的行動鎖要讓假人程式也看得到，不能只是程式內的執行緒鎖。"""
    calls = []
    real = SqliteWorldStore.action_lock

    def spy(self, timeout=None):
        calls.append(timeout)
        return real(self, timeout)

    monkeypatch.setattr(SqliteWorldStore, "action_lock", spy)
    server.act(game, lambda g: None)
    server.look(game, server.main_view)
    assert calls == [None, None]


def test_act_saves_the_character(game, save_dir):
    assert not open_characters().exists("測試")
    server.act(game, lambda g: g.choose("act:explore"))
    assert open_characters().exists("測試")


# ── 資料庫是唯一的真實來源：動作出錯撤回、同一角色開兩個分頁（線上架構設計 5.1）────────────────


def _bind(name: str, login: str) -> TestClient:
    """把已經存好的角色綁到一個新帳號並登入（像管理者用 scripts/set_password.py 綁角色那樣），回傳登入好的 client。"""
    store = server.account_store()
    store.register(login, "secret-pw")
    store.bind_character(login, name)
    tab = TestClient(server.app)
    tab.post("/api/login", json={"login": login, "password": "secret-pw"})
    return tab


@pytest.mark.parametrize("next_step", ["act", "tick"])
def test_a_failed_action_does_not_leave_its_changes_for_the_next_save(client, next_step):
    """動作中途丟例外時資料庫整筆撤回，但伺服器記憶體裡那份 Game（GAMES）已經被就地改過：下一個動作
    （包括每十秒的計時器）不能把那份做到一半的狀態存回去。"""
    _player(client)
    game = server.game_for("沈青衫")
    before = game.state.player.stats["silver"]

    def broken(g):
        g.state.player.stats["silver"] = 4242
        g.state.player.team.append("zhangliang")
        raise RuntimeError("動作中途出錯")

    with pytest.raises(RuntimeError):
        server.act(game, broken)
    assert open_characters().load("沈青衫").player.stats["silver"] == before  # 資料庫撤回了
    if next_step == "act":
        server.act(game, lambda g: None)
    else:
        client.get("/api/main")
    stored = open_characters().load("沈青衫").player
    assert stored.stats["silver"] == before and stored.team == []
    assert game.state.player.stats["silver"] == before and game.state.player.team == []


def test_a_failed_menxia_action_does_not_leave_its_changes_for_the_next_save(client, monkeypatch):
    _player(client)
    game = server.game_for("沈青衫")

    def broken(g, body):
        g.state.player.team.append("zhangliang")
        raise RuntimeError("動作中途出錯")

    monkeypatch.setitem(server.MENXIA_ACTIONS, "heal", broken)
    with pytest.raises(RuntimeError):
        client.post("/api/menxia/heal", json={})
    monkeypatch.setitem(server.MENXIA_ACTIONS, "heal", lambda g, body: None)
    client.post("/api/menxia/heal", json={})
    assert open_characters().load("沈青衫").player.team == [] and game.state.player.team == []


def test_two_games_of_one_character_do_not_overwrite_each_other(game):
    """同一個角色有兩份 Game（伺服器裡只會有一份，但資料庫才是真實來源，不靠這一點）：A 做了動作並存檔，
    B 接著動作之前先重讀，不會把 A 的改動蓋回去。"""
    server.act(game, lambda g: None)
    tab_b = server.open_game("測試")
    server.act(game, lambda g: g.state.player.stats.__setitem__("silver", 777))
    server.act(tab_b, lambda g: None)
    assert open_characters().load("測試").player.stats["silver"] == 777
    assert tab_b.state.player.stats["silver"] == 777


def _game_clock(monkeypatch, start: float = 1000.0) -> list[float]:
    """GAMES 的閒置時鐘（server._game_clock）換成手撥的；掃描的節流從頭算。"""
    clock = [start]
    monkeypatch.setattr(server, "_game_clock", lambda: clock[0])
    monkeypatch.setattr(server, "_games_swept", None)
    return clock


def _stored_view(game):
    """這一份 Game 進鎖重讀之後的角色（不含賽季）與江湖畫面的狀態列：丟掉重建的那一份要跟它一模一樣。"""
    return server.look(game, lambda g: (g.state.model_dump(exclude={"world"}), server.main_view(g)["status"]))


def test_an_idle_game_is_dropped_and_rebuilt_the_same(client, monkeypatch):
    """審查 S-06：GAMES 不是只進不出。閒置滿 GAME_IDLE_SECONDS 的那一份下一次 game_for 時丟掉，再有請求時照資料庫重建，
    角色、畫面跟丟掉之前一模一樣；之後的動作照常存得進去。"""
    clock = _game_clock(monkeypatch)
    _player(client)
    old = server.game_for("沈青衫")
    server.act(old, lambda g: g.state.player.stats.__setitem__("silver", 321))
    clock[0] += server.GAME_IDLE_SECONDS - 1
    assert server.game_for("沈青衫") is old  # 還沒閒置滿
    clock[0] += server.GAME_IDLE_SECONDS
    assert client.get("/api/main").status_code == 200  # 有請求進來：先丟掉，再照資料庫重建
    rebuilt = server.GAMES["沈青衫".casefold()]
    assert rebuilt is not old
    assert _stored_view(rebuilt) == _stored_view(old)  # 丟掉的那一份照資料庫重讀：兩份一模一樣
    out = client.post("/api/choose", json={"id": "act:rest"})
    assert out.status_code == 200
    assert open_characters().load("沈青衫").player.stats["silver"] == 321


def test_a_game_in_use_is_not_dropped(client, monkeypatch):
    """請求拿著的那一份（進鎖、出鎖都算用過；三段式的 B 段在鎖外等模型）不算閒著：最後一次用過之後才開始算。
    管理者快轉過的那一份（advanced_real 只留在那一份上）也不丟。"""
    clock = _game_clock(monkeypatch)
    _player(client)
    game = server.game_for("沈青衫")
    clock[0] += server.GAME_IDLE_SECONDS - 10
    server.look(game, lambda g: None)  # 這一下用過
    clock[0] += 20
    assert server.game_for("沈青衫") is game
    game.advanced_real = 3600.0  # 管理者快轉推過的那一截
    clock[0] += 10 * server.GAME_IDLE_SECONDS
    assert server.game_for("沈青衫") is game


def test_dropping_idle_games_leaves_a_renamed_game_under_its_new_name(client, monkeypatch):
    """易名帖把 GAMES 換到新名號底下（mall routes）：用到的時間跟著那一份 Game 走，新名號底下照樣會被丟、照樣重建得回來。"""
    clock = _game_clock(monkeypatch)
    _player(client)
    game = server.game_for("沈青衫")
    with server._GAMES_LOCK:
        server.GAMES.pop("沈青衫".casefold())
        server.GAMES["新名號"] = game
    clock[0] += server.GAME_IDLE_SECONDS + 1
    server.game_for("別人")
    assert "新名號" not in server.GAMES


def test_two_sessions_of_one_character_keep_each_others_changes(client):
    """同一個帳號開兩個分頁（兩個 session）：A 改了存檔，B 下一個動作保留 A 的改動、畫面也看得到。
    A 的改動經由另一份 Game 存進資料庫（不是 GAMES 裡共用的那一份）：兩個 session 共用同一份 Game，
    改動只在那一份的記憶體裡的話，不重讀也看得到，就測不到「資料庫才是真實來源」。"""
    _player(client)
    tab_b = TestClient(server.app)
    tab_b.post("/api/login", json={"login": "shen_01", "password": "secret-pw"})
    assert tab_b.get("/api/main").json()["status"]["anonymous"] is False  # B 已經用過共用的那份 Game
    server.act(server.open_game("沈青衫"), lambda g: g.set_anonymous(True))  # A 的分頁存好的
    out = tab_b.post("/api/choose", json={"id": "act:rest"}).json()
    assert out["main"]["status"]["anonymous"] is True
    assert open_characters().load("沈青衫").player.anonymous is True


def test_a_render_only_view_shows_what_the_database_says(game):
    """只重畫、不存檔的畫面（look）也先重讀：別的地方改了角色，這裡畫出來的是資料庫裡的樣子；
    state.world 也要重新指向共用賽季，不然畫面讀到的是空的賽季。"""
    server.act(game, lambda g: None)
    tab_b = server.open_game("測試")
    server.act(tab_b, lambda g: g.state.player.stats.__setitem__("xinde", 321))
    assert server.look(game, server.menxia_view)["xinde"] == 321
    assert game.state.world.storyline  # 指到共用賽季了


@pytest.mark.parametrize("handler", ["act", "tick", "look"])
@pytest.mark.parametrize("stale", ["location", "pending_event"])
def test_a_stored_character_with_stale_references_is_cleaned_and_not_bricked(stale, handler):
    """內容改版後，存檔裡可能留著已經不存在的地點、事件。Game 建構時會清掉，但進鎖重讀換進來的是資料庫那一列：
    重讀之後也要再清一次，不然這個角色在每一個請求（包括十秒一次的計時器）都會當機。"""
    old = Game.new(server.CONTENT, "老玩家")
    if stale == "location":
        old.state.player.location = "no_such_place"
    else:
        old.state.pending_event = "no_such_event"
    open_characters().save(old.state)
    if handler == "tick":
        assert _bind("老玩家", "old_hand").get("/api/main").status_code == 200
        state = open_characters().load("老玩家")
    else:
        game = server.open_game("老玩家")
        if handler == "act":
            server.act(game, lambda g: None)
            state = open_characters().load("老玩家")
        else:
            server.look(game, server.main_view)  # 只讀不存：記憶體裡那一份要是清乾淨的
            state = game.state
    assert state.player.location in server.CONTENT.locations
    assert state.pending_event is None


def test_the_sync_done_while_preparing_a_dialogue_is_saved(game):
    """對話備料的 A 段會同步時間（共用賽季的推進照樣寫進資料庫，江湖大事也寫進這個角色的江湖紀錄）：A 段結束要把角色存起來，
    不然 C 段的 act 一重讀，A 段同步出來的紀錄就被資料庫裡舊的那一份蓋掉了。"""
    server.act(game, lambda g: None)
    later = game.state.last_real + 200 * 3600  # 實測：這麼久之後同步會冒出「江湖大事」
    with mock.patch("server.time.time", return_value=later):
        server.prepare_dialogue(game, "act:socialize")
        stored = open_characters().load("測試")
        assert stored.model_dump_json() == game.state.model_dump_json()  # A 段結束，資料庫與記憶體一致
        assert any(e.title == WORLD_NEWS for e in stored.journal)
        server.act(game, lambda g: None)  # C 段的 act 重讀
    assert any(e.title == WORLD_NEWS for e in game.state.journal)


def test_a_game_that_was_never_saved_keeps_its_in_memory_character(game):
    """剛建好、還沒存過的角色資料庫裡沒有：重讀不能把它換成空的。"""
    assert not open_characters().exists("測試")
    assert server.look(game, server.menxia_view)["xinde"] == server.CONTENT.config.start_stats["xinde"]
    assert game.state.player.name == "測試"


@pytest.mark.parametrize("path", ["/api/main", "/api/menxia"])  # act、look
def test_a_reload_never_hands_a_bots_save_to_a_player(client, path):
    """資料庫裡這個名號的那一列變成假人的存檔時（例如壞檔備份走之後，假人程式拿同一個名號建了角色），
    重讀不能把假人的角色換進真人的 Game：跟 open_game 一樣回「名號已有人使用」（伺服器假人設計第五節）。"""
    _player(client)
    game = server.game_for("沈青衫")
    bot = Game.new(server.CONTENT, "沈青衫")
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    bot.state.player.stats["silver"] = 4242
    open_characters().save(bot.state)
    out = client.get(path)
    assert out.status_code == 400 and out.json() == {"error": NAME_TAKEN}
    assert game.state.player.bot is None and game.state.player.stats["silver"] != 4242
    assert open_characters().load("沈青衫").player.bot is not None  # 假人的存檔原樣留著


# ── 登入與角色（HTTP）────────────────────────────────────


def test_register_then_create_a_character_enters_the_game(client):
    out = client.post("/api/register", json={"login": "Shen_01", "password": "secret-pw", "again": "secret-pw"})
    assert out.json() == {"stage": "create"}
    assert server.COOKIE in out.cookies
    out = client.post("/api/character", json={"name": "沈青衫"}).json()
    assert out["stage"] == "game"
    assert out["main"]["status"]["name"] == "沈青衫"
    assert out["main"]["admin"] is False
    assert open_characters().exists("沈青衫")
    assert server.account_store().get("shen_01").character == "沈青衫"
    assert client.get("/api/me").json()["stage"] == "game"


def test_without_a_login_the_game_is_closed(client):
    assert client.get("/api/me").json() == {"stage": "login"}
    assert client.get("/api/main").status_code == 401
    assert client.post("/api/choose", json={"id": "act:explore"}).status_code == 401
    assert client.post("/api/character", json={"name": "沈青衫"}).status_code == 401


def test_a_login_without_a_character_cannot_play_yet(client):
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    assert client.get("/api/main").status_code == 409
    assert client.post("/api/character", json={"name": "  "}).json() == {"error": "請先輸入你的名號。"}


def test_login_with_a_character_goes_straight_in(client):
    _player(client)
    client.post("/api/logout")
    assert client.get("/api/me").json() == {"stage": "login"}
    out = client.post("/api/login", json={"login": "SHEN_01", "password": "secret-pw"}).json()
    assert out["stage"] == "game"


def test_a_login_survives_a_server_restart(client):
    """審查 S-10：登入狀態在資料庫，伺服器重開（記憶體裡的角色快取、連線全清掉）同一個 cookie 照樣進得去；登出之後就不認。"""
    _player(client)
    token = client.cookies.get(server.COOKIE)
    server.GAMES.clear()
    database.close_all()
    again = TestClient(server.app)
    again.cookies.set(server.COOKIE, token)
    assert again.get("/api/me").json()["stage"] == "game"
    with database.open_database().snapshot() as conn:  # 資料庫裡只有雜湊
        stored = [row[0] for row in conn.execute("SELECT token_hash FROM sessions")]
    assert stored and token not in stored
    again.post("/api/logout")
    assert again.get("/api/me").json() == {"stage": "login"}


def _register(client, login, headers=None):
    return client.post("/api/register", json={"login": login, "password": "secret-pw", "again": "secret-pw"}, headers=headers or {})


def test_one_address_registers_at_most_five_accounts_an_hour(client, monkeypatch):
    clock = [1_000.0]
    monkeypatch.setattr(server.time, "time", lambda: clock[0])
    for i in range(server.REGISTER_LIMIT):
        assert _register(client, f"user_{i}").json()["stage"] == "create"
    over = _register(client, "user_x")
    assert over.status_code == 400 and over.json() == {"error": server.TOO_MANY_REGISTERS}
    assert server.account_store().get("user_x") is None
    clock[0] += server.REGISTER_WINDOW
    assert _register(client, "user_x").json()["stage"] == "create"  # 過了一小時又可以


def test_failed_registrations_do_not_count(client):
    for _ in range(server.REGISTER_LIMIT + 2):
        _register(client, "沈")  # 格式不對
    assert _register(client, "shen_01").json()["stage"] == "create"


def test_behind_the_tunnel_each_visitor_counts_on_their_own(monkeypatch):
    """走 cloudflared 進來時直接連線的一端是本機，照 CF-Connecting-IP 分開算；不是本機連進來的帶那個標頭也不算數。"""
    local = TestClient(server.app, client=("127.0.0.1", 50000))
    for i in range(server.REGISTER_LIMIT):
        assert _register(local, f"a_{i}", {"CF-Connecting-IP": "203.0.113.5"}).json()["stage"] == "create"
    assert _register(local, "a_x", {"CF-Connecting-IP": "203.0.113.5"}).json() == {"error": server.TOO_MANY_REGISTERS}
    assert _register(local, "b_0", {"CF-Connecting-IP": "198.51.100.7"}).json()["stage"] == "create"
    outside = TestClient(server.app, client=("192.0.2.9", 50000))
    for i in range(server.REGISTER_LIMIT):
        _register(outside, f"c_{i}", {"CF-Connecting-IP": f"10.0.0.{i}"})
    assert _register(outside, "c_x", {"CF-Connecting-IP": "10.0.0.99"}).json() == {"error": server.TOO_MANY_REGISTERS}


def _set_cookie(response) -> str:
    return next(v for k, v in response.headers.items() if k == "set-cookie" and v.startswith(server.COOKIE))


def test_the_cookie_is_secure_on_https_and_plain_on_local_http(monkeypatch):
    monkeypatch.delenv(server.PUBLIC_URL_ENV, raising=False)
    local = TestClient(server.app, base_url="http://127.0.0.1:7861", client=("127.0.0.1", 50000))
    assert "secure" not in _set_cookie(_register(local, "plain_1")).lower()
    tunnel = {"X-Forwarded-Proto": "https", "CF-Connecting-IP": "203.0.113.5"}
    assert "secure" in _set_cookie(_register(local, "tunnel_1", tunnel)).lower()
    monkeypatch.setenv(server.PUBLIC_URL_ENV, "https://tianxiadashi.com")
    assert "secure" not in _set_cookie(_register(local, "plain_2")).lower()  # 主機在這台電腦上開 http 照樣登入得了
    lan = TestClient(server.app, base_url="http://192.168.1.20:7861", client=("192.168.1.30", 50000))
    assert "secure" not in _set_cookie(_register(lan, "lan_1")).lower()  # --lan 的區網也是 http
    public = TestClient(server.app, base_url="http://tianxiadashi.com", client=("127.0.0.1", 50000))
    assert "secure" in _set_cookie(_register(public, "public_1", {"CF-Connecting-IP": "203.0.113.9"})).lower()


def test_login_errors_read_the_same(client):
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    wrong = client.post("/api/login", json={"login": "shen_01", "password": "wrong-pw"})
    nobody = client.post("/api/login", json={"login": "nobody", "password": "secret-pw"})
    assert wrong.status_code == nobody.status_code == 400
    assert wrong.json() == nobody.json() == {"error": "帳號或密碼不對。"}


def test_register_checks_the_repeated_password_and_the_format(client):
    out = client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-px"})
    assert out.json() == {"error": "兩次輸入的密碼不一樣。"}
    out = client.post("/api/register", json={"login": "沈", "password": "secret-pw", "again": "secret-pw"})
    assert out.json() == {"error": "帳號只能用英文字母、數字、底線，3～20 字。"}
    assert server.account_store().get("shen_01") is None


def test_a_bot_name_a_player_name_and_an_admin_name_are_refused_with_the_same_words(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "admins", ["掌門"])
    bot = server.open_game("周泰安")
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    open_characters().save(bot.state)
    _player(TestClient(server.app), "first", "沈青衫")
    client.post("/api/register", json={"login": "second", "password": "secret-pw", "again": "secret-pw"})
    answers = [client.post("/api/character", json={"name": name}).json() for name in ("周泰安", "沈青衫", "掌門")]
    assert answers == [{"error": "這個名號已有人使用。"}] * 3
    assert server.account_store().get("second").character is None


def test_famous_people_and_figures_in_the_content_are_refused_with_the_same_words(client):
    """FB-004：真人不能取名人或遊戲人物的名號；訊息跟名號被用掉時一字不差，不透露是哪一份名單。"""
    figure = next(iter(server.CONTENT.characters.values())).name
    client.post("/api/register", json={"login": "first", "password": "secret-pw", "again": "secret-pw"})
    for name in ("曹操", figure):
        assert client.post("/api/character", json={"name": name}).json() == {"error": "這個名號已有人使用。"}
    assert server.account_store().get("first").character is None


def test_names_with_invisible_characters_or_too_long_are_refused(client):
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    for bad in ("Ray​al", "‮Rayal", "名" * 17):
        assert client.post("/api/character", json={"name": bad}).json() == {"error": server.BAD_NAME}
    assert server.account_store().get("shen_01").character is None


def test_full_width_letters_count_as_the_same_name(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "admins", ["Rayal"])
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    assert client.post("/api/character", json={"name": "Ｒａｙａｌ"}).json() == {"error": "這個名號已有人使用。"}


def test_change_password(client):
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})

    def change(old, new, again):
        return client.post("/api/password", json={"old": old, "new": new, "again": again}).json()["message"]

    assert change("wrong-pw", "new-secret", "new-secret") == "舊密碼不對。"
    assert change("secret-pw", "new-secret", "new-secreX") == "兩次輸入的密碼不一樣。"
    assert change("secret-pw", "123", "123") == "密碼至少 6 字。"
    assert change("secret-pw", "new-secret", "new-secret") == "密碼已更新。"
    server.login("shen_01", "new-secret")


def test_changing_the_password_keeps_this_device_and_logs_out_the_others(client):
    # PM 2026-10-31：改密碼時同一個帳號別的裝置登出，改的這一台不必重登
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    other = server.SESSIONS.create("shen_01")  # 另一台裝置
    out = client.post("/api/password", json={"old": "secret-pw", "new": "new-secret", "again": "new-secret"})
    assert out.json() == {"message": "密碼已更新。"}
    assert server.SESSIONS.get(client.cookies.get(server.COOKIE)) == "shen_01"
    assert server.SESSIONS.get(other) is None


def test_register_and_change_password_never_hash_while_holding_the_write_lock(client, monkeypatch):
    """scrypt 很慢：註冊、改密碼不另外包一層交易（帳號的每個方法自己就是一筆交易，雜湊在進交易之前算好），
    不然算雜湊的那段時間全服玩家與假人程式都拿不到寫入權。"""
    from tianxia import accounts

    real = accounts.hash_password
    holding = []

    def spy(password, salt):
        holding.append(database.open_database().writing())
        return real(password, salt)

    monkeypatch.setattr(accounts, "hash_password", spy)
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    out = client.post("/api/password", json={"old": "secret-pw", "new": "new-secret", "again": "new-secret"})
    assert out.json() == {"message": "密碼已更新。"}
    assert len(holding) == 3 and not any(holding)  # 註冊一次、改密碼核對舊的一次、算新的一次


# ── 江湖上的動作（HTTP）────────────────────────────────────


def test_choosing_an_option_plays_it_and_saves(client, monkeypatch):
    old_explore(server.CONTENT.config, monkeypatch.setattr)  # 舊探索當手段（同 classic_rules）
    _player(client)
    out = client.post("/api/choose", json={"id": "act:explore"}).json()
    assert out["main"]["status"]["stamina"] < out["main"]["status"]["stamina_max"]
    assert open_characters().exists("沈青衫")


def test_api_answers_say_where_the_time_went(client):
    """Joy 2026-11-03「探索選完、果出來前就等 5 秒」（雲端量不到）：/api/ 的回應帶 Server-Timing——等鎖幾次與幾毫秒、重讀角色、
    重組畫面、拿著鎖多久、量表那一筆、整個請求，主機用 curl 或開發者工具就看得到。只有數字；推送的長連線不帶。"""
    _player(client)
    timing = client.post("/api/choose", json={"id": "act:explore"}).headers["server-timing"]
    names = [part.split(";")[0] for part in timing.split(", ")]
    assert names[-1] == "total" and {"lock", "reload", "view", "hold"} <= set(names)
    lock = next(part for part in timing.split(", ") if part.startswith("lock;"))
    assert 'desc="n=' in lock and ";dur=" in lock
    assert "server-timing" in client.get("/api/main").headers
    assert "server-timing" not in client.get("/").headers  # 只有 /api/


def test_server_timing_lists_only_what_was_measured():
    assert server.server_timing({}, 0.0123) == "total;dur=12.3"
    assert server.server_timing({"lock": 0.5, "lock_n": 3, "view": 0.02}, 1.0) == 'lock;desc="n=3";dur=500.0, view;dur=20.0, total;dur=1000.0'


def test_every_response_carries_the_csp(client):
    """CSP（帳號與客服第 213 批，設計第三節「CSP 標頭另開小批」）：每個回應都帶同一條 Content-Security-Policy——頁、API、靜態檔、404、
    GameError 的 400、沒登入的 401 都是；Turnstile 要 challenges.cloudflare.com。字面寫死在這裡，防有人悄悄改寬。
    （500 由 Starlette 最外層回、不經 middleware，不帶；那是純文字頁，這裡不打。）"""
    from fastapi.routing import APIRoute

    assert server.CSP == "script-src 'self' https://challenges.cloudflare.com; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
    # 第 209 批（設計第七節「只加一處 middleware」）：同一處多三個標頭；HSTS 不加 preload
    extra = {"strict-transport-security": "max-age=31536000; includeSubDomains", "referrer-policy": "strict-origin-when-cross-origin",
             "x-content-type-options": "nosniff"}
    assert {k.lower(): v for k, v in server.SECURITY_HEADERS.items()} == extra
    gets = sorted(r.path for r in server.app.routes if isinstance(r, APIRoute) and "GET" in r.methods and "{" not in r.path)
    gets += ["/zhuan/nope", "/zhanji/nope", "/static/app.js", "/static/zhuan_page.js", "/static/tale_page.js", "/no/such/page"]
    seen = {}
    for path in gets:
        r = client.get(path)
        seen[path] = r.headers
    seen["POST /api/login"] = client.post("/api/login", json={"login": "nobody_here", "password": "wrong-pw"}).headers
    _player(client)
    for path in ("/api/main", "/admin", "/"):
        seen[f"{path} (登入後)"] = client.get(path).headers
    want = {"content-security-policy": server.CSP, **extra}
    assert {path: got for path, h in seen.items() if (got := {k: h.get(k) for k in want}) != want} == {}
    assert client.get("/static/zhuan_page.js").status_code == 200 and client.get("/static/tale_page.js").status_code == 200

def test_an_option_that_is_not_on_the_menu_does_nothing(client):
    _player(client)
    before = client.get("/api/main").json()["status"]["stamina"]
    out = client.post("/api/choose", json={"id": "act:nonsense"}).json()
    assert out["main"]["status"]["stamina"] == before


def _play_rows():
    with database.open_database().snapshot() as conn:
        days = [dict(r) for r in conn.execute("SELECT owner, season, day, buttons FROM action_counts")]
        firsts = [dict(r) for r in conn.execute("SELECT owner, kind FROM action_firsts")]
    return days, firsts


def test_the_play_log_counts_what_a_real_player_pressed_and_nothing_else(client, monkeypatch):
    """真人量表（減法季批 0）：自己的請求記「這一天上線了」，做成的選項記一次（照 playlog.button_of 歸類），
    不在選單上的不記；交友、求見、對話記第一次跟人物說話。畫面上一個字都沒有（不露給玩家）。"""
    old_explore(server.CONTENT.config, monkeypatch.setattr)  # 舊探索當手段（同上一個測試）
    _player(client)
    out = client.post("/api/choose", json={"id": "act:explore"}).json()
    client.post("/api/choose", json={"id": "act:nonsense"})
    days, firsts = _play_rows()
    assert [(d["owner"], json.loads(d["buttons"])) for d in days] == [("沈青衫", {"act:explore": 1})]
    assert days[0]["season"] >= 1 and firsts == []
    assert not {"action_counts", "buttons", "figure_talk"} & set(out["main"])
    monkeypatch.setattr(server, "choose", lambda game, option_id, text=None: ["（你走上前去。）"])
    client.post("/api/choose", json={"id": "talk:2"})
    days, firsts = _play_rows()
    assert json.loads(days[0]["buttons"]) == {"act:explore": 1, "talk": 1}
    assert firsts == [{"owner": "沈青衫", "kind": "figure_talk"}]


def test_the_play_log_skips_characters_marked_as_bots(game):
    """假人不經過伺服器；萬一經過了（測試、管理工具），量表也不記。"""
    game.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    server._play_seen(game)
    server._play_did(game, "act:train", "free_text")
    assert _play_rows() == ([], [])


def test_an_unknown_action_is_not_found(client):
    _player(client)
    assert client.post("/api/do/nonsense", json={}).status_code == 404
    assert client.post("/api/menxia/nonsense", json={}).status_code == 404


def test_self_creating_an_art_is_gone_for_good(client):
    """自創已經作廢（武學與成長設計 3.8）：伺服器不收這個動作，選單與修練頁也不提供，身上的功夫不變。"""
    _player(client)
    assert "create" not in server.MENXIA_ACTIONS
    out = client.post("/api/menxia/create", json={"kind": "武學", "name": "流雲手"})
    assert out.status_code == 404
    member = open_characters().load("沈青衫").player.member
    assert (member.neigong_id, member.wugong_id) == ("jichu_tuna", "jichu_quanjiao")
    options = client.get("/api/main").json()["options"]
    assert not any("create" in o["id"] for o in options)
    assert "create-skill" not in webharness.app_source()


def test_the_old_craft_endpoints_are_gone(client):
    _player(client)
    assert "craft" not in server.MENXIA_ACTIONS and "forge" in server.MENXIA_ACTIONS
    assert client.post("/api/menxia/craft", json={"materials": ["gang_1", "gang_1"]}).status_code == 404
    assert client.post("/api/craft_line", json={"materials": []}).status_code == 404


def test_the_allocate_buttons_call_what_the_server_has():
    """網頁沒有測試框架：配點鈕（web/app.js）叫的動作與送的欄位要在伺服器的 MAIN_ACTIONS 與狀態資料裡。"""
    js = webharness.app_source()
    assert 'doMain("allocate", { stat:' in js
    assert "allocate" in server.MAIN_ACTIONS
    data = Game.new(server.CONTENT, "測試").status_data()
    for field in re.findall(r"\bs\.(stat_points|stat_cap)\b", js):
        assert field in data


def test_the_points_hint_stays_out_of_the_ellipsized_name_span():
    """收起來的狀態列，名號那一行是單行、超出就「…」：「可配 N 點」寫在那個 <span> 裡（尤其是最後面）會先被長長的「門派・陣營」
    擠掉，玩家看不到有點可配（＋鈕要展開才有）。所以它自己一個不縮的元素（flex: none），放在那個 <span> 外面。"""
    js = webharness.app_source()
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    start = js.index('<div class="who-name">')
    line = js[start:js.index("\n", start)]
    assert line.index("</span>") < line.index("可配") < line.index("more-ico")  # 在名號那個 <span> 後面、展開箭頭前面
    assert 'class="pts"' in line
    rule = re.search(r"\.who-name \.pts \{([^}]*)\}", css)
    assert rule is not None and "flex: none" in rule.group(1)


def _who_name_helper(js: str) -> tuple[str, str]:
    """狀態列名號那一塊的函式（FB-071）拆成（收起來的那一行, 展開的那一段）。"""
    assert "function whoNameHtml" in js
    body = js[js.index("function whoNameHtml"):]
    body = body[:body.index("\n  }\n")]
    first, _, rest = body.partition("\n    if (!S.showMore)")
    assert rest, "whoNameHtml 要先處理收起來的那一行（if (!S.showMore) …）"
    if rest.startswith(" {"):  # 名聲（1B）：收起來的那一段多一行稱號，寫成一個區塊
        collapsed, _, expanded = rest.partition("\n    }\n")
        return collapsed, expanded
    collapsed_line, _, expanded = rest.partition("\n")
    return collapsed_line, expanded


def test_the_expanded_title_is_one_nowrap_span_per_segment():
    """FB-071：展開時頭銜（門派・陣營・頭銜、匿名、第 N 級）是第二行；每一段各自一個不折行的 <span>，「地方豪強」不會從中間折斷，
    只在段與段之間換行。段以「・」切開、再用「・」接回去。"""
    js = webharness.app_source()
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    _, expanded = _who_name_helper(js)
    assert 's.affiliation.split("・")' in expanded and '<span class="who-seg">' in expanded and '.join("・")' in expanded
    assert "匿名" in expanded and "s.level" in expanded
    assert 'class="who-title"' in expanded
    seg = re.search(r"\.who-title \.who-seg \{([^}]*)\}", css)
    assert seg is not None and "white-space: nowrap" in seg.group(1)


def test_the_title_segment_class_is_not_shared_with_any_site_wide_style():
    """FB-071 的瀏覽器驗收抓到：頭銜的每一段原本叫 seg，而 .seg 早就是全站的分段選單（display: flex、下方留 12px），
    每一段都變成整列、一段一行。段落的 class 要獨一無二：style.css 裡凡是提到它的規則都掛在 .who-title 底下，
    沒有任何一條規則是單獨選它的名字（之後加全站樣式也不會撞上）；而且別的地方不會用這個 class。"""
    js = webharness.app_source()
    css = re.sub(r"/\*.*?\*/", "", (server.WEB / "style.css").read_text(encoding="utf-8"), flags=re.S)
    _, expanded = _who_name_helper(js)
    seg_class = re.search(r'<span class="([\w-]+)">\$\{esc\(t\)\}</span>', expanded).group(1)
    assert seg_class != "seg"  # 全站的分段選單
    mentions = [sel.strip() for group in re.findall(r"([^{}]+)\{", css) for sel in group.split(",")
                if re.search(rf"\.{seg_class}\b", sel)]
    assert mentions and all(sel.startswith(".who-title ") for sel in mentions), mentions
    assert js.count(f'class="{seg_class}"') == 1  # 只有頭銜那一處用它


def test_the_expanded_name_line_is_the_name_alone_and_the_points_label_sits_above_the_buttons():
    """FB-071：展開時第一行只有名號與 ▴，「可配 N 點」不再擠在名號那一行，改放在＋鈕上面當那一排的標題（跟＋鈕同一個條件：
    有點才出現）。收起來的那一行照舊帶著 class="pts"（計畫二 T5：放在會「…」的 <span> 外面，不會被擠掉）。"""
    js = webharness.app_source()
    collapsed, expanded = _who_name_helper(js)
    assert 'class="pts"' in collapsed and "可配" in collapsed and "▾" in collapsed
    assert "▴" in expanded and "s.name" in expanded
    assert "可配" not in expanded and 'class="pts"' not in expanded  # 展開的名號那一行與頭銜那一行都不帶它
    start = js.index('S.showMore ? `<div class="more-stats">')
    block = js[start:js.index("</div>` : \"\"}", start)]
    allocate = next(line for line in block.splitlines() if 'data-act="allocate"' in line)
    assert allocate.strip().startswith("${s.stat_points ?")  # 有點可配才有
    assert allocate.index("可配") < allocate.index('class="row alloc"') < allocate.index('data-act="allocate"')
    assert 'class="pts"' in allocate.split('class="row alloc"')[0]  # 標題在那排按鈕的前面


def test_the_five_stat_buttons_share_one_row_and_keep_their_labels_on_one_line():
    """FB-071：五顆＋鈕要在 375 與 360 寬的一排裡放得下（排寬 343／328，五顆加四個 4px 的縫，每顆約 65／62px，
    標籤「＋博聞」是三個全形字 14px ≈ 42px）。只改這一排（.alloc），不動全站的 .btn。"""
    js = webharness.app_source()
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    assert 'class="row alloc"' in js
    row = re.search(r"\.more-stats \.alloc(?:, \.self-stats \.alloc)? \{([^}]*)\}", css)  # 「自己」頁的心得與屬性那一塊（減法季批 1）同一排
    assert row is not None and "gap: 4px" in row.group(1)
    button = re.search(r"\.more-stats \.alloc \.btn(?:, \.self-stats \.alloc \.btn)? \{([^}]*)\}", css)
    assert button is not None and "white-space: nowrap" in button.group(1) and "padding: 6px 2px" in button.group(1)
    site = re.search(r"\n\.btn\.small \{([^}]*)\}", css)
    assert site is not None and "padding: 6px 12px" in site.group(1)  # 全站的小按鈕照舊
    label = re.search(r"\.more-stats \.pts-label \.pts(?:, \.self-stats \.pts-label \.pts)? \{([^}]*)\}", css)  # 跟收起來時那一句同樣的金色粗體 12px
    assert label is not None and "var(--gold)" in label.group(1) and "600 12px" in label.group(1)


def test_no_stale_four_stat_wording_is_left_around_the_status_bar():
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    fun_run = (server.WEB.parent / "scripts" / "fun_run.py").read_text(encoding="utf-8")
    assert "四項各管什麼" not in css and "整季四項都停在 5" not in fun_run


def test_the_allocate_buttons_say_what_each_stat_does():
    """M2：＋鈕底下那一行（五項各管什麼）跟＋鈕畫在同一個條件裡——有點可配才出現；用的是伺服器送的 stat_uses 與
    stat_uses_note，網頁不寫死屬性的用途。"""
    js = webharness.app_source()
    # 狀態列那一排在 app.js（第 64 批起俠客頁那一排切去修練包的檔、接起來排在 app.js 前面，所以這一行照 app.js 找）
    shell = (webharness.WEB / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    start = shell.index('data-act="allocate" data-stat="${esc(key)}" data-glow="allocate"')  # 狀態列那一排（江湖頁頂上提示條攤開的另有一排）
    line = shell[shell.rindex("\n", 0, start):shell.index("\n", start)]
    assert line.strip().startswith("${s.stat_points ?") and "statUsesHtml(s)" in line
    helper = js[js.index("function statUsesHtml"):]
    helper = helper[:helper.index("\n  }\n")]
    assert "s.stat_uses" in helper and "s.stat_uses_note" in helper
    data = Game.new(server.CONTENT, "測試").status_data()
    for field in re.findall(r"\bs\.(stat_uses\w*)\b", js):
        assert field in data


def test_the_news_dot_lights_only_for_a_new_fight_card():
    """配點之後「剛剛」照舊是升級那一場的卡片（計畫二最終審查 M1）：看過那一場的戰報再配點，見聞的紅點不能再亮一次——
    比的是卡片是不是新的一場（card_id），不是「有沒有卡片」。比在 setMain：動作回來的與輪詢拿到的都走它，
    決戰收場的卡片常常是輪詢（sync）補送的，那一場也要亮。"""
    js = webharness.app_source()
    set_main = js[js.index("function setMain"):js.index("// ── 整體 ──")]
    assert "main.card_id" in set_main and "S.unseen = true" in set_main
    apply_main = js[js.index("function applyMain"):js.index("async function choose")]
    assert "S.unseen = true" not in apply_main
    # 輪詢只重畫狀態列與頁面、不重畫分頁列：亮的當下要把紅點補進見聞那一顆（不然要等下一次整頁重畫才看得到）
    assert "paintNewsDot()" in set_main
    paint = js[js.index("function paintNewsDot"):]
    paint = paint[:paint.index("\n  }\n")]
    assert 'data-tab="news"' in paint and 'class="dot"' in paint


def test_the_practice_and_furnace_pages_only_read_and_call_what_the_server_has(game):
    """Task 12：修練頁、煉製頁（web/app.js）讀的欄位都要在 menxia_view 裡、叫的動作都要在 MENXIA_ACTIONS 裡；
    舊煉製的端點、欄位、說法不再出現。網頁沒有測試框架，這條擋住「改了伺服器忘了改網頁」。"""
    js = webharness.app_source()
    pages = js[js.index("function pagePractice"):js.index("// ── 輿圖 ──")]
    keys = set(server.look(game, server.menxia_view))
    assert {"owned_arts", "insights", "holdings", "naming", "slot_cards", "forge_line", "bag"} <= keys
    assert set(re.findall(r"\bx\.(\w+)", pages)) <= keys
    shown = js[js.index("const MENXIA_SHOWN"):]
    shown = shown[:shown.index("};")]
    assert set(re.findall(r'"(\w+)"', shown)) - {"practice", "craft"} <= keys  # 輪詢比對的欄位也都送得到
    called = set(re.findall(r'\bmx\("(\w+)"', js)) | set(re.findall(r"/api/menxia/(\w+)", js)) | set(re.findall(r'data-act="mx" data-op="(\w+)"', js))
    assert {"practice", "forge", "switch", "cultivate", "melt", "melt_insight", "name"} <= called  # heal：療傷鈕 2026-10-25 從俠客頁拿掉（入口是江湖頁 act:heal）
    assert called <= set(server.MENXIA_ACTIONS), called - set(server.MENXIA_ACTIONS)
    for gone in ("/api/craft_line", "/api/menxia/craft", "per_craft", "x.materials", "x.arts", "craftSel", "放入素材", "素材說明"):
        assert gone not in js, gone


def test_the_new_map_has_no_legend_box_and_the_chips_carry_the_colors():
    """輿圖升級（設計第一節）：圖例拿掉；地圖框是夾在狀態列與分頁列之間的整頁一層，寬 900 以上抽屜變右欄。輿圖第三版第 4 批起濾鏡那一排
    也拿掉了（輿圖簡化設計 5.4）；一張到底（2026-10-30）篩選改成浮在搜尋列底下的一排。網頁的版面與樣式對得上，就靠這一條。"""
    js = webharness.app_source()
    css = re.sub(r"/\*.*?\*/", "", (server.WEB / "map.css").read_text(encoding="utf-8"), flags=re.S)
    assert "function legendHtml(" not in js and ".map-legend" not in css and "legend-toggle" not in js
    # 一張到底（企劃者 2026-10-30）：右上角那一欄（我在哪、放大、縮小）沒有了，改成右下兩顆圓鈕（回到我、看整張）；篩選回來了，浮在搜尋列底下
    assert "map-ctl" not in js and ".map-ctl" not in css and 'data-act="map-home"' in js and 'data-act="map-fit"' in js
    assert re.search(r"\n\.mapx \{[^}]*position: fixed", css) and "var(--map-top, 0px)" in css and "var(--map-bottom, 0px)" in css
    assert "@media (min-width: 900px)" in css and "grid-template-columns: 1fr 360px" in css
    assert re.search(r"\n\.mv-fab button \{[^}]*height: 46px;", css) and re.search(r"\n\.mv-q \{[^}]*height: 46px;", css)  # 浮著的鈕與搜尋列：觸控目標夠大
    assert "overflow: clip" in css  # 地圖框不能被 scrollIntoView 捲走（overflow: hidden 的框可以）


def test_a_refused_name_keeps_what_the_player_typed_and_the_pill_tick_does_not_outlive_the_tab():
    js = webharness.app_source()
    submit = js[js.index('form.id === "name-art"'):]
    submit = submit[:submit.index('} // cultivationForm')]  # 名字表單那一段到那個框的結尾（第 85 批：下一個表單 ad-mall-form 搬進商城那一包的畫面檔，排在前面了）
    assert 'await mx("name"' in submit and "again.value = data.name" in submit  # 被拒（表單還在）把字放回去
    assert "legendTick" not in js  # 破境丹不再是勾的：服丹、心得各一顆衝關鈕（Joy 2026-10-21），沒有勾要收


def test_the_fight_card_shows_the_first_round_until_the_player_opens_the_rest():
    """計畫三 Task 1、G6（暫定，等 PM／企劃者拍板）：「剛剛」的戰鬥卡片上「過程」只露第一回合、按「展開過程」才攤開，
    其餘回合一回合一回合浮現；第一屏要留給剛剛、場景與整排行動（企劃者 2026-10-04）。戰報頁照樣整段列出。
    網頁認的是伺服器把「**過程**」轉成的那段 HTML：兩邊對不上的話卡片會整段攤開、把行動擠出第一屏，這條擋住。"""
    from tianxia import battlelog
    from tianxia.state import BattleRecord, Fighter

    record = BattleRecord(
        id=1, time=0, location="湖邊", kind="train", opponent="水寇", ours=[Fighter(name="沈浪", level=1)], tier="大勝",
        our_power=50, difficulty=10, rounds=["第1回合　甲。", "第2回合　乙。", "第3回合　丙。"],
    )
    html = server.md(battlelog.card_text(record))
    js = webharness.app_source()
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    mark = re.search(r'const ROUNDS_MARK = "([^"]*)";', js)
    assert mark is not None and mark.group(1).replace("\\n", "\n") in html and html.count("<ul>") == 1
    assert "fightCard(m.card, m.card_id)" in _js_function(js, "function pageJianghu(")
    assert "roundsFold(card, id)" in _js_function(js, "function fightCard(")
    assert "roundsFold" not in _js_function(js, "function pageNews(")  # 戰報頁整段列出
    assert 'case "rounds-more"' in js and "S.roundsOpen = open ? S.main.card_id : null" in js
    # 收著時只露第一個「不是功效句」的 li（功效句藏起來，Task 4 審查 I-1）：沒有功效句的卡片就是第一個 li，跟以前一樣
    hidden = re.search(r"\.battle-card ul\.rounds:not\(\.open\) > li:not\(\.trait\) ~ li:not\(\.trait\) \{([^}]*)\}", css)
    assert hidden is not None and "display: none" in hidden.group(1)
    assert re.search(r"\.battle-card ul\.rounds > li:nth-child\(2\) \{ animation-delay: [\d.]+s; \}", css)


def test_the_fight_card_head_is_one_heading_and_one_paragraph():
    """標題、時間與類型、結果三行：標題是 h3，底下兩行是同一個 <p>（單換行變 <br />）——手機上只佔一塊的間距，不是三塊
    （battlelog.card_text）。「過程」那一段緊接在後面，網頁認的 ROUNDS_MARK 照舊對得上。"""
    from tianxia import battlelog
    from tianxia.state import BattleRecord, Fighter

    record = BattleRecord(
        id=1, time=0, location="湖邊", kind="train", opponent="水寇", ours=[Fighter(name="沈浪", level=1)], tier="大勝",
        our_power=50, difficulty=10, rounds=["第1回合　甲。"],
    )
    html = server.md(battlelog.card_text(record))
    assert html.startswith(
        "<h3>⚔ 湖邊・對陣 水寇</h3>\n<p>第1天 00:00　遊歷<br />\n<strong>大勝</strong>　我方威力 50　對手難度 10</p>\n"
        "<p><strong>過程</strong></p>\n<ul>"
    )


def _app_functions_in_node(js: str, script: str) -> str:
    """把 app.js 裡幾個不碰畫面的函式（戰鬥卡片的折疊、看完整戰報、數字行）拿出來在 node 裡跑，回傳 script 印出的東西；
    網頁沒有測試框架，這是唯一真的執行過它們的地方。這台沒裝 node 就略過（行為由下面的標記測試擋住兩邊對不上）。
    node 由 tests/kit/webharness.py 跑。"""
    if webharness.NODE is None:
        pytest.skip("沒有裝 node")
    names = ("ROUNDS_MARK", "TALE_MARK", "ROUND_BITS", "reportLink", "TRAIT_LEAD")
    consts = [m.group(0) for name in names if (m := re.search(rf"(?m)^  const {name} = .*;$", js))]
    funcs = [
        _js_function(js, f"function {name}(") + "\n  }"
        for name in ("roundsFold", "withReportLink", "fightCard", "keepGainsWhole", "trailMoves", "compactRound", "foldTraitItems", "foldTraitText")
        if f"function {name}(" in js
    ]
    prelude = 'const S = { roundsOpen: null };\nconst roundsMore = (open) => (open ? "收起過程 ▴" : "展開過程 ▾");\n'
    done = webharness.node(prelude + "\n".join(consts + funcs) + "\n" + script)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_the_report_link_sits_in_the_process_head_row_of_the_fight_card():
    """「看完整戰報 ›」放在「過程 … 展開過程 ▾」那一行的中間（戰鬥卡片壓縮第二輪，PM 2026-10-05），不再接在「結果／得失」句尾
    多撐一行；沒有「過程」那一行的卡片（全服決戰、舊戰報）照舊接在最後一段的句尾。網頁認的是伺服器的 HTML 一律以 </p> 收尾
    （卡片最後一塊永遠是「結果／得失」那一段）與「過程」那一段的 ROUNDS_MARK／TALE_MARK；這條擋住兩邊對不上。"""
    from tianxia import battlelog
    from tianxia.state import BattleRecord, Fighter

    js = webharness.app_source()
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    for narration in ("", "波才刀勢沉猛，你左支右絀。"):
        record = BattleRecord(
            id=1, time=0, location="湖邊", kind="event", opponent="水寇", ours=[Fighter(name="沈浪", level=1)], tier="大勝",
            our_power=50, difficulty=10, rounds=["第1回合　甲。"], narration=narration, notes=["你贏了。"],
        )
        html = server.md(battlelog.card_text(record))
        assert html.endswith("</p>\n") and "<strong>得失</strong>" in html.rsplit("<p>", 1)[1]
    fold = _js_function(js, "function roundsFold(")
    assert '<p class="rounds-head"><strong>過程</strong>${id == null ? "" : reportLink(id)}${more}</p>' in fold  # 連結在過程與展開鈕之間
    assert 'data-act="report"' in js[js.index("const reportLink"):js.index("function roundsFold(")]
    link = _js_function(js, "function withReportLink(")
    assert 'card.lastIndexOf("</p>")' in link and "reportLink(id)" in link  # 沒有過程那一行時的退路
    card = _js_function(js, "function fightCard(")
    assert "roundsFold(card, id)" in card and "withReportLink(card, id)" in card and "folded !== card" in card
    jianghu = _js_function(js, "function pageJianghu(")
    assert "fightCard(m.card, m.card_id)" in jianghu and 'data-act="report"' not in jianghu  # 不再另放一顆
    assert re.search(r"\.battle-card \.report-link \{[^}]*display: inline-block", css)
    # 在「過程」那一行裡不撐高那一行：上下 padding 8px、上下 margin -8px（點擊範圍約 38px 高），展開鈕一樣
    head_link = re.search(r"(?m)^\.battle-card \.rounds-head \.report-link \{([^}]*)\}", css)
    assert head_link is not None and "margin: -8px 0" in head_link.group(1)
    assert "padding: 8px 4px" in re.search(r"(?m)^\.battle-card \.report-link \{([^}]*)\}", css).group(1)
    more = re.search(r"(?m)^\.battle-card \.rounds-more \{([^}]*)\}", css).group(1)
    assert "padding: 8px 2px" in more and "margin: -8px 0" in more and "white-space: nowrap" in more


def test_fight_card_puts_the_report_link_in_the_head_row_or_ends_the_last_paragraph():
    """在 node 裡真的跑 fightCard：有「過程」的卡片（回合清單與大場面一段話兩種）連結只在 .rounds-head 裡、一顆，位置在「過程」
    與展開鈕之間，展開與收著都一樣；沒有「過程」的卡片（全服決戰）接在最後一段的句尾、也是一顆。"""
    import json

    from tianxia import battlelog
    from tianxia.state import BattleRecord, Fighter

    js = webharness.app_source()
    base = dict(
        id=7, time=0, location="湖邊", kind="event", opponent="水寇", ours=[Fighter(name="沈浪", level=1)], tier="大勝",
        our_power=50, difficulty=10, notes=["你贏了。"], changes=["銀兩 +5"],
    )
    cards = {
        "list": server.md(battlelog.card_text(BattleRecord(**base, rounds=["第1回合　甲。", "第2回合　乙。"]))),
        "tale": server.md(battlelog.card_text(BattleRecord(**base, rounds=["第1回合　甲。"], narration="波才刀勢沉猛，你左支右絀。"))),
        "showdown": server.md(battlelog.card_text(BattleRecord(**{**base, "kind": "showdown"}, side="官軍"))),
    }
    script = f"""
    const cards = {json.dumps(cards, ensure_ascii=False)};
    const out = {{}};
    for (const [name, card] of Object.entries(cards)) {{
      S.roundsOpen = null; const shut = fightCard(card, 7);
      S.roundsOpen = 7; const open = fightCard(card, 7);
      out[name] = {{ shut, open, none: fightCard(card, null) }};
    }}
    console.log(JSON.stringify(out));
    """
    out = json.loads(_app_functions_in_node(js, script))
    link = '<button class="linkish report-link" data-act="report" data-id="7">看完整戰報 ›</button>'
    for name in ("list", "tale"):
        for state in ("shut", "open"):
            html = out[name][state]
            assert html.count("看完整戰報") == 1, (name, state)
            head = re.search(r'<p class="rounds-head">(.*?)</p>', html).group(1)
            assert head.startswith("<strong>過程</strong>" + link + '<button class="linkish rounds-more"'), (name, state, head)
            assert "看完整戰報" not in html.rsplit("<p>", 1)[1]  # 結果／得失那一段不再多一個
        assert ' open' in out[name]["open"] and ' open' not in out[name]["shut"]
        assert "看完整戰報" not in out[name]["none"] and "rounds-head" in out[name]["none"]  # 沒有流水號就不放連結
    assert "rounds-head" not in out["showdown"]["shut"]
    last = out["showdown"]["shut"].rsplit("<p>", 1)[1]
    assert out["showdown"]["shut"].count("看完整戰報") == 1 and link + "</p>" in last and "<strong>大勢</strong>" in last
    assert out["showdown"]["none"] == cards["showdown"]  # 沒有流水號：連結也不放


def test_the_folded_first_round_is_two_lines_or_a_numbers_only_line():
    """收著的「過程」第一回合最多兩行、不藏任何數字（戰鬥卡片壓縮第二輪，PM 2026-10-05）：畫好之後量（fitFirstRound，不靠字數），
    放不進兩行又拼得出數字行就整句省略、只留「第1回合　你氣血 -13，對手氣勢 -10……」；認不出來就回 null、整句照常顯示。
    網頁沒有測試框架：樣式與量法用標記擋住，數字行怎麼拼在 node 裡真的跑（沒裝 node 就略過那一段）。"""
    import json

    js = webharness.app_source()
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    fit = _js_function(js, "function fitFirstRound(")
    assert 'querySelector(".battle-card ul.rounds")' in fit and "first.offsetHeight <= 2.5 * lineHeight" in fit  # 兩行加幾 px（拉丁數字混漢字量出來會高一兩 px）不算三行
    assert "compactRound(" in fit and "if (short == null) return;" in fit  # 拼不出數字行就整句照常顯示
    assert 'list.classList.remove("tight")' in fit and 'list.classList.add("tight")' in fit
    assert "fitFirstRound();" in _js_function(js, "function afterPage(")
    assert "fitFirstRound();" in js[js.index('window.addEventListener("resize"'):js.index("const onPhoneChange")]  # 轉向、拉視窗之後重量
    for selector, shown in ((".battle-card ul.rounds .r-short", "none"), (".battle-card ul.rounds.tight:not(.open) .r-full", "none"),
                            (".battle-card ul.rounds.tight:not(.open) .r-short", "inline")):
        found = re.search(r"(?m)^" + re.escape(selector) + r" \{([^}]*)\}", css)
        assert found is not None and f"display: {shown}" in found.group(1), selector  # 展開（.open）時一律露整句
    cases = {
        # 對手先出手：照句子裡出現的先後
        "第1回合　黃巾散兵掄起兵刃猛砸過來，你氣血 -13；驗收卡片以【基礎拳腳】守中帶攻，步步紮實地逼過去，對手氣勢 -10。":
            "第1回合　你氣血 -13，對手氣勢 -10……",
        "第2回合　沈浪以【旋風腿】身形一晃，搶到側面出手，對手氣勢 -18；山賊掄起兵刃猛砸過來，你氣血 -102。":
            "第2回合　對手氣勢 -18，你氣血 -102……",
        # 沒打中的沒有數字，照寫「被對方架開」「被你閃開了」
        "第3回合　山賊掄起兵刃，被你閃開了；沈浪出拳，被對方架開。": "第3回合　被你閃開了，被對方架開……",
        # 劇情戰不扣氣血：對手出手沒有結尾
        "第1回合　山賊掄起兵刃；沈浪出拳，對手氣勢 -12。": "第1回合　對手氣勢 -12……",
        "  第4回合　甲，你氣血 -5；乙，對手氣勢 -34。\n": "第4回合　你氣血 -5，對手氣勢 -34……",
        # 認不出來：整句照常顯示（null），寧可多一行也不藏數字
        "第1回合　甲，你氣血 -13，連擊 ×2；乙，對手氣勢 -10。": None,  # 多了一個沒見過的數字
        "第1回合　甲，你氣血 -13；乙，對手氣勢 -10，士氣 -5。": None,
        "第1回合　劍客7掄起兵刃，你氣血 -4。": None,  # 名字裡的數字也分不出來，一律不縮
        "甲，你氣血 -13；乙，對手氣勢 -10。": None,  # 沒有「第N回合」
        "第1回合　甲乙丙，一路纏鬥。": None,  # 一個結尾也找不到
        "": None,
    }
    script = f"const cases = {json.dumps(list(cases), ensure_ascii=False)}; console.log(JSON.stringify(cases.map(compactRound)));"
    assert json.loads(_app_functions_in_node(js, script)) == list(cases.values())


def test_the_numbers_only_line_keeps_every_number_the_round_wrote(content):
    """真的由 battlelog.round_lines 寫出來的回合（每一種結果、先後手、有沒有扣氣血、有沒有武學），拿去跑 compactRound：
    拼得出來的數字行裡 -N 的數字與順序都跟原句一模一樣，一個都不能少。"""
    import json

    from tianxia import battlelog, rounds

    js = webharness.app_source()
    foe = rounds.Foe(name="山賊", attribute="剛", agility=9.0)
    lines = []
    for ours, theirs in ((0, 0), (0, 24), (18, 0), (7, None), (0, None)):  # 沒打中的兩種寫法，play 很少剛好擲出 0，手排幾回合
        for first in ("ours", "theirs"):
            beats = [rounds.Beat(side="ours", actor="沈浪", art="旋風腿", attribute="快", amount=ours),
                     rounds.Beat(side="theirs", actor="山賊", art=None, attribute="剛", amount=theirs)]
            lines += battlelog.round_lines(content, [rounds.Round(number=2, beats=beats if first == "ours" else beats[::-1])], random.Random(0))
    for seed in range(15):
        rng = random.Random(seed)
        for tier in rounds.ROUNDS:
            for fighters in ([rounds.Fighter(name="沈浪", art="旋風腿", attribute="快"), rounds.Fighter(name="蘇晴", art=None, attribute=None)],
                             [rounds.Fighter(name="沈浪", art=None, attribute=None)]):
                for hp_lost in (None, 0, 37, 480):
                    for our_agility in (3.0, 30.0):
                        played = rounds.play(tier, fighters, foe, our_agility, hp_lost, rng)
                        lines += battlelog.round_lines(content, played, rng)
    assert len(lines) > 1000 and any("，被你閃開了" in line for line in lines) and any("，被對方架開" in line for line in lines)
    script = f"const lines = {json.dumps(lines, ensure_ascii=False)}; console.log(JSON.stringify(lines.map(compactRound)));"
    shorts = json.loads(_app_functions_in_node(js, script))
    for line, short in zip(lines, shorts, strict=True):
        assert short is not None, line  # 名字裡沒有數字，句子的每一種寫法都拼得出來
        assert re.findall(r"-\d+", short) == re.findall(r"-\d+", line), (line, short)
        assert short.startswith(line[:line.index("回合") + 2]) and short.endswith("……") and len(short) < len(line)


def test_the_fight_card_spacing_is_tight_and_only_for_the_fight_card():
    """戰鬥卡片壓縮：打完一場要在第一屏直接按下一顆行動。段距、標題與行高收緊，但只動「剛剛」那張戰鬥卡片
    （.battle-card 只用在它身上，別張卡片與狀態列、行動列一個字不動），字級不縮到比 .order-text 的 13px 還小。
    行高第二輪（PM 2026-10-05）：內文與過程、補充一律 1.45，標題以外沒有低於 1.4 的。"""
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    js = webharness.app_source()
    assert re.findall(r'class="[^"]*battle-card[^"]*"', js) == ['class="card battle-card"']  # 只有「剛剛」那張戰鬥卡片用這個 class

    def rule(selector: str) -> str:
        found = re.search(r"(?m)^" + re.escape(selector) + r" \{([^}]*)\}", css)
        assert found is not None, selector
        return found.group(1)

    assert re.search(r"padding: [0-9]px [0-9]+px", rule(".battle-card")) and "line-height: 1.45;" in rule(".battle-card")
    assert "margin: 3px 0" in rule(".battle-card p")
    assert "font-size: 16px" in rule(".battle-card h3") and "margin: 0 0 1px" in rule(".battle-card h3")
    assert "margin: 1px 0 5px" in rule(".battle-card ul.rounds") and "margin: 1px 0 5px" in rule(".battle-card p.rounds-tale")
    for selector in (".battle-card ul.rounds", ".battle-card p.rounds-tale", ".battle-card .tx-extra"):
        assert "line-height: 1.45;" in rule(selector), selector
    # 這張卡片的規則一律寫在 .battle-card 底下，字級沒有比 13px 小的，行高除了單行的標題都不低於 1.4
    for selectors, body in re.findall(r"(?m)^([^{}\n@/]*\.battle-card[^{}\n]*) \{([^}]*)\}", css):
        assert all(s.strip().startswith(".battle-card") for s in selectors.split(",")), selectors
        assert all(float(px) >= 13 for px in re.findall(r"font-size: ([\d.]+)px", body)), selectors
        if selectors.strip() != ".battle-card h3":
            assert all(float(n) >= 1.4 for n in re.findall(r"line-height: ([\d.]+)", body)), selectors


def test_the_big_fight_account_is_folded_behind_the_same_button():
    """大場面模型寫的過程是一段話（不是回合清單，最多 200 字、手機上約十行）：「剛剛」那張也收起來，只露前兩行，
    按同一顆「展開過程」攤開、展開記在同一個 S.roundsOpen（PM 2026-10-05，Task 2 審查修正 2）；戰報頁照樣整段。
    網頁認的是伺服器把「**過程**＋換行＋一段話」轉成的那段 HTML：兩邊對不上的話整段攤開、把行動擠出第一屏，這條擋住。
    新的 class 只用在戰鬥卡片底下，不跟全站的撞名（.seg 那次的教訓）。"""
    from tianxia import battlelog
    from tianxia.state import BattleRecord, Fighter

    record = BattleRecord(
        id=1, time=0, location="黃巾別部營寨", kind="event", opponent="波才", ours=[Fighter(name="沈浪", level=1)],
        tier="落敗", our_power=50, difficulty=150, rounds=["第1回合　甲。"], narration="波才刀勢沉猛，你左支右絀。" * 8,
    )
    html = server.md(battlelog.card_text(record))
    js = webharness.app_source()
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    mark = re.search(r'const TALE_MARK = "([^"]*)";', js)
    assert mark is not None and mark.group(1).replace("\\n", "\n") in html and "<ul>" not in html
    fold = _js_function(js, "function roundsFold(")
    assert "TALE_MARK" in fold and 'class="rounds-tale' in fold and "S.roundsOpen === id" in fold
    toggle = js[js.index('case "rounds-more"'):]
    assert 'querySelector("ul.rounds, p.rounds-tale")' in toggle[:toggle.index("break;")]
    clamp = re.search(r"\.battle-card p\.rounds-tale:not\(\.open\) \{([^}]*)\}", css)
    assert clamp is not None and "-webkit-line-clamp: 2" in clamp.group(1) and "overflow: hidden" in clamp.group(1)
    selectors = re.findall(r"([^{}\n]*rounds-tale[^{}]*)\{", css)
    assert selectors and all(s.strip().startswith(".battle-card p.rounds-tale") for s in selectors)
    assert not re.search(r"\.tale\b", css + js)  # 沒有別的叫 tale 的 class


def test_a_hostile_big_fight_account_renders_as_one_plain_paragraph_on_the_card():
    """模型寫的過程走伺服器的 Markdown 轉換：連結、圖片、程式碼區塊、引言都不能出現，「結果」「得失」不能被吞進
    程式碼區塊（卡片上它們併成一段「結果／得失」），網頁認的 TALE_MARK 要對得上（Final review Minor 1）。"""
    from tianxia import battlelog, fight_llm
    from tianxia.state import BattleRecord, Fighter

    js = webharness.app_source()
    mark = re.search(r'const TALE_MARK = "([^"]*)";', js).group(1).replace("\\n", "\n")
    hostile = [
        "```\n你一拳打出，對方連退三步。", "![圖](http://example.com/a.png)你出手如電。", "> 你退了一步，咬牙再上。",
        "[點我](http://example.com/x)你收劍而立。", "---", "你**橫掃**一腿。",
    ]
    for text in hostile:
        record = BattleRecord(
            id=1, time=0, location="黃巾別部營寨", kind="event", opponent="波才", ours=[Fighter(name="沈浪", level=1)],
            tier="大勝", our_power=50, difficulty=150, notes=["波才抱拳認輸。"], changes=["銀兩 +5"],
            narration=fight_llm._account(text),  # 整段只有 --- 的話整段拿光：那就沒有過程這一段（卡片不用回合清單頂替）
        )
        html = server.md(battlelog.card_text(record))
        for tag in ("<img", "<a ", "<pre", "<code", "<blockquote", "<h1", "<h2", "<hr", "<ul", "<ol", "<em"):
            assert tag not in html, (text, tag, html)
        assert (mark in html) == bool(record.narration), (text, html)
        # 結果與得失併成同一段（卡片上少一段的間距），沒被吞進任何區塊
        assert "<p><strong>結果</strong>　波才抱拳認輸。　<strong>得失</strong>　" in html, (text, html)


def test_a_trait_line_never_looks_like_a_round_to_the_numbers_only_fold():
    """收著的第一行是功效的句子時，fitFirstRound 量到太高也不會把它縮成數字行：compactRound 只認「第N回合」開頭的句子，
    〔功效名〕開頭的一律回 null、整句照常顯示（寧可多佔一行也不藏字）。S1 的 45 句，每一句配上一個人名與一群人都試過；
    S1 的句子本來就不寫數字（traits.check_traits 擋），所以也不會被當成「還剩數字」的回合。"""
    import json

    js = webharness.app_source()
    lines = []
    for name, pool in server.CONTENT.trait_lines.items():  # 伺服器載的是正式內容
        for text in pool:
            for foe in ("波才", "黃巾散兵"):
                lines.append(f"〔{name}〕" + text.format(who="沈浪", art="基礎拳腳", foe=foe))
    assert len(lines) == 2 * 3 * len(server.CONTENT.trait_lines) == 138  # 23 個功效（意境效果池多八個）
    script = f"const lines = {json.dumps(lines, ensure_ascii=False)}; console.log(JSON.stringify(lines.map(compactRound)));"
    assert json.loads(_app_functions_in_node(js, script)) == [None] * len(lines)


# 收著的「剛剛」卡片（Task 4 審查 I-1）：功效的演出句只在展開與戰報頁才看得到，收著時照舊由第一回合帶頭。
# 網頁沒有 DOM 測試框架：app.js 的標記在 node 裡真的跑（roundsFold／fightCard 認得〔開頭的句子、標成 trait），
# 「收著時看得到什麼」由下面這段小程式照 style.css 的兩條規則算（規則本身由靜態測試釘死，兩邊對得上才算數）。
FOLD_VIEW_SCRIPT = r"""
const cards = __CARDS__;
const strip = (s) => s.replace(/<[^>]+>/g, "").trim();
// 鏡像 style.css：.rounds:not(.open) > li.trait 藏起來、其他的 li 只露第一個；.rounds-tale:not(.open) .trait 藏起來
function view(html, open) {
  const list = /<ul class="rounds( open)?">([\s\S]*?)<\/ul>/.exec(html);
  if (list) {
    const items = list[2].match(/<li[^>]*>[\s\S]*?<\/li>/g) || [];
    const shown = [];
    for (const li of items) {
      const isTrait = /^<li class="trait">/.test(li);
      if (list[1] || open) { shown.push(strip(li)); continue; }
      if (isTrait || shown.length) continue;
      shown.push(strip(li));
    }
    return shown;
  }
  const tale = /<p class="rounds-tale( open)?">([\s\S]*?)<\/p>/.exec(html);
  if (tale) {
    const text = (tale[1] || open) ? tale[2] : tale[2].replace(/<span class="trait">[\s\S]*?<\/span>/g, "");
    return text.split("<br />").map(strip).filter(Boolean);
  }
  return null;
}
const out = {};
for (const [name, card] of Object.entries(cards)) {
  S.roundsOpen = null; const shut = fightCard(card, 7);
  S.roundsOpen = 7; const open = fightCard(card, 7);
  out[name] = { shut: view(shut, false), open: view(open, true), shutHtml: shut, first: null };
  const lead = out[name].shut && out[name].shut[0];
  out[name].compact = lead ? compactRound(lead) : null;
}
console.log(JSON.stringify(out));
"""


def _fold_view(cards: dict[str, str]) -> dict:
    import json

    js = webharness.app_source()
    return json.loads(_app_functions_in_node(js, FOLD_VIEW_SCRIPT.replace("__CARDS__", json.dumps(cards, ensure_ascii=False))))


def _trait_card_record(**extra):
    from tianxia.state import BattleRecord, Fighter

    base = dict(
        id=1, time=0, location="湖邊", kind="train", opponent="水寇", ours=[Fighter(name="沈浪", level=1)], tier="大勝",
        our_power=50, difficulty=10,
        rounds=["第1回合　甲以【穿林腿】身形一晃，搶到側面出手，對手氣勢 -34；水寇掄起兵刃猛砸過來，你氣血 -12。", "第2回合　乙。", "第3回合　丙。"],
        trait_before=["〔先手〕沈浪搶得先機，【穿林腿】出手在前。", "〔險〕沈浪兵行險著，【穿林腿】專走險路。"],
        trait_after=["〔化勁〕沈浪以【基礎吐納】卸去來勢，傷得輕了。"],
    )
    return BattleRecord(**(base | extra))


def test_the_folded_fight_card_leads_with_round_one_and_hides_the_trait_lines():
    """兩句開打前的功效、三個回合、一句之後的功效：收著時看得到的只有第一回合（太長時就是 fitFirstRound 縮成的數字行），
    沒有任何〔開頭的句子；展開之後全部照今天的順序列出（前面的功效句、回合、後面的功效句）。大場面的一段話也一樣：
    收著只剩模型的話（兩行的截斷看到的是它），展開才有功效的句子在前與後。"""
    from tianxia import battlelog

    cards = {
        "list": server.md(battlelog.card_text(_trait_card_record())),
        "tale": server.md(battlelog.card_text(_trait_card_record(narration="波才刀勢沉猛，你左支右絀，硬是撐過了這一輪。"))),
    }
    seen = _fold_view(cards)
    folded, opened = seen["list"]["shut"], seen["list"]["open"]
    assert len(folded) == 1 and folded[0].startswith("第1回合") and not any("〔" in line for line in folded)
    # 清單的一條人在前、招在後（app.js 的 trailMoves，招式與絕學稿案第一節）：「沈浪搶得先機……〔先手〕」
    assert [line[:4] for line in opened] == ["沈浪搶得", "沈浪兵行", "第1回合", "第2回合", "第3回合", "沈浪以【"]
    assert opened[0].endswith("〔先手〕") and opened[-1].endswith("〔化勁〕")
    assert seen["list"]["compact"] == "第1回合　對手氣勢 -34，你氣血 -12……"  # 太高時 fitFirstRound 換成的數字行：第一回合的數字一個沒少
    assert 'ul class="rounds"' in seen["list"]["shutHtml"] and seen["list"]["shutHtml"].count('<li class="trait">') == 3
    tale_shut, tale_open = seen["tale"]["shut"], seen["tale"]["open"]
    assert tale_shut == ["波才刀勢沉猛，你左支右絀，硬是撐過了這一輪。"]
    assert len(tale_open) == 4 and tale_open[0].startswith("〔先手〕") and tale_open[-1].startswith("〔化勁〕")
    assert tale_open[2] == tale_shut[0]  # 展開時模型的話夾在兩句之間，順序跟引擎寫的一樣


def test_the_fold_marks_nothing_when_a_card_has_no_trait_lines_or_only_trait_lines():
    """沒有功效句的卡片（舊戰報、沒有武學的人）一個字都沒變：沒有 trait 標記；全部都是功效句（沒有回合）的卡片不藏，
    免得收著的「過程」是空的；大場面模型的話剛好以〔開頭、又沒有別的行時也一樣不藏。"""
    from tianxia import battlelog

    plain = _trait_card_record(trait_before=[], trait_after=[])
    only = _trait_card_record(rounds=[], trait_before=["〔先手〕甲"], trait_after=["〔乘勝〕乙"])
    odd = _trait_card_record(narration="〔這是模型寫的話〕你左支右絀。", trait_before=[], trait_after=[])
    seen = _fold_view({name: server.md(battlelog.card_text(rec)) for name, rec in (("plain", plain), ("only", only), ("odd", odd))})
    assert 'class="trait"' not in seen["plain"]["shutHtml"] and len(seen["plain"]["shut"]) == 1
    assert 'class="trait"' not in seen["only"]["shutHtml"] and len(seen["only"]["shut"]) == 1  # 沒有回合：第一句功效句照舊領頭
    assert 'class="trait"' not in seen["odd"]["shutHtml"] and seen["odd"]["shut"] == ["〔這是模型寫的話〕你左支右絀。"]


def test_the_trait_lead_mark_is_the_one_the_engine_writes():
    """網頁認功效句靠〔這個開頭（TRAIT_LEAD）：引擎的 battlelog.trait_line 一律以它開頭、回合句型一律不是。"""
    from tianxia import battlelog

    js = webharness.app_source()
    lead = re.search(r'const TRAIT_LEAD = "([^"]*)";', js).group(1)
    assert lead == battlelog.TRAIT_LEAD == "〔"
    for name, pool in server.CONTENT.trait_lines.items():
        for index in range(len(pool)):
            rng = random.Random(0)
            rng.choice = lambda items, index=index: items[index]  # noqa: B023  逐句挑
            assert battlelog.trait_line(server.CONTENT, name, "沈浪", "穿林腿", "山賊", rng).startswith(lead)
    assert not any(line.startswith(lead) for line in _trait_card_record().rounds)


def test_the_folded_fight_card_css_hides_the_trait_lines_and_keeps_one_round():
    """靜態釘住上面那段小程式鏡像的規則：收著時 li.trait 藏起來、其他的 li 只留第一個（前面已有非功效的 li 就藏）；
    大場面那一段話收著時藏 .trait 的 span；fitFirstRound 量的是第一個非功效的 li（不是 firstElementChild）；
    展開、戰報頁不受影響（規則都掛在 :not(.open) 與 .battle-card 底下，戰報頁沒有這張卡片）。"""
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    js = webharness.app_source()
    hide_trait = re.search(r"(?m)^\.battle-card ul\.rounds:not\(\.open\) > li\.trait \{([^}]*)\}", css)
    one_round = re.search(r"(?m)^\.battle-card ul\.rounds:not\(\.open\) > li:not\(\.trait\) ~ li:not\(\.trait\) \{([^}]*)\}", css)
    tale = re.search(r"(?m)^\.battle-card p\.rounds-tale:not\(\.open\) \.trait \{([^}]*)\}", css)
    assert all(rule is not None and "display: none" in rule.group(1) for rule in (hide_trait, one_round, tale))
    assert ":not(:first-child)" not in css[css.index("ul.rounds:not(.open)"):css.index("/* 收著的第一回合最多兩行")]
    fit = _js_function(js, "function fitFirstRound(")
    assert 'querySelector(":scope > li:not(.trait)")' in fit and "firstElementChild" not in fit


def test_the_visible_round_of_a_folded_card_does_not_wait_for_the_hidden_trait_lines():
    """最終審查 M2：延遲是照 nth-child 算的，藏起來的功效句佔著位置，收著時唯一看得到的第一回合（第 2～4 個）要白等 0.25～0.75 秒才浮現
    （以前是 0 秒）。收著時（:not(.open)）每一個「不是功效句」的 li 延遲都是 0（看得到的只有第一個）；展開之後照位置遞增。
    要蓋過 nth-child 那幾條，選擇器的權重要比它們高：這裡照 CSS 的規則算給你看。"""
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    folded = re.search(r"(?m)^(\.battle-card ul\.rounds:not\(\.open\) > li:not\(\.trait\)) \{([^}]*)\}", css)
    assert folded is not None and re.search(r"animation-delay: 0s;?", folded.group(2))

    def specificity(selector: str) -> tuple[int, int]:
        classes = len(re.findall(r"\.[\w-]+", selector)) + len(re.findall(r":(?!not)[\w-]+", selector))  # :not(.x) 算裡面的 .x
        elements = len(re.findall(r"(?<![.:#\w-])[a-z]+\b", selector))
        return classes, elements

    staggers = re.findall(r"(?m)^(\.battle-card ul\.rounds > li:nth-child\([^)]*\)) \{ animation-delay", css)
    assert staggers and all(specificity(folded.group(1)) > specificity(selector) for selector in staggers)
    assert "animation: none !important" in css[css.index("@media (prefers-reduced-motion: reduce)"):]  # 減少動態照舊整站關掉


def test_the_expanded_rounds_fade_in_in_order_however_many_lines_there_are():
    """Task 4 審查 M4：功效的句子加進去之後過程可以有十幾行（3＋5＋8），延遲只寫到第 5 個的話，第 6 個以後會比第 2～5 個先浮現。
    現在每一個位置都有延遲，而且一路不減；減少動態（prefers-reduced-motion）整站關動畫的規則照舊。"""
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    delays = {1: 0.0}
    for number, seconds in re.findall(r"\.battle-card ul\.rounds > li:nth-child\((\d+)\) \{ animation-delay: ([\d.]+)s; \}", css):
        delays[int(number)] = float(seconds)
    catch_all = re.search(r"\.battle-card ul\.rounds > li:nth-child\(n\+(\d+)\) \{ animation-delay: ([\d.]+)s; \}", css)
    assert catch_all is not None and max(delays) == int(catch_all.group(1)) - 1  # 最後一個明寫的位置接著 n+K 的收尾規則
    assert sorted(delays) == list(range(1, max(delays) + 1)) and max(delays) >= 12  # 沒有跳號、至少涵蓋常見的十二行
    ordered = [delays[number] for number in sorted(delays)]
    assert ordered == sorted(ordered) and len(set(ordered)) == len(ordered)  # 嚴格遞增：後面的一定晚浮現
    assert float(catch_all.group(2)) >= ordered[-1]
    assert "animation: none !important" in css[css.index("@media (prefers-reduced-motion: reduce)"):]


def test_the_scroll_card_buttons_sit_two_to_a_row_at_phone_width():
    """卷軸卡（2026-10-06）：卡上兩顆大鈕（練成／改練、修練）各佔一半，字寫兩行（上面動作、下面價錢或機率），
    375px 手機上不用擠成一排三顆；只管卡裡這一排（.acts），不動全站的 .btn。（療傷、閉關那兩格 .tune 2026-10-25 拿掉了）"""
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    acts = re.search(r"\.acts \{([^}]*)\}", css)
    assert acts is not None and "grid-template-columns: 1fr 1fr" in acts.group(1)
    two_lines = re.search(r"\.acts \.btn \{([^}]*)\}", css)
    assert two_lines is not None and "flex-direction: column" in two_lines.group(1)


def test_the_heal_button_says_what_it_costs(client):
    """療傷鈕上寫內傷與價錢：價錢由伺服器照 team.heal_cost 算好送來，網頁不自己算。"""
    _player(client)
    assert client.get("/api/menxia").json()["heal_cost"] == 0
    game = server.game_for("沈青衫")
    game.state.player.member.injury = 23.0
    open_characters().save(game.state)
    assert client.get("/api/menxia").json()["heal_cost"] == 12  # 每 2 點內傷 1 兩，無條件進位


def test_a_new_recipe_is_named_outside_the_action_lock(lock_events):
    game = _forger()
    lock_events.clear()

    def reply(client, messages):
        lock_events.append("generate")
        _nobody_holds_the_lock(game)
        return "旋風腿"

    with _model(reply):
        msgs = server.forge(game, None, ["feng", "huo"])
    assert lock_events == ["enter", "exit", "generate", "enter", "exit"]  # 鎖內備料 → 鎖外取名 → 鎖內登記
    assert open_world().lookup_insight_recipe(FENG_HUO).name == "旋風腿"
    assert any("第一次" in m for m in msgs)


def test_the_forge_naming_outside_the_lock_keeps_its_retry_and_budget(monkeypatch):
    """鎖內的模型呼叫不重問、只試一次（Config.in_lock_model_timeout），鎖外的取名不受影響：真的 chat_structured 格式不對
    照舊重問一趟，一趟最多是預算（60 秒）的一半，每一趟都用複本、原本那個 client 不動。"""
    game = _forger()
    sent = []

    def post(url, json=None, timeout=None):
        sent.append(timeout)

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": "這不是 JSON"}}

        return Reply()

    monkeypatch.setattr("requests.post", post)
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    assert server.prepare_forge(game, None, ["feng", "huo"]) == server.NO_NAME
    assert len(sent) == 2 and all(25 < t <= server.CONTENT.config.naming_budget_seconds / 2 for t in sent)  # 第一趟＋重問
    assert game.client.timeout == server.CONTENT.config.ollama_timeout and game.client.retry is True


def test_each_lock_hold_gets_a_fresh_model_budget(game, monkeypatch, breaker_clock):
    """一次拿鎖期間鎖內的模型呼叫只容忍一次失敗（之後都不叫模型）；server._locked 每次拿到行動鎖先歸零，下一個請求重新有額度。
    失敗之後全服會暫停一陣子（斷路器，見下面那幾個測試），所以第一次失敗之後先把斷路器的時鐘撥過那段時間。"""
    sent = []

    def chat_text(self, messages, **kwargs):
        sent.append(self.timeout)
        raise ConnectionError("模型太慢")

    monkeypatch.setattr(OllamaClient, "chat_text", chat_text)

    def first(g):
        quick = g._quick_client()
        assert quick is not None and quick.timeout == server.CONTENT.config.in_lock_model_timeout
        with pytest.raises(ConnectionError):
            quick.chat_text([])
        assert g._quick_client() is None  # 同一次拿鎖：後面的鎖內呼叫都不叫模型

    def second(g):
        assert g._quick_client() is not None  # 新的一次拿鎖：重新有額度

    server.act(game, first)
    breaker_clock[0] += server.MODEL_BREAKER_SECONDS
    server.act(game, second)
    server.look(game, second)  # 只讀的畫面（look）也是一次拿鎖，一樣先歸零
    server.act(game, first)
    assert len(sent) == 2


# ── 鎖內模型呼叫的全服斷路器（PM 2026-10-05）──────────────────
# 模型掛了的時候，每個玩家的下一個動作都還要在行動鎖裡等一次 15 秒逾時，全服跟著等。一次鎖內呼叫失敗之後，
# 全服 MODEL_BREAKER_SECONDS（180 秒）內每一次拿鎖一開始額度就用完，鎖內直接用固定文字；時間到之後的第一次拿鎖照常叫。


def _model_down(monkeypatch):
    """模型掛了：鎖內的 chat_text 一叫就失敗。回傳送出去的紀錄（每送一次一筆）。"""
    sent = []

    def chat_text(self, messages, **kwargs):
        sent.append(self.timeout)
        raise ConnectionError("模型連不上")

    monkeypatch.setattr(OllamaClient, "chat_text", chat_text)
    return sent


def _ask_the_model_in_the_lock(g):
    """鎖內叫一次模型，跟引擎各處一樣：拿 _quick_client，拿不到（None）就直接用固定文字；失敗照例吞掉、走固定文字。"""
    quick = g._quick_client()
    if quick is not None:
        with contextlib.suppress(Exception):
            quick.chat_text([])


def test_a_failed_in_lock_model_call_trips_the_breaker(game, monkeypatch, breaker_clock, capsys):
    sent = _model_down(monkeypatch)
    server.act(game, _ask_the_model_in_the_lock)
    assert len(sent) == 1
    seen = []
    server.act(game, lambda g: seen.append((g._model_budget.gave_up, g._quick_client())))
    server.look(game, lambda g: seen.append((g._model_budget.gave_up, g._quick_client())))  # 只讀的畫面也是一次拿鎖
    assert seen == [(True, None), (True, None)] and len(sent) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1 and f"{server.MODEL_BREAKER_SECONDS} 秒" in lines[0]
    assert "測試" not in lines[0]  # 不寫是誰（也就看不出是不是假人）


def test_after_the_pause_the_next_hold_asks_again_and_a_new_failure_trips_it_again(
    game, monkeypatch, breaker_clock, capsys,
):
    sent = _model_down(monkeypatch)
    server.act(game, _ask_the_model_in_the_lock)  # 第 1000 秒打開
    breaker_clock[0] += server.MODEL_BREAKER_SECONDS - 0.5
    server.act(game, _ask_the_model_in_the_lock)
    assert len(sent) == 1  # 還差半秒：不叫
    breaker_clock[0] += 0.5
    server.act(game, _ask_the_model_in_the_lock)  # 滿 180 秒：這一次照常叫，又失敗 → 再打開
    assert len(sent) == 2
    server.act(game, _ask_the_model_in_the_lock)
    assert len(sent) == 2  # 又開著了（暫停中的拿鎖不會把時間往後延）
    breaker_clock[0] += server.MODEL_BREAKER_SECONDS
    monkeypatch.setattr(OllamaClient, "chat_text", lambda self, messages, **kwargs: sent.append("ok") or "一句話")
    server.act(game, _ask_the_model_in_the_lock)
    server.act(game, _ask_the_model_in_the_lock)
    assert sent[2:] == ["ok", "ok"]  # 模型回來了：關上之後每一次都照常叫
    trip, close, trip_again, close_again = capsys.readouterr().out.splitlines()  # 打開、關上各印一行
    assert trip == trip_again and close == close_again and trip != close
    assert all(f"{server.MODEL_BREAKER_SECONDS} 秒" in line for line in (trip, close))
    # 這一行在叫模型之前印（讀主畫面也算一次拿鎖），模型還掛著時緊接著就是再打開的那一行：只說下一次再試，不說已經恢復（PM 2026-10-05）
    assert close == f"鎖內的模型呼叫暫停滿 {server.MODEL_BREAKER_SECONDS} 秒，下一次再試模型。"


def test_a_successful_in_lock_call_does_not_trip_it(game, monkeypatch, breaker_clock, capsys):
    calls = []
    monkeypatch.setattr(OllamaClient, "chat_text", lambda self, messages, **kwargs: calls.append(1) or "一句話")
    server.act(game, _ask_the_model_in_the_lock)
    server.act(game, _ask_the_model_in_the_lock)
    assert len(calls) == 2 and capsys.readouterr().out == ""


def test_a_failed_call_trips_it_even_when_the_action_then_errors(game, monkeypatch, breaker_clock):
    """動作出錯整筆撤回，可是模型確實掛了：照樣打開。"""
    _model_down(monkeypatch)

    def fail_then_error(g):
        _ask_the_model_in_the_lock(g)
        raise server.GameError("名冊裡沒有這個人。")

    with pytest.raises(server.GameError):
        server.act(game, fail_then_error)
    assert server.look(game, lambda g: g._quick_client()) is None


def test_the_breaker_does_not_gate_model_use_outside_the_lock(monkeypatch, breaker_clock):
    """鎖外的模型呼叫（開爐取名的 B 段；對話、隨口應對的評分也一樣）不歸斷路器管：打開了照樣叫。"""
    jia, yi = _forger("甲", insights=("shan", "shui")), _forger("乙")
    server.act(jia, lambda g: g.forge(None, ["shan", "shui"]))  # 鎖內取名失敗：打開
    assert server.look(yi, lambda g: g._quick_client()) is None
    asked = []
    with _model(lambda model, messages: asked.append(1) or "旋風腿"):
        assert server.prepare_forge(yi, None, ["feng", "huo"])[0] == "旋風腿"  # 另一個新配方
    assert asked == [1]


def test_when_the_first_trip_saw_no_need_for_the_model_the_lock_never_asks_it(monkeypatch):
    """A 段說不必叫模型（那一刻會被拒絕、配方有了、沒有 client），C 段進鎖時卻做得成（中間狀態變了）：
    鎖裡也不叫模型，直接用退路字表——伺服器永遠不走「鎖裡取名」那條路。"""
    game = _forger()
    monkeypatch.setattr(Game, "forge_request", lambda self, art_id, insight_ids, **kwargs: None)
    asked = []
    with _model(lambda model, messages: asked.append(1) or "旋風腿"):
        server.forge(game, None, ["feng", "huo"])
    assert asked == []
    assert open_world().lookup_insight_recipe(FENG_HUO).name == naming.fallback_name(server.CONTENT, FENG_HUO, "意境")


# ── 伺服器自己的排程：排程的一下（world_step）跟玩家請求同一把鎖、同一套鎖內模型守衛 ──────────────


def test_world_step_pushes_the_season_under_the_action_lock(monkeypatch):
    """排程的一下：拿行動鎖、推全服的事；鎖內的模型額度照玩家請求那一套（斷路器開著時這一下也不叫模型）。"""
    held = []
    real_lock = SqliteWorldStore.action_lock

    def spy_lock(self, timeout=None):
        held.append(timeout)
        return real_lock(self, timeout)

    monkeypatch.setattr(SqliteWorldStore, "action_lock", spy_lock)
    server.world_step(lambda: 1000.0)
    before = open_world().get_season().time
    server.world_step(lambda: 1300.0)
    assert open_world().get_season().time == pytest.approx(before + 300 * server.CONTENT.config.time_scale)
    assert held and all(t is None for t in held)  # 跟玩家請求一樣等到拿到為止


def test_world_step_reads_the_clock_inside_the_action_lock():
    """排程那一下的現在時間在拿到行動鎖之後才讀（跟 act() 一樣）：等鎖等了多久，這一下開的集結、回合的期限都不會因此變短。"""
    seen = []

    def clock():
        seen.append(database.open_database().writing())
        return 1000.0

    server.world_step(clock)
    assert seen == [True]


def test_world_step_respects_the_model_breaker(monkeypatch, breaker_clock):
    """斷路器開著時，排程那一下的鎖內模型額度一開始就用完（跟 _locked 同一套 _model_guard）。"""
    seen = []
    monkeypatch.setattr(Game, "world_tick", lambda self, now: seen.append(self._model_budget.gave_up) or [])
    server._pause_model()
    server.world_step(lambda: 1000.0)
    assert seen == [True]


def test_the_model_guard_refuses_to_run_without_the_action_lock(game):
    """_model_guard 假設已經拿到行動鎖（審查 M1）：沒拿鎖就用它直接丟 RuntimeError，不會悄悄在鎖外歸零額度、查斷路器。
    所以把順序寫反（with _model_guard(g), action_lock()）的呼叫端一進來就會壞。"""
    with pytest.raises(RuntimeError, match="行動鎖"), server._model_guard(game):
        pass
    with game.world.action_lock(), server._model_guard(game):
        pass


def test_every_lock_hold_resets_the_model_budget_while_holding_the_lock(game, monkeypatch):
    """玩家請求（act、look）與排程（world_step）都是先拿到行動鎖、才歸零鎖內的模型額度。"""
    seen = []
    real = Game.reset_model_budget
    monkeypatch.setattr(Game, "reset_model_budget", lambda self: seen.append(self.world.db.writing()) or real(self))
    server.act(game, lambda g: None)
    server.look(game, lambda g: None)
    server.world_step(lambda: 1000.0)
    assert seen == [True, True, True]


def test_a_failed_in_lock_call_in_a_world_step_trips_the_breaker_for_everyone(game, monkeypatch, breaker_clock, capsys):
    """排程那一下鎖內的模型呼叫失敗：跟玩家請求一樣打開全服的斷路器、印同一行，下一個玩家的拿鎖一開始額度就用完。"""
    sent = _model_down(monkeypatch)
    monkeypatch.setattr(Game, "world_tick", lambda self, now: _ask_the_model_in_the_lock(self) or [])
    server.world_step(lambda: 1000.0)
    assert len(sent) == 1
    assert server.look(game, lambda g: (g._model_budget.gave_up, g._quick_client())) == (True, None)
    assert len(sent) == 1
    assert capsys.readouterr().out.splitlines() == [
        f"鎖內的模型呼叫失敗或逾時：接下來 {server.MODEL_BREAKER_SECONDS} 秒全服鎖內不叫模型，改用固定文字。",
    ]


def _lock_is_free() -> bool:
    """另一個執行緒拿得到行動鎖嗎（拿不到就是有人沒放）。"""
    got = []

    def grab():
        with contextlib.suppress(TimeoutError), open_world().action_lock(timeout=2.0):
            got.append(True)

    thread = threading.Thread(target=grab)
    thread.start()
    thread.join(5.0)
    return got == [True]


def test_a_failed_world_step_rolls_back_and_releases_the_lock(monkeypatch):
    """排程那一下出錯：這一下推的整筆撤回、鎖放掉、例外丟給呼叫端；記憶體裡那份做到一半的空殼也不留，下一下從資料庫重建、
    照常推（Review Focus 2 的伺服器這一半）。"""
    server.world_step(lambda: 1000.0)  # 第一下只記下時鐘
    before = open_world().get_season().time
    real_tick = Game.world_tick

    def tick_then_fail(self, now):
        real_tick(self, now)
        raise RuntimeError("這一下壞了")

    monkeypatch.setattr(Game, "world_tick", tick_then_fail)
    with pytest.raises(RuntimeError, match="這一下壞了"):
        server.world_step(lambda: 1300.0)
    assert open_world().get_season().time == pytest.approx(before)  # 推過的那一段撤回了
    assert _lock_is_free()
    assert server.WORLD_GAME is None
    monkeypatch.setattr(Game, "world_tick", real_tick)
    server.world_step(lambda: 1300.0)
    assert open_world().get_season().time == pytest.approx(before + 300 * server.CONTENT.config.time_scale)


def test_a_world_step_that_cannot_build_its_game_raises_and_tries_again_next_time(monkeypatch):
    """建那一份沒有玩家的 Game 就失敗（例如資料庫一時打不開）：例外丟給呼叫端（排程迴圈印出來），下一下重新建。"""
    real = Game.for_world
    calls = []

    def flaky(content, world, rng=None):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("資料庫打不開")
        return real(content, world, rng)

    monkeypatch.setattr(Game, "for_world", staticmethod(flaky))
    with pytest.raises(OSError):
        server.world_step(lambda: 1000.0)
    assert server.WORLD_GAME is None
    server.world_step(lambda: 1000.0)
    assert server.WORLD_GAME is not None and len(calls) == 2


# ── 排程執行緒與開關（Config.world_tick_seconds，預設 0＝關）──────────────


def _boom(exc: BaseException) -> None:
    """在同一行丟出 exc：排程的出錯紀錄認「同一個錯」看的是類別與丟出來的那一行。"""
    raise exc


def test_scheduler_keeps_running_after_a_failed_step(capsys):
    """排程那一下出錯：印一行（stdout，只寫例外的類別）加呼叫堆疊（stderr），下一輪照跑；執行緒不會死（Review Focus 2）。
    例外訊息不寫（常夾著名號，跟 bot_runner.log_failure 一樣，最終審查 I1）；每一下回傳的訊息也不印。"""
    stop = threading.Event()
    calls = []
    broken = RuntimeError("第一下壞了")  # 訊息不寫在丟出來那一行：呼叫堆疊會照實印出那一行原始碼

    def step(clock):
        calls.append(clock())
        if len(calls) == 1:
            _boom(broken)
        if len(calls) == 3:
            stop.set()
        return ["沈浪加入了官軍。"]

    server.run_scheduler(0.001, stop, step=step, clock=lambda: 42.0)
    assert calls == [42.0, 42.0, 42.0]
    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["排程這一下出錯：RuntimeError"]
    assert "in step" in captured.err and "in _boom" in captured.err  # 呼叫堆疊：程式碼的位置
    assert "第一下壞了" not in captured.out + captured.err
    assert "沈浪" not in captured.out + captured.err


def _strict_cp950_console(monkeypatch) -> tuple[io.BytesIO, io.BytesIO]:
    """主控台是 cp950、寫不出的字直接丟例外（errors="strict"）：stdout 導到檔案、環境又不是 UTF-8 時就是這樣
    （最終審查 I1 重現的情形）。回傳 stdout、stderr 底下的位元組。"""
    out, err = io.BytesIO(), io.BytesIO()
    for name, raw in (("stdout", out), ("stderr", err)):
        monkeypatch.setattr(sys, name, io.TextIOWrapper(raw, encoding="cp950", errors="strict", write_through=True))
    return out, err


def test_a_failed_step_logs_no_names_and_survives_a_console_that_cannot_write_them(monkeypatch):
    """I1：一下丟出夾著名號的例外（簡體字，cp950 寫不出來）、下一下又丟一個夾著名號的：排程執行緒照樣跑完每一下，
    主控台只看到例外的類別與程式碼的位置，看不到名號也看不到訊息。以前 print 在 except 裡丟 UnicodeEncodeError，
    執行緒就這樣死了，世界又變成等人點擊才動。"""
    out, err = _strict_cp950_console(monkeypatch)
    stop = threading.Event()
    secrets_in_messages = [KeyError("孙坚"), RuntimeError("沈浪的存檔讀不進來")]  # 名號不能出現在丟出來那一行的原始碼上
    calls = []

    def step(clock):
        calls.append(1)
        if len(calls) <= len(secrets_in_messages):
            _boom(secrets_in_messages[len(calls) - 1])
        stop.set()
        return []

    thread = threading.Thread(target=server.run_scheduler, args=(0.001, stop), kwargs={"step": step})
    thread.start()
    thread.join(5.0)
    assert not thread.is_alive() and len(calls) == 3  # 每一下都跑到了：排程沒有死在寫紀錄上
    text = out.getvalue().decode("cp950") + err.getvalue().decode("cp950")
    assert "排程這一下出錯：KeyError" in text and "排程這一下出錯：RuntimeError" in text
    assert "in _boom" in text
    assert "沈浪" not in text and "存檔讀不進來" not in text


def test_a_console_that_breaks_never_stops_the_scheduler(monkeypatch):
    """寫紀錄本身出錯（主控台不見了、寫不進去）一律吞掉：記錄不能讓排程停下來。"""

    class Gone(io.StringIO):
        def write(self, text):
            raise OSError("主控台不見了")

    monkeypatch.setattr(sys, "stdout", Gone())
    monkeypatch.setattr(sys, "stderr", Gone())
    stop = threading.Event()
    calls = []

    def step(clock):
        calls.append(1)
        if len(calls) <= 2:
            _boom(RuntimeError("壞了"))
        stop.set()
        return []

    server.run_scheduler(0.001, stop, step=step)
    assert len(calls) == 3


def test_a_failure_that_repeats_every_tick_is_counted_not_flooded(capsys):
    """同一個錯（同一個類別、在同一行丟出來）一直重複：第一次整段印，之後只數次數，換了別的錯時先印一行「又出錯 N 次」
    再整段印新的那個，不會每一下都印一整段（最終審查 M2：每 10 秒一下，一天八千多段）。"""
    stop = threading.Event()
    kinds = [KeyError] * 4 + [ValueError] * 2
    calls = []

    def step(clock):
        calls.append(1)
        if len(calls) <= len(kinds):
            _boom(kinds[len(calls) - 1]("某某"))
        stop.set()
        return []

    server.run_scheduler(0.001, stop, step=step, log_clock=lambda: 0.0)
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "排程這一下出錯：KeyError",
        "排程這一下又出錯 3 次：KeyError（同一個地方，細節同上）",
        "排程這一下出錯：ValueError",
    ]
    assert captured.err.count("in _boom") == 2  # 整段的呼叫堆疊只印兩次：每個錯第一次


def test_a_repeating_failure_still_reports_its_count_every_few_minutes(capsys):
    """一直是同一個錯：滿 SCHEDULER_REPEAT_SUMMARY_SECONDS 秒印一行累計的次數（log 的節流時鐘跟世界時間無關）。"""
    stop = threading.Event()
    now = [0.0]
    calls = []

    def step(clock):
        calls.append(1)
        if len(calls) == 3:
            now[0] = float(server.SCHEDULER_REPEAT_SUMMARY_SECONDS)
        if len(calls) <= 4:
            _boom(KeyError("某某"))
        stop.set()
        return []

    server.run_scheduler(0.001, stop, step=step, log_clock=lambda: now[0])
    assert capsys.readouterr().out.splitlines() == [
        "排程這一下出錯：KeyError",
        "排程這一下又出錯 2 次：KeyError（同一個地方，細節同上）",
    ]


def test_scheduler_off_starts_nothing():
    """開關關著（0）：不開執行緒，啟動時印一行說排程關著（Review Focus 5）。"""
    assert server.start_scheduler(0) is None
    assert server.SCHEDULER_THREAD is None
    assert "排程：關" in server.scheduler_line(0)
    assert "每 10 秒" in server.scheduler_line(10)


def test_scheduler_on_runs_steps_in_the_background(monkeypatch):
    done = threading.Event()
    monkeypatch.setattr(server, "world_step", lambda clock: done.set() or [])
    thread = server.start_scheduler(0.01)
    try:
        assert thread is not None and thread.daemon
        assert done.wait(2.0)
    finally:
        server.SCHEDULER_STOP.set()
        if thread is not None:
            thread.join(2.0)
            assert not thread.is_alive()
        server.SCHEDULER_STOP.clear()


def test_a_second_scheduler_is_refused(monkeypatch):
    """一個伺服器只開一條排程執行緒（WORLD_GAME 只給一條執行緒用）：已經有一條在跑，再開就拒絕。"""
    monkeypatch.setattr(server, "world_step", lambda clock: [])
    first = server.start_scheduler(0.01)
    with pytest.raises(RuntimeError, match="排程"):
        server.start_scheduler(0.01)
    assert server.SCHEDULER_THREAD is first and first.is_alive()


def _users_in_server(name: str) -> set[str | None]:
    """server.py 裡用到 name 這個名字的地方各在哪個函式裡（模組層級是 None）。功能包的路由（tianxia/features/<包>/routes.py，
    殼照 FEATURES 掛，開發規範手冊 3.3）也是伺服器的一部分：那裡照 shell.<名字> 叫殼的東西，也算用到。"""
    found: set[str | None] = set()

    def visit(node: ast.AST, owner: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if isinstance(child, ast.Name) and child.id == name:
                found.add(owner)
            if isinstance(child, ast.Attribute) and child.attr == name and isinstance(child.value, ast.Name) and child.value.id == "shell":
                found.add(owner)
            visit(child, owner)

    visit(ast.parse((server.ROOT / "server.py").read_text(encoding="utf-8")), None)
    for routes in sorted((server.ROOT / "tianxia" / "features").glob("*/routes.py")):
        visit(ast.parse(routes.read_text(encoding="utf-8")), None)
    return found


def test_only_main_starts_the_scheduler_and_only_the_scheduler_runs_world_steps():
    """排程只有一條：只從 main() 開（import 時不開）；請求的處理從不呼叫 world_step，只有排程迴圈用它。"""
    assert _users_in_server("start_scheduler") == {"main"}
    assert _users_in_server("world_step") == {"run_scheduler"}


def test_main_starts_the_scheduler_only_when_switched_on(capsys, monkeypatch):
    """啟動時在設定那一行後面印排程開了沒有；關著（預設）不開執行緒，開著就開一條、每隔幾秒推一下。"""
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    server.main([])
    assert "排程：關（世界時間等有人連線才推）" in capsys.readouterr().out
    assert server.SCHEDULER_THREAD is None
    done = threading.Event()
    monkeypatch.setattr(server.CONTENT.config, "world_tick_seconds", 0.01)
    monkeypatch.setattr(server, "world_step", lambda clock: done.set() or [])
    server.main([])
    assert "排程：每 0.01 秒推一次全服的事" in capsys.readouterr().out
    assert server.SCHEDULER_THREAD is not None and done.wait(2.0)


def test_the_furnace_button_stays_disabled_with_the_wait_line_while_naming():
    """企劃者 2026-10-05：等取名的時候「開爐」鈕關著、寫著爐火正旺，同一個分頁按不了第二下（busy）；
    重新整理之後頁面重畫、按鈕照常能按——伺服器不留任何等待中的狀態，重複扣由 C 段的重驗擋（見上面幾條）。"""
    js = webharness.app_source()
    body = _js_function(js, "async function forge(")
    assert "await busy(" in body and "btn.disabled = true" in body and 'lab.textContent = "爐火正旺…"' in body  # 寫在小太極底下那兩個字上（煉製頁太極爐合一，2026-10-17）
    assert "S.forgeResult = { html: esc(FORGE_WAIT) };" in body and "要等它取名，請稍候" in js  # 等的時候寫的字（W10：不誇大成「一分鐘」），寫在開爐旁邊
    assert body.index("btn.disabled = true") < body.index('api("/api/menxia/forge"')


def test_the_page_never_polls_twice_at_once():
    """最終審查 Critical 1：取名要等的時候伺服器的執行緒還在跑；輪詢若不等上一次回來就再打一次 /api/main，
    卡住的請求會越疊越多、把執行緒池用光。poll() 有一個「還在等」的旗子，上一次沒回來就不打。"""
    js = webharness.app_source()
    body = _js_function(js, "async function poll(")
    assert "pollInFlight" in body and "finally" in body and "pollInFlight = false" in body
    assert body.index("pollInFlight") < body.index('api("/api/main")')
    assert "S.busy" in body and "document.hidden" in body  # 原本的守門照舊


def test_menxia_view_lists_owned_arts_insights_and_holdings(client):
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = ["feng"]
    open_characters().save(game.state)
    view = client.get("/api/menxia").json()
    assert view["holdings"] == {"count": 3, "cap": 50}
    assert [row["name"] for row in view["owned_arts"]] == ["基礎吐納", "基礎拳腳"]
    assert view["insights"][0]["name"] == "風" and view["naming"] is None
    assert view["slot_cards"][0]["price"] == 2


def test_slot_prices_are_none_when_empty_or_at_the_tenth_level(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "starter_skills", [])  # 沒有開局送的武學：讀檔才不會把空著的欄位補回來
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.member.wugong_id, game.state.player.member.wugong_level = "jichu_quanjiao", 10
    game.state.player.member.neigong_id = None
    open_characters().save(game.state)
    cards = {c["kind"]: c for c in client.get("/api/menxia").json()["slot_cards"]}
    assert cards["武學"]["price"] is None and cards["內功"]["price"] is None  # 第十成、還沒學
    game.state.player.member.wugong_level = 9
    open_characters().save(game.state)
    cards = {c["kind"]: c for c in client.get("/api/menxia").json()["slot_cards"]}
    assert cards["武學"]["price"] == 18


def test_the_new_menxia_actions_survive_oddly_shaped_bodies(client):
    """cultivate／melt／melt_insight／name 的 body 是客戶端寫的：什麼形狀都只會得到一句話，不會 500，也不會動到東西。"""
    _a_player_with_insights(client)
    bodies = ({}, {"art": 5}, {"art": ["jichu_quanjiao"]}, {"art": None}, {"insight": {"a": 1}}, {"insight": 7},
              {"name": 5}, {"name": ["旋風腿"]}, {"name": None})
    for op in ("cultivate", "melt", "melt_insight", "name"):
        for body in bodies:
            out = client.post(f"/api/menxia/{op}", json=body)
            assert out.status_code == 200 and out.json()["message"], (op, body)
    saved = open_characters().load("沈青衫").player
    assert (saved.member.neigong_id, saved.member.wugong_id) == ("jichu_tuna", "jichu_quanjiao")
    assert saved.insights == ["feng", "huo"] and saved.stats["xinde"] == 100 and saved.arts == []


# ── 功法卡（FB-006）與功法庫先看卡再改練（QA L4）────────────────


def test_the_practice_page_gets_a_card_for_each_worn_art(client, monkeypatch):
    _player(client)
    cards = client.get("/api/menxia").json()["slot_cards"]
    assert [c["kind"] for c in cards] == list(server.KINDS)
    wugong, neigong = cards
    assert "基礎拳腳" in wugong["card"] and "第十成" in wugong["card"]  # 現在這一成、下一成與第十成的威力那一行是功法卡才有的（W1）
    assert "基礎吐納" in neigong["card"]
    game = server.game_for("沈青衫")
    monkeypatch.setattr(server.CONTENT.config, "starter_skills", [])  # 沒有開局送的武學：讀檔才不會把空著的欄位補回來
    game.state.player.member.neigong_id = None  # 內容改版之後欄位空著的舊角色：卡片照舊說沒有
    open_characters().save(game.state)
    neigong = client.get("/api/menxia").json()["slot_cards"][1]
    assert "你還沒有內功。" in neigong["card"]


def test_the_menxia_payload_carries_the_attribute_note_both_pages_fold_away(client):
    """W2：修練頁與煉製頁各摺一行「屬性有什麼用」，字由 art_view.attribute_line 照程式的規則寫，網頁只放進去。"""
    _player(client)
    note = client.get("/api/menxia").json()["attribute_note"]
    assert note == art_view.attribute_line(server.CONTENT)
    assert "×1.3" in note and "剛柔" in note


def _a_player_with_library_arts(client, *arts):
    """新角色，功法庫裡放這幾門功法。功法本體登記進共用世界（煉製、自創都放在那裡），
    角色的功法庫存進資料庫（每次進鎖都從資料庫重讀角色，只改記憶體的話下一個請求就看不到）。"""
    _player(client)
    game = server.game_for("沈青衫")
    for art in arts:
        assert open_world().claim_skill_name(art)
        game.state.player.arts.append(art.id)
    open_characters().save(game.state)


def _library_art(name: str, note: str) -> MartialArt:
    return MartialArt(
        id=name, name=name, kind="武學", quality="上品", attribute="柔", affinity=["柔"],  # 武學重構：屬性＝相容屬性的第一個
        base_power=28.0, top_power=72.0, creator="沈浪", note=note,
    )


def test_a_library_art_comes_with_its_card_and_note(client):
    _a_player_with_library_arts(client, _library_art("沉柳纏勁", "以柔勁纏住兵刃，<b>借力</b>卸力。"))
    (item,) = [r for r in client.get("/api/menxia").json()["owned_arts"] if r["id"] == "沉柳纏勁"]
    assert "【沉柳纏勁】" in item["card"] and "第1成" in item["card"]
    assert "以柔勁纏住兵刃，&lt;b&gt;借力&lt;/b&gt;卸力。" in item["card"]  # 模型寫的說明句也一律跳脫


def test_a_library_art_without_a_note_leaves_no_blank_line(client):
    """退路字表取名的功法沒有說明句：整行省略，不出現 None、不留空的 <br> 行（FB-006 驗收）。"""
    _a_player_with_library_arts(client, _library_art("鐵柳纏勁", ""))
    card = next(r for r in client.get("/api/menxia").json()["owned_arts"] if r["id"] == "鐵柳纏勁")["card"]
    assert "None" not in card
    assert "<br />\n<br />" not in card and "<br />\n</p>" not in card
    # 來源之後一行功效：武學重構之後功效照槽裡裝的意境寫，槽空著寫一句指路（不是空行）；
    # W6：功法庫裡的功法再多一行跟身上同一種那門的比較，沒有說明句時它是最後一行（本人身上那門自己的卡沒有）
    # 自創的武學在功效之後多一行自己長出來的招（以意成招，私印是創的人名號的第一個字）
    assert "來源：自創（沈浪 所創）<br />\n功效：（意境槽空著，到煉製頁裝意境）<br />\n沈〔" in card
    assert "<br />\n比身上的【基礎拳腳】：威力 " in card
    assert card.rstrip().endswith("（第一成）</p>")


def test_the_map_offers_walking_and_dashing(game):
    view = server.look(game, lambda g: server.map_view(g, "situation", "yingshui"))
    walk, dash = view["travel"]  # 趕路拿掉了（企劃者 2026-10-12）
    assert [walk["mode"], dash["mode"]] == list(atlas.MODES)
    assert walk["label"].startswith("步行（約 ") and walk["enabled"] is True
    assert dash["label"].startswith("疾行（立刻到・體力 ")
    here = server.look(game, lambda g: server.map_view(g, "situation", g.state.player.location))
    assert here["travel"] is None


def test_a_pending_event_blocks_the_map_travel_button_and_flags_the_way_back(game):
    """FB-063：事件沒選完，輿圖那顆灰的按鈕寫出是哪一則（「先回江湖頁處理「…」」），並帶 to_jianghu：頁面照它多給一顆「回江湖」，
    不去解析中文；沒被事件擋的按鈕沒有這個旗標。"""
    pending = server.CONTENT.events[next(iter(server.CONTENT.events))]
    game.state.pending_event = pending.id
    view = server.look(game, lambda g: server.map_view(g, "situation", "yingshui"))
    (blocked,) = view["travel"]
    assert blocked["enabled"] is False and blocked["label"] == f"先回江湖頁處理「{pending.title}」"
    assert blocked["to_jianghu"] is True
    game.state.pending_event = None
    walk, dash = server.look(game, lambda g: server.map_view(g, "situation", "yingshui"))["travel"]
    assert [o["to_jianghu"] for o in (walk, dash)] == [False, False]
    game.state.player.busy_until = game.state.world.time + 3600  # 閉關中：也不能出發，但那不是回江湖頁的事
    (resting,) = server.look(game, lambda g: server.map_view(g, "situation", "yingshui"))["travel"]
    assert resting["enabled"] is False and resting["to_jianghu"] is False


def test_the_other_blocks_settled_on_the_jianghu_page_flag_the_way_back_too(game):
    """FB-063 的餘項：交談中、（求見中）、投靠待確認、答話中也是要回江湖頁了結才解得開，輿圖的灰按鈕同樣帶 to_jianghu；
    原因的話不變，閉關、賽季結束照舊沒有這個旗標。"""
    p = game.state.player
    content = server.CONTENT  # 進鎖時會清掉指向不存在東西的欄位，所以用真的人物、陣營與伏筆鏈（求見中要在有兩位人物的地方，atlas 的測試涵蓋）
    for setup, reason, to_jianghu in (
        (lambda: setattr(p, "pending_companion", next(iter(content.characters))), "交談中，先告辭才能安排前往", True),
        (lambda: setattr(p, "pending_faction", content.scenario.factions[0].id), "投靠還沒決定，先決定再安排前往", True),
        (lambda: setattr(p, "fs_asking", content.foreshadows.chains[0].id), "正在答話，先作罷才能安排前往", True),
    ):
        p.pending_companion, p.picking_audience, p.pending_faction, p.fs_asking = None, False, None, None
        setup()
        (blocked,) = server.look(game, lambda g: server.map_view(g, "situation", "yingshui"))["travel"]
        assert (blocked["enabled"], blocked["label"], blocked["to_jianghu"]) == (False, reason, to_jianghu)


def test_duel_text_without_a_duel_asks_no_model(game, monkeypatch):
    from tianxia.core import battle_base  # 第二輪第 102 批：bout.routes 讀核心那一格，換別名那一格打不到（這條是「不該評」，打不到會假綠）

    monkeypatch.setattr(battle_base, "assess_gamble", lambda *a, **k: pytest.fail("不該評"))
    with at(game, 0.0), mock.patch("server.time.time", return_value=0.0):
        assert server.duel_text(game, "撒石灰") == ["（此刻無法這麼做。）"]


def test_the_free_text_action_does_not_ask_the_model_when_it_cannot_be_sent(client, monkeypatch):
    _a_showdown_fighter(client, started=True)  # 還沒加入戰局：送不出去
    monkeypatch.setattr(battle_instance, "score_gamble", lambda *a, **k: pytest.fail("不該評"))
    out = client.post("/api/do/battle_text", json={"text": "火燒糧草"}).json()
    assert "（此刻無法這麼做。）" in out["message"]


def test_an_ordinary_option_does_not_come_back_with_a_message(client):
    """它的話已經在江湖紀錄與「剛剛」裡，再跳一句提示會重複。"""
    _player(client)
    out = client.post("/api/choose", json={"id": "act:explore"}).json()
    assert "message" not in out


# ── 管理者 ────────────────────────────────────────────


def _admin(client, monkeypatch, name="掌門"):
    monkeypatch.setattr(server.CONTENT.config, "admins", [name])
    boss = server.open_game(name)
    open_characters().save(boss.state)
    store = server.account_store()
    store.register("boss", "secret-pw")
    store.bind_character("boss", name)  # 管理者的帳號由主機端腳本綁（scripts/set_password.py）
    return client.post("/api/login", json={"login": "boss", "password": "secret-pw"}).json()


def test_an_admin_account_sees_the_admin_tools(client, monkeypatch):
    assert _admin(client, monkeypatch)["main"]["admin"] is True
    choices = client.get("/api/admin").json()
    assert [b["id"] for b in choices["battles"]] == ["huangjin_showdown"]  # 開關關著：三場大戲是第一季的，不列
    assert len(choices["events"]) == len(server.CONTENT.scenario.thresholds) + len(server.CONTENT.scenario.world_events)
    assert [t["id"] for t in choices["trends"]] == ["huangjin", "yuxi"]  # 開關關著：第一季才有的線不列


def test_admin_triggers_work_for_admins(client, monkeypatch):
    _admin(client, monkeypatch)
    game = server.game_for("掌門")
    client.post("/api/do/push_trend", json={"id": "huangjin", "amount": 5})
    assert game.world.get_season().trends["huangjin"] == server.CONTENT.scenario.trends[0].start + 5
    client.post("/api/do/fire", json={"id": "huangjin_50"})
    assert "huangjin_50" in game.world.get_season().fired_thresholds
    client.post("/api/do/start_battle", json={"id": "huangjin_showdown"})
    assert game.world.get_battle() is not None


def test_admin_triggers_are_refused_for_players(client):
    _player(client)
    game = server.game_for("沈青衫")
    for op, body in (("start_battle", {"id": "huangjin_showdown"}), ("push_trend", {"id": "huangjin", "amount": 50}),
                     ("fast_forward", {"hours": 24}), ("open_season", {}), ("jump_next", {}),
                     ("schedule", {"id": "changshe_fire", "at": 0}), ("resolve_event", {"id": "uprising", "key": "fixed"}),
                     ("set_trend", {"id": "huangjin", "value": 90}), ("clear_lock", {"id": "uprising"}), ("cancel_battle", {})):
        out = client.post(f"/api/do/{op}", json=body)
        assert out.status_code == 400 and out.json() == {"error": "只有管理者能這麼做。"}
    assert game.world.get_battle() is None
    assert game.world.get_season().trends["huangjin"] == server.CONTENT.scenario.trends[0].start
    assert client.get("/api/admin").status_code == 403


def test_next_season_runs_the_admin_rollover(client, monkeypatch):
    _admin(client, monkeypatch, "測試")
    game = server.game_for("測試")
    game.advance(server.CONTENT.config.season_days * 86400)
    assert game.state.world.ended
    client.post("/api/do/next_season", json={})
    assert not game.state.world.ended
    assert game.state.player.season_number == 2


def test_server_admin_end_season(client, monkeypatch):
    """立刻收季：只有管理者的帳號行；一般玩家打同一個網址被擋下（跟其他管理者動作同一種回法），季照舊在進行。"""
    _player(client)
    game = server.game_for("沈青衫")
    refused = client.post("/api/do/end_season", json={})
    assert refused.status_code == 400 and refused.json() == {"error": "只有管理者能這麼做。"}
    assert game.world.season_phase() == "running"

    _admin(client, monkeypatch)
    out = client.post("/api/do/end_season", json={})
    assert out.status_code == 200
    assert game.world.season_phase() == "resting"
    assert "賽季落幕" in out.json()["message"]


def test_open_season_only_works_for_admins(tmp_path, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", False)
    fresh = Game.new(server.CONTENT, "路人", world=open_world(tmp_path / "world.db"))
    assert fresh.world.season_phase() == "preparing"
    monkeypatch.setattr(server.CONTENT.config, "admins", ["路人"])
    server.act(fresh, lambda g: server.FEATURE_ADMIN_ACTIONS["open_season"].run(g, {}))
    assert fresh.world.season_phase() == "running"


def _a_guide_step_after_the_hut(monkeypatch):
    """幾個測試要量的是「有一個草廬之外、有話要說的步驟時對話框怎麼畫」，就在這份內容的引導最後接一步。初入江湖那幾步（序章之後）
    沒走的人一律略過，所以呼叫的測試自己把角色擺到這一步（`_stand_on`）。回傳那一步。"""
    from tianxia.models import TutorialGoal, TutorialStep

    step = TutorialStep(id="t_walk", text="出去走走。", done_when=TutorialGoal(action="explore"))
    monkeypatch.setattr(server.CONTENT.tutorial, "steps", [*server.CONTENT.tutorial.steps, step])
    return step


def _stand_on(game, step):
    game.state.player.tutorial_step = game.content.tutorial.steps.index(step)


def test_preparing_has_no_now_card_and_no_countdown(tmp_path, monkeypatch):
    """FB-049：籌備中時鐘沒走、什麼都不能做：江湖頁不畫「剛剛」（開場那一則寫「賽季開始」、叫人先去探索），
    狀態列不倒數下一件大事；江湖紀錄頁照樣列得到開場那一則。開季之後照常。"""
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", False)
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["路人"])
    walk = _a_guide_step_after_the_hut(monkeypatch)
    fresh = Game.new(server.CONTENT, "路人", world=open_world(tmp_path / "world.db"))
    _stand_on(fresh, walk)
    assert fresh.world.season_phase() == "preparing"
    view = server.main_view(fresh)
    assert view["now"] == "" and "賽季開始" in view["latest"]
    assert view["status"]["calendar"] and view["status"]["next_event"] is None
    assert view["guide"] is None  # 說書人的對話框也不叫人去探索（FB-045～052 審查 I1）
    server.act(fresh, lambda g: server.FEATURE_ADMIN_ACTIONS["open_season"].run(g, {}))
    view = server.main_view(fresh)
    assert view["now"] and view["status"]["next_event"] is not None and view["guide"] is not None
    # FB-062：下一件寫季曆時刻加現實倒數，畫面（web/app.js）把兩個拼成「宛城之戰・第 9 週・週四 20:44（現實約 4 小時 32 分後）」
    next_event = view["status"]["next_event"]
    assert re.fullmatch(r"第 \d+ 週・週[一二三四五六日] \d\d:\d\d", next_event["at"]) and next_event["in_seconds"] >= 0
    server.act(fresh, lambda g: server.FEATURE_ADMIN_ACTIONS["end_season"].run(g, {}))
    assert server.main_view(fresh)["guide"] is None  # 休季也一樣


def test_only_admins_can_reset_a_password(client, monkeypatch):
    _player(client)
    player = server.game_for("沈青衫")
    assert admin_routes.reset_password(server, player, "shen_01", "temp-pass") == "（只有管理者能重設密碼。）"
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
    assert admin_routes.reset_password(server, player, "沒這個人", "temp-pass") == "找不到這個帳號或名號。"
    assert admin_routes.reset_password(server, player, "shen_01", "123") == "密碼至少 6 字。"
    out = client.post("/api/admin/reset_password", json={"target": "沈青衫", "temp": "temp-pass"}).json()
    assert out == {"message": "已重設 shen_01 的密碼。"}
    server.login("shen_01", "temp-pass")


def test_the_dialogue_prepared_outside_the_lock_gets_its_budget_not_the_in_lock_limit(game, breaker_clock):
    """鎖內的模型呼叫有 15 秒的上限（Config.in_lock_model_timeout），鎖外的備料不受它管：一輪對話本來就要九、十秒，不能被短複本
    的 15 秒誤傷。鎖外有自己的總預算（Config.dialogue_budget_seconds，PM 2026-10-06）：拿的是 game.client 的複本，一趟的逾時是
    預算的一半（chat_structured 一次最多送兩趟，整段不超過預算）；原本那個 client 不動。"""
    _stand_by_a_figure(game)
    seen = []

    def generate(client, messages, required=()):
        seen.append(client)
        return DIALOGUE_TURN

    with mock.patch.object(companion_agent, "generate_turn", side_effect=generate):
        server.choose(game, "act:socialize")
    config = server.CONTENT.config
    assert len(seen) == 1 and seen[0] is not game.client
    assert seen[0].timeout == config.dialogue_budget_seconds / 2 > config.in_lock_model_timeout
    assert game.client.timeout == config.ollama_timeout and game.client.retry is True


def test_calling_on_a_figure_generates_outside_the_action_lock(game, lock_events):
    _stand_in_a_hall(game)
    server.choose(game, "act:call")
    lock_events.clear()

    def generate(client, messages, required=()):
        lock_events.append("generate")
        assert not game.world.db.writing()  # 這個執行緒沒拿著寫入交易
        return DIALOGUE_TURN

    with mock.patch.object(companion_agent, "generate_turn", side_effect=generate) as gen:
        server.choose(game, "call:zhangliang")
    gen.assert_called_once()
    assert lock_events == ["enter", "exit", "generate", "enter", "exit"]  # 鎖內備料 → 鎖外生成 → 鎖內套用
    assert game.state.player.pending_companion == "zhangliang"


def test_may_generate_dialogue_covers_calls_but_not_leaving():
    assert server.may_generate_dialogue("act:socialize")
    assert server.may_generate_dialogue("talk:0") and server.may_generate_dialogue("call:zhangliang")
    assert not server.may_generate_dialogue("talk:leave") and not server.may_generate_dialogue("call:back")
    assert not server.may_generate_dialogue("act:call") and not server.may_generate_dialogue("move:yingshui")


def test_a_non_dialogue_option_takes_the_lock_once_and_never_asks_the_model(game, lock_events, monkeypatch):
    old_explore(server.CONTENT.config, monkeypatch.setattr)  # 舊探索當手段（同 classic_rules）
    with mock.patch.object(companion_agent, "generate_turn", side_effect=AssertionError("不該呼叫模型")):
        server.choose(game, "act:explore")
    assert lock_events == ["enter", "exit"]  # 只拿一次鎖，沒有多餘的備料那一趟
    assert game.state.player.stamina < server.CONTENT.config.stamina_max


# ── 大場面在行動鎖外請模型判讀（武學與成長設計 8.3、計畫三 Task 2）────────────


def test_only_fights_and_event_choices_may_be_judged():
    assert server.may_judge_fight("act:train") and server.may_judge_fight("choice:0")
    assert server.may_judge_fight("act:challenge:bocai")
    assert not server.may_judge_fight("act:explore") and not server.may_judge_fight("move:lake")
    assert not server.may_judge_fight("choice:free")  # 隨口應對只是叫出輸入框（真正送出走 /api/answer）


FIGHT_JUDGMENT = fight_llm.Judgment(advantage=15, winning="佔上風。", losing="落下風。")


def test_a_big_fight_is_judged_outside_the_action_lock(game, lock_events):
    """打頭目（翻江龍，難度 150）：鎖內備料 → 鎖外問模型 → 鎖內重驗套用（Review Focus 3 的前提：模型不在鎖裡跑）。
    模型拿的是 game.client 本身（鎖外不受鎖內 15 秒的上限管），預算是 big_fight_budget_seconds 扣掉 A 段等鎖的時間。
    按鈕上寫「兩人對峙……」：頁面按下去就換上這幾個字（app.js 的 choose）。"""
    game.state.pending_event = "kou_boss"
    options = server.look(game, server.main_view)["options"]
    assert [(o["id"], o["wait"]) for o in options] == [("choice:0", "兩人對峙……"), ("choice:1", "")]
    lock_events.clear()
    seen = []

    def judge(client, request, swing, budget=None):
        lock_events.append("judge")
        _nobody_holds_the_lock(game)
        seen.append((client, request.squad_id, swing, budget))
        return FIGHT_JUDGMENT

    with mock.patch.object(server.fight_llm, "judge", side_effect=judge):
        server.choose(game, "choice:0")
    assert lock_events == ["enter", "exit", "judge", "enter", "exit"]  # 鎖內備料 → 鎖外判讀 → 鎖內重驗套用
    client, squad_id, swing, budget = seen[0]
    config = server.CONTENT.config
    assert client is game.client and squad_id == "fanjianglong" and swing == config.big_fight_swing
    assert 0 < budget <= config.big_fight_budget_seconds
    record = game.state.battles[0]
    assert record.opponent == "波才" and record.narration == ("佔上風。" if record.tier in team.WIN_TIERS else "落下風。")
    assert open_characters().load("測試").battles[0].narration == record.narration


def test_a_big_fight_the_model_cannot_judge_is_fought_as_usual(game, lock_events):
    """模型叫不動（conftest 把它假成連不上）：優勢當 0、照平常的回合演出，這一仗照樣打。"""
    game.state.pending_event = "kou_boss"
    server.choose(game, "choice:0")
    assert lock_events == ["enter", "exit", "enter", "exit"]
    record = game.state.battles[0]
    assert record.opponent == "波才" and record.narration == "" and record.rounds


def _a_big_fight_at_the_wilds(game, monkeypatch):
    """潁川郊野的對手難度都不到大場面的門檻（100）：把門檻壓到 1，這裡的遊歷就是大場面（鎖外判讀、按鈕寫「兩人對峙」）。
    存一份到資料庫：鎖外判讀的時候，別的分頁看到、改的就是這一份。散人的遊歷：出陣關掉（出陣開著時散人沒有這顆鈕）。"""
    monkeypatch.setattr(server.CONTENT.config, "big_fight_difficulty", 1)
    server.act(game, lambda g: setattr(g.state.player, "location", "yingchuan_wilds"))  # 進鎖會先從資料庫重讀，改要在鎖裡改
    assert next(o for o in server.look(game, lambda g: g.options()) if o.id == "act:train").wait == "兩人對峙……"


@pytest.mark.parametrize("judgment", [FIGHT_JUDGMENT, None], ids=["judged", "model_too_slow"])
def test_a_big_fight_the_player_left_while_it_was_judged_replies_with_one_line(game, monkeypatch, judgment):
    """等模型判讀的時候（另一個分頁）把人帶走了：判讀回來作廢，這一仗不打、不寫戰報、不寫江湖紀錄，回一句話
    （以前回給畫面的是空的，玩家什麼也沒看到）。模型太慢沒回來（判讀是 None）也一樣——等得久的正是這種時候。"""
    _a_big_fight_at_the_wilds(game, monkeypatch)
    journal = len(open_characters().load("測試").journal)

    def judge(client, request, swing, budget=None):
        server.act(game, lambda g: setattr(g.state.player, "location", "yingchuan"))  # 另一個分頁：走到別處去了
        return judgment

    with mock.patch.object(server.fight_llm, "judge", side_effect=judge):
        reply = server.choose(game, "act:train")
    assert reply == ["你離開了，這一仗沒打成。"]
    stored = open_characters().load("測試")
    assert stored.battles == [] and stored.player.location == "yingchuan" and len(stored.journal) == journal


def test_the_page_gets_the_line_when_a_judged_big_fight_is_not_started(client, monkeypatch):
    """/api/choose 一般選項不回話（話在江湖紀錄裡），這一句不寫紀錄，所以這裡回給前端跳提示；江湖畫面照樣回。"""
    _player(client)
    game = server.game_for("沈青衫")
    _a_big_fight_at_the_wilds(game, monkeypatch)

    def judge(client, request, swing, budget=None):
        server.act(game, lambda g: setattr(g.state.player, "location", "yingchuan"))
        return FIGHT_JUDGMENT

    with mock.patch.object(server.fight_llm, "judge", side_effect=judge):
        out = client.post("/api/choose", json={"id": "act:train"}).json()
    assert "你離開了，這一仗沒打成。" in out["message"] and "main" in out
    assert "act:train" not in [o["id"] for o in out["main"]["options"]]
    # 平常打完一場仗的回話照舊不回（在「剛剛」卡片裡）
    out = client.post("/api/choose", json={"id": "act:rest"}).json()
    assert "message" not in out


def test_a_big_fight_that_became_impossible_for_another_reason_says_the_situation_changed(game, monkeypatch):
    """人還在、選項卻按不下去了（別的分頁把體力花光）：說得中性一點，一樣不打、不寫紀錄。"""
    _a_big_fight_at_the_wilds(game, monkeypatch)

    def judge(client, request, swing, budget=None):
        server.act(game, lambda g: setattr(g.state.player, "stamina", 0))
        return FIGHT_JUDGMENT

    with mock.patch.object(server.fight_llm, "judge", side_effect=judge):
        assert server.choose(game, "act:train") == ["情勢變了，這一仗沒打成。"]
    assert open_characters().load("測試").battles == []


@pytest.mark.parametrize(("event", "option"), [(None, "act:train"), ("wolves", "choice:0")])
def test_an_ordinary_fight_takes_the_lock_once_and_never_asks_the_model(game, lock_events, event, option, monkeypatch):
    """Review Focus 5：一般的仗（潁川郊野的地痞、山賊；狼群）不問模型、按鈕不寫「兩人對峙」，而且只拿一次行動鎖——
    備料與動作在同一次拿鎖裡做完（計畫三 G14：遊歷與事件選項天天在按，不能每一下都多搶一次鎖）。散人的遊歷：出陣關掉。"""
    game.state.player.location = "yingchuan_wilds"
    game.state.pending_event = event
    assert next(o for o in game.options() if o.id == option).wait == ""
    lock_events.clear()
    with mock.patch.object(server.fight_llm, "judge", side_effect=AssertionError("一般的仗不該問模型")):
        msgs = server.choose(game, option)
    assert lock_events == ["enter", "exit"]
    assert msgs and game.state.battles and game.state.battles[0].narration == ""
    assert open_characters().load("測試").battles[0].id == game.state.battles[0].id  # 同一次拿鎖裡存好了


def test_the_page_shows_the_wait_words_while_a_big_fight_is_judged():
    js = webharness.app_source()
    body = _js_function(js, "async function choose(")
    assert "opt.wait" in body and body.index("opt.wait") < body.index('api("/api/choose"')


# ── 網頁本身 ────────────────────────────────────────────


def test_the_page_and_its_files_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "天下大勢" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert ".tx-now" in client.get("/journal.css").text


def _version_of(content: bytes) -> str:
    """測試自己算期望的版本號，不拿 server 的函式去比 server 的函式。"""
    return hashlib.sha256(content).hexdigest()[:10]


def test_the_page_names_every_file_with_a_version_from_its_content(client):
    """更版後手機要拿到新檔：網址帶檔案內容的雜湊，新網址就是新的快取鍵（舊的快取不會被用到）。"""
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["Cache-Control"] == "no-cache"
    app_js = _version_of((server.WEB / "app.js").read_bytes())
    style_css = _version_of((server.WEB / "style.css").read_bytes())
    journal_css = _version_of(server.JOURNAL_CSS.encode("utf-8"))
    assert f'src="/static/app.js?v={app_js}"' in page.text
    assert f'href="/static/style.css?v={style_css}"' in page.text
    assert f'href="/journal.css?v={journal_css}"' in page.text
    # 以後有人在 index.html 加一個沒有版本號的資源，這裡會抓到
    urls = re.findall(r"""(?:src|href)=["'](/[^"']*)["']""", page.text)
    assert urls and all("?v=" in url for url in urls)


def test_the_versioned_urls_are_served_and_the_browser_must_ask_each_time(client, monkeypatch):
    """no-cache：每次都向伺服器確認（/static 有 ETag，沒變就是 304）；改了檔沒重開伺服器也不會被瀏覽器釘住舊檔。"""
    monkeypatch.delenv("TIANXIA_PUBLIC_URL", raising=False)  # 設了這個變數 /static 走長快取（第二輪第 78 批），跑測試的 shell 可能設著
    app_js = _version_of((server.WEB / "app.js").read_bytes())
    style_css = _version_of((server.WEB / "style.css").read_bytes())
    journal_css = _version_of(server.JOURNAL_CSS.encode("utf-8"))
    for url in (f"/static/app.js?v={app_js}", f"/static/style.css?v={style_css}", f"/journal.css?v={journal_css}"):
        got = client.get(url)
        assert got.status_code == 200, url
        assert got.headers["Cache-Control"] == "no-cache", url


def test_the_unversioned_urls_are_not_cached_either(client):
    """舊網址（沒帶版本號）也一樣不能被啟發式快取。"""
    assert client.get("/static/app.js").headers["Cache-Control"] == "no-cache"
    assert client.get("/journal.css").headers["Cache-Control"] == "no-cache"


def test_the_versioned_urls_are_cached_for_good_only_online_with_the_right_hash(client, monkeypatch):
    """設了 TIANXIA_PUBLIC_URL（線上）、?v= 又等於那個檔現在的內容雜湊，才回長快取；HEAD 與 304 也一樣，
    已經快取舊標頭的手機再驗一次就換成新標頭，上線不用換網址、不用清快取。"""
    monkeypatch.setenv(server.PUBLIC_URL_ENV, "https://tianxiadashi.com")
    long_cache = "max-age=31536000, immutable"
    # 頁面給的網址就是拿得到長快取的網址
    app_js = _version_of((server.WEB / "app.js").read_bytes())
    assert re.search(r'"(/static/app\.js\?v=[^"]+)"', client.get("/").text)[1] == f"/static/app.js?v={app_js}"
    for name in ("app.js", "style.css", "icon-180.png"):
        url = f"/static/{name}?v={_version_of((server.WEB / name).read_bytes())}"
        got = client.get(url)
        assert got.status_code == 200, url
        assert got.headers["Cache-Control"] == long_cache, url
        head = client.head(url)
        assert head.status_code == 200, url
        assert head.headers["Cache-Control"] == long_cache, url
        again = client.get(url, headers={"If-None-Match": got.headers["ETag"]})
        assert again.status_code == 304, url
        assert again.headers["Cache-Control"] == long_cache, url


def test_every_other_url_still_asks_each_time(client, monkeypatch):
    """其餘照舊 no-cache（各打一次）：改了檔沒重開，舊網址的 ?v= 對不上就還是會問；首頁、管理頁、sw.js 與自己路由的檔不會被釘死。"""

    def version_of(name):
        return _version_of((server.WEB / name).read_bytes())

    def asks_each_time(url):
        got = client.get(url)
        assert got.status_code == 200, url
        assert got.headers["Cache-Control"] == "no-cache", url

    app_js = f"/static/app.js?v={version_of('app.js')}"
    monkeypatch.setenv(server.PUBLIC_URL_ENV, "https://tianxiadashi.com")
    for url in (
        "/static/app.js",
        "/static/app.js?v=0000000000",
        f"{app_js}&x=1",
        "/",
        "/admin",
        "/sw.js",
        f"/static/sw.js?v={version_of('sw.js')}",
        f"/static/index.html?v={version_of('index.html')}",
        f"/journal.css?v={_version_of(server.JOURNAL_CSS.encode('utf-8'))}",
        f"/manifest.webmanifest?v={version_of('manifest.webmanifest')}",
    ):
        asks_each_time(url)
    # 環境變數空字串算沒設，跟拿掉一樣
    monkeypatch.setenv(server.PUBLIC_URL_ENV, "")
    asks_each_time(app_js)
    monkeypatch.delenv(server.PUBLIC_URL_ENV)
    asks_each_time(app_js)


def test_the_version_follows_the_content():
    assert server.content_version(b"abc") == server.content_version(b"abc")
    assert server.content_version(b"abc") != server.content_version(b"abd")
    assert server.content_version(b"abc") == _version_of(b"abc")


def test_versioned_page_marks_our_own_files_and_leaves_everything_else():
    html = (
        '<link rel="icon" href="data:image/svg+xml,%3Csvg%3E">'
        '<link rel="stylesheet" href="/journal.css">'
        '<link rel="stylesheet" href="/static/style.css">'
        '<script src="/static/app.js"></script>'
        '<script src="https://example.com/x.js"></script>'
    )
    out = server.versioned_page(html, lambda url: "v" + url.replace("/", "_"))
    assert 'href="/journal.css?v=v_journal.css"' in out
    assert 'href="/static/style.css?v=v_static_style.css"' in out
    assert 'src="/static/app.js?v=v_static_app.js"' in out
    assert 'href="data:image/svg+xml,%3Csvg%3E"' in out
    assert 'src="https://example.com/x.js"' in out
    assert out.count("?v=") == 3
    # 已經帶版本號的不會再加一次
    assert server.versioned_page(out, lambda url: "other") == out


def test_versioned_page_refuses_a_file_that_does_not_exist():
    """index.html 指到 web/ 裡沒有的檔：啟動時就丟例外，不要默默送出壞網址。"""
    with pytest.raises(FileNotFoundError):
        server.versioned_page('<script src="/static/no_such_file.js"></script>', server.asset_version)


def test_asset_version_reads_the_files_the_server_really_sends():
    assert server.asset_version("/static/app.js") == _version_of((server.WEB / "app.js").read_bytes())
    assert server.asset_version("/journal.css") == _version_of(server.JOURNAL_CSS.encode("utf-8"))


def test_starting_the_server_prints_the_database_path(capsys, monkeypatch):
    """跟 run_bots.py 要開同一個資料庫：啟動時印出路徑，TIANXIA_DB 設錯時一眼看得出來（只印路徑，不印任何名號）。"""
    import uvicorn

    ran = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: ran.append(kwargs["port"]))
    server.main([])
    assert ran == [server.PORT]
    assert str(database.default_path().resolve()) in capsys.readouterr().out


def test_server_prints_the_profile_at_startup(capsys, monkeypatch):
    """跟資料庫路徑一起印出用的是哪一份設定（計畫 T2）：TIANXIA_PROFILE 設錯時一眼看得出來。"""
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "PROFILE", None)
    server.main([])
    out = capsys.readouterr().out
    assert "設定：預設" in out and str(database.default_path().resolve()) in out
    monkeypatch.setattr(server, "PROFILE", "week7")
    monkeypatch.setattr(server, "CONTENT", real_content("week7"))
    server.main([])
    assert "設定：week7（第一季濃縮版規則開啟、季長 7 天、人數上限 20）" in capsys.readouterr().out


def _host_passed_to_uvicorn(monkeypatch, argv):
    import uvicorn

    ran = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: ran.append(kwargs["host"]))
    server.main(argv)
    return ran


def test_the_server_listens_on_localhost_by_default(capsys, monkeypatch):
    """預設只聽本機：沒加 --lan，同一個區網的裝置連不到。--share 走 cloudflared（連的就是 127.0.0.1），不受影響。"""
    assert _host_passed_to_uvicorn(monkeypatch, []) == ["127.0.0.1"]
    out = capsys.readouterr().out
    assert f"http://127.0.0.1:{server.PORT}" in out
    assert "區網" not in out


def test_the_lan_flag_opens_every_network_card_and_says_so(capsys, monkeypatch):
    assert _host_passed_to_uvicorn(monkeypatch, ["--lan"]) == ["0.0.0.0"]
    out = capsys.readouterr().out
    assert "已開放區網連線：同一個網路裡的裝置都連得到。" in out
    assert f"http://127.0.0.1:{server.PORT}" in out
    assert str(database.default_path().resolve()) in out


def _moves(options):
    return [o for o in options if o["id"].startswith("move:")]


def test_the_move_mode_header_switches_the_travel_options(client):
    _player(client)
    walking = client.get("/api/main").json()["options"]
    dashing = client.get("/api/main", headers=DASH).json()["options"]
    assert len(dashing) == len(walking)  # 只換「前往」的走法，按鈕數不變
    moves = _moves(dashing)
    assert moves and all(o["id"].count(":") == 2 and o["id"].endswith(":dash") for o in moves)
    assert all("疾行" in o["label"] for o in moves)
    hurrying = _moves(client.get("/api/main", headers=HURRY).json()["options"])
    assert [o["id"] for o in hurrying] == [o["id"] for o in _moves(walking)]  # 趕路拿掉了：當成步行


def test_the_move_mode_lasts_one_request_like_two_tabs(client):
    _player(client)
    client.get("/api/main", headers={"X-Move-Mode": "dash"})
    moves = _moves(client.get("/api/main").json()["options"])  # 另一個分頁沒選走法：照樣步行，不會被上一個請求帶走
    assert moves and all(o["id"].count(":") == 1 and "步行" in o["label"] for o in moves)
    unknown = _moves(client.get("/api/main", headers={"X-Move-Mode": "fly"}).json()["options"])
    assert [o["id"] for o in unknown] == [o["id"] for o in moves]  # 不認得的走法當成步行


def test_the_menu_walks_unless_this_request_chose_otherwise(game):
    def moves():
        return [o["id"] for o in _moves(server.look(game, server.main_view)["options"])]

    walking = moves()
    assert walking and all(option_id.count(":") == 1 for option_id in walking)
    token = server.MOVE_MODE.set("dash")
    try:
        assert moves() == [f"{option_id}:dash" for option_id in walking]
    finally:
        server.MOVE_MODE.reset(token)
    assert moves() == walking  # 同一份 Game 上一次是疾行：這次沒選走法，就回到步行


def test_entering_the_game_always_walks(client):
    """登入、重新整理頁面（/api/me）的畫面照步行排，就算請求帶著別的走法；頁面在 enter() 也把切換鈕放回步行。"""
    _player(client)
    entry = client.get("/api/me", headers=HURRY).json()
    moves = _moves(entry["main"]["options"])
    assert moves and all(o["id"].count(":") == 1 and "步行" in o["label"] for o in moves)


def test_the_move_mode_is_never_saved(client):
    _player(client)
    client.get("/api/main", headers=HURRY)
    assert "move_mode" not in open_characters().load("沈青衫").model_dump_json()


# ── 隨口應對（探索的多人與 LLM 玩法 §8.1）────────────────────


@pytest.fixture
def at_a_gamble(game, monkeypatch):
    """正式內容裡挑一則事件掛上隨口應對（劇情還沒寫），玩家正停在這則事件上，角色已經存檔。"""
    from tianxia.models import Effect, FreeTextChoice

    event = next(iter(server.CONTENT.events.values()))
    free = FreeTextChoice(prompt="自己想辦法……", stat="str", effect=Effect(text="成了。"), fail_effect=Effect(text="砸了。"))
    monkeypatch.setattr(event, "free_text", free)
    game.state.pending_event = event.id
    open_characters().save(game.state)
    return event


def test_answering_asks_the_model_outside_the_lock(game, at_a_gamble, lock_events):
    def assess(client, event, text, **_):
        lock_events.append(f"assess:{text}")
        return server.event_llm.EventVerdict(85)

    game.rng = random.Random(0)
    def narrate(client, event, text, success, effect_text, evil=False):
        lock_events.append("narrate")
        return "你扯開嗓子一喊。"

    with mock.patch.object(server.event_llm, "judge_event_gamble", side_effect=assess), \
            mock.patch.object(server.event_llm, "narrate_event_gamble", side_effect=narrate):
        server.answer_event(game, "大喊官兵來了")
    assert lock_events == ["enter", "exit", "assess:大喊官兵來了", "enter", "exit", "narrate", "enter", "exit"]
    assert game.state.journal[0].lines[1] == "你扯開嗓子一喊。"
    assert game.state.pending_event is None
    assert game.state.journal[0].title == f"{at_a_gamble.title}・隨口應對"
    assert game.state.journal[0].lines[0].startswith("你：「大喊官兵來了」（成算")
    view = server.look(game, server.main_view)
    assert view["event_free_text"] is None


def test_the_free_text_assessment_and_the_narration_share_one_budget(game, at_a_gamble, breaker_clock):
    """隨口應對的評分與潤色都在鎖外，不是鎖內那個 15 秒的短複本：兩件共用同一份總預算（Config.free_text_budget_seconds，PM 2026-10-06
    ＋控制者 2026-10-06 把潤色也算進來），都拿 game.client 的複本、一趟的逾時是「剩下的」一半；原本那個 client 不動。"""
    seen = []

    def assess(client, event, text, **_):
        seen.append(("assess", client))
        return server.event_llm.EventVerdict(85)

    def narrate(client, event, text, success, effect_text, evil=False):
        seen.append(("narrate", client))
        return ""

    game.rng = random.Random(0)
    with mock.patch.object(server.event_llm, "judge_event_gamble", side_effect=assess), \
            mock.patch.object(server.event_llm, "narrate_event_gamble", side_effect=narrate):
        server.answer_event(game, "大喊官兵來了")
    config = server.CONTENT.config
    assert [kind for kind, _ in seen] == ["assess", "narrate"]
    (_, scored), (_, narrated) = seen
    assert scored is not game.client and scored.timeout == config.free_text_budget_seconds / 2 > config.in_lock_model_timeout
    assert narrated is not game.client and narrated.timeout == config.free_text_budget_seconds / 2
    assert game.client.timeout == config.ollama_timeout > config.in_lock_model_timeout


def test_the_narration_gets_what_the_scoring_left_of_the_free_text_budget(game, at_a_gamble, breaker_clock):
    """評分花掉 50 秒：潤色只剩 60 − 50 = 10 秒，一趟的逾時是 5 秒（複本；原本那個 client 不動）。"""
    seen = []

    def assess(client, event, text, **_):
        breaker_clock[0] += 50
        return server.event_llm.EventVerdict(85)

    def narrate(client, event, text, success, effect_text, evil=False):
        seen.append(client)
        return GAMBLE_NARRATION

    game.rng = random.Random(0)
    with mock.patch.object(server.event_llm, "judge_event_gamble", side_effect=assess), \
            mock.patch.object(server.event_llm, "narrate_event_gamble", side_effect=narrate):
        server.answer_event(game, "大喊官兵來了")
    assert len(seen) == 1 and seen[0] is not game.client
    assert seen[0].timeout == pytest.approx((server.CONTENT.config.free_text_budget_seconds - 50) / 2)
    assert game.state.journal[0].lines[1] == GAMBLE_NARRATION
    assert game.client.timeout == server.CONTENT.config.ollama_timeout


def test_a_narration_with_no_budget_left_is_skipped(game, at_a_gamble, breaker_clock):
    """評分把預算用得只剩半秒（不夠一趟）：不叫潤色，一句都不插，跟模型叫不動時一樣（結果與擲骰照常套用，請求不再等）。"""
    def assess(client, event, text, **_):
        breaker_clock[0] += server.CONTENT.config.free_text_budget_seconds - 0.5
        return server.event_llm.EventVerdict(85)

    game.rng = random.Random(0)
    with mock.patch.object(server.event_llm, "judge_event_gamble", side_effect=assess), \
            mock.patch.object(server.event_llm, "narrate_event_gamble", side_effect=AssertionError("預算用完了，不該叫潤色")):
        msgs = server.answer_event(game, "大喊官兵來了")
    assert game.state.pending_event is None and game.state.journal[0].title == f"{at_a_gamble.title}・隨口應對"
    assert GAMBLE_NARRATION not in game.state.journal[0].lines and msgs


@pytest.mark.parametrize("story", ["你一言不發地揮鏟，把他推進坑裡填平了土。", None], ids=["narrated", "no-narration"])
def test_an_evil_deed_that_lands_goes_through_all_three_steps(game, at_a_gamble, monkeypatch, story):
    """FB-223：B 段判成「惡」、擲中了：C 段換成惡行的版本（不接內容的結果句「成了。」），D 段請模型照惡行寫（evil=True）；
    寫成了換掉固定那一句（rules.EVIL_DONE），沒寫成就留那一句收尾。善惡跟著成功率一起交給 C 段。"""
    from conftest import FixedRandom
    from tianxia import rules

    asked, given = [], []
    real = Game.answer_event
    monkeypatch.setattr(
        Game, "answer_event", lambda self, request, llm_rate=None, moral=None: given.append((llm_rate, moral)) or real(self, request, llm_rate, moral),
    )

    def narrate(client, event, text, success, effect_text, evil=False):
        asked.append((success, effect_text, evil))
        return story

    game.rng = FixedRandom(0.0)
    with mock.patch.object(server.event_llm, "judge_event_gamble", return_value=server.event_llm.EventVerdict(3, "惡")), \
            mock.patch.object(server.event_llm, "narrate_event_gamble", side_effect=narrate):
        server.answer_event(game, "原地挖坑把他埋了")
    assert given == [(3, "惡")] and asked == [(True, rules.EVIL_DONE, True)]
    lines = game.state.journal[0].lines
    assert lines[0].startswith("你：「原地挖坑把他埋了」（成算") and "成了。" not in lines
    assert lines[1] == (story or rules.EVIL_DONE) and lines.count(rules.EVIL_DONE) == (0 if story else 1)


@pytest.mark.parametrize("spent", [20.0, "all"], ids=["some-left", "none-left"])
def test_the_moral_call_gets_what_the_scoring_left_of_the_budget(game, at_a_gamble, breaker_clock, monkeypatch, spent):
    """FB-223：評分之後另外判一次善惡（PM 2026-10-14：不併進評分那一次），兩次在同一個 B 段、共用 free_text_budget_seconds：
    判善惡那一次用評分剩下來的再切一份（複本，原本的 client 不動）；評分把預算用到不夠一趟就不判、當「中」，成功率照用、不退回 40。"""
    from conftest import FixedRandom

    total = server.CONTENT.config.free_text_budget_seconds
    used = total - 0.5 if spent == "all" else spent
    seen, given = [], []

    def chat(self, messages, response_model, **kwargs):
        seen.append((response_model, self.timeout))
        if response_model is server.event_llm.SuccessRateJudgment:
            breaker_clock[0] += used
            return server.event_llm.SuccessRateJudgment(success_rate=85)
        return server.event_llm.MoralJudgment(moral="惡")

    real = Game.answer_event
    monkeypatch.setattr(OllamaClient, "chat_structured", chat)
    monkeypatch.setattr(
        Game, "answer_event", lambda self, request, llm_rate=None, moral=None: given.append((llm_rate, moral)) or real(self, request, llm_rate, moral),
    )
    game.rng = FixedRandom(0.0)
    with mock.patch.object(server.event_llm, "narrate_event_gamble", return_value=None):
        server.answer_event(game, "原地挖坑把他埋了")
    assert seen[0] == (server.event_llm.SuccessRateJudgment, total / 2)
    if spent == "all":
        assert len(seen) == 1 and given == [(85, "中")]  # 不夠一趟：不判，成功率照用
    else:
        assert seen[1] == (server.event_llm.MoralJudgment, pytest.approx((total - used) / 2)) and given == [(85, "惡")]
    assert game.client.timeout == server.CONTENT.config.ollama_timeout


def test_answering_does_nothing_when_the_event_was_dealt_with_meanwhile(game, at_a_gamble):
    def assess(client, event, text, **_):
        server.act(game, lambda g: setattr(g.state, "pending_event", None))  # 另一個分頁先選了別的
        return server.event_llm.EventVerdict(85)

    with mock.patch.object(server.event_llm, "judge_event_gamble", side_effect=assess):
        msgs = server.answer_event(game, "大喊官兵來了")
    assert "事情已經過去了" in "\n".join(msgs)
    assert not any(e.title.endswith("隨口應對") for e in game.state.journal)


def test_the_page_offers_the_box_and_rejects_empty_words(client, monkeypatch):
    _player(client)
    game = next(iter(server.GAMES.values()))
    from tianxia.models import FreeTextChoice

    event = next(iter(server.CONTENT.events.values()))
    monkeypatch.setattr(event, "free_text", FreeTextChoice(prompt="自己想辦法……", stat="str"))
    server.act(game, lambda g: setattr(g.state, "pending_event", event.id))
    main = client.get("/api/main").json()
    assert main["event_free_text"] == "自己想辦法……"
    # 選項只有一行，底下不另起一行（企劃者 2026-10-05）；wait 是大場面按下去等模型時換上的字，這裡不是仗、是空的
    assert main["options"][-1] == {"id": "choice:free", "label": "自己想辦法……", "enabled": True, "wait": "", "confirm": "", "confirm_yes": "",
                                   "tag": "", "note": ""}  # note：名聲 5B 俠寇選項的第二行，這裡空著
    assert client.post("/api/answer", json={"text": "  "}).status_code == 400
    with mock.patch.object(server.event_llm, "judge_event_gamble", return_value=server.event_llm.EventVerdict(50)):
        main = client.post("/api/answer", json={"text": "大喊官兵來了"}).json()["main"]
    assert main["event_free_text"] is None


def test_main_view_sends_the_season_result_only_when_season_one_rests(game, monkeypatch):
    """第一季（開關開著、這一季蓋了章）收季之後才有結算卡；進行中、開關關著收季都沒有（計畫 T9）。"""
    monkeypatch.setattr(server.CONTENT.config, "admins", ["測試"])
    assert "season_result" not in server.look(game, server.main_view)
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))
    assert "season_result" not in server.look(game, server.main_view)  # 還在進行
    game.admin_end_season(now=game.now)
    result = server.look(game, server.main_view)["season_result"]
    assert result["title"] and result["text"].startswith("<p>戰事提前收束。")
    assert len(result["timeline"]) == 12 and all(row["text"].startswith("<p>") for row in result["timeline"])


def test_resting_season_one_writes_the_ending_once(game, monkeypatch):
    """FB-046：休季時結局那句只在結算卡上：「剛剛」不再是季末那則公告（放再前面那一則）、場景寫所在的地方、
    本週大事不畫（這一季的大事結算卡上都有）。江湖紀錄頁照舊列得到季末那則。"""
    monkeypatch.setattr(server.CONTENT.config, "admins", ["測試"])
    _season_one_now(game, monkeypatch)
    player = Game.new(server.CONTENT, "路人", world=game.world)
    player.sync(game.now)
    game.admin_end_season(now=game.now)
    player.sync(game.now)
    ending = game.state.world.ending_text
    assert player.state.journal[0].title == WORLD_NEWS and player.state.journal[0].tag == ending
    view = server.main_view(player)
    assert view["season_result"]["text"] == server.md(ending)
    assert ending not in view["now"] and "賽季開始" in view["now"] and ending in view["latest"]
    assert ending not in view["scene"] and view["scene"] == server.md(player.location_text())
    assert view["bulletin"] == []


def test_switch_off_season_end_sends_no_result_card(game, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "admins", ["測試"])
    game.admin_end_season(now=game.now)
    assert game.state.world.ended and "season_result" not in server.look(game, server.main_view)


def test_orders_hidden_from_other_factions(game, monkeypatch):
    """T6 RF2：/api/main 只給自己陣營的軍令；散人沒有 orders 鍵；別陣營的軍令文字不出現在整份資料裡。"""
    import json as _json

    _season_one_now(game, monkeypatch)
    guan = Game.new(server.CONTENT, "官甲", world=game.world)
    huang = Game.new(server.CONTENT, "黃乙", world=game.world)
    guan.state.player.faction, huang.state.player.faction = "guan", "huang"
    guan.advance(700)  # 跨過第一個曆時交界（這一季照 14 天的章，一個曆時 600 秒）：第 1 週發令
    huang.sync(huang.now)  # 伺服器每個請求都會同步；黃乙手上那份季還是官甲推進之前的
    g, h = server.main_view(guan), server.main_view(huang)  # 這兩個角色沒存進資料庫：直接組畫面，不經過重讀角色的 look
    assert g["orders"] and h["orders"]
    dumped = _json.dumps(h, ensure_ascii=False)
    assert not any(o["text"] in dumped for o in g["orders"])
    assert "orders" not in server.main_view(game)  # 散人


def test_switch_off_main_view_has_no_orders(game):
    game.state.player.faction = "guan"
    game.advance(7 * 86400)
    assert "orders" not in server.main_view(game)


def test_main_view_shows_the_cart_being_carried(game, monkeypatch):
    from tianxia.state import Convoy

    _season_one_now(game, monkeypatch)
    game.state.player.faction = "guan"
    game.state.player.convoy = Convoy(order="x", grain=4, from_loc="xinye", to_loc="wan_city")
    assert server.main_view(game)["convoy"] == "你押著一車糧（4 份），要送到宛城。"
    game.state.player.convoy = None
    assert "convoy" not in server.main_view(game)


# ── 管理者：時刻表與救場（計畫 T10）────────────────────────


def _season_one_admin(client, monkeypatch):
    """開關打開（週末設定）之後才開季：這一季蓋了「開」的章，有時刻表。回傳管理者的 Game。"""
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    monkeypatch.setattr(server.CONTENT.config, "season_days", 2.5)
    _admin(client, monkeypatch)
    return server.game_for("掌門")


def test_admin_timetable_choices(client, monkeypatch):
    """/api/admin 多回時刻表（十二件，照內容順序；可排的三場決戰與季末附現實時間）、可以定的結果（宛城要等第 3 週、
    季末不列）、有人鎖定的大事。開關關著是空的。"""
    game = _season_one_admin(client, monkeypatch)
    assert game.world.get_season().season_one
    choices = client.get("/api/admin").json()
    rows = choices["timetable"]
    assert [r["id"] for r in rows] == [e.id for e in server.CONTENT.timetable]
    changshe = next(r for r in rows if r["id"] == "changshe_fire")
    season = game.world.get_season()
    assert changshe["label"] == "第6週　長社火攻" and changshe["schedulable"] and changshe["state"] == "later"
    assert abs(changshe["at_real"] - (time.time() + season.schedule["changshe_fire"] - season.time)) < 5
    assert next(r for r in rows if r["id"] == "luzhi_siege")["schedulable"] is False
    results = {r["value"]: r["label"] for r in choices["results"]}
    assert results["bocai_routs_zhujun|成"] == "波才大敗朱儁：成"
    assert results["changshe_fire|guan:大勝"] == "長社火攻：官軍大勝"
    assert not any(v.startswith(("wancheng|", "xiaquyang|")) for v in results)
    assert choices["locks"] == []


def test_admin_timetable_choices_empty_with_the_switch_off(client, monkeypatch):
    _admin(client, monkeypatch)
    choices = client.get("/api/admin").json()
    assert (choices["timetable"], choices["results"], choices["locks"]) == ([], [], [])


def test_admin_schedule_jump_and_rescue_via_api(client, monkeypatch):
    """每個新動作都走 /api/do/<op>，回應的 message 是引擎那一句。"""
    game = _season_one_admin(client, monkeypatch)
    out = client.post("/api/do/schedule", json={"id": "changshe_fire", "at": time.time() + 3600}).json()
    assert "已把長社火攻排在" in out["message"]
    season = game.world.get_season()
    assert 0 <= season.schedule["changshe_fire"] - (season.time + 3600) < 115  # 對齊到下一個曆時交界（約 107 秒內）
    assert "跳到" in client.post("/api/do/jump_next", json={}).json()["message"]
    client.post("/api/do/resolve_event", json={"id": "bocai_routs_zhujun", "key": "成"})
    assert game.world.get_season().timeline["bocai_routs_zhujun"].key == "成"
    client.post("/api/do/set_trend", json={"id": "yingru", "value": 70})
    assert game.world.get_season().trends["yingru"] == 70
    assert "沒有人鎖定" in client.post("/api/do/clear_lock", json={"id": "luzhi_siege"}).json()["message"]
    assert "沒有進行中的決戰" in client.post("/api/do/cancel_battle", json={}).json()["message"]


def test_a_fight_then_an_event_sends_a_short_now_card_and_a_stable_guide_key(client, monkeypatch):
    """FB-076（正式內容）：遊歷打贏、升級、聽到一件事，接著冒出事件。事件的選項在畫面上時，/api/main 的「剛剛」卡片（card）
    沒有升級那一行、卡片底下（now）沒有「你聽到一件事」那一行，江湖紀錄頁最上面（latest）與紀錄那一則（journal）照舊有；
    說書人的框換成「先把眼前的「…」了結」，key 還是這一步的 id。事件了結（沒有待處理的事件）之後兩行都照舊畫。"""
    from conftest import FixedRandom
    from tianxia import journal

    monkeypatch.setattr(server.CONTENT.config, "train_event_chance", 1.0)  # 打完一定接戰後的事件
    first_step = _a_guide_step_after_the_hut(monkeypatch)  # 序章之後沒有引導步驟了（軍令兩步由入伍段取代）：接一步測試用的
    _player(client, prologue=True)
    game = server.game_for("沈青衫")

    def graduated(g):
        g.state.player.location = "yingchuan_wilds"
        _stand_on(g, first_step)
        g.state.pending_event = None

    server.act(game, graduated)
    assert client.get("/api/main").json()["guide"]["key"] == first_step.id
    game.rng = FixedRandom(0.99)
    assert client.post("/api/choose", json={"id": "act:train"}).status_code == 200
    heard = journal.fragment_line("聽說皇甫嵩說過：「兵有奇變，不在眾寡。」")
    server.act(game, lambda g: g.state.journal[0].lines.append(heard))  # 打完仗順便聽到一件事
    stored = open_characters().load("沈青衫")
    assert stored.pending_event is not None and stored.battles[0].levelups.you == 2  # 升了級，事件選項在畫面上
    main = client.get("/api/main").json()
    assert [o["id"] for o in main["options"]][0] == "choice:0"
    assert main["card"] and "升到第" not in main["card"] and "可配" not in main["card"]
    assert "你聽到一件事" not in main["now"] and "tx-hearsay" not in main["now"]
    assert "你聽到一件事" in main["latest"]  # 江湖紀錄頁最上面照舊
    assert main["guide"]["key"] == first_step.id and main["guide"]["text"].startswith("先把眼前的「")
    assert main["guide"]["pending"] is True  # 網頁認這個旗標、預設把這一句收成一行（說書人的框不擠掉事件的選項）
    assert "升到第 2 級！" in "\n".join(stored.journal[0].lines)  # 紀錄那一則裡升級的句子還在
    assert heard in stored.journal[0].lines
    report = client.get(f"/api/reports?id={main['card_id']}").json()["detail"]
    assert "升到第 2 級！" in report and "你有 1 點屬性可以分配" in report  # 戰報頁：完整的句子照舊
    server.act(game, lambda g: setattr(g.state, "pending_event", None))  # 沒有事件待處理：兩行都照舊
    main = client.get("/api/main").json()
    assert "升到第 2 級" in main["card"] and "你聽到一件事" in main["now"]


def test_a_character_created_on_the_web_starts_in_the_hut(client, monkeypatch, prologue_content):
    """網頁上建的角色走序章（create_character 傳 prologue=True）；假人與腳本用的 Game.new 不傳，站在起點。"""
    monkeypatch.setattr(server, "CONTENT", prologue_content)
    main = _player(client, prologue=True)["main"]
    player = server.game_for("沈青衫").state.player
    assert player.location == "hut" and player.tutorial_step == 0
    assert main["prologue"] == {"reveal": [], "glow": [], "skip": True}
    assert main["guide"] is None  # 遇險的事件還在眼前，還沒遇到師父
    assert Game.new(prologue_content, "假人").state.player.location == "town"


def test_the_prologue_recap_is_empty_without_a_prologue(client, monkeypatch, content):
    """設定頁的「重看序章」：沒有序章的內容（測試內容）是空字串（網頁就不畫那顆鈕）。"""
    monkeypatch.setattr(server, "CONTENT", content)
    _player(client, "shen_02", "無序章")
    assert client.get("/api/prologue").json() == {"text": ""}


def test_the_real_prologue_recap_reads_the_whole_prologue(client):
    """正式內容的序章回顧：遇險、拜師、師父十一步的話照順序排成一頁，沒有沒換掉的佔位字。"""
    _player(client, "shen_04", "沈青衫", prologue=True)
    text = client.get("/api/prologue").json()["text"]
    assert text.index("潁川城外") < text.index("草廬") < text.index("去，按底下的「俠客」") < text.index("這是盤纏")
    assert "{武學}" not in text and "山腰上的草廬不見了" in text


def test_the_prologue_recap_is_served_as_html(client, monkeypatch, prologue_content):
    """設定頁的「重看序章」：GET /api/prologue 回 {text: html}。跟上面分成兩個測試：同一個資料庫裡全服的賽季只認先開季的那份
    內容的主線，進了角色畫面（現在一進去就輪詢）換一份內容再開，找不到那一份的主線。"""
    monkeypatch.setattr(server, "CONTENT", prologue_content)
    _player(client, "shen_03", "沈青衫")
    text = client.get("/api/prologue").json()["text"]
    assert "<strong>城外</strong>" in text and "草廬已經看不見了。" in text and "{武學}" not in text
    assert text.index("城外") < text.index("去看修練頁。")
    assert client.get("/api/prologue").status_code == 200


def test_timetable_finale_row_shows_the_ending_title(client, monkeypatch):
    """FB-051：收季之後，時刻表季末那一列寫結局的標題（豪強坐大），不是結局 id。"""
    game = _season_one_admin(client, monkeypatch)
    client.post("/api/do/end_season", json={})
    rows = client.get("/api/admin").json()["timetable"]
    finale = next(r for r in rows if r["id"] == "xiaquyang")
    ending = game.world.get_season().ending_id
    title = next(e.title for e in server.CONTENT.scenario.endings if e.id == ending)
    assert finale["result"] == title and ending not in finale["result"]


def test_admin_choices_say_whether_the_next_season_has_a_timetable(client, monkeypatch):
    """FB-050：「開啟下一季」的問句要提醒排時間——下一季會照第一季的規則開（開關開著）時，/api/admin 說一聲。"""
    _admin(client, monkeypatch)
    assert client.get("/api/admin").json()["next_has_timetable"] is False
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    assert client.get("/api/admin").json()["next_has_timetable"] is True


# ── 一次輪詢只拿一次行動鎖（壓測發現 /api/main 拿兩次：一次 act、一次 look，PM 2026-10-06）──────────────


def _two_step_poll(game):
    """舊的 /api/main：一次無事的 act、再一次 look(main_view)，各拿一次行動鎖。拿來當參考答案。"""
    server.act(game, lambda g: None)
    return server.look(game, server.main_view)


def test_a_poll_takes_the_action_lock_once(client, lock_events):
    _player(client)
    lock_events.clear()
    assert client.get("/api/main").status_code == 200
    assert lock_events == ["enter", "exit"]  # 以前是 enter、exit、enter、exit


def test_the_page_load_takes_the_action_lock_once_too(client, lock_events):
    """/api/me（開頁、登入、取名之後的第一畫面）也是一次無事的 act 加一次 look(main_view)：同一個形狀、同一個修法。"""
    _player(client)
    lock_events.clear()
    assert client.get("/api/me").json()["stage"] == "game"
    assert lock_events == ["enter", "exit"]


POLL_T0 = 1_800_000_000.0
POLL_SCENES = ["idle", "event", "muster", "showdown", "resting", "road", "road_arrives"]
POLL_OFFLINE = {"road": 60}  # 其他都離線三小時；到潁川水邊的路要走 182 秒，離線 60 秒時還在路上（走一半）


def _poll_scene(client, monkeypatch, scene):
    """某個狀態下的新角色，時間釘在 POLL_T0（server.time.time 換成固定值，兩次布置得到一模一樣的狀態）。"""
    _player(client)
    game = server.game_for("沈青衫")
    game.rng = random.Random(7)
    if scene == "event":
        game.state.pending_event = next(iter(server.CONTENT.events))
        open_characters().save(game.state)
    elif scene in ("muster", "showdown"):
        game.state.player.faction = "guan"
        open_characters().save(game.state)
        definition = server.CONTENT.battles["huangjin_showdown"]
        open_world().start_battle(definition, now=POLL_T0 - (definition.muster_seconds + 1 if scene == "showdown" else 0))
        open_world().mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=320.0))
    elif scene == "resting":
        monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
        server.act(game, lambda g: g.admin_end_season(POLL_T0))
    elif scene in ("road", "road_arrives"):
        server.act(game, lambda g: g.travel("yingshui", "walk"))  # 出發了；輪詢時還在路上，或同步補算時抵達
        assert game.state.player.journey is not None


def _everything_after(poll):
    """跑一次輪詢，回傳畫面資料與它留在資料庫裡的東西（角色存檔、這一季、決戰），各轉成排好序的 JSON 字串好比對。"""
    import json

    body = poll()
    world = open_world()
    return {
        "view": json.dumps(body, sort_keys=True, ensure_ascii=False),
        "character": open_characters().load("沈青衫").model_dump_json(),
        "season": world.get_season().model_dump_json(),
        "battle": None if world.get_battle() is None else world.get_battle().model_dump_json(),
    }


@pytest.mark.parametrize("scene", POLL_SCENES)
def test_one_lock_poll_answers_and_leaves_exactly_what_the_two_step_poll_did(scene, tmp_path, monkeypatch):
    """同一個狀態、同一個現在：新的（一把鎖）與舊的（act 加 look）回同一份畫面，也留下同一份存檔、季與決戰——
    補算時間、決戰推進、大事補送都照舊。兩次各用自己的資料庫、各自布置（時間與亂數都釘住）。"""
    from tianxia import database

    answers = {}
    admins = list(server.CONTENT.config.admins)
    for label in ("two_step", "one_lock"):
        monkeypatch.setattr(server.CONTENT.config, "admins", admins)  # 休季那一幕把玩家設成管理者，名號就成了保留的：第二輪要還原
        monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / f"{label}.db")
        for store in (server.SESSIONS, server.GAMES):
            store.clear()
        client = TestClient(server.app)
        with mock.patch("server.time.time", return_value=POLL_T0):
            _poll_scene(client, monkeypatch, scene)
        game = server.game_for("沈青衫")
        with mock.patch("server.time.time", return_value=POLL_T0 + POLL_OFFLINE.get(scene, 3 * 3600)):  # 離線三小時：同步有東西可補
            if label == "two_step":
                answers[label] = _everything_after(lambda: _two_step_poll(game))
            else:
                answers[label] = _everything_after(lambda: client.get("/api/main").json())
        database.close_all()
    assert answers["one_lock"] == answers["two_step"]
    if scene in ("road", "road_arrives"):  # 路上的兩幕真的是路上、與抵達（不是兩個一樣的畫面）
        assert ('"act:on_road"' in answers["one_lock"]["view"]) == (scene == "road")


def test_a_view_that_breaks_still_leaves_the_catch_up_saved(client, monkeypatch):
    """舊的兩步：補算與存檔那一把鎖已經放了，畫面才壞掉，補算的結果留著。一把鎖之後也要一樣：畫面壞了不能把補算一起撤回。"""
    _player(client)
    before = open_characters().load("沈青衫").last_real
    monkeypatch.setattr(server, "main_view", lambda g: 1 / 0)
    with mock.patch("server.time.time", return_value=before + 5000):
        with pytest.raises(ZeroDivisionError):
            client.get("/api/main")
    assert open_characters().load("沈青衫").last_real == before + 5000


def test_a_view_that_breaks_rolls_back_what_the_view_itself_wrote(client, monkeypatch):
    """畫面建構不是唯讀：options() 會把全服決戰追趕到現在（寫共用狀態）。舊的兩步裡畫面壞掉時，畫面那把鎖整筆撤回；
    一把鎖之後只能撤回畫面寫的那一段（savepoint），補算與存檔照舊留著。
    情境：沒人參戰的決戰，最後一回合逾時，由這次輪詢收場；套用結果時壞一次。壞掉那次，決戰要還是「進行中」
    （收場的標記跟著撤回），下一次輪詢才會重新收場、把結果套上——不然標記已經是「收場」，結果永遠套不上。"""
    definition = server.CONTENT.battles["huangjin_showdown"]
    with mock.patch("server.time.time", return_value=POLL_T0):  # 時間從頭釘住：季的時鐘也從 POLL_T0 起算，不會被補算到收季
        _player(client)
        open_world().start_battle(definition, now=POLL_T0)
        client.get("/api/main")
    deadline = open_world().get_battle().muster_deadline_real
    with mock.patch("server.time.time", return_value=deadline):
        client.get("/api/main")  # 集結截止，沒人參戰：開打
    assert open_world().get_battle().phase == "active"
    chronicle_before = len(open_world().get_season().chronicle)
    applied = []
    real = Game._apply_battle_outcome

    def breaks_once(self, battle):
        applied.append(battle.phase)
        if len(applied) == 1:
            raise RuntimeError("套用結果時壞了")
        return real(self, battle)

    monkeypatch.setattr(Game, "_apply_battle_outcome", breaks_once)
    with mock.patch("server.time.time", return_value=deadline + definition.round_seconds):
        with pytest.raises(RuntimeError, match="套用結果時壞了"):
            client.get("/api/main")
        assert open_world().get_battle().phase == "active"  # 畫面寫的「收場」撤回了
        assert open_characters().load("沈青衫").last_real == deadline + definition.round_seconds  # 補算與存檔照舊留著
        client.get("/api/main")
    assert applied == ["ended", "ended"]  # 第二次輪詢重新收場、重新套用
    assert open_world().get_battle().phase == "ended"
    assert len(open_world().get_season().chronicle) == chronicle_before + 1  # 保底結果寫了一則江湖史


def test_a_poll_for_an_account_without_a_character_is_still_refused(client):
    client.post("/api/register", json={"login": "no_char", "password": "secret-pw", "again": "secret-pw"})
    assert client.get("/api/main").status_code == 409


# ── 畫面建構時，季的階段只讀一次（壓測：每次建選單都把整份全服狀態讀一遍）───────────────


def test_building_the_main_view_reads_the_season_phase_once(game, monkeypatch):
    reads = []
    real = type(game.world).season_phase
    monkeypatch.setattr(type(game.world), "season_phase", lambda self: reads.append(1) or real(self))
    server.look(game, server.main_view)
    assert len(reads) == 1  # 以前狀態列、選單、「剛剛」、說書人對話框各讀一次，共四次


def test_the_season_phase_is_read_again_on_the_next_screen(tmp_path, monkeypatch):
    """記住的只在這一次建構裡：別人（管理者的另一個分頁、另一個程式）在兩次畫面之間開了季，下一次畫面就看到。"""
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", False)
    fresh = Game.new(server.CONTENT, "路人", world=open_world(tmp_path / "world.db"))
    assert fresh.world.season_phase() == "preparing"
    assert [o["id"] for o in server.look(fresh, server.main_view)["options"]] == ["season:preparing"]
    assert open_world(tmp_path / "world.db").open_season(server.CONTENT, 0.0)  # 另一個執行緒、程式開的季
    assert "season:preparing" not in [o["id"] for o in server.look(fresh, server.main_view)["options"]]


def test_an_action_that_changes_the_phase_is_seen_by_the_view_of_the_same_poll(tmp_path, monkeypatch):
    """act_look 的動作與畫面在同一把鎖裡：動作開了季，同一次的畫面就是開了季的樣子（記住階段只從畫面開始）。"""
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", False)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["路人"])
    fresh = Game.new(server.CONTENT, "路人", world=open_world(tmp_path / "world.db"))
    msgs, view = server.act_look(fresh, lambda g: server.FEATURE_ADMIN_ACTIONS["open_season"].run(g, {}), server.main_view)
    assert msgs and "season:preparing" not in [o["id"] for o in view["options"]]
    assert fresh.world.season_phase() == "running"


# ── 模型佇列（線上架構第 2 期，llm_queue.py）：鎖外的五個模型呼叫都走 server.model_call ───────────────
# 五件事：對話生成（prepare_dialogue）、大場面判讀（prepare_fight）、開爐取名（prepare_forge）、隨口應對的評分與潤色
# （answer_event 的 B、D 段）。開關是 Config.llm_queue_slots（預設 0＝關，server.QUEUE 是 None，照舊直接叫）。


class _FullQueue:
    """直接把退路交回來的佇列、不叫 job：LlmQueue 現在只有「假人滿了」（bot_cap）會這樣；排太久與重複的那一件丟的是
    QueueTimeout 與 Busy（見 _TimedOutQueue、_ScriptedQueue），不給退路。"""

    def __init__(self):
        self.calls = []

    def run(self, owner, job, *, fallback, bot=False, wait=30.0):
        self.calls.append((owner, bot, wait))
        return fallback


def _slow_queue(monkeypatch, breaker_clock, seconds):
    """每一件都排了 seconds 秒才輪到（撥 server._monotonic，不真的等），輪到了照常叫 job。回傳每一件的名號紀錄。"""
    owners = []
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)

    def run(owner, job, *, fallback, bot=False, wait=30.0):
        owners.append(owner)
        breaker_clock[0] += seconds
        return job()

    monkeypatch.setattr(queue, "run", run)
    monkeypatch.setattr(server, "QUEUE", queue)
    return owners


def test_model_call_without_a_queue_calls_directly(game):
    """開關關著：直接叫，跟現在一樣（Review Focus 5）。"""
    assert server.QUEUE is None
    assert server.model_call(game, lambda: "模型的話", fallback="退路") == "模型的話"


def test_model_call_queues_under_the_character_and_flags_bots(game, monkeypatch):
    seen = {}

    def fake_run(owner, job, *, fallback, bot=False, wait=30.0):
        seen.update(owner=owner, bot=bot, wait=wait)
        return job()

    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    monkeypatch.setattr(queue, "run", fake_run)
    monkeypatch.setattr(server, "QUEUE", queue)
    assert server.model_call(game, lambda: "好", fallback="退路") == "好"
    assert seen == {"owner": "測試", "bot": False, "wait": server.CONTENT.config.llm_queue_wait_seconds}
    game.state.player.bot = BotProfile(personality="積極", seed=1)  # 假人的存檔
    server.model_call(game, lambda: "好", fallback="退路")
    assert seen["bot"] is True


def test_a_second_request_from_the_same_player_is_cancelled_or_refused_as_the_call_site_says(game, monkeypatch):
    """同一個角色兩個分頁同時送：第二件不叫第二次模型（Review Focus 1）。佇列對它丟 Busy，model_call 照呼叫端的意思：
    沒給 busy 訊息的（潤色：不插句子，本來就無害）拿 fallback；給了 busy 訊息的（評分、開爐、大場面、對話：
    退路是一個結果，第二個分頁就能拿它挑結果）丟 GameError、一個字都不套用（審查 M2、控制者裁示；對話是 FB-077）。"""
    queue = llm_queue.LlmQueue(slots=2, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    started, release = threading.Event(), threading.Event()

    def slow():
        started.set()
        release.wait(5)
        return "第一件"

    first = threading.Thread(target=lambda: server.model_call(game, slow, fallback="退路"))
    first.start()
    assert started.wait(2)
    assert server.model_call(game, lambda: "第二件", fallback="退路") == "退路"
    with pytest.raises(server.GameError, match="還在掂量"):
        server.model_call(game, lambda: pytest.fail("不該叫"), fallback="退路", busy="上一件還在掂量。")
    release.set()
    first.join(2)
    assert queue.snapshot() == {"running": 0, "waiting": 0}


def test_the_queue_key_ignores_the_case_of_the_name(monkeypatch):
    """「Rayal」與「rayal」是同一個人（名號比對不分大小寫）：用大小寫換名字，也不能多拿一件。"""
    queue = llm_queue.LlmQueue(slots=2, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    upper, lower = Game.new(server.CONTENT, "Rayal"), Game.new(server.CONTENT, "rayal")
    started, release = threading.Event(), threading.Event()

    def slow():
        started.set()
        release.wait(5)
        return "第一件"

    first = threading.Thread(target=lambda: server.model_call(upper, slow, fallback="退路"))
    first.start()
    assert started.wait(2)
    assert server.model_call(lower, lambda: pytest.fail("不該叫"), fallback="退路") == "退路"  # 同一個人：沒給 busy 訊息就是 fallback
    release.set()
    first.join(2)


def test_forge_budget_counts_the_time_spent_in_the_queue(game, monkeypatch, breaker_clock):
    """開爐首次取名：交給模型的預算從 A 段算起，扣掉排隊等掉的時間（Review Focus 4）。"""
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)

    def queued(owner, job, *, fallback, bot=False, wait=30.0):
        breaker_clock[0] += 45  # 排了 45 秒才輪到
        return job()

    monkeypatch.setattr(queue, "run", queued)
    monkeypatch.setattr(server, "QUEUE", queue)
    monkeypatch.setattr(Game, "forge_request", lambda self, art, insights, **kwargs: "單子")
    budgets = []
    monkeypatch.setattr(
        server.naming, "generate",
        lambda client, content, request, *, budget, person: budgets.append(budget) or ("名字", "說明"),
    )
    assert server.prepare_forge(game, None, []) == ("名字", "說明")
    assert budgets == [pytest.approx(server.CONTENT.config.naming_budget_seconds - 45)]


def test_the_big_fight_budget_counts_the_time_spent_in_the_queue(game, monkeypatch, breaker_clock):
    """大場面判讀：跟開爐取名一樣，預算從 A 段算起、扣掉排隊的時間；排太久預算就是 0（judge 分不到一趟就不叫）。"""
    game.state.pending_event = "kou_boss"
    budgets = []

    def judge(client, request, swing, budget=None):
        budgets.append(budget)
        return FIGHT_JUDGMENT

    for waited in (45, 75):
        _slow_queue(monkeypatch, breaker_clock, waited)
        with mock.patch.object(server.fight_llm, "judge", side_effect=judge):
            fight = server.prepare_fight(game, "choice:0")
        assert isinstance(fight, fight_llm.PreparedFight) and fight.judgment == FIGHT_JUDGMENT
    assert budgets == [pytest.approx(server.CONTENT.config.big_fight_budget_seconds - 45), 0.0]


def test_the_dialogue_budget_counts_the_time_spent_in_the_queue(game, monkeypatch, breaker_clock):
    """對話生成跟開爐、大場面一樣有總預算（Config.dialogue_budget_seconds，PM 2026-10-06）：從 A 段算起、扣掉排隊的時間，
    交給模型的是複本，逾時是剩下的一半（chat_structured 一次最多送兩趟）；原本那個 client 不動。"""
    _stand_by_a_figure(game)
    _slow_queue(monkeypatch, breaker_clock, 45)
    seen = []

    def generate(client, messages, required=()):
        seen.append(client)
        return DIALOGUE_TURN

    monkeypatch.setattr(companion_agent, "generate_turn", generate)
    prepared = server.prepare_dialogue(game, "act:socialize")
    config = server.CONTENT.config
    assert prepared.turn is DIALOGUE_TURN
    assert len(seen) == 1 and seen[0] is not game.client
    assert seen[0].timeout == pytest.approx((config.dialogue_budget_seconds - 45) / 2)
    assert game.client.timeout == config.ollama_timeout


def test_a_dialogue_that_waited_out_its_budget_is_cancelled_without_asking_the_model(game, monkeypatch, breaker_clock):
    _stand_by_a_figure(game)
    _slow_queue(monkeypatch, breaker_clock, server.CONTENT.config.dialogue_budget_seconds + 1)
    monkeypatch.setattr(companion_agent, "generate_turn", lambda *args: pytest.fail("預算用完了，不該叫模型"))
    prepared = server.prepare_dialogue(game, "act:socialize")
    assert prepared.turn is None and (prepared.option_id, prepared.companion_id) == ("act:socialize", "luzhi")


def test_the_free_text_budget_counts_the_time_spent_in_the_queue(game, at_a_gamble, monkeypatch, breaker_clock):
    """隨口應對的評分也有總預算（Config.free_text_budget_seconds）：扣掉排隊的時間；排太久就不叫、直接是保底的 40。
    潤色跟評分共用這一份預算，它自己再排隊的時間也扣：這裡每一件都排 45 秒以上，評分之後預算剩不到一趟，潤色一律不叫。"""
    rates, timeouts, narrated = [], [], []
    real = Game.answer_event
    monkeypatch.setattr(
        Game, "answer_event", lambda self, request, llm_rate=None, moral=None: rates.append(llm_rate) or real(self, request, llm_rate, moral),
    )

    def assess(client, event, text, **_):
        timeouts.append(client.timeout)
        return server.event_llm.EventVerdict(85)

    def narrate(client, event, text, success, effect_text, evil=False):
        narrated.append(client)
        return GAMBLE_NARRATION

    for waited in (45, 61):
        _slow_queue(monkeypatch, breaker_clock, waited)
        game.state.pending_event = at_a_gamble.id
        open_characters().save(game.state)
        with mock.patch.object(server.event_llm, "judge_event_gamble", side_effect=assess), \
                mock.patch.object(server.event_llm, "narrate_event_gamble", side_effect=narrate):
            server.answer_event(game, "大喊官兵來了")
    assert timeouts == [pytest.approx((server.CONTENT.config.free_text_budget_seconds - 45) / 2)]  # 第二次排太久，沒叫
    assert rates == [85, server.event_llm.DEFAULT_FREE_TEXT_SUCCESS_RATE]
    assert narrated == []  # 評分排掉 45 秒、潤色再排 45 秒：預算早就沒了
    assert game.client.timeout == server.CONTENT.config.ollama_timeout


# 五個呼叫點：dialogue 對話生成、fight 大場面判讀、forge 開爐取名、score 隨口應對評分、narrate 隨口應對潤色
# （最後兩個是同一個請求 server.answer_event 的 B、D 段）。
SITES = ["dialogue", "fight", "forge", "score", "narrate"]
GAMBLE_NARRATION = "你扯開嗓子一喊。"


def _ready(site, monkeypatch):
    """讓一個角色站在 site 那一件鎖外模型呼叫會被叫到的地方，模型換成假的（記下每一次拿到的 client 與預算、回固定的結果）。
    回傳（這個角色的 Game、做那件事的函式、模型被叫到的紀錄 [dict]）。"""
    seen = []
    if site == "dialogue":
        game = Game.new(server.CONTENT, "測試")
        _stand_by_a_figure(game)

        def generate(client, messages, required=()):
            seen.append({"kind": "dialogue", "client": client})
            return DIALOGUE_TURN

        monkeypatch.setattr(companion_agent, "generate_turn", generate)
        return game, lambda: server.choose(game, "act:socialize"), seen
    if site == "fight":
        game = Game.new(server.CONTENT, "測試")
        game.state.pending_event = "kou_boss"

        def judge(client, request, swing, budget=None):
            seen.append({"kind": "fight", "client": client, "budget": budget})
            return FIGHT_JUDGMENT

        monkeypatch.setattr(server.fight_llm, "judge", judge)
        return game, lambda: server.choose(game, "choice:0"), seen
    if site == "forge":
        game = _forger()

        def generate(client, content, request, *, budget, person):
            seen.append({"kind": "forge", "client": client, "budget": budget})
            return "旋風腿", "一句話。"

        monkeypatch.setattr(server.naming, "generate", generate)
        return game, lambda: server.forge(game, None, ["feng", "huo"]), seen
    from tianxia.models import Effect, FreeTextChoice

    game = Game.new(server.CONTENT, "測試")
    game.rng = random.Random(0)
    event = next(iter(server.CONTENT.events.values()))
    monkeypatch.setattr(event, "free_text", FreeTextChoice(
        prompt="自己想辦法……", stat="str", effect=Effect(text="成了。"), fail_effect=Effect(text="砸了。"),
    ))
    game.state.pending_event = event.id
    open_characters().save(game.state)
    real = Game.answer_event

    def answer(self, request, llm_rate=None, moral=None):
        seen.append({"kind": "rate", "rate": llm_rate})
        return real(self, request, llm_rate, moral)

    def assess(client, event, text, **_):
        seen.append({"kind": "score", "client": client})
        return server.event_llm.EventVerdict(85)

    def narrate(client, event, text, success, effect_text, evil=False):
        seen.append({"kind": "narrate", "client": client})
        return GAMBLE_NARRATION

    monkeypatch.setattr(Game, "answer_event", answer)
    monkeypatch.setattr(server.event_llm, "judge_event_gamble", assess)
    monkeypatch.setattr(server.event_llm, "narrate_event_gamble", narrate)
    return game, lambda: server.answer_event(game, "大喊官兵來了"), seen


def _asked(seen, kind):
    return [s for s in seen if s["kind"] == kind]


@pytest.mark.parametrize("site", SITES)
def test_with_the_queue_off_each_site_asks_the_model_directly(site, monkeypatch, breaker_clock):
    """開關關著（llm_queue_slots = 0）：沒有佇列，五個呼叫點直接叫模型。拿到的 client 與預算照現在的樣子：開爐、大場面拿
    game.client 本身（預算在 naming／fight_llm 裡再分）；對話、隨口應對的評分與潤色是 PM 2026-10-06 加的總預算，拿預算複本
    （逾時是剩下的一半、原本那個 client 不動）。"""
    assert server.QUEUE is None
    monkeypatch.setattr(llm_queue.LlmQueue, "run", lambda *args, **kwargs: pytest.fail("開關關著，不該碰佇列"))
    game, run, seen = _ready(site, monkeypatch)
    run()
    config = server.CONTENT.config
    if site == "dialogue":
        [asked] = _asked(seen, "dialogue")
        assert asked["client"] is not game.client and asked["client"].timeout == config.dialogue_budget_seconds / 2
        assert game.state.player.pending_companion == "luzhi"
    elif site == "fight":
        [asked] = _asked(seen, "fight")
        assert asked["client"] is game.client and asked["budget"] == config.big_fight_budget_seconds
        assert game.state.battles[0].narration in (FIGHT_JUDGMENT.winning, FIGHT_JUDGMENT.losing)
    elif site == "forge":
        [asked] = _asked(seen, "forge")
        assert asked["client"] is game.client and asked["budget"] == config.naming_budget_seconds
        assert open_world().lookup_insight_recipe(FENG_HUO).name == "旋風腿"
    elif site == "score":
        [asked] = _asked(seen, "score")
        assert asked["client"] is not game.client and asked["client"].timeout == config.free_text_budget_seconds / 2
        assert _asked(seen, "rate") == [{"kind": "rate", "rate": 85}]
    else:
        [asked] = _asked(seen, "narrate")
        assert asked["client"] is not game.client and asked["client"].timeout == config.free_text_budget_seconds / 2
        assert game.state.journal[0].lines[1] == GAMBLE_NARRATION
    assert game.client.timeout == config.ollama_timeout and game.client.retry is True


@pytest.mark.parametrize("site", SITES)
def test_a_queue_that_will_not_take_the_job_gives_each_site_its_old_fallback(site, monkeypatch):
    """佇列開著、這一件拿到退路（假人滿了；排太久與重複的那一件不在這裡，它們是拒絕）：模型一次都沒叫，結果跟現在模型叫不動時一模一樣
    ——對話取消（不扣體力）、大場面照打（優勢 0）、開爐走退路字表、隨口應對評分 40、潤色不插句子。"""
    queue = _FullQueue()
    monkeypatch.setattr(server, "QUEUE", queue)
    game, run, seen = _ready(site, monkeypatch)
    stamina = game.state.player.stamina
    run()
    config = server.CONTENT.config
    assert [_asked(seen, k) for k in ("dialogue", "fight", "forge", "score", "narrate")] == [[]] * 5
    owner = game.state.player.name.casefold()
    assert queue.calls == [(owner, False, config.llm_queue_wait_seconds)] * (2 if site in ("score", "narrate") else 1)
    if site == "dialogue":
        assert game.state.player.pending_companion is None and game.state.player.stamina == stamina
        assert game.state.journal[0].lines == ["盧植似乎無心多談，你只好先行告辭。"]
    elif site == "fight":
        record = game.state.battles[0]
        assert record.opponent == "波才" and record.narration == "" and record.rounds
    elif site == "forge":
        assert open_world().lookup_insight_recipe(FENG_HUO).name == naming.fallback_name(server.CONTENT, FENG_HUO, "意境")
    elif site == "score":
        assert _asked(seen, "rate") == [{"kind": "rate", "rate": server.event_llm.DEFAULT_FREE_TEXT_SUCCESS_RATE}]
    else:
        assert GAMBLE_NARRATION not in game.state.journal[0].lines


REFUSED_AS_DUPLICATE = {  # 重複的那一件：各呼叫點自己的一句（潤色沒有，不插句子就是了）
    "dialogue": server.BUSY_DIALOGUE, "fight": "還在對峙，稍等。", "forge": "上一爐還沒出爐。", "score": "上一句還在掂量，稍等。",
}


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("why", ["duplicate", "queue-timeout"])
def test_a_request_the_queue_refuses_gets_no_fallback(why, site, monkeypatch):
    """重複的那一件（why=duplicate）。審查 M2、控制者裁示：同一個玩家已經有一件在等模型，第二件（另一個分頁）不能拿退路——
    評分 40 是一個結果（灌水的寫法本來該得 0 分）、首次取名用退路字表是一個結果（整季登記）。所以隨口應對的評分、開爐、大場面都
    擋下來：不擲骰、不登記、不打、什麼都不收，回一句短話，眼前的事還在原地。對話也是（FB-077，PM 2026-10-06）：以前第二件拿
    cancelled 先進鎖，把「無心多談，你只好先行告辭」寫進紀錄、求見的選單也收掉，第一件的回話後來照樣套不上；現在被擋下來、什麼都
    不動，第一件照常套用。潤色照舊不插句子。

    排太久的那一件（why=queue-timeout）。PM 2026-10-06：排超過 llm_queue_wait_seconds 秒還沒輪到的那一件，跟重複的那一件一樣
    處理——不給退路。沒被服務到的人拿一個結果沒有道理，再試一次就好；每個呼叫點回同一句 BUSY_QUEUE_TIMEOUT（對話是 FB-077 之後：
    跟重複的那一件一樣被擋下來，不再取消那一輪）；潤色不插句子（沒給 busy 訊息的呼叫點，跟重複的那一件一樣）。"""
    answer = "busy" if why == "duplicate" else "timeout"
    queue = _ScriptedQueue("run", answer) if site == "narrate" else _ScriptedQueue(answer)
    monkeypatch.setattr(server, "QUEUE", queue)
    game, run, seen = _ready(site, monkeypatch)
    stamina = game.state.player.stamina
    refusal = REFUSED_AS_DUPLICATE.get(site) if why == "duplicate" else server.BUSY_QUEUE_TIMEOUT
    if site == "dialogue":
        with pytest.raises(server.GameError, match=refusal):
            run()
        assert _asked(seen, "dialogue") == []
        stored = open_characters().load("測試")
        assert stored.player.pending_companion is None and stored.player.stamina == stamina
        assert not any("無心多談" in "".join(e.lines) for e in stored.journal)  # 沒有寫紀錄
    elif site == "fight":
        with pytest.raises(server.GameError, match=refusal):
            run()
        assert _asked(seen, "fight") == []
        stored = open_characters().load("測試")
        assert stored.battles == [] and stored.pending_event == "kou_boss" and stored.player.stamina == stamina
    elif site == "forge":
        with pytest.raises(server.GameError, match=refusal):
            run()
        assert _asked(seen, "forge") == [] and open_world().lookup_insight_recipe(FENG_HUO) is None
        assert open_characters().load("沈青衫").player.stats["xinde"] == 100
    elif site == "score":
        with pytest.raises(server.GameError, match=refusal):
            run()
        assert _asked(seen, "score") == [] and _asked(seen, "rate") == []  # 沒評分、也沒擲骰，不是保底的 40
        stored = open_characters().load("測試")
        assert stored.pending_event is not None and not any(e.title.endswith("隨口應對") for e in stored.journal)
    else:
        run()  # 評分照常、擲骰照常；潤色那一件被擋下來（或排太久）：不插句子
        assert _asked(seen, "rate") == [{"kind": "rate", "rate": 85}] and _asked(seen, "narrate") == []
        assert GAMBLE_NARRATION not in game.state.journal[0].lines
    assert queue.calls == (2 if site == "narrate" else 1)


def test_the_queue_timeout_refusal_is_a_sentence_of_its_own_next_to_the_duplicate_ones():
    """排太久的那句話跟三句重複的拒絕放在一起、同樣標「待 joy 潤」；不是「上一件還在……」（排太久不是因為你自己有上一件）。"""
    source = (server.ROOT / "server.py").read_text(encoding="utf-8")
    for name in ("BUSY_QUEUE_TIMEOUT", "BUSY_DIALOGUE"):  # BUSY_DIALOGUE 是 FB-077 加的第四句重複的拒絕
        line = next(row for row in source.splitlines() if row.startswith(f"{name} = "))
        assert "待 joy 潤" in line and getattr(server, name) in line, name
    sentences = [server.BUSY_FREE_TEXT, server.BUSY_FORGE, server.BUSY_FIGHT, server.BUSY_DIALOGUE, server.BUSY_QUEUE_TIMEOUT]
    assert len(set(sentences)) == 5
    assert all(word not in server.BUSY_QUEUE_TIMEOUT for word in ("上一", "還在"))


def test_a_request_held_in_a_real_queue_past_its_timeout_is_refused_and_changes_nothing(game, at_a_gamble, monkeypatch):
    """真的佇列（不假的）：一個位子被別人佔著，隨口應對排超過 llm_queue_wait_seconds——丟拒絕、不叫模型評分、不擲骰、不扣體力、
    不寫任何一行江湖紀錄，眼前的事還在原地；位子與票都讓出來，放掉佔位之後同一個人再送一次照常過。"""
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    monkeypatch.setattr(server.CONTENT.config, "llm_queue_wait_seconds", 0.05)
    started, release = threading.Event(), threading.Event()

    def hold():
        started.set()
        release.wait(5)

    holder = threading.Thread(target=lambda: queue.run("別人", hold, fallback=None))
    holder.start()
    assert started.wait(2)
    scored, rolled = [], []
    real = Game.answer_event
    monkeypatch.setattr(
        server.event_llm, "judge_event_gamble", lambda client, event, text, **_: scored.append(text) or server.event_llm.EventVerdict(85),
    )
    monkeypatch.setattr(Game, "answer_event", lambda self, request, llm_rate=None, moral=None: rolled.append(llm_rate) or real(self, request, llm_rate, moral))
    before = open_characters().load("測試")
    rng_before = game.rng.getstate()
    with pytest.raises(server.GameError, match=server.BUSY_QUEUE_TIMEOUT):
        server.answer_event(game, "大喊官兵來了")
    assert scored == [] and rolled == [] and game.rng.getstate() == rng_before  # 沒評分、沒擲骰
    after = open_characters().load("測試")
    assert after.pending_event == before.pending_event == at_a_gamble.id  # 事件還在原地
    assert (after.player.stamina, after.player.stats, after.battles) == (before.player.stamina, before.player.stats, before.battles)
    assert [(e.title, e.lines) for e in after.journal] == [(e.title, e.lines) for e in before.journal]  # 沒有任何一行紀錄
    assert queue.position("測試") is None and queue.snapshot() == {"running": 1, "waiting": 0}  # 票讓出來了，只剩佔位的人
    release.set()
    holder.join(2)
    monkeypatch.setattr(server.CONTENT.config, "llm_queue_wait_seconds", 20)
    server.answer_event(game, "大喊官兵來了")  # 再試一次：位子空了，照常評分、擲骰
    assert scored == ["大喊官兵來了"] and rolled == [85]
    assert queue.snapshot() == {"running": 0, "waiting": 0}


@pytest.mark.parametrize("failure", [TimeoutError("模型叫了一半逾時"), ConnectionError("連不上"), ValueError("答得不成樣")])
def test_a_model_failure_after_getting_a_slot_still_falls_back_to_forty(game, at_a_gamble, monkeypatch, failure):
    """不能把「模型壞了」當成「排太久」一起擋掉：輪到了、叫了模型、模型自己失敗（答得不成樣、叫到一半逾時、連不上），評分照舊
    退到保底的 40 再擲骰（隨口應對評分的設計，企劃者 2026-10-05 起每次都先看有沒有保底警告）。只有「根本沒輪到」才是拒絕。"""
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    asked, rates = [], []

    def chat(self, messages, response_model, **kwargs):
        asked.append(queue.snapshot())  # 叫模型的時候，這一件正在佇列裡跑
        raise failure

    monkeypatch.setattr(OllamaClient, "chat_structured", chat)
    real = Game.answer_event
    monkeypatch.setattr(Game, "answer_event", lambda self, request, llm_rate=None, moral=None: rates.append(llm_rate) or real(self, request, llm_rate, moral))
    server.answer_event(game, "大喊官兵來了")
    assert asked == [{"running": 1, "waiting": 0}]
    assert rates == [server.event_llm.DEFAULT_FREE_TEXT_SUCCESS_RATE] == [40]
    assert any(e.title.endswith("隨口應對") for e in open_characters().load("測試").journal)  # 擲了骰、寫了紀錄
    assert queue.snapshot() == {"running": 0, "waiting": 0}


def test_only_a_timeout_changes_the_other_ways_a_queue_hands_back_the_fallback(game, monkeypatch):
    """沒給 busy 句子的呼叫點（對話、潤色）排太久照舊拿 fallback；假人滿了（LlmQueue 直接給 fallback）給了 busy 句子也照舊拿
    fallback；給了 busy 句子的呼叫點排太久才丟拒絕。三種都只在 model_call 這一個地方分。"""
    monkeypatch.setattr(server, "QUEUE", _ScriptedQueue("timeout", "timeout"))
    assert server.model_call(game, lambda: pytest.fail("不該叫"), fallback="退路") == "退路"
    with pytest.raises(server.GameError, match=server.BUSY_QUEUE_TIMEOUT):
        server.model_call(game, lambda: pytest.fail("不該叫"), fallback="退路", busy="上一件還在掂量。")
    monkeypatch.setattr(server, "QUEUE", llm_queue.LlmQueue(slots=1, bot_cap=0))
    game.state.player.bot = BotProfile(personality="積極", seed=1)  # 假人的存檔：bot_cap 是 0，一件都排不進去
    assert server.model_call(game, lambda: pytest.fail("不該叫"), fallback="退路", busy="上一件還在掂量。") == "退路"


def test_a_refused_dialogue_reaches_the_page_as_a_short_message(client, monkeypatch):
    """FB-077：重複的那一次對話被擋下來，回 400 與那一句話（前端的 api() 會跳成提示），眼前的選項還在、什麼都沒動。"""
    monkeypatch.setattr(server, "QUEUE", _ScriptedQueue("busy"))
    _player(client)
    game = server.game_for("沈青衫")
    server.act(game, lambda g: _stand_by_a_figure(g))
    stamina = open_characters().load("沈青衫").player.stamina
    refused = client.post("/api/choose", json={"id": "act:socialize"})
    assert refused.status_code == 400 and refused.json() == {"error": server.BUSY_DIALOGUE}
    stored = open_characters().load("沈青衫")
    assert stored.player.stamina == stamina and stored.player.pending_companion is None
    assert not any("無心多談" in "".join(e.lines) for e in stored.journal)
    assert "act:socialize" in [o["id"] for o in client.get("/api/main").json()["options"]]


class _PassQueue:
    """記下每一件要排多久（wait），然後照常叫 job。"""

    def __init__(self):
        self.waits = []

    def run(self, owner, job, *, fallback, bot=False, wait=30.0):
        self.waits.append(wait)
        return job()


def test_model_call_caps_the_queue_wait_by_what_is_left_of_the_budget(game, monkeypatch):
    """審查 M1：排隊最久只等 min(llm_queue_wait_seconds, 這一件預算還剩的秒數)，不再固定等 20 秒。"""
    queue = _PassQueue()
    monkeypatch.setattr(server, "QUEUE", queue)
    config = server.CONTENT.config
    for left in (7.5, 100, 0, -3, None):
        server.model_call(game, lambda: "好", fallback="退路", left=left)
    assert queue.waits == [7.5, config.llm_queue_wait_seconds, 0.0, 0.0, config.llm_queue_wait_seconds]


def test_a_request_never_queues_past_its_budget(game, monkeypatch):
    """排隊的位子被佔滿、這一件的預算只剩 0.2 秒：0.2 秒左右就回來（沒給 busy 句子的拿退路、給了的被擋下來），不是等 20 秒
    （真的佇列、真的時間）。"""
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    started, release = threading.Event(), threading.Event()

    def hold():
        started.set()
        release.wait(5)

    holder = threading.Thread(target=lambda: queue.run("佔著的人", hold, fallback=None))
    holder.start()
    assert started.wait(2)
    begun = time.monotonic()
    assert server.model_call(game, lambda: pytest.fail("不該輪到"), fallback="退路", left=0.2) == "退路"
    assert 0.15 < time.monotonic() - begun < 5.0 < server.CONTENT.config.llm_queue_wait_seconds  # 不是等 20 秒；機器忙時留餘裕
    assert queue.position("測試") is None  # 票讓出來了
    begun = time.monotonic()
    with pytest.raises(server.GameError, match=server.BUSY_QUEUE_TIMEOUT):  # 給了 busy 句子的呼叫點：同樣只等 0.2 秒，然後被擋下來
        server.model_call(game, lambda: pytest.fail("不該輪到"), fallback="退路", left=0.2, busy=server.BUSY_FREE_TEXT)
    assert 0.15 < time.monotonic() - begun < 5.0
    assert queue.position("測試") is None
    release.set()
    holder.join(2)


@pytest.mark.parametrize("site", SITES)
def test_each_site_waits_in_the_queue_no_longer_than_its_budget_has_left(site, monkeypatch, breaker_clock):
    """備料那一段（含等行動鎖）花了 50 秒：預算 60 秒只剩 10 秒，這一件排隊最久也只等 10 秒；潤色是同一份預算的第二次排隊，
    評分與擲骰進鎖之後又過了 50 秒，它一秒都不等（0）。其他四個呼叫點只排一次。"""
    real_sync = Game.sync

    def slow_sync(self, now):
        breaker_clock[0] += 50
        return real_sync(self, now)

    monkeypatch.setattr(Game, "sync", slow_sync)
    queue = _PassQueue()
    monkeypatch.setattr(server, "QUEUE", queue)
    game, run, seen = _ready(site, monkeypatch)
    run()
    assert queue.waits == ([10.0, 0.0] if site in ("score", "narrate") else [10.0])


def test_model_call_never_runs_while_the_action_lock_is_held(game, monkeypatch):
    """鎖外的模型呼叫才排隊：握著行動鎖等模型佇列，全服玩家與假人都跟著等。model_call 在鎖裡被叫到就直接丟 RuntimeError
    （跟 _model_guard 一樣的做法），開關開著關著都一樣——一個還沒打開的佇列也不該被當成可以在鎖裡叫模型的理由。"""
    real = llm_queue.LlmQueue(slots=1, bot_cap=1)
    for queue in (None, real):
        monkeypatch.setattr(server, "QUEUE", queue)
        with game.world.action_lock():
            with pytest.raises(RuntimeError, match="行動鎖"):
                server.model_call(game, lambda: pytest.fail("不該叫"), fallback="退路")
        assert server.model_call(game, lambda: "放掉鎖之後就行", fallback="退路") == "放掉鎖之後就行"
    assert real.snapshot() == {"running": 0, "waiting": 0}


def test_only_the_out_of_lock_steps_enter_the_model_queue():
    """靜態檢查：server.py 裡只有鎖外的四個函式（對話備料、大場面備料、開爐備料、隨口應對）呼叫 model_call；請求的鎖內段落（act、look、
    _locked）與排程（world_step）都不碰它。tianxia/（引擎，鎖內的 _quick_client 在那裡）沒有人 import llm_queue
    （Config 的三個開關欄位 llm_queue_* 是設定，不算）。"""
    assert _users_in_server("model_call") == {
        "prepare_dialogue", "prepare_fight", "prepare_forge", "answer_event", "sense_draw", "battle_text", "duel_text",
        "prepare_peer",  # 論武答應時的首創取名（玩家卡上的互動，social.CardAction.request）
        "zhuan_job",  # 季末寫傳（玩家傳第二批）：server.write_zhuan 開的背景執行緒，A、C 段各拿一次鎖，模型在兩段之間
        "seal_text",  # 奪璽單挑的放手一搏（玉璽碎片設計 5.7）：三段同 duel_text
        "screen_text",  # 挑釁附的一句、名帖自題一句：鎖外請模型審（speech.judge），結果交給 C 段
        "tavern_ask",  # 酒肆問酒家：三段同 duel_text，模型只寫酒家那一句
        "feast_text",  # 宴客自己寫的那一句敬酒（大勢人物擴充第三批）：三段同 answer_event
        "create_intent",  # 自創武學的形意那一句（武學重構）：鎖外請模型評分（create.score），結果交給 C 段
        "create_reread",  # 重悟帖重讀這句意：三段同 create_intent
        "outing_tale",  # 走一趟的遊記：三段同 tavern_ask，模型只寫那三四句
        "ascend_line",  # 破境卡那一句（招式與絕學稿案第三節）：三段同 create_intent
        "persuade_text",  # 託付的勸降（減法季批 6）：三段同 feast_text，模型只評那一句
        "epiphany_think",  # 特殊頓悟的靜心思名：三段同 prepare_forge，模型一次取三個名字
        "guard_say",  # 親衛隊長自己寫的那一句（features/guard）：三段同 feast_text
        "_draft",  # 一句話自創的導演稿（功能包 looks 的 routes）：A 鎖內驗那一句 → B 鎖外請模型填表 → C 鎖內組稿／扣元寶
    }
    # 宣告、model_call 讀、main() 建佇列；另外兩個只看不排：/api/queue 問位置、管理者那份資料抄總數（admin_choices 在 look 的鎖裡，
    # 但 snapshot 只碰佇列自己的短鎖、不等任何一件，不算在行動鎖裡排隊）
    # narrate_once：決戰放手一搏的劇情（Joy 2026-10-13），回合結算後在背景一整批寫，排在真人後面、名號不是任何一個角色，所以不走 model_call
    # crowd_once：擂台場邊那一句（Joy 2026-10-17），A、C 段各拿一次鎖，模型在兩段之間、當假人排在真人後面
    # letter_once：人物書信重寫那一封（大勢人物擴充第二批），同 crowd_once
    # yuedan_once：月旦評的評語（大勢人物擴充第三批），同 letter_once
    # xingshi_once：〈天下形勢〉的文章（領地爭奪第三批 A），同 yuedan_once，名號是 XINGSHI_OWNER（不是任何一個角色）
    assert _users_in_server("QUEUE") == {None, "model_call", "main", "api_queue", "admin_choices", "narrate_once", "crowd_once",
                                         "letter_once", "yuedan_once", "chatter_once",  # chatter_once：酒肆鄰桌閒談，同 crowd_once 當假人排
                                         "xingshi_once",
                                         "flavor_once",  # 江湖大事的潤色（S-09）：觸發那一下寫固定的原文，放鎖之後背景請模型，當假人排，名號 FLAVOR_OWNER
                                         "narration_round",  # 事件旁白每週改寫（減法季批 10）：背景一則一則，當假人排，名號 NARRATION_KEY
                                         "verdict_text",  # 人物評曰（減法季批 7b-2）：zhuan_job 寫完正文後在鎖外逐條叫，當假人排在真人後面
                                         "event_once",  # 親衛隊長的背景生事件（features/guard），同 chatter_once 當假人排
                                         "tale_round"}  # 戰記（Joy 2026-10-29）：決戰收場後在背景寫一篇，當假人排，名號 TALE_OWNER_KEY
    importers = [  # 核心本體 tianxia/core/ 也掃（事件檢定搬進 core/event_check.py，dev/core-events-1 審查）
        p.name for p in [*(server.ROOT / "tianxia").glob("*.py"), *(server.ROOT / "tianxia" / "core").glob("*.py")]
        if re.search(r"^\s*(import|from)\s+llm_queue\b", p.read_text(encoding="utf-8"), re.M)
    ]
    assert importers == []


def _fire_an_event(g):
    """觸發一件不收季、不開戰的江湖大事（huangjin_50），跟引擎各處一樣把潤色單子交給 _flavor_sink。"""
    from tianxia import world as world_rules
    return world_rules.fire_by_id(g.state, g.content, "huangjin_50", g.world, g._flavor_sink(), now=g.now)


def test_a_world_event_is_written_plain_in_the_lock_and_polished_after(game, monkeypatch):
    """S-09：觸發江湖大事的那一下鎖內不叫模型，先寫固定的原文；放鎖之後才請模型潤色（背景執行緒，這裡直接叫 flavor_once），
    寫回時存進全服快取、把這個人江湖紀錄裡的那一則換掉。"""
    from tianxia import flavor
    game.client = OllamaClient.from_config(server.CONTENT.config)
    calls = []

    def polish(client, text):
        calls.append(open_world().db.writing())
        return "城頭的旗幟在風裡獵獵作響。"

    monkeypatch.setattr(flavor, "polish_world_event", polish)
    queued = []
    monkeypatch.setattr(server, "TALE_THREADS", True)
    monkeypatch.setattr(server, "write_flavor", lambda g, jobs: queued.extend(jobs))
    text = server.CONTENT.scenario.thresholds[[t.id for t in server.CONTENT.scenario.thresholds].index("huangjin_50")].text

    def action(g):
        msgs = g._log(_fire_an_event(g) or [])
        g.state.journal.insert(0, journal.news_entry(g.state.world.time, msgs))
        return msgs

    msgs = server.act(game, action)
    assert msgs[0] == f"【江湖大事】{text}"  # 鎖內只寫原文
    assert calls == [] and [job[:2] for job in queued] == [("huangjin_50", text)]
    line = "城頭的旗幟在風裡獵獵作響。"

    def told():  # 天下大事裡那一句潤色出現幾次（Joy 2026-10-31「也進天下大事」）
        return sum(r.text == line for r in open_world().get_season().rumors)

    assert told() == 0  # 潤色回來之前天下大事只有原文
    assert server.flavor_once(game, queued[0])
    assert calls == [False]  # 模型在鎖外
    assert game.world.get_event_flavor("huangjin_50") == line
    assert told() == 1
    saved = open_characters().load(game.state.player.name)
    assert f"{text}\n\n城頭的旗幟在風裡獵獵作響。" in [saved.journal[0].tag, *saved.journal[0].lines]
    assert text not in [saved.journal[0].tag, *saved.journal[0].lines]  # 固定的原文換掉了
    assert f"【江湖大事】{text}\n\n城頭的旗幟在風裡獵獵作響。" in saved.log
    assert server.flavor_once(game, queued[0]) and calls == [False]  # 快取裡有了：不再叫模型
    assert told() == 1  # 天下大事只記存進快取的那一下


def test_a_world_event_without_a_client_queues_nothing(game, monkeypatch):
    """沒有 client（伺服器假人的 Game）：一張潤色單子都不記、一個模型都不叫，原文照寫。"""
    game.client = None
    monkeypatch.setattr(server, "TALE_THREADS", True)
    queued = []
    monkeypatch.setattr(server, "write_flavor", lambda g, jobs: queued.extend(jobs))
    msgs = server.act(game, _fire_an_event)
    assert msgs and msgs[0].startswith("【江湖大事】") and queued == []


def test_in_lock_model_calls_and_the_scheduler_never_wait_in_the_queue(game, monkeypatch):
    """鎖內的小呼叫（Game._quick_client）與排程（world_step）照現在的 15 秒上限與斷路器，不進佇列：佇列開著也一樣。"""
    queue = _FullQueue()
    monkeypatch.setattr(server, "QUEUE", queue)
    sent = []
    monkeypatch.setattr(OllamaClient, "chat_text", lambda self, messages, **kwargs: sent.append(self.timeout) or "好")
    server.act(game, _ask_the_model_in_the_lock)
    assert sent == [server.CONTENT.config.in_lock_model_timeout]  # 鎖內真的叫了模型（短逾時的複本）
    server.world_step()
    assert queue.calls == []


def test_make_queue_and_the_startup_line_follow_the_switch(monkeypatch):
    config = server.CONTENT.config
    assert server.make_queue(config) is None and "模型佇列：關" in server.queue_line(config)
    monkeypatch.setattr(config, "llm_queue_slots", 2)
    monkeypatch.setattr(config, "llm_queue_bot_cap", 1)
    monkeypatch.setattr(config, "llm_queue_wait_seconds", 20)
    queue = server.make_queue(config)
    assert (queue.slots, queue.bot_cap) == (2, 1)
    assert server.queue_line(config) == "模型佇列：同時 2 件，假人最多 1 件，排超過 20 秒就擋下來（請玩家再試一次）"


def test_main_builds_the_queue_only_when_switched_on(capsys, monkeypatch):
    """啟動時在設定那一行後面印佇列開了沒有；關著（預設）不建佇列，開著就建一個（Config 三個欄位）。"""
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    server.main([])
    assert "模型佇列：關（鎖外的模型呼叫照舊直接叫）" in capsys.readouterr().out
    assert server.QUEUE is None
    monkeypatch.setattr(server.CONTENT.config, "llm_queue_slots", 2)
    server.main([])
    assert "模型佇列：同時 2 件" in capsys.readouterr().out
    assert isinstance(server.QUEUE, llm_queue.LlmQueue) and server.QUEUE.slots == 2


# ── 看得到前面還有幾件（/api/queue、管理者的總數、網頁的「前面還有 N 件」）──────────────────────


def test_queue_endpoint_reports_how_many_are_ahead(client, monkeypatch):
    _player(client)
    assert client.get("/api/queue").json() == {"ahead": None}  # 開關關著（Review Focus 5）
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    monkeypatch.setattr(queue, "position", lambda owner: 2)
    assert client.get("/api/queue").json() == {"ahead": 2}


def test_queue_endpoint_needs_a_logged_in_character(client):
    assert client.get("/api/queue").status_code == 401  # 沒登入
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    assert client.get("/api/queue").status_code == 409  # 登入了但還沒有角色


def test_a_waiting_player_counts_the_runners_and_humans_ahead_but_not_the_bots_behind(client, monkeypatch):
    """真人排在假人前面：先排進去的假人不算在「前面」，正在跑的算一件；輪到之前問是 1，做完就沒有在排（null）。
    也看得出來假人只是排序：回傳的只有一個數字，沒有名號。"""
    _player(client)
    queue = llm_queue.LlmQueue(slots=1, bot_cap=2)
    monkeypatch.setattr(server, "QUEUE", queue)
    started, release = threading.Event(), threading.Event()

    def hold():
        started.set()
        release.wait(5)

    threads = [threading.Thread(target=lambda: queue.run("佔著的人", hold, fallback=None))]
    threads[0].start()
    assert started.wait(2)
    threads.append(threading.Thread(target=lambda: queue.run("某假人", lambda: None, fallback=None, bot=True)))
    threads[1].start()
    assert _wait_for(lambda: queue.snapshot()["waiting"] == 1)
    me = server.game_for("沈青衫")
    threads.append(threading.Thread(target=lambda: server.model_call(me, lambda: None, fallback=None)))
    threads[2].start()
    assert _wait_for(lambda: queue.snapshot()["waiting"] == 2)  # 假人與我
    assert client.get("/api/queue").json() == {"ahead": 1}  # 只有正在跑的那一件；先排的假人在後面
    release.set()
    for thread in threads:
        thread.join(2)
    assert client.get("/api/queue").json() == {"ahead": None}


def test_the_queue_endpoint_finds_a_mixed_case_name_under_the_key_the_queue_uses(client, monkeypatch):
    """審查 M-4：佇列的鍵是名號的 casefold（model_call），/api/queue 也要用同一個鍵問。中文名號 casefold 什麼都沒變，
    所以要用有大小寫的名號：「ShenQing」排進去之後，問的人是「ShenQing」、鍵是「shenqing」。問錯鍵就永遠是 null。
    （管理者的名號「Rayal」是保留的、玩家取不到，所以用別的名號；管理者角色走的是同一條路。）"""
    assert _player(client, login="shen_01", name="ShenQing", prologue=True)["stage"] == "game"
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    started, release = threading.Event(), threading.Event()

    def hold():
        started.set()
        release.wait(5)

    me = server.game_for("ShenQing")
    thread = threading.Thread(target=lambda: server.model_call(me, hold, fallback=None))
    thread.start()
    assert started.wait(2)
    assert queue.position("shenqing") == 0  # 佇列裡的鍵是小寫的
    assert client.get("/api/queue").json() == {"ahead": 0}  # 這一件正在跑；問成 position("ShenQing") 會是 None
    release.set()
    thread.join(2)
    assert client.get("/api/queue").json() == {"ahead": None}


def _wait_for(predicate, seconds=2.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_admin_sees_queue_totals_only(client, monkeypatch):
    """管理者看的是總數，不列名號（假人不能被看出來）。"""
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    _admin(client, monkeypatch)
    data = client.get("/api/admin").json()
    assert data["llm_queue"] == {"running": 0, "waiting": 0}


def _keys(value, found=None):
    """一份 JSON 裡所有（任何一層的）鍵。"""
    found = set() if found is None else found
    if isinstance(value, dict):
        for key, inner in value.items():
            found.add(key)
            _keys(inner, found)
    elif isinstance(value, list):
        for inner in value:
            _keys(inner, found)
    return found


def test_admin_totals_mix_bots_and_humans_and_show_no_names_or_bot_keys(client, monkeypatch):
    """審查 M4：管理者的畫面也不能透露假人。在排的有一個假人、一個真人：管理者只看到「兩件在排」，不分開數；
    /api/admin 與 /api/queue 的 JSON 裡沒有任何帶 bot 的鍵，文字裡沒有名號。"""
    queue = llm_queue.LlmQueue(slots=1, bot_cap=2)
    monkeypatch.setattr(server, "QUEUE", queue)
    _admin(client, monkeypatch)
    started, release = threading.Event(), threading.Event()

    def hold():
        started.set()
        release.wait(5)

    threads = [threading.Thread(target=lambda: queue.run("佔著的人", hold, fallback=None))]
    threads[0].start()
    assert started.wait(2)
    threads.append(threading.Thread(target=lambda: queue.run("某假人", lambda: None, fallback=None, bot=True)))
    threads.append(threading.Thread(target=lambda: queue.run("路過的真人", lambda: None, fallback=None)))
    for thread in threads[1:]:
        thread.start()
    assert _wait_for(lambda: queue.snapshot()["waiting"] == 2)
    admin, ahead = client.get("/api/admin"), client.get("/api/queue")
    assert admin.json()["llm_queue"] == {"running": 1, "waiting": 2}
    assert not any("bot" in str(key).lower() for key in _keys(admin.json()) | _keys(ahead.json()))
    assert not any(name in admin.text + ahead.text for name in ("佔著的人", "某假人", "路過的真人"))
    release.set()
    for thread in threads:
        thread.join(2)


def test_admin_has_no_queue_numbers_while_the_switch_is_off(client, monkeypatch):
    _admin(client, monkeypatch)
    assert client.get("/api/admin").json()["llm_queue"] is None


def test_the_page_polls_the_queue_only_while_waiting_on_the_model():
    """網頁沒有測試框架：標記擋住「伺服器有 /api/queue、網頁卻沒人問」。等模型的幾個地方（對話、大場面、對話「自己說」、隨口應對、開爐、有所感）各開一個
    watchQueue、在 finally 裡收掉；管理者區只在伺服器給了數字時多一行。"""
    js = webharness.app_source()
    assert js.count("function watchQueue(") == 1 and '"/api/queue"' in _js_function(js, "function watchQueue(")
    choose = _js_function(js, "async function choose(")
    assert "watchQueue(" in choose and "talking || (opt && opt.wait)" in choose and "finally { stop(); }" in choose
    answer = _js_function(js, "async function answer(")
    assert 'watchQueue(submitBtn, "思量中……")' in answer and "stop();" in answer.split("finally")[1]
    forge = _js_function(js, "async function forge(")
    assert 'watchQueue(lab, "爐火正旺…")' in forge and "finally { stop(); }" in forge
    assert 'watchQueue(send, "心念漸凝……")' in _js_function(js, "async function senseSend(")
    say = _js_function(js, "async function sayLine(")
    assert 'watchQueue(submitBtn, "對方沉吟中…")' in say and "stop();" in say.split("finally")[1]
    persuade = _js_function(js, "async function persuadeSay(")  # 託付的勸降（減法季批 6，FB-829）
    assert "watchQueue(submitBtn, PERSUADE_WAIT)" in persuade and "stop();" in persuade.split("finally")[1]
    assert js.count("watchQueue(") == 8  # 定義一個、使用七個（對話與大場面是同一個選項流程；有所感畫完送出、對話「自己說」、找素材「自己說」、勸降各另一個）
    now = _js_function(js, "function adTilesHtml(")  # 管理頁頂上四格（admin.js；介面重整之前是「現在」那張卡）
    assert "q = a.llm_queue" in now and "處理中／在排" in now


def test_watch_queue_shows_the_count_ahead_only_while_someone_is_ahead():
    """在 node 裡真的跑 watchQueue（假的 fetch 與計時器）：問不到、佇列關著（null）、正在跑（0）都不多寫字；前面有人才寫
    「（前面還有 N 件）」，而且接在原本的字後面、不會一層一層疊上去。寫過之後前面沒人了（輪到自己了：0，或評分與潤色之間：null）
    要還原成原本的字（審查 I-1），不然舊的「前面還有 N 件」會一路留在按鈕上，直到自己那一件做完；問不到（斷線）不動。
    收掉之後不再問，收掉那一刻才回來的回應也不寫（審查 M-4：已經在路上的那一趟 fetch 不能把字寫到還原好的按鈕上）。"""
    import json

    if webharness.NODE is None:
        pytest.skip("沒有裝 node")
    js = webharness.app_source()
    watch = _js_function(js, "function watchQueue(") + "\n  }"
    script = f"""
    {watch}
    const el = {{ textContent: "思量中……" }};
    const answers = [
      {{ ahead: null }}, "boom", {{ ahead: 0 }}, {{ ahead: 3 }}, {{ ahead: 1 }}, {{ ahead: 0 }}, {{ ahead: 2 }}, {{ ahead: null }},
      {{ ahead: 2 }},  // 最後這一趟：收掉的那一刻才回來，不能寫
    ];
    const seen = [];
    const urls = [];
    let stop = null;
    globalThis.setTimeout = (f) => {{ queueMicrotask(f); }};
    globalThis.fetch = async (url, opts) => {{
      seen.push(el.textContent);
      urls.push([url, opts && opts.credentials]);
      const next = answers[seen.length - 1];
      if (seen.length === answers.length) stop();
      if (next === "boom") throw new Error("斷線");
      return {{ json: async () => next }};
    }};
    stop = watchQueue(el, "思量中……");
    (async () => {{
      for (let i = 0; i < 200; i++) await new Promise((r) => setImmediate(r));
      const calls = seen.length;
      for (let i = 0; i < 50; i++) await new Promise((r) => setImmediate(r));
      console.log(JSON.stringify({{ seen, final: el.textContent, urls: urls[0], more: seen.length - calls }}));
    }})();
    """
    done = webharness.node(script)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert out["urls"] == ["/api/queue", "same-origin"]
    base = "思量中……"
    assert out["seen"] == [
        base, base, base, base,  # 每一趟問之前的字：null、斷線、0 都不多寫
        f"{base}（前面還有 3 件）", f"{base}（前面還有 1 件）",  # 3、1：每次都從原本的字接，不疊
        base,  # 3、1 之後問到 0：還原
        f"{base}（前面還有 2 件）",
        base,  # 2 之後問到 null：還原
    ]
    assert out["final"] == base  # 收掉那一趟回 2，也沒寫
    assert out["more"] == 0  # 收掉之後沒有再問


def test_app_js_parses():
    """node --check 網頁的三個檔（main.js、map.js、app.js；沒裝 node 就略過）。"""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("沒有裝 node")
    for name in webharness.APP_FILES:
        done = subprocess.run([node, "--check", str(server.WEB / name)], capture_output=True, timeout=60)
        assert done.returncode == 0, (name, done.stderr.decode("utf-8", "replace"))


def test_the_page_loads_the_three_scripts_in_order_and_app_js_last():
    """網頁切成三個檔（減法季批 0）：index.html 照 main.js、map.js、app.js 的順序載入（app.js 最後一行才啟動）。
    三個檔都是一般的 script、頂層的名字同在一個全域裡，所以不能重名，也不能再包 IIFE。"""
    import re as _re

    html = server.PAGE  # 第 64 批起 script 標籤由伺服器生成（features_core.with_scripts），web/index.html 裡只有一行標記
    assert _re.findall(r'<script src="/static/([^"?]+)\?v=[0-9a-f]{10}"></script>', html) == list(webharness.APP_FILES)
    names: dict[str, str] = {}
    for name in webharness.APP_FILES:
        js = (server.WEB / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        assert '"use strict";' in js.split("\n", 3)[1] + js[:4000], name
        assert "\n(() => {" not in js and not js.rstrip().endswith("})();"), name
        for top in _re.findall(r"^  (?:async function|function|const|let|var|class) ([A-Za-z_$][\w$]*)", js, _re.M):
            assert top not in names, (top, names.get(top), name)
            names[top] = name
    assert webharness.app_source().rstrip().endswith('api("/api/me").then(enter).catch(() => { S.stage = "gate"; render(); });\n})();')


def test_the_page_versions_follow_a_pull_without_a_restart(tmp_path, monkeypatch):
    """2026-11-07 對話告辭急修：主機只 pull、沒重開，頁面上的 ?v= 還是啟動時那一份，手機一直拿舊檔。web/ 的檔換了，頁面就重算。"""
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text('<link rel="stylesheet" href="/static/a.css">', encoding="utf-8")
    (web / "a.css").write_text("a{}", encoding="utf-8")
    monkeypatch.setattr(server, "WEB", web)
    monkeypatch.setattr(server.features_core, "with_scripts", lambda html: html)
    monkeypatch.setattr(server, "PAGE", server.PAGE)  # 測完換回正式那一份
    monkeypatch.setattr(server, "_PAGE_STAMP", ())
    first = server.current_page()
    assert server.current_page() is first  # 沒換檔不重算
    (web / "a.css").write_text("a{color:red}", encoding="utf-8")
    os.utime(web / "a.css", ns=(1, 1))
    second = server.current_page()
    assert second != first and f"?v={server.content_version(b'a{color:red}')}" in second


class _OneShot(server_push.PushHub):
    """一訂閱就送一則再收尾，TestClient 才拿得到整份回應（不會結束的串流 TestClient 等不完）。"""

    def subscribe(self, name, loop, queue):
        super().subscribe(name, loop, queue)
        self.notify(name)
        self.close()


def _get_events(client):
    """GET /api/events；回應不會結束（串流）就讓測試失敗而不是卡住整個測試：TestClient 要等整份回應收完才回來。"""
    got: list = []
    thread = threading.Thread(target=lambda: got.append(client.get("/api/events")), daemon=True)
    thread.start()
    thread.join(5.0)
    assert got, "/api/events 沒有結束：不該開串流的時候（開關關著、沒登入、還沒有角色）開了串流，或是沒有用 server.HUB"
    return got[0]


def test_events_off_by_default(client):
    """開關關著：沒有 /api/events，main 也說沒有推送（Review Focus 5）。"""
    main = _player(client)["main"]
    assert main["push"] is False
    assert _get_events(client).status_code == 404
    assert _get_events(TestClient(server.app)).status_code == 404  # 沒登入也是 404：關著就是沒有這個東西


def test_events_stream_for_the_logged_in_character(client, monkeypatch):
    monkeypatch.setattr(server, "HUB", _OneShot())
    seen = []
    real = server_push.sse_stream
    monkeypatch.setattr(
        server_push, "sse_stream",
        lambda hub, name, heartbeat=15.0: (seen.append((name, heartbeat)), real(hub, name, heartbeat))[1],
    )
    main = _player(client)["main"]
    assert main["push"] is True
    r = _get_events(client)
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"  # 代理不能把串流攢著
    assert "event: self" in r.text
    assert seen == [(ME, server.HEARTBEAT_SECONDS)]
    assert 0 < server.HEARTBEAT_SECONDS < 60  # Cloudflare 閒置約 100 秒就切線：心跳要比它勤


def test_events_need_a_login(monkeypatch):
    """真的 PushHub：萬一帳號檢查被挪到串流開始之後，回應就永遠不結束，所以走 _get_events（5 秒沒結束就判失敗，不是卡住整個測試）。"""
    monkeypatch.setattr(server, "HUB", server_push.PushHub())
    assert _get_events(TestClient(server.app)).status_code == 401


def test_events_need_a_character(client, monkeypatch):
    monkeypatch.setattr(server, "HUB", server_push.PushHub())
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    assert _get_events(client).status_code == 409  # 還沒取名號：跟別的需要角色的端點一樣


def test_the_main_view_says_whether_push_is_on_and_how_long_to_spread_the_refresh(game, monkeypatch):
    """前端照 push 決定開不開 /api/events；push_spread 是世界通知之後各分頁重抓畫面要攤開的秒數（預檢 F3：
    不攤開的話，每次世界變了就是全服同一兩秒各建一次畫面，在同一把行動鎖上排隊）。"""
    view = server.look(game, server.main_view)
    assert view["push"] is False and view["push_spread"] == server.CONTENT.config.push_world_min_seconds == 10
    monkeypatch.setattr(server, "HUB", server_push.PushHub())
    monkeypatch.setattr(server.CONTENT.config, "push_world_min_seconds", 7)
    view = server.look(game, server.main_view)
    assert view["push"] is True and view["push_spread"] == 7


def test_polling_and_entering_never_notify(client, told):
    """預檢 B1：輪詢（/api/main）、開頁（/api/me）、登入、註冊、建角色都會同步並存檔，但都不通知。通知一旦寫在輪詢的路上，
    同一個角色的兩個看得到的分頁就會互相叫醒、永遠停不下來（一個分頁輪詢 → 通知另一個 → 它輪詢 → 通知回來……）。"""
    _player(client, prologue=True)  # 略過序章是一個動作（會通知），這裡只建角色
    assert client.get("/api/main").status_code == 200
    assert client.get("/api/me").json()["stage"] == "game"
    tab_b = TestClient(server.app)
    assert tab_b.post("/api/login", json={"login": "shen_01", "password": "secret-pw"}).json()["stage"] == "game"
    assert tab_b.get("/api/main").status_code == 200
    assert told == []


def test_the_lock_helpers_never_notify(game, told):
    """通知不在 act、look、act_look、poll_main 裡（它們是輪詢與每個動作共用的底層）；只有動作的端點在鎖放掉之後通知。"""
    server.act(game, lambda g: None)
    server.look(game, server.main_view)
    server.act_look(game, lambda g: None, server.main_view)
    server.poll_main(game)
    assert told == []


def test_an_action_notifies_that_characters_other_tabs(client, told):
    _player(client)
    told.clear()  # 建角色走過 _entry，那一段不通知，這裡只看接下來這個動作
    client.post("/api/choose", json={"id": "act:rest"})
    assert told == [(ME, "self")]


class _NamesSeen(_OneShot):
    """記下串流是用什麼名字訂閱的（然後跟 _OneShot 一樣送一則就收尾）。"""

    def __init__(self):
        super().__init__()
        self.names: list[str] = []

    def subscribe(self, name, loop, queue):
        self.names.append(name)
        super().subscribe(name, loop, queue)


def test_a_name_with_capitals_is_subscribed_and_notified_under_the_same_lowercase_key(client, told, monkeypatch):
    """m4：名號不分大小寫（casefold），訂閱（/api/events）與通知（_tell_tabs）兩邊要用同一個鍵。其中一邊少了 casefold，
    名號有大寫英文字母的角色（例如管理者）就收不到自己其他分頁的通知；中文名號不受 casefold 影響，所以要用英文字母混著大小寫的名號測。"""
    _player(client, login="libai_01", name="LiBai")
    told.clear()
    client.post("/api/choose", json={"id": "act:rest"})
    assert told == [("libai", "self")]
    seen = _NamesSeen()
    monkeypatch.setattr(server, "HUB", seen)
    assert _get_events(client).status_code == 200
    assert seen.names == ["libai"]


def test_a_fight_notifies_even_though_it_never_goes_through_act(client, told, monkeypatch):
    """預檢 F1：一般的仗（遊歷、事件選項）在 prepare_fight 的 A 段同一次拿鎖裡就做完、存檔，不經過 act()。
    通知在端點、不在 act，所以天天在按的遊歷與事件選項也會通知；而這一步確實沒走 act。散人的遊歷：出陣關掉。"""
    _player(client)
    game = server.game_for("沈青衫")
    server.act(game, lambda g: setattr(g.state.player, "location", "yingchuan_wilds"))
    assert "act:train" in [o["id"] for o in client.get("/api/main").json()["options"]]
    through_act = []
    real_act = server.act
    monkeypatch.setattr(server, "act", lambda *args: through_act.append(1) or real_act(*args))
    told.clear()
    out = client.post("/api/choose", json={"id": "act:train"}).json()
    assert open_characters().load("沈青衫").battles  # 真的打了一仗
    assert out["main"]["card"] is not None
    assert through_act == [] and told == [(ME, "self")]


def test_choosing_an_event_option_notifies(client, told):
    _player(client)
    game = server.game_for("沈青衫")
    pending = server.CONTENT.events[next(iter(server.CONTENT.events))]
    server.act(game, lambda g: setattr(g.state, "pending_event", pending.id))
    told.clear()
    assert client.post("/api/choose", json={"id": "choice:0"}).status_code == 200
    assert told == [(ME, "self")]


def test_an_action_that_failed_or_only_reads_does_not_notify(client, told):
    """動作丟例外時交易整筆撤回、什麼都沒變：不通知。唯讀的端點更不通知。"""
    _player(client)
    told.clear()
    assert client.post("/api/do/open_season", json={}).status_code == 400  # 不是管理者
    assert client.post("/api/do/nonsense", json={}).status_code == 404
    assert client.post("/api/menxia/join", json={"person": "nobody"}).status_code == 400  # 在鎖裡才丟，整筆撤回
    assert client.post("/api/answer", json={"text": "  "}).status_code == 400
    for path in ("/api/main", "/api/menxia", "/api/map", "/api/reports", "/api/queue", "/api/admin", "/api/me"):
        client.get(path)
    client.post("/api/forge_line", json={})
    assert told == []


def test_a_notice_reaches_a_tab_of_the_same_character_end_to_end(client, monkeypatch):
    """不換掉 notify：真的 PushHub，另一個分頁（另一個事件迴圈）訂閱了，這個分頁做的動作要送到它那裡。"""
    import asyncio

    hub = server_push.PushHub()
    monkeypatch.setattr(server, "HUB", hub)
    _player(client)
    other_tab = asyncio.new_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    hub.subscribe(ME, other_tab, queue)
    try:
        client.get("/api/main")
        client.post("/api/choose", json={"id": "act:rest"})
        assert other_tab.run_until_complete(asyncio.wait_for(queue.get(), 2)) == "self"
        assert queue.empty()  # 輪詢沒有再叫它；只有那一個動作
    finally:
        hub.unsubscribe(ME, other_tab, queue)
        other_tab.close()


def _function_users(attribute: str) -> set[str | None]:
    """server.py 裡呼叫 .attribute(...) 的地方各在哪個函式裡（模組層級是 None）。"""
    found: set[str | None] = set()

    def visit(node: ast.AST, owner: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if isinstance(child, ast.Attribute) and child.attr == attribute:
                found.add(owner)
            visit(child, owner)

    visit(ast.parse((server.ROOT / "server.py").read_text(encoding="utf-8")), None)
    return found


def test_only_the_action_endpoints_tell_other_tabs():
    """預檢 B1 釘在結構上：HUB.notify 只在 _tell_tabs 裡，而 _tell_tabs 只有動作的端點在叫，act／look／act_look／
    poll_main／_entry 都不叫。以後誰把通知挪進共用的底層，輪詢會連帶通知，這個測試先紅。"""
    assert _function_users("notify") == {"_tell_tabs"}
    assert _users_in_server("_tell_tabs") == {
        "api_choose", "api_answer", "api_say", "api_do", "api_menxia_do", "api_travel", "api_sense", "api_peer_act", "api_party_leave",
        "api_mingtie_do",  # 名帖定稿、檢舉（Joy 2026-10-19）
        "api_mail_do",  # 帖友書信：寄出去了，收信的人開著的分頁刷新紅點（2026-11-07）
        "api_mall_buy",  # 商城的購買（2026-10-20）：手上的回體丹變了，其他分頁跟著刷新
        "api_mall_claim", "api_mall_rename",  # 月卡每日領、易名帖（萬寶閣販賣清單定案 2026-10-21）
        "api_looks_order", "api_looks_move", "api_looks_market", "api_looks_withdraw",  # 自建形象、招式動畫下單、市集購買（擂台形象第二～四批）：扣了元寶，其他分頁的錠子鈕跟著刷新
    }


def test_current_fingerprint_follows_the_public_world():
    before = server.current_fingerprint()
    open_world().mutate_season(lambda s: s.chronicle.append(Rumor(time=0.0, text="江湖史一筆")))
    assert server.current_fingerprint() != before


def test_pausing_and_resuming_the_season_clock_change_the_fingerprint():
    """暫停賽季時鐘，全服每個人的選單都變成一顆灰的；繼續又變回來：這是大家都看得到的變化，開著的分頁要被叫醒（不然停機前
    最久要等慢速輪詢 60 秒，繼續之後每個人還對著一顆灰的按鈕等一分鐘）。算的是「有沒有暫停」，不是停了幾分鐘：
    暫停中畫面上的分鐘數每分鐘都在變，不能因此每分鐘叫醒一次全服。"""
    world = open_world()
    world.seed_first_season(server.CONTENT)
    if world.season_phase() == "preparing":
        world.open_season(server.CONTENT, 1000.0)
    before = server.current_fingerprint()
    assert world.pause_clock(1000.0)
    paused = server.current_fingerprint()
    assert paused != before
    world.mutate(lambda st: setattr(st, "paused_at", 99999.0))  # 停了更久：分鐘數變了，畫面上「停著」這件事沒變
    assert server.current_fingerprint() == paused
    assert world.resume_clock(server.CONTENT, 5000.0) is not None
    resumed = server.current_fingerprint()
    assert resumed != paused and resumed == before


def test_the_fingerprint_is_read_once_without_loading_the_rumor_and_chronicle_rows(monkeypatch):
    """m2：每 5 秒讀一次，一季的傳聞與江湖史會長大（五萬列時整份讀回來要 244 毫秒），所以讓資料庫數（MAX 與 COUNT），一個列都不建。"""
    world = open_world()
    world.seed_first_season(server.CONTENT)
    world.mutate_season(lambda s: (
        s.rumors.extend(Rumor(time=float(i), text="天下", layer="world") for i in range(150)),
        s.chronicle.extend(Rumor(time=float(i), text="史") for i in range(40)),
    ))
    built, loads = [], []
    monkeypatch.setattr(sqlite_world, "_rumor", lambda row: built.append(1))
    monkeypatch.setattr(sqlite_world, "_chronicle_entry", lambda row: built.append(1))
    real_load = SqliteWorldStore._load
    monkeypatch.setattr(SqliteWorldStore, "_load", lambda self, conn, logs=False: loads.append(logs) or real_load(self, conn, logs))
    server.current_fingerprint()
    assert built == [] and loads == [False]  # 整份全服狀態讀一次、不帶傳聞與江湖史


def test_the_fingerprint_cannot_be_torn_by_a_write_between_its_reads(monkeypatch):
    """m2：三次各自的快照時，讀的中間有人寫（例如決戰收場、套結果），看守會讀到一半舊一半新、不屬於任何一個時刻的指紋，
    廣播一次、下一輪又廣播一次（每個分頁白白多建一次畫面）。一次快照讀的是同一個時刻：這裡在第一次讀完的那一刻，
    另一個執行緒（另一條連線）寫進一則天下大事、一則江湖史、改了大勢，這一次指紋要還是寫之前的；寫之後再讀才看得到。"""
    world = open_world()
    world.seed_first_season(server.CONTENT)
    key = next(iter(world.get_season().revealed))
    before = server.current_fingerprint()
    reader, armed, reads = threading.current_thread(), [True], []
    real_load = SqliteWorldStore._load

    def write():
        def change(season):
            season.rumors.append(Rumor(time=5.0, text="讀到一半才寫的天下大事", layer="world"))
            season.chronicle.append(Rumor(time=5.0, text="讀到一半才寫的江湖史"))
            season.trends[key] += 1

        open_world().mutate_season(change)

    def hooked(self, conn, logs=False):
        out = real_load(self, conn, logs)
        if threading.current_thread() is reader and armed[0]:
            reads.append(logs)
            armed[0] = False
            writer = threading.Thread(target=write)
            writer.start()
            writer.join(10)
            assert not writer.is_alive()
        return out

    monkeypatch.setattr(SqliteWorldStore, "_load", hooked)
    during = server.current_fingerprint()
    assert reads == [False]  # 寫是在第一次讀完的時候發生的
    assert during == before
    assert server.current_fingerprint() != before  # 寫確實進去了：下一次讀（新的快照）才看得到


def test_the_fingerprint_ignores_the_clock_the_schedule_and_who_acts(client):
    """預檢 F4：世界時間與 season_last_real 每一次同步、每一下排程都在動，不能算進指紋，不然每個分頁每幾秒就被叫醒；
    決戰裡誰加入、這一回合出手了幾個（預檢 F2）畫面上看不到，也不算。"""
    open_world().mutate(lambda st: None)
    before = server.current_fingerprint()
    open_world().mutate(lambda st: (setattr(st, "season_last_real", 9e9), setattr(st.season, "time", st.season.time + 3600)))
    assert server.current_fingerprint() == before
    _a_showdown_fighter(client)
    with_battle = server.current_fingerprint()
    assert with_battle != before  # 決戰開了：大家都看得到
    client.post("/api/choose", json={"id": "battle:join:guan"})  # 又一個人加入：看不到
    open_world().mutate_battle(lambda b: b.round.pending_actions.__setitem__("沈青衫", "safe"))
    assert server.current_fingerprint() == with_battle
    open_world().mutate_battle(lambda b: setattr(b, "trend", b.trend + 1))  # 戰局動了：看得到
    assert server.current_fingerprint() != with_battle


# 推送指紋的欄位分類（最終審查 m5）：全服共用的世界狀態（SharedWorldState、它的賽季 WorldState、進行中的決戰 BattleInstance）
# 每一個欄位，不是「算進指紋」（底下的改法真的讓指紋變，下面的測試會試）、就是「不算」（寫一句為什麼）。以後誰加了新欄位，
# 兩邊都沒有就紅——到時候要決定：它改了，全服每個人的畫面看得出來嗎？看得出來就要算進去（不然開著的分頁最久 60 秒才知道），
# 看不出來（或不能讓人看出來）就寫進「不算」。暫停（paused_at）就是這樣漏過一次。
_SEASON = "season"  # 容器欄位：它自己不算，裡面的欄位各自分類（WorldState 的欄位在 "WorldState" 那一組）
FINGERPRINTED = {
    "SharedWorldState": {
        "season_number": lambda st: setattr(st, "season_number", st.season_number + 1),
        "season_opened": lambda st: setattr(st, "season_opened", False),  # 籌備中：階段變了
        "paused_at": lambda st: setattr(st, "paused_at", 1000.0),
        "season": _SEASON,
        "active_battle": lambda st: setattr(st, "active_battle", None),  # 決戰收掉
        # 奪璽單挑（玉璽碎片設計 5.10、13.3）：全服觀戰，回合推進、出招，開著的分頁要更新
        "seal_duels": lambda st: st.seal_duels.append(_seal_duel()),
        # 攻城戰（領地爭奪第二批）：每一場同決戰，開集結、回合推進、收場，開著的分頁要更新
        "sieges": lambda st: st.sieges.append(battle_instance.BattleInstance(battle_id="changshe_fire")),
    },
    "WorldState": {
        "trends": lambda st: st.season.trends.__setitem__("t", st.season.trends["t"] + 1),  # 浮現的那一條
        "revealed": lambda st: st.season.revealed.add("h"),  # 隱藏的那一條浮現了
        "rumors": lambda st: st.season.rumors.append(Rumor(time=0.0, text="天下大事", layer="world")),
        "chronicle": lambda st: st.season.chronicle.append(Rumor(time=0.0, text="江湖史一筆")),
        "ended": lambda st: setattr(st.season, "ended", True),  # 休季：階段變了
        "ending_title": lambda st: setattr(st.season, "ending_title", "天下大亂"),
        "storyline": lambda st: setattr(st.season, "storyline", "另一條主線"),
        "act": lambda st: setattr(st.season, "act", st.season.act + 1),
        "timeline": lambda st: st.season.timeline.__setitem__("uprising", TimelineResult(key="fixed", time=0.0)),
        "showdowns_opened": lambda st: st.season.showdowns_opened.__setitem__("changshe_fire", "changshe_fire"),
        "figures": lambda st: st.season.figures.__setitem__("lu_zhi", FigureState(prestige=70)),
    },
    "BattleInstance": {
        "battle_id": lambda st: setattr(st.active_battle, "battle_id", "wancheng"),
        "phase": lambda st: setattr(st.active_battle, "phase", "active"),
        "round_number": lambda st: setattr(st.active_battle, "round_number", 1),
        "trend": lambda st: setattr(st.active_battle, "trend", 55),
        # 「已送出 X／在場 Y」（試玩回饋 2026-10-08）：兩軍有人出手，開著的分頁要更新那個數
        "round": lambda st: (
            setattr(st.active_battle, "phase", "active"),
            st.active_battle.participants.__setitem__("甲", battle_instance.BattleParticipant(name="甲", faction="guan", neili=1, neili_cap=1)),
            st.active_battle.round.pending_actions.__setitem__("甲", "guan_hold"),
        ),
        # 放手一搏的劇情回合結算後才補上（Joy 2026-10-13）：補上的那一下場景的字變了
        "tales": lambda st: st.active_battle.tales.append(battle_instance.GambleTale(
            round=1, act_index=0, name="甲", faction="guan", text="火攻", won=True, fixed="x", numbers="y",
        )),
    },
}
NOT_IN_THE_FINGERPRINT = {
    "SharedWorldState": {
        "companion_tag_counts": "跟人物對話才用的記數，不在共用的畫面上",
        "companion_drift_note": "同伴的性情句，只在跟他對話時用",
        "companion_drift_synthesized_at": "性情語意化的記數，不在畫面上",
        "companions": "同伴被招走、升級只影響門下頁與招募鈕，那是各人自己的畫面（自己的動作走 self 通知），別人下次輪詢才補也不礙事",
        "event_flavor": "事件的潤色句，一次寫好之後不變，跟著事件的公告出現",
        "jade_seal_fragments": "玉璽碎片的歸屬，只在持有者的畫面",
        "season_last_real": "賽季時鐘的對時點：每次同步、每一下排程都在動，算進去每幾秒就叫醒全服（推送計畫 F4）",
        "tianji": "換季才加一，同時 season_number 也變了",
        "seal": "碎片的歸屬：現世、易手、隱沒都寫天下大事（傳聞流水號已在指紋裡）；密鹽不能讓人看出來（13.3）",
        "mingtie_reports": "名帖的檢舉：誰檢舉了誰不能讓人看出來；藏起來的那一張別人下次打開才補",
        "mingtie_removed": "管理者撤下的名帖：被撤的人江湖紀錄一句（自己的動作走 self 通知），收過的人下次打開才補",
        "mingtie_cleared": "管理者放回的名帖，同上",
        "divine": "神器輪替的全服登記：開季換季時才挑；原品與仿品數在打造、定名那一下改，傳聞與江湖史已在指紋裡",
        "jieyi": "結義的帳：邀請與答應是雙方自己的動作（被邀的人選單上的那一對下次同步補），名冊只在俠客頁與玩家卡",
        "siege_records": "攻城戰的流水號（存檔時照 sieges 寫）；sieges 本身算進指紋",
        # 3b-2 接線了（main.sortie_card、main.sorties）；搬進指紋要在 server_push.world_fingerprint 加一格、server.current_fingerprint 傳
        # shared.sorties——server_push 是雲端側的檔，交雲端側改（計畫 4.0 之三第 5 條）
        "sect_books": "師門武譜：只在同門自己的畫面，獻式、試練、入譜都寫各人的江湖紀錄（自己的動作走 self 通知），別的同門下次輪詢才補也不礙事",
        "sorties": "出陣約戰（減法季批 3b）：接線了，但推送指紋的那一格在雲端側的 server_push，等他們改；之前開著的分頁照輪詢看到別人貼的約戰",
    },
    "WorldState": {
        "time": "時鐘一直在走，靠慢速輪詢更新（排程每 10 秒推一次，算進去會一直叫醒全服）",
        "flags": "世界旗標只是條件，不直接畫在共用畫面上（推送計畫 F4）",
        "flag_times": "旗標第一次成立的時間，同上",
        "chapter_weights": "章回主線做成的份量：畫面上只有章回卡那一行（各人自己的卡，下次輪詢才補也不礙事），改歷史在大事結算那一刻才看得出來",
        "chapter_done": "章回做成的人數：同上，只寫在各人自己的章回卡上",
        "fired_thresholds": "門檻觸發過的記號；畫面看的是它帶來的傳聞與大勢",
        "sim_accum": "不滿一小時的時間累積器",
        "life_turn": "人物每日行事做到第幾輪的記號；畫面看的是它帶來的傳聞（傳聞流水號已在指紋裡）",
        "whereabouts": "人物走動時一定同時寫一則傳聞（傳聞流水號已在指紋裡），誰在這裡下次輪詢就補",
        "feasts": "開席、散席都寫天下大事（傳聞流水號已在指紋裡）；席上別人敬的那一句只畫在入席的人的場景，下次輪詢才補也不礙事",
        "feast_seq": "宴席的流水號，跟 feasts 一起寫",
        "plans": "盤算公告、結算都寫天下大事（傳聞流水號已在指紋裡）；兩邊各幾人只畫在江湖頁的盤算卡，下次輪詢才補也不礙事",
        "stops_done": "行程每一站做完了沒，做的那一下都寫天下大事",
        "deeds": "世界記事：人物對話與此地舊事才讀，寫的那一下都有天下大事或江湖紀錄",
        "deed_seq": "世界記事的流水號，跟 deeds 一起寫",
        "places": "地點的樣子（地點會變樣）：變樣那一下都有天下大事或世界記事一起寫；照時間轉重建、回太平不寫存檔，畫面下次輪詢自己現算",
        "inscriptions": "走一趟的留言：只在別人下一次走一趟、路上抽到才看得到，不在共用的畫面上",
        "inscription_seq": "留言的流水號，跟 inscriptions 一起寫",
        "yuedan": "月旦評發出去那一刻寫天下大事與江湖史（都在指紋裡）；還沒發的那一批誰都看不到",
        "yuedan_week": "評到第幾週的記號，跟 yuedan 一起寫",
        "rallies": "求援委託只在那一方的人的懸賞卡（各人自己的畫面），掛單時寫一則陣營傳聞",
        "ending_text": "收季那一刻跟 ended、ending_title 一起寫入",
        "ending_id": "同上",
        "final_trends": "同上（結算卡的資料）",
        "final_rankings": "同上（結算卡的資料）",
        "final_tiers": "同上（結局卡的資料：收季那一刻跟 ended 一起寫，減法季批 3c）",
        "act_reached": "隊伍數與統御上限的內部計數，不畫在共用畫面上",
        "marks": "地方痕跡只畫成模糊人數，改了讓每個分頁多刷新一次會洩漏有人做了看不見的事（推送計畫 F4）",
        "marks_fired": "痕跡過門檻那一刻寫一則地方傳聞（傳聞流水號在指紋裡；世界層那一句 2026-10-25 拿掉）；江湖史在季末",
        "mark_helpers": "誰替痕跡出過力只用來記本人的行狀，不畫在共用畫面上（改了讓每個分頁刷新會洩漏有人做了看不見的事，同 marks）",
        "stance_counts": "人物心意的全服計數（減法季批 6）：只畫在跟他談的人自己的人物頁（自己的動作走 self 通知）；算進去會洩漏有人跟他說了話（同 marks）",
        "stance_week": "心意計數是哪一週的記號，玩家看不到",
        "persona": "人物性子此刻的值（功能包 persona）：只畫在點人物那一層的簡介；換段那一刻另寫傳聞（傳聞流水號已在指紋裡）",
        "persona_day": "人物性子結算到第幾天的記號，玩家看不到",
        "persona_push": "人物性子今天的淨推力：玩家看不到；算進去會洩漏有人跟他說了話（同 stance_counts）",
        "persona_tug": "同上（今天的總份數）",
        "persona_torn": "拉鋸只在結算那一刻變（每天一次），畫在簡介上；簡介跟著人物那一層重讀",
        "persona_log": "換段紀錄：換的那一刻另寫傳聞（傳聞流水號已在指紋裡）",
        "god_names": "特殊頓悟全服神品意境的名字（只拿來擋重名），不畫在共用畫面上；首悟上江湖史走傳聞流水號",
        "god_firsts": "特殊頓悟每個模板這一季第一個悟出的人（江湖史那一句走傳聞流水號），不畫在共用畫面上",
        "stance_active": "人物此刻照哪一個心意做事：換的那一刻另寫天下大事（傳聞流水號已在指紋裡）；週初歸零跟著週初的掛鉤",
        "pending_battle": "背景推進記下要開的戰鬥，開成集結之後 active_battle 的指紋就變了",
        "season_one": "開季時蓋的章，開季之後不變",
        "season21": "開季時蓋的章（21 天季），開季之後不變",
        "precise_actions": "開季時蓋的章（一類一顆），開季之後不變",
        "cal_offset": "開季時蓋的章（21 天季季曆的偏移），開季之後不變",
        "cal_offset_history": "21 天季暫停再繼續時才多一筆（FB-332）：繼續那一下季的時間與排定本來就跟著變",
        "length_days": "同上",
        "locks": "伏筆鎖定不能露出來（推送計畫 Review Focus 1）",
        "lock_losers": "同上",
        "event_mods": "一般伏筆的修正，畫面上看不到（推送計畫 F4）",
        "event_bonus": "時刻表結果帶來的修正，同上",
        "schedule": "只畫成『下一件大事』的倒數；時鐘本來就靠慢速輪詢，管理者改排定很少見（推送計畫沒納入）",
        "hooked_week": "週初掛鉤的內部記號",
        "hooked_day": "21 天季每天掛鉤的內部記號",
        "showdowns_waiting": "排隊等著開的決戰記號，開成集結之後 active_battle 的指紋就變了",
        "showdown_opened_at": "開集結那一刻（輿圖歸週用），跟 showdowns_opened 一起寫，那一下指紋已經變了（FB-563）",
        "showdowns_cancelled": "管理者取消的決戰：取消那一下另寫天下大事（傳聞流水號已在指紋裡），輿圖不列它下次輪詢才補（FB-563）",
        "orders": "陣營軍令只有那個陣營看得到（推送計畫 F4）",
        "plots": "集體密謀只有自己陣營的人看得到（發起的軍情是陣營軍情，不進天下大事的流水號）；算進去，別的陣營會從『又被叫醒了』看出對方有動靜（乙二）",
        "promoted_today": "晉升的每日彙整，進陣營軍情，不是共用畫面",
        "trend_accum": "不足一點的推力累積器（推送計畫 F4）",
        "active_pushers": "人數緩衝的記錄，畫面上看不到（推送計畫 F4）",
        "invites": "玩家之間的邀請只有發的人與收的人看得到，伺服器做完動作直接叫醒他們兩個的分頁（Game.touched）；算進去會叫醒全服",
        "spar_tally": "切磋的每日次數，畫面上看不到",
        "gift_tally": "贈物的每日次數（FB-116），只在玩家卡上那一顆鈕灰不灰，打開卡才重問",
        "discuss_tally": "論武的每日次數（FB-116），只在玩家卡上那一顆鈕灰不灰，打開卡才重問",
        "raids": "截殺的冷卻，只在打開玩家卡時看得到（截殺當下 touched 叫醒被截殺的人）",
        "ambushes": "埋伏是看不見的（設伏劫道）：中伏的那一下 touched 叫醒伏兵",
        "figure_guards": "護衛的崗只寫在挑戰鈕的「身邊有 N 人護衛」與自家人的按鈕上；站崗、擋下都是某個人自己的動作，別人下次輪詢才補也不礙事",
        "aid_tally": "犒軍、探望、聲威回復的每日記數，畫面上看不到",
        "guard_credits": "護衛擋下挑戰、等著補給護衛的那幾句，只在護衛自己同步時領",
        "supply": "屯糧練兵的量只在自家人的按鈕上（自己的動作走 self 通知），開集結那一刻寫天下大事",
        "bounties": "懸賞榜只在城裡打開第二層選單時看得到，揭、交差都是自己的動作（通緝當下 touched 叫醒被通緝的人）",
        "bounty_seq": "懸賞的流水號，玩家看不到",
        "armaments": "陣營的軍備存量（素材與經濟）：捐的人自己那一下的畫面就更新；同陣營其他人的存量等下一次輪詢，不必為它叫醒全服的分頁",
        "bounty_week": "懸賞自動掛單掛到第幾週，玩家看不到",
        "bounty_day": "21 天季懸賞每天掛單掛到第幾天，玩家看不到",
        "raided": "被截殺過的冷卻，只在打開玩家卡時看得到",
        "clashes": "混戰寫進截殺冷卻的那幾筆（FB-607：拒絕話照實寫），跟 raids 一起寫、一樣只在打開玩家卡時看得到",
        "clashed": "混戰被撞的護身是混戰寫的（FB-607），跟 raided 一起寫、一樣只在打開玩家卡時看得到",
        "arena": "擂台的分身與名次只在打開擂台、看擂台榜時看得到；稱號在狀態列，守擂的人的戰報與俸在他自己同步時補",
        "arena_pairs": "挑擂的同一對冷卻，只在打開擂台時看得到",
        "arena_seq": "擂台的流水號，玩家看不到",
        "arena_closed": "擂台這一季收了沒（季末排名寫進江湖史與傳聞，那一下指紋就變了）",
        "arena_day": "擂台的俸記到哪一天，玩家看不到（俸在本人同步時補）",
        "tavern_walls": "酒肆的題壁只在坐進那一間酒肆時看得到；坐在裡面的人照輪詢每十秒重抓",
        "tavern_whispers": "酒肆的風聲在被打聽的人自己同步時補（寫風聲的人另外叫醒他的分頁，Game.touched）",
        "tavern_treats": "請全店喝酒只在坐進那一間酒肆時看得到；請的那一下另有地方傳聞",
        "tavern_hits": "雇殺手（第三批）只在本人同步時結算與補",
        "tavern_hit_seq": "雇殺手的流水號，玩家看不到",
        "tavern_chatter": "酒客閒談（第四批）只在坐進那一間酒肆時看得到",
        "echoes": "首創名望回饋的帳，只在首創者自己同步時補一則紀錄；湊滿時那一句傳聞進 rumors，那一下指紋就變了",
        "seat_ledger": "第四階席次的貢獻帳，畫面上看不到；陣營私有，跟 orders、plots 一樣（正式版丁）",
        "seats": "在任名單只改那個陣營的人自己的頭銜，上任的消息是陣營軍情；算進去，別的陣營會從『又被叫醒了』看出對方有人上任（同 orders、plots，正式版丁）",
        "general_gifts": "名將贈禮給了誰，只寫在拿到的人自己的江湖紀錄裡（裝備四欄 6.4）",
        "secret_sets": "「裝滿」秘方這一季誰先暗合；傳聞與江湖史另有自己的欄位，這裡只記先後",
        "signature_arms": "名將本命兵器給了誰，只寫在拿到的人自己的江湖紀錄裡；江湖史與天下大事傳聞進 chronicle、rumors，那一下指紋就變了（兵器設計 4.10）",
        "tianji": "開季時蓋進季裡的天機，開季之後不變（週初掛單的重賞亂數用）",
        "forge_divine_per_kind": "開季時蓋的章（素材與經濟），開季之後不變",
        "forge_split_clues": "開季時蓋的章（素材與經濟），開季之後不變",
        "divine_lineup": "開季時蓋的章（神器輪替），開季之後不變",
        "renown_scale": "開季時蓋的章（名聲的門檻倍數），開季之後不變",
        "mandate": "天命之季的章：蓋章時另寫天下大事（傳聞流水號已在指紋裡）",
        "mandate_result": "天命之爭定下來時跟時間軸、天下大事一起寫入",
        "territory": "地盤的控制方只跟著戰線、割據（trends）與大事（timeline）改；易手的那一下另寫天下大事（傳聞流水號已在指紋裡），第一次算不發也不必叫醒誰",
        "conquest_on": "開季時蓋的章（領地爭奪），開季之後不變",
        "jianfa_on": "開季時蓋的章（減法季），開季之後不變",
        "attrs_v2": "開季時蓋的章（五項屬性），開季之後不變",
        "fight_practice": "開季時蓋的章（武學打了才升），開季之後不變",
        "craft_v2": "開季時蓋的章（意境合成改版），開季之後不變",
        "no_gentry": "開季時蓋的章（拿掉地方豪強），開季之後不變",
        "titles_week": "名號結算到第幾週的記號，跟 titles_holders 一起寫",
        "titles_holders": "名號結算的那一下寫江湖傳聞（傳聞流水號已在指紋裡）；各人戴哪一個是自己存檔的事，下次輪詢才補也不礙事",
        "conquest": "領地爭奪的開季種類、偏移與進度：易手另寫天下大事（傳聞流水號已在指紋裡），偏移跟著 trends 一起改；"
                    "進度不露數字、只回推的人自己那一句話",
        "xingshi": "〈天下形勢〉收下的文章：收下那一刻另寫天下大事與江湖史（都在指紋裡）；見聞「形勢」頁自己去讀，不叫醒全服",
        "xingshi_ticket": "還在等模型寫的那一張單，誰都看不到",
        "xingshi_mark": "上一篇讀到哪裡的記號，玩家看不到",
        "seal_acts": "玉璽碎片的獨門行動（改版第 2 批）：起用那一下另寫天下大事與江湖史（都在指紋裡）；引將期滿回原處改的是 figures（算進指紋）",
    },
    "BattleInstance": {
        "muster_deadline_real": "現實時間的期限，畫面上的倒數靠輪詢（推送計畫 F4）",
        "participants": "誰加入、誰出手了，畫面上看不到；這一回合送出幾個的人數算在 round 那一格（推送計畫 F2）",
        "act_index": "換幕只在 round_number 加一的那一下發生",
        "narrative_log": "戰報的敘事一回合結算才加一行，那一下 round_number 也變了",
        "tactic_kinds": "戰法名 → kind 只在回合結算時跟著 narrative_log 一起加，那一下 round_number 也變了",
        "last_mix": "上一回合兩邊的出招比例，一回合結算才改，那一下 round_number 也變了（每個人的份量與上一回合的結果在 participants 裡，同它）",
        "outcome_title": "收場時跟 phase 一起寫入",
        "outcome_text": "同上",
        "outcome_world_flags": "同上",
        "outcome_trend_delta": "同上",
        "end_time": "同上",
        "unfinished_text": "同上",
        "unfinished": "同上",
        "record_id": "資料庫裡的流水號，不是畫面",
        "rounds": "還沒寫進資料庫的回合緩衝，不是畫面",
        "trend_start": "開打時就定了，跟 phase 一起寫入",
        "swings": "每回合戰局怎麼走，一回合結算才加一筆，那一下 round_number 也變了",
        "mvps": "每回合的 MVP（looks 的 mvp.crown），一回合結算才加一筆，那一下 round_number 也變了",
        "marked": "誰在這一幕顯眼，只在回合結算時改，那一下 round_number 也變了",
        "last_targets": "上一回合誰被點名，只在回合結算時改，那一下 round_number 也變了",
        "outcome_reason": "收場時跟 phase 一起寫入",
        "outcome_side": "收場時跟 phase 一起寫入（軍餉看誰贏）",
        "outcome_margin": "收場時跟 phase 一起寫入",
        "highlight": "最有戲的放手一搏：跟著回合結算變（回合已經算進指紋），收場時寫進傳聞",
        "seal_emerge": "現世擲中了：集結那一刻另寫天下大事（3.4），指紋本來就變了",
        "seal_shard": "璽動牽動哪一片：另寫天下大事（4.3）",
        "seal_holder": "同上",
        "seal_holder_faction": "同上（快照，畫面上看不到）",
        "seal_holder_side": "同上",
        "seal_notes": "收場時跟 phase 一起寫入（戰報那一行）",
        "seal_lean": "天命之爭開集結那一刻快照（集結公告另寫天下大事，指紋本來就變了）",
        "supply_lean": "屯糧練兵開集結那一刻快照（集結公告另寫天下大事，指紋本來就變了）",
        "front_note": "起點照哪一條戰線：開集結那一刻快照（另寫天下大事，指紋本來就變了），之後不再改",
        "commanders": "上陣的大勢人物：開集結那一刻派上來（另寫天下大事），氣血與敗走只在回合結算時改，那一下 round_number 也變了",
        "orders": "主將令：回合結算那一下換，round_number 也變了",
        "siege": "攻城戰打哪一塊、誰攻：開集結那一刻就定了（跟 phase 一起寫入）；收場的易手另寫天下大事（傳聞流水號已在指紋裡）",
    },
}


WORLD_MODELS = {"SharedWorldState": SharedWorldState, "WorldState": WorldState, "BattleInstance": battle_instance.BattleInstance}


def test_every_shared_world_field_is_classified_for_the_push_fingerprint():
    """新欄位兩邊都沒寫就紅：逼加欄位的人當場決定它算不算進推送的指紋。"""
    for name, model in WORLD_MODELS.items():
        counted, ignored = set(FINGERPRINTED[name]), set(NOT_IN_THE_FINGERPRINT[name])
        assert not counted & ignored, f"{name} 同時在兩邊：{sorted(counted & ignored)}"
        assert set(model.model_fields) == counted | ignored, (
            f"{name} 的欄位沒分類或寫錯了：沒分類 {sorted(set(model.model_fields) - counted - ignored)}，"
            f"不存在 {sorted((counted | ignored) - set(model.model_fields))}——見 FINGERPRINTED／NOT_IN_THE_FINGERPRINT 上面的說明"
        )
        assert all(reason.strip() for reason in NOT_IN_THE_FINGERPRINT[name].values()), name


@pytest.mark.parametrize(
    ("name", "field"),
    [(name, field) for name, fields in FINGERPRINTED.items() for field, change in fields.items() if change != _SEASON],
)
def test_every_field_counted_in_the_push_fingerprint_really_changes_it(name, field):
    """上面說「算進指紋」的欄位，真的改了就讓 server.current_fingerprint() 變（不是只寫在清單上）。每個欄位自己一個資料庫。"""
    world = open_world()
    world.seed_first_season(server.CONTENT)
    if world.season_phase() == "preparing":
        world.open_season(server.CONTENT, 1000.0)

    def setup(st):
        st.season.trends, st.season.revealed = {"t": 10, "h": 5}, {"t"}  # 一條浮現的、一條隱藏的
        st.active_battle = battle_instance.BattleInstance(battle_id="changshe_fire")

    world.mutate(setup)
    before = server.current_fingerprint()
    world.mutate(FINGERPRINTED[name][field])
    assert server.current_fingerprint() != before, f"{name}.{field} 改了，指紋沒變"


def _three_read_fingerprint() -> str:
    """推送看守原本的讀法：三次各自的快照，還把這一季每一則傳聞與江湖史讀回來數。新的讀法（一次快照加 MAX／COUNT）要跟它一樣。"""
    world = open_world()
    shared = world.read()
    return server_push.world_fingerprint(
        shared.season_number, shared.season_phase(), world.get_season(), world.get_battle(),
        paused=shared.paused_at is not None,
    )


def test_the_one_snapshot_fingerprint_is_the_old_three_read_one_on_every_state():
    """m2：同樣的東西算進去、同樣的東西不算（F2 的決戰、F4 的排除項），在一連串不同的狀態裡每一步都跟舊的算法一樣，
    該變的變、不該變的不變。"""
    world = open_world()
    content = server.CONTENT
    revealed = []

    def trend_up(season):
        key = revealed[0]
        season.trends[key] += 1

    def nudge_trend():
        world.mutate_season(trend_up)

    def pick_revealed():
        revealed.append(next(iter(world.get_season().revealed)))

    def rumors(*items):
        return lambda: world.mutate_season(lambda s: s.rumors.extend(items))

    steps = [  # (這一步, 指紋會不會變)
        (lambda: world.seed_first_season(content), True),
        (pick_revealed, False),
        (rumors(Rumor(time=1.0, text="天下大事", layer="world")), True),
        (rumors(Rumor(time=1.0, text="軍情", layer="faction", faction="guan"),
                Rumor(time=1.0, text="地方", layer="local", region="yingchuan"),
                Rumor(time=1.0, text="只有你", layer="personal", character="甲")), False),
        (rumors(Rumor(time=3.0, text="又一則天下大事", layer="world")), True),
        (lambda: world.mutate_season(lambda s: s.chronicle.append(Rumor(time=2.0, text="江湖史一筆"))), True),
        (nudge_trend, True),
        (lambda: world.mutate_season(lambda s: s.locks.__setitem__("changshe_fire", Lock(side="guan", name="甲", time=1.0))), False),
        (lambda: world.start_battle(content.battles["huangjin_showdown"], now=0.0), True),
        (lambda: world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=320.0)), False),
        (lambda: world.mutate_battle(lambda b: setattr(b, "trend", b.trend + 3)), True),
        (lambda: world.mutate_season(lambda s: s.timeline.__setitem__("uprising", TimelineResult(key="fixed", time=0.0))), True),
        (lambda: world.mutate_season(lambda s: setattr(s, "ended", True)), True),
        (lambda: world.next_season(content, now=1.0), True),
    ]
    assert server.current_fingerprint() == _three_read_fingerprint()  # 還沒有賽季的空資料庫
    for number, (step, changes) in enumerate(steps):
        before = server.current_fingerprint()
        step()
        now = server.current_fingerprint()
        assert now == _three_read_fingerprint(), number
        assert (now != before) is changes, number


def test_push_line_says_whether_push_is_on():
    config = server.CONTENT.config
    assert server.push_line(config) == "推送：關（分頁每 10 秒輪詢）"
    on = config.model_copy(update={"push_events": True})
    assert server.push_line(on) == "推送：開（SSE；世界每 5 秒看一次，兩次通知至少隔 10 秒）"


def _uvicorn_runs(monkeypatch) -> list[dict]:
    import uvicorn

    runs: list[dict] = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: runs.append(kwargs))
    return runs


def test_main_starts_the_push_watcher_only_when_switched_on(capsys, monkeypatch):
    """啟動時印一行推送開了沒有；關著（預設）不建 HUB、不開執行緒，開著就建 HUB、開一條看守，每隔幾秒看一次世界。"""
    runs = _uvicorn_runs(monkeypatch)
    server.main([])
    assert "推送：關（分頁每 10 秒輪詢）" in capsys.readouterr().out
    assert server.HUB is None and server.PUSH_THREAD is None
    looked = threading.Event()
    monkeypatch.setattr(server.CONTENT.config, "push_events", True)
    monkeypatch.setattr(server.CONTENT.config, "push_watch_seconds", 0.01)
    monkeypatch.setattr(server, "current_fingerprint", lambda: looked.set() or "x")
    server.main([])
    assert "推送：開（SSE；" in capsys.readouterr().out
    assert isinstance(server.HUB, server_push.PushHub) and server.PUSH_THREAD is not None and server.PUSH_THREAD.daemon
    assert looked.wait(2.0)
    assert len(runs) == 2


def test_the_server_gives_open_streams_three_seconds_to_close_on_shutdown(monkeypatch):
    """預檢 F7：uvicorn 關機時會等進行中的回應收完，而 SSE 串流永遠不會自己收完，一個 Ctrl+C 就卡住。
    timeout_graceful_shutdown 到了就取消它們（sse_stream 的 finally 會退訂）。"""
    runs = _uvicorn_runs(monkeypatch)
    server.main([])
    assert runs[0]["timeout_graceful_shutdown"] == 3


def test_only_main_starts_the_push_watcher():
    assert _users_in_server("start_push") == {"main"}


def test_the_push_watcher_logs_only_the_kind_of_error(capsys, monkeypatch):
    """預檢 F5：看守讀不到世界時只寫例外的類別（跟排程同一個規矩：例外的訊息常夾著名號，伺服器視窗不該看得出誰是假人），
    同一個錯一直重複也只印一行。"""
    rounds = []
    secret = KeyError("某某人的名號")  # 在變數裡：呼叫堆疊印的是程式碼那一行，不是例外的訊息，源碼裡不能寫出名號

    def unreadable():
        rounds.append(1)
        _boom(secret)

    monkeypatch.setattr(server.CONTENT.config, "push_events", True)
    monkeypatch.setattr(server.CONTENT.config, "push_watch_seconds", 0.01)
    monkeypatch.setattr(server, "current_fingerprint", unreadable)
    server.start_push(server.CONTENT.config)
    deadline = time.time() + 5
    while len(rounds) < 6 and time.time() < deadline:
        time.sleep(0.01)
    assert len(rounds) >= 6
    shown = capsys.readouterr()
    assert shown.out.splitlines() == ["推送的看守這一下出錯：KeyError"]  # 第六輪了，同一個錯還是只印一行
    assert "某某人的名號" not in shown.out + shown.err


def test_start_push_does_nothing_when_switched_off():
    assert server.start_push(server.CONTENT.config) is None
    assert server.HUB is None and server.PUSH_THREAD is None


# ── 賽季時鐘暫停（賽季計畫 Task 4）────────────────────────────


def test_a_paused_season_refuses_actions_but_keeps_the_pages(client):
    """暫停中（線上架構 8.3「擋住所有動作」）：每一種動作都回同一句（走鎖外三段的也在第一段就擋）；計時器、修練頁、輿圖、
    戰報照常看得到，打開輿圖照做（頁面靠它載入輿圖）。"""
    _player(client)
    game = server.game_for("沈青衫")
    assert game.world.pause_clock(time.time())
    main = client.get("/api/main").json()
    assert main["paused"] == 0 and [o["id"] for o in main["options"]] == ["season:paused"]
    refused = {"error": f"{server.PAUSED_TEXT}。"}
    for path, body in (
        ("/api/choose", {"id": "act:explore"}), ("/api/choose", {"id": "act:train"}),
        ("/api/choose", {"id": "act:socialize"}), ("/api/travel", {"place": "x", "mode": "walk"}),
        ("/api/menxia/practice", {"kind": "武學"}), ("/api/menxia/forge", {"art": "x", "insights": ["y"]}),
        ("/api/answer", {"text": "上前勸架"}), ("/api/do/seclude", {"hours": 8}), ("/api/do/battle_text", {"text": "放火"}),
    ):
        out = client.post(path, json=body)
        assert (out.status_code, out.json()) == (400, refused), path
    for path in ("/api/menxia", "/api/map", "/api/reports"):
        assert client.get(path).status_code == 200
    assert client.post("/api/do/view_map", json={}).status_code == 200


def test_the_admin_pauses_and_resumes_from_the_settings_page(client, monkeypatch):
    _admin(client, monkeypatch)
    game = server.game_for("掌門")
    out = client.post("/api/do/pause_clock", json={}).json()
    assert "賽季時鐘停了" in out["message"] and out["main"]["paused"] == 0
    assert game.world.paused_at() is not None
    assert "暫停中" in client.post("/api/do/fast_forward", json={"hours": 1}).json()["message"]
    out = client.post("/api/do/resume_clock", json={}).json()
    assert "賽季時鐘接著走了" in out["message"] and out["main"]["paused"] is None
    assert game.world.paused_at() is None


def test_players_cannot_pause_the_season(client):
    _player(client)
    for op in ("pause_clock", "resume_clock"):
        out = client.post(f"/api/do/{op}", json={})
        assert out.status_code == 400 and out.json() == {"error": "只有管理者能這麼做。"}


def test_the_pause_buttons_call_what_the_server_has():
    """網頁沒有測試框架：設定頁的「暫停／繼續」叫的動作要在 FEATURE_ADMIN_ACTIONS 裡、有確認問句，讀的欄位要在 main_view 裡。"""
    js = webharness.app_source()
    for op in ("pause_clock", "resume_clock"):
        assert f'data-op="{op}"' in js and f"{op}: [" in js and op in server.FEATURE_ADMIN_ACTIONS
    assert "S.main.paused" in js
    assert "paused" in server.main_view(Game.new(server.CONTENT, "測試"))


def test_the_resume_confirmation_does_not_promise_that_every_pause_is_taken_off():
    """「▶ 繼續」的確認問句照 world.resume_skip_text 說：整個季曆鐘頭才扣，停不到一個季曆鐘頭的話什麼都不扣、季末不動
    （B12）——不能一律說「不算進賽季、季末往後延一樣長」。"""
    js = webharness.app_source()
    line = next(row for row in js.splitlines() if row.strip().startswith("resume_clock: ["))
    assert "整個季曆鐘頭" in line and "不到一個季曆鐘頭" in line and "季末不動" in line
    assert "停的這一段不算進賽季，季末往後延一樣長" not in line


def test_world_step_does_not_move_a_paused_season():
    """伺服器排程的一下（world_step）暫停中什麼都不推——過了三個季長也不收季；繼續之後從停的那一刻接著走。
    打到一半的決戰那一路見 tianxia/features/admin/tests/test_season_pause.py::test_the_scheduler_tick_waits_out_the_pause。"""
    world = open_world()
    scale = server.CONTENT.config.time_scale
    server.world_step(lambda: 1000.0)  # 記下時鐘
    server.world_step(lambda: 1600.0)
    stopped = world.get_season().time
    assert stopped == pytest.approx(600 * scale)
    assert world.pause_clock(1600.0)
    far = 1600.0 + 3 * season_length_days(world.get_season(), server.CONTENT) * 86400 / scale  # 過了三個季長
    server.world_step(lambda: far)
    assert (world.get_season().time, world.get_season().ended, world.season_phase()) == (stopped, False, "running")
    assert world.resume_clock(server.CONTENT, far) == far - 1600.0
    server.world_step(lambda: far + 10)
    assert world.get_season().time == pytest.approx(stopped + 10 * scale)


def test_the_fingerprint_follows_the_seal_duel_but_not_who_was_seen():
    """奪璽單挑：回合 +1、親自出了一手，指紋變；last_seen（每 15 秒就可能動一次）變了不算（5.10）。"""
    world = open_world()
    world.seed_first_season(server.CONTENT)
    if world.season_phase() == "preparing":
        world.open_season(server.CONTENT, 1000.0)
    world.mutate(lambda st: st.seal_duels.append(_seal_duel()))
    before = server.current_fingerprint()
    world.mutate(lambda st: setattr(st.seal_duels[0].challenger, "last_seen", 1234.0))
    assert server.current_fingerprint() == before
    world.mutate(lambda st: st.seal_duels[0].pending.__setitem__("challenger", "強攻"))
    sent = server.current_fingerprint()
    assert sent != before
    world.mutate(lambda st: setattr(st.seal_duels[0], "round", 1))
    assert server.current_fingerprint() != sent


# ── 見聞的「榜單」（企劃者 2026-10-14）──


def test_boards_lists_six_boards_and_caches_the_scan(client, monkeypatch):
    """/api/boards：六張榜照 leaderboard.BOARDS 的順序；整份快取 BOARDS_TTL_SECONDS 秒，期間再多人點開也只掃一次角色。"""
    from tianxia import leaderboard

    monkeypatch.setattr(server, "BOARDS_CACHE", {})
    _player(client)
    calls = []
    real = leaderboard.compute_boards
    monkeypatch.setattr(leaderboard, "compute_boards", lambda *a, **k: calls.append(1) or real(*a, **k))
    out = client.get("/api/boards").json()
    assert [b["id"] for b in out["boards"]] == [kind for kind, _, _ in leaderboard.BOARDS] + ["神器"]  # 最後是神器譜（2026-10-17）
    assert out["boards"][-1]["book"] == []
    client.get("/api/boards")
    assert len(calls) == 1
    server.BOARDS_CACHE["at"] -= server.BOARDS_TTL_SECONDS
    client.get("/api/boards")
    assert len(calls) == 2


def test_boards_tab_is_in_the_news_page():
    from pathlib import Path

    src = webharness.app_source()
    assert '{ id: "boards", name: "榜單" }' in src and 'api("/api/boards")' in src

def test_the_first_request_after_a_restart_posts_the_wanted_notice(client):
    """名聲 4.6：系統通緝在本人這一輪掛（Game.own_turn_checks，mark_seen 叫）。伺服器重開之後（GAMES 是空的、Game 物件重建）
    第一個請求就要掛：掛單不靠前一個請求留在 Game 物件上的記號。"""
    _player(client)
    characters = open_characters()
    state = characters.load("沈青衫")
    state.player.faction = "guan"
    state.player.joined_at = -1e9  # 過了新手期
    state.player.stats["fame"] = 10_000  # 不管這一季乘幾倍都是天下聞名
    characters.save(state)
    server.GAMES.clear()  # 重開：記憶體裡的 Game 都沒了
    client.get("/api/main")
    posted = [b for b in open_world().get_season().bounties if b.auto_by == "陣營" and b.target == "沈青衫"]
    assert len(posted) == 1 and posted[0].faction == "huang"
