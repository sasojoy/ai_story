import contextlib
import hashlib
import random
import re
import sqlite3
import time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import server
from conftest import at, season_one_events
from tianxia import atlas, battle_instance, calendar, companion_agent, database, fusion, naming
from tianxia.accounts import NAME_TAKEN
from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.journal import WORLD_NEWS
from tianxia.martial_arts import MartialArt
from tianxia.ollama_client import OllamaClient
from tianxia.sqlite_world import SqliteWorldStore, open_world
from tianxia.state import BotProfile


@pytest.fixture(autouse=True)
def save_dir(tmp_path):
    return tmp_path


@pytest.fixture(autouse=True)
def season_already_open(monkeypatch):
    """server.CONTENT 是正式內容（預設要管理者開季）；這裡的測試要的是一季已經開打的畫面。"""
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)


@pytest.fixture(autouse=True)
def fresh_server_memory():
    """登入紀錄、登入狀態、角色快取都只放在伺服器記憶體裡：每個測試從空的開始。"""
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    yield
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()


@pytest.fixture
def game():
    return Game.new(server.CONTENT, "測試")


@pytest.fixture
def client():
    return TestClient(server.app)


def _player(client, login="shen_01", name="沈青衫"):
    client.post("/api/register", json={"login": login, "password": "secret-pw", "again": "secret-pw"})
    return client.post("/api/character", json={"name": name}).json()


# ── 畫面資料 ────────────────────────────────────────────


def _fixed(event_id: str, week: int, day: float = 0):
    from tianxia.models import TimetableEvent, TimetableOutcome

    return TimetableEvent(id=event_id, week=week, day=day, title=f"{event_id}事", kind="fixed",
                          outcomes={"fixed": TimetableOutcome(text=f"{event_id}事的公告。")})


def test_main_view_bulletin_this_week(monkeypatch):
    """江湖頁最上面的公告卡：這一週已經發生的大事（Markdown 轉成 HTML），最多 3 則、新的在前。"""
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
    """FB-046：時刻表大事補進江湖紀錄那一則，全文公告卡上已經有了，江湖頁的「剛剛」（now）不再寫一次，
    改放再前面那一則（這裡是開場那一則）；江湖紀錄頁（latest＋journal＋older）照舊從最新一則列起。"""
    content = server.CONTENT
    monkeypatch.setattr(content.config, "season_one", True)
    monkeypatch.setattr(content.config, "season_days", 2.5)
    monkeypatch.setattr(content, "timetable", [_fixed("甲", 1)])
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
    """開關關著（現在的試玩伺服器）：推進一週，時刻表不跑、狀態列沒有季曆、公告卡是空的。"""
    monkeypatch.setattr(server.CONTENT, "timetable", season_one_events())
    assert server.CONTENT.config.season_one is False
    game.advance(7 * 86400)
    assert game.state.world.timeline == {} and game.state.world.schedule == {}
    view = server.main_view(game)
    assert "calendar" not in view["status"] and "next_event" not in view["status"]
    assert view["bulletin"] == []


def test_main_view_has_everything_the_page_draws(game):
    view = server.look(game, server.main_view)
    assert view["status"]["name"] == "測試"
    assert view["status"]["stamina"] == view["status"]["stamina_max"]
    assert "主線" in view["quest"]
    assert view["scene"].startswith("<p>")
    assert {"id", "label", "enabled"} <= set(view["options"][0])
    assert view["free_text"] is None
    assert view["card"] is None
    assert view["minimap"].startswith("<svg")
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
    assert view["status"]["stances"] == {"guan": 55, "huang": 45, "haoqiang": 10}


def test_main_view_carries_the_chaos_band_and_which_fronts_are_in_it(game, monkeypatch):
    """FB-065：圖卡要畫亂局帶（兩端讀設定、不寫死在前端）、標出在亂局裡的戰線，態勢那一行的說法也由伺服器給。"""
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    game.world.mutate_season(lambda season: (setattr(season, "season_one", True),
                                             season.trends.update(yingru=35, nanyang=65, jizhou=66)))
    view = server.look(game, server.main_view)
    assert view["status"]["chaos_band"] == {"low": 35, "high": 65}
    assert [(f["name"], f["value"], f["chaos"]) for f in view["fronts"]] == [
        ("潁川汝南", 35, True), ("南陽", 65, True), ("冀州", 66, False)]  # 35 與 65 剛好在邊上：算在亂局裡
    assert view["status"]["stance_notes"] == {"sum": "三條戰線合計", "haoqiang": "2 條戰線在亂局，割據漸長"}
    game.world.mutate_season(lambda season: season.trends.update(yingru=34, nanyang=66, jizhou=66))
    view = server.look(game, server.main_view)
    assert [f["chaos"] for f in view["fronts"]] == [False, False, False]
    assert view["status"]["stance_notes"]["haoqiang"] == "沒有戰線在亂局，割據漸消"
    assert "在亂局" in view["trends"] and "割據漸消" in view["trends"]  # 見聞→大勢的割據那一段同一句話


def test_main_view_has_no_chaos_data_with_the_switch_off(game):
    status = server.look(game, server.main_view)["status"]
    assert "chaos_band" not in status and "stance_notes" not in status


def test_admin_choices_follow_the_switch(game, monkeypatch):
    """管理者推大勢的下拉選單：開關關著跟 beta 一樣；開關打開但這一季沒蓋章也一樣；這一季蓋了「開」的章時
    列三條戰線與割據，不列黃巾聲勢（由戰線合成）。"""
    def listed():
        return [t["id"] for t in server.look(game, server.admin_choices)["trends"]]

    assert listed() == ["huangjin", "yuxi"]
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    assert listed() == ["huangjin", "yuxi"]
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))
    assert listed() == ["yingru", "nanyang", "jizhou", "geju", "yuxi"]


def test_admin_choices_leave_out_the_beta_battle_and_thresholds_in_season_one(game, monkeypatch):
    """計畫 T8：開戰與觸發大事的下拉選單照 Game.admin_battles／admin_fires——這一季蓋了「開」的章時，
    beta 那場決戰與四個黃巾聲勢門檻不列；開關關著照舊。"""
    def listed(kind):
        return [x["id"] for x in server.look(game, server.admin_choices)[kind]]

    assert "huangjin_showdown" in listed("battles") and "huangjin_60" in listed("events")
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))
    assert listed("battles") == ["changshe_fire", "guangzong"]  # 三場大戲；宛城要等第 3 週結算才知道開哪一版，先不列（PM 2026-10-05）
    assert not {"huangjin_50", "huangjin_60", "huangjin_80", "huangjin_10"} & set(listed("events"))
    assert {"yuxi_50", "yuxi_100"} <= set(listed("events"))


def test_menxia_view_falls_back_to_no_person_for_an_unknown_one(game):
    view = server.look(game, lambda g: server.menxia_view(g, "沒這個人"))
    assert view["person"] is None and view["person_card"] is None
    assert view["roster"][0]["key"] == "player"
    assert "forge_line" in view and "per_craft" not in view and "craft_line" not in view
    assert "materials" not in view and "arts" not in view  # 煉製頁不再列素材、修練頁不再從舊功法庫畫（改畫 owned_arts）


def test_a_json_list_person_is_treated_as_nobody_not_a_500(client, game):
    """名冊裡點的人是客戶端寫的：JSON 清單、數字之類不是字串的東西，一律當作沒點到人（以前 `in {…}` 會丟 TypeError → 500）。"""
    for odd in (["follower:x"], [], 7, {"k": "v"}):
        view = server.look(game, lambda g, odd=odd: server.menxia_view(g, odd))
        assert view["person"] is None and view["person_card"] is None
    _player(client)
    out = client.post("/api/menxia/heal", json={"person": ["follower:x"]})
    assert out.status_code == 200 and out.json()["menxia"]["person"] is None
    out = client.post("/api/menxia/join", json={"person": ["nobody"]})
    assert out.status_code == 400 and out.json() == {"error": "名冊裡沒有這個人。"}


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


def test_status_text_still_reads_the_same(game):
    text = game.status_text()
    assert text.startswith("### 測試　·　散人　第1級")
    assert "⚡ 體力 150/150" in text


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


def test_join_and_leave_check_the_roster_inside_the_actions_own_lock(client, monkeypatch, lock_events):
    """誰在名冊上是全服狀態（換季時同伴全部重獲自由、假人程式也在寫）：鎖外看完名冊、進鎖之前就可能變了。
    加入／移出隊伍要在動作的同一把鎖裡核對，引擎才能照它的假設、只處理名冊上的人。"""
    _player(client)
    real = Game.roster_lines

    def roster_spy(self):
        lock_events.append("roster")
        return real(self)

    monkeypatch.setattr(Game, "roster_lines", roster_spy)
    monkeypatch.setattr(Game, "remove_from_team", lambda self, person: lock_events.append("leave") or [])
    lock_events.clear()
    assert client.post("/api/menxia/leave", json={"person": "player"}).status_code == 200
    leave = lock_events.index("leave")
    enter = max(i for i, e in enumerate(lock_events[:leave]) if e == "enter")
    assert "roster" in lock_events[enter:leave] and "exit" not in lock_events[enter:leave]


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


def test_choosing_an_option_plays_it_and_saves(client):
    _player(client)
    out = client.post("/api/choose", json={"id": "act:explore"}).json()
    assert out["main"]["status"]["stamina"] < out["main"]["status"]["stamina_max"]
    assert open_characters().exists("沈青衫")


def test_an_option_that_is_not_on_the_menu_does_nothing(client):
    _player(client)
    before = client.get("/api/main").json()["status"]["stamina"]
    out = client.post("/api/choose", json={"id": "act:nonsense"}).json()
    assert out["main"]["status"]["stamina"] == before


def test_seclude_and_anonymous(client):
    _player(client)
    out = client.post("/api/do/anonymous", json={"value": True}).json()
    assert out["main"]["status"]["anonymous"] is True
    out = client.post("/api/do/seclude", json={"hours": 2}).json()
    assert out["main"]["status"]["busy_hours"] is not None


def test_an_unknown_action_is_not_found(client):
    _player(client)
    assert client.post("/api/do/nonsense", json={}).status_code == 404
    assert client.post("/api/menxia/nonsense", json={}).status_code == 404


def test_menxia_practice_and_heal(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "practice_injury_chance", 0.0)
    _player(client)
    out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()
    assert "基礎拳腳" in out["message"] and "第2成" in out["message"]  # 開局送的那一門
    assert "基礎拳腳" in out["menxia"]["player_card"]
    out = client.post("/api/menxia/heal", json={}).json()
    assert out["message"]
    assert out["main"]["status"]["name"] == "沈青衫"


def test_menxia_practice_costs_xinde_and_says_how_much_is_missing(client, monkeypatch):
    """練成花心得：第 1 成升第 2 成 1 點、第 2 成升第 3 成 2 點；不夠時直接說還差多少，等級與心得都不動。"""
    monkeypatch.setattr(server.CONTENT.config, "practice_injury_chance", 0.0)
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.stats["xinde"] = 1
    open_characters().save(game.state)
    out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()
    assert "第2成" in out["message"]
    assert open_characters().load("沈青衫").player.stats["xinde"] == 0
    out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()  # 第 2 成升第 3 成要 2 點，只剩 0 點
    assert "要 2 點心得，你只有 0 點" in out["message"] and "還差 2 點" in out["message"]
    saved = open_characters().load("沈青衫").player
    assert saved.member.wugong_level == 2 and saved.stats["xinde"] == 0


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
    assert "create-skill" not in (server.ROOT / "web" / "app.js").read_text(encoding="utf-8")


def test_roster_pick_and_team_toggle_ignore_people_you_do_not_have(client):
    _player(client)
    assert client.get("/api/menxia?person=nobody").json()["person"] is None
    out = client.post("/api/menxia/join", json={"person": "nobody"})
    assert out.status_code == 400 and out.json() == {"error": "名冊裡沒有這個人。"}


def test_forge_line_previews_without_forging(client):
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = ["feng"]
    game.state.player.stats["xinde"] = 100
    open_characters().save(game.state)  # 資料庫是唯一的真實來源：進鎖先重讀，只改記憶體的話下一個請求就看不到
    out = client.post("/api/forge_line", json={"art": "jichu_quanjiao", "insights": ["feng"]}).json()
    assert "合成" in out["line"] and "【基礎拳腳】＋「風」" in out["line"]
    out = client.post("/api/forge_line", json={}).json()  # 什麼都沒放：只說怎麼放
    assert "放一門武學和一個意境" in out["line"]
    saved = open_characters().load("沈青衫").player
    assert saved.arts == [] and saved.insights == ["feng"] and saved.stats["xinde"] == 100
    view = client.get("/api/menxia").json()
    assert "放一門武學和一個意境" in view["forge_line"] and "craft_line" not in view and "per_craft" not in view


def test_the_old_craft_endpoints_are_gone(client):
    _player(client)
    assert "craft" not in server.MENXIA_ACTIONS and "forge" in server.MENXIA_ACTIONS
    assert client.post("/api/menxia/craft", json={"materials": ["gang_1", "gang_1"]}).status_code == 404
    assert client.post("/api/craft_line", json={"materials": []}).status_code == 404


def test_allocate_through_the_main_actions(client):
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.stat_points = 1
    open_characters().save(game.state)
    r = client.post("/api/do/allocate", json={"stat": "con"}).json()
    assert r["main"]["status"]["stat_points"] == 0
    assert open_characters().load("沈青衫").player.stats["con"] == 6
    stat_names = server.CONTENT.config.stat_names
    assert [(name, key) for name, _, key in r["main"]["status"]["attrs"]] == [
        (stat_names[key], key) for key in ("str", "agi", "con", "wis")
    ]  # 網頁的配點鈕送的鍵就是這個鍵，要跟 Config.stat_names 對得上


def test_a_refused_allocation_through_the_server_only_says_why(client):
    _player(client)
    r = client.post("/api/do/allocate", json={"stat": "con"}).json()
    assert "沒有可以分配" in r["message"]
    r = client.post("/api/do/allocate", json={}).json()  # 客戶端沒帶 stat：也只是一句話，不是 500
    assert "沒有這項" in r["message"]


def test_the_allocate_buttons_call_what_the_server_has():
    """網頁沒有測試框架：配點鈕（web/app.js）叫的動作與送的欄位要在伺服器的 MAIN_ACTIONS 與狀態資料裡。"""
    js = (server.WEB / "app.js").read_text(encoding="utf-8")
    assert 'doMain("allocate", { stat:' in js
    assert "allocate" in server.MAIN_ACTIONS
    data = Game.new(server.CONTENT, "測試").status_data()
    for field in re.findall(r"\bs\.(stat_points|stat_cap)\b", js):
        assert field in data


def test_the_practice_and_furnace_pages_only_read_and_call_what_the_server_has(game):
    """Task 12：修練頁、煉製頁（web/app.js）讀的欄位都要在 menxia_view 裡、叫的動作都要在 MENXIA_ACTIONS 裡；
    舊煉製的端點、欄位、說法不再出現。網頁沒有測試框架，這條擋住「改了伺服器忘了改網頁」。"""
    js = (server.WEB / "app.js").read_text(encoding="utf-8")
    pages = js[js.index("function pagePractice"):js.index("// ── 輿圖 ──")]
    keys = set(server.look(game, server.menxia_view))
    assert {"owned_arts", "insights", "holdings", "naming", "slot_cards", "forge_line", "bag"} <= keys
    assert set(re.findall(r"\bx\.(\w+)", pages)) <= keys
    shown = js[js.index("const MENXIA_SHOWN"):]
    shown = shown[:shown.index("};")]
    assert set(re.findall(r'"(\w+)"', shown)) - {"practice", "craft"} <= keys  # 輪詢比對的欄位也都送得到
    called = set(re.findall(r'\bmx\("(\w+)"', js)) | set(re.findall(r"/api/menxia/(\w+)", js)) | set(re.findall(r'data-act="mx" data-op="(\w+)"', js))
    assert {"practice", "heal", "forge", "switch", "cultivate", "melt", "melt_insight", "name"} <= called
    assert called <= set(server.MENXIA_ACTIONS), called - set(server.MENXIA_ACTIONS)
    for gone in ("/api/craft_line", "/api/menxia/craft", "per_craft", "x.materials", "x.arts", "craftSel", "放入素材", "素材說明"):
        assert gone not in js, gone


def _js_function(js: str, header: str) -> str:
    """app.js 裡 IIFE 內的一個函式本體：從標頭（例如 "async function mx("）到下一個縮兩格的收尾 "\\n  }\\n"。"""
    start = js.index(header)
    return js[start:js.index("\n  }\n", start)]


def test_the_pages_trim_the_furnace_whenever_the_menxia_data_is_replaced():
    """修練頁熔掉爐裡放著的東西、再回煉製頁：S.forgeSel 還留著那個 id，爐子看起來是空的、開爐卻亮著（forgeReady 照 id 數）。
    只有輪詢的 refreshPage 會補，所以每個換掉 S.menxia 的地方都要自己修剪（mx、loadMenxia）。網頁沒有測試框架，這裡擋住漏改。"""
    js = (server.WEB / "app.js").read_text(encoding="utf-8")
    for header in ("async function mx(", "async function loadMenxia("):
        body = _js_function(js, header)
        assert "S.menxia = " in body and "trimPot()" in body, header
        assert body.index("trimPot()") > body.index("S.menxia = "), header  # 換上新資料之後才修剪
    trim = _js_function(js, "function trimPot(")
    assert "trimForgeSel()" in trim and 'S.forgeLine = ""' in trim and "updateForgeLine()" in trim


def test_a_refused_name_keeps_what_the_player_typed_and_the_pill_tick_does_not_outlive_the_tab():
    js = (server.WEB / "app.js").read_text(encoding="utf-8")
    submit = js[js.index('form.id === "name-art"'):]
    submit = submit[:submit.index('form.id === "seclude"')]
    assert 'await mx("name"' in submit and "again.value = data.name" in submit  # 被拒（表單還在）把字放回去
    assert "S.legendTick = {}" in _js_function(js, "async function goTab(")  # 回到修練頁時，破境丹的勾是真的沒勾


def test_the_three_art_buttons_stay_on_one_line_at_phone_width():
    """修練／改練這一門／熔煉在 375px 手機寬度：頁邊 16、清單邊框 1、卡內邊 14（兩側）、三顆之間兩個 8px 的縫，一排可用 375-32-2-28-16=297px。
    原本三顆等寬各 99px，扣掉邊框 2 與內距 28，「改練這一門」（5 字 × 15px = 75px）只剩 69px 放不下而折行。
    改成照字寬分配（flex: 1 1 auto、width: auto）、不折行、橫向內距縮到 8px：三顆自然寬 48＋93＋48 = 189px，一排有 108px 的餘裕。"""
    js = (server.WEB / "app.js").read_text(encoding="utf-8")
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    assert 'class="row art-actions"' in js[js.index("const artRow"):js.index("const insightRow")]
    rule = re.search(r"\.art-body \.art-actions > \.btn \{([^}]*)\}", css)
    assert rule is not None, "要有只管開啟的武學那一排按鈕的 class，不動全站的 .btn"
    body = rule.group(1)
    assert "white-space: nowrap" in body and "width: auto" in body and "flex: 1 1 auto" in body
    assert re.search(r"padding:\s*10px 8px", body)


def _a_player_with_insights(client, insights=("feng", "huo"), xinde=100):
    """新角色（開局送的兩門基礎武學在身上），悟得 insights、心得 xinde；存進資料庫（進鎖會重讀）。"""
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = list(insights)
    game.state.player.stats["xinde"] = xinde
    open_characters().save(game.state)


def test_the_forge_fuses_an_art_with_an_insight(client):
    """合成：武學＋意境，花 5 點心得，新武學進功法庫、底留著。不連模型：conftest 把 chat_structured 假成連不上，
    首次發現的配方走退路字表取名。"""
    _a_player_with_insights(client)
    out = client.post("/api/menxia/forge", json={"art": "jichu_quanjiao", "insights": ["feng"]})
    assert out.status_code == 200 and "衍生出" in out.json()["message"]
    saved = open_characters().load("沈青衫").player
    key = fusion.fuse_key("jichu_quanjiao", "feng")
    art = open_world().lookup_recipe(key)
    assert art is not None and art.id in saved.arts and art.kind == "武學" and art.attribute == "快"
    assert art.name == naming.fallback_name(server.CONTENT, key, "武學")  # 沒問模型
    assert saved.member.wugong_id == "jichu_quanjiao"  # 底留著
    assert saved.stats["xinde"] == 95
    assert saved.insights == ["feng", "huo"]  # 意境不會用掉


def test_the_forge_merges_two_insights(client):
    _a_player_with_insights(client)
    out = client.post("/api/menxia/forge", json={"insights": ["feng", "huo"]})
    assert out.status_code == 200 and "交融" in out.json()["message"]
    saved = open_characters().load("沈青衫").player
    merged = open_world().lookup_insight_recipe(fusion.merge_key("feng", "huo"))
    assert merged is not None and merged.attribute == "陽" and saved.insights == ["feng", "huo", merged.id]
    assert saved.stats["xinde"] == 95


def test_the_forge_refuses_what_it_cannot_do_and_charges_nothing(client):
    _a_player_with_insights(client, insights=("feng",), xinde=2)
    for body in ({"art": "jichu_quanjiao", "insights": ["feng"]}, {"insights": ["feng", "feng"]},
                 {"art": "jichu_quanjiao", "insights": ["huo"]}, {"art": "jichu_quanjiao", "insights": []}):
        out = client.post("/api/menxia/forge", json=body)
        assert out.status_code == 200 and out.json()["message"], body
    saved = open_characters().load("沈青衫").player
    assert saved.arts == [] and saved.insights == ["feng"] and saved.stats["xinde"] == 2


def test_the_forge_endpoints_survive_oddly_shaped_bodies(client):
    """body 是玩家（或亂送的客戶端）寫的：art 不是字串、insights 不是清單都不能打出 500，也不能動到任何東西。"""
    _a_player_with_insights(client)
    bodies = (
        {"art": ["jichu_quanjiao"], "insights": ["feng"]},
        {"art": {"id": "jichu_quanjiao"}, "insights": ["feng"]},
        {"art": 5, "insights": ["feng"]},
        {"art": "jichu_quanjiao", "insights": "feng"},
        {"art": "jichu_quanjiao", "insights": {"feng": 1}},
        {"art": None, "insights": 7},
        {"insights": [["feng"], {"x": 1}]},
        {},
    )
    for body in bodies:
        line = client.post("/api/forge_line", json=body)
        assert line.status_code == 200 and isinstance(line.json()["line"], str), body
        out = client.post("/api/menxia/forge", json=body)
        assert out.status_code == 200 and out.json()["message"], body
    saved = open_characters().load("沈青衫").player
    assert saved.arts == [] and saved.insights == ["feng", "huo"] and saved.stats["xinde"] == 100


def test_forge_line_warns_about_an_insight_you_have_not_learned(client):
    _player(client)
    line = client.post("/api/forge_line", json={"art": "jichu_quanjiao", "insights": ["feng"]}).json()["line"]
    assert "還沒悟到" in line


# ── 開爐的首次取名在行動鎖外（最終審查 Critical 1）：A 鎖內備料 → B 鎖外取名（有預算）→ C 鎖內重驗、登記、收費 ──

FIST_FENG = fusion.fuse_key("jichu_quanjiao", "feng")


def _forger(name="沈青衫", insights=("feng", "huo"), xinde=100) -> Game:
    """伺服器上這個角色唯一的那份 Game（server.game_for），悟得 insights、心得 xinde，存進資料庫（進鎖會重讀）。"""
    game = server.game_for(name)
    game.state.player.insights = list(insights)
    game.state.player.stats["xinde"] = xinde
    open_characters().save(game.state)
    return game


def _model(reply):
    """假的模型：reply(self, messages) 回名字（字串）。self 是那一次呼叫用的 OllamaClient（有預算時是複本）。"""
    def chat_structured(self, messages, response_model, **kwargs):
        return naming.NameReply(name=reply(self, messages), description="一句話。")

    return mock.patch.object(OllamaClient, "chat_structured", chat_structured)


def _nobody_holds_the_lock(game):
    assert not game.world.db.writing()  # 這個執行緒沒拿著寫入交易
    probe = sqlite3.connect(game.world.db.path, timeout=0)
    try:
        probe.execute("BEGIN IMMEDIATE")  # 別的程式（假人、別的玩家）也拿得到寫入權
        probe.execute("ROLLBACK")
    finally:
        probe.close()


def _crafts(name):
    """這個角色江湖紀錄裡「煉製」的那幾則（同一種連續的會併成一則，所以比內容，不只比則數）。"""
    return [e.model_dump() for e in open_characters().load(name).journal if e.title == "煉製"]


def test_a_new_recipe_is_named_outside_the_action_lock(lock_events):
    game = _forger()
    lock_events.clear()

    def reply(client, messages):
        lock_events.append("generate")
        _nobody_holds_the_lock(game)
        return "旋風腿"

    with _model(reply):
        msgs = server.forge(game, "jichu_quanjiao", ["feng"])
    assert lock_events == ["enter", "exit", "generate", "enter", "exit"]  # 鎖內備料 → 鎖外取名 → 鎖內登記
    assert open_world().lookup_recipe(FIST_FENG).name == "旋風腿"
    assert any("第一次" in m for m in msgs)


def test_the_forge_endpoint_never_asks_the_model_while_holding_the_lock(client):
    _a_player_with_insights(client)
    game = server.game_for("沈青衫")
    asked = []

    def reply(model, messages):
        _nobody_holds_the_lock(game)
        asked.append(model.timeout)
        return "旋風腿"

    with _model(reply):
        out = client.post("/api/menxia/forge", json={"art": "jichu_quanjiao", "insights": ["feng"]})
    assert out.status_code == 200 and "旋風腿" in out.json()["message"]
    # 預算 60 秒（扣掉 A 段等鎖的時間）；chat_structured 一次最多送兩趟，所以一趟最多一半。原本那個 client 不動
    assert len(asked) == 1 and 25 < asked[0] <= server.CONTENT.config.naming_budget_seconds / 2
    assert game.client.timeout == server.CONTENT.config.ollama_timeout


def test_when_the_first_trip_saw_no_need_for_the_model_the_lock_never_asks_it(monkeypatch):
    """A 段說不必叫模型（那一刻會被拒絕、配方有了、沒有 client），C 段進鎖時卻做得成（中間狀態變了）：
    鎖裡也不叫模型，直接用退路字表——伺服器永遠不走「鎖裡取名」那條路。"""
    game = _forger()
    monkeypatch.setattr(Game, "forge_request", lambda self, art_id, insight_ids: None)
    asked = []
    with _model(lambda model, messages: asked.append(1) or "旋風腿"):
        server.forge(game, "jichu_quanjiao", ["feng"])
    assert asked == []
    assert open_world().lookup_recipe(FIST_FENG).name == naming.fallback_name(server.CONTENT, FIST_FENG, "武學")


def test_a_recipe_registered_between_the_two_trips_gives_the_registered_art():
    """乙備料、取名的時候，甲把同一個配方合出來登記了：乙進鎖時拿到的是甲登記的那一門（照常付心得），
    乙的模型取的名字不登記，全服只有一筆。"""
    first, second = _forger("甲"), _forger("乙")
    with _model(lambda model, messages: "疾風腿"):
        proposed = server.prepare_forge(second, "jichu_quanjiao", ["feng"])  # 乙的 A、B
    assert proposed == ("疾風腿", "一句話。")
    with _model(lambda model, messages: "旋風腿"):
        server.forge(first, "jichu_quanjiao", ["feng"])  # 甲從頭到尾
    msgs = server.act(second, lambda g: g.forge("jichu_quanjiao", ["feng"], proposed=proposed))  # 乙的 C
    world = open_world()
    art = world.lookup_recipe(FIST_FENG)
    assert art.name == "旋風腿" and world.recipe_keys() == {FIST_FENG} and not world.is_skill_name_taken("疾風腿")
    saved = open_characters().load("乙").player
    assert art.id in saved.arts and saved.stats["xinde"] == 95
    assert any("由甲首創" in m for m in msgs)


@pytest.mark.parametrize(("art", "picked", "refusal"), [
    ("jichu_quanjiao", ["feng"], "你已經有了"),
    (None, ["feng", "huo"], "你已經悟得了"),
])
def test_the_same_forge_sent_twice_while_naming_is_charged_once(art, picked, refusal):
    """企劃者 2026-10-05（不能重複扣）：同一個人連按兩下、重新整理再按、開兩個分頁，兩個請求都在配方登記之前
    走完 A（都叫了模型）。C 段只有一個成功：第二個重驗時看見配方有了、東西已經在你身上，回「你已經有了／悟得了」，
    什麼都不收——不扣心得、不扣體力、不寫江湖紀錄；全服只登記一筆。"""
    game = _forger()
    names = iter(["旋風腿", "疾風腿"])
    with _model(lambda model, messages: next(names)):
        one = server.prepare_forge(game, art, picked)
        two = server.prepare_forge(game, art, picked)
    assert (one[0], two[0]) == ("旋風腿", "疾風腿")  # 兩趟都在配方登記之前：各叫了一次模型
    before = open_characters().load("沈青衫").player
    first = server.act(game, lambda g: g.forge(art, picked, proposed=one))
    after_one = open_characters().load("沈青衫").player
    crafts = _crafts("沈青衫")
    second = server.act(game, lambda g: g.forge(art, picked, proposed=two))
    after_two = open_characters().load("沈青衫").player
    assert not any(refusal in m for m in first) and len(second) == 1 and refusal in second[0]
    assert after_one.stats["xinde"] == after_two.stats["xinde"] == before.stats["xinde"] - 5
    assert after_two.stamina == pytest.approx(after_one.stamina, abs=0.01)  # 體力照現實時間回（sync），只差一點點
    assert (after_one.arts, after_one.insights) == (after_two.arts, after_two.insights)
    assert _crafts("沈青衫") == crafts  # 第二下沒有寫紀錄
    world = open_world()
    assert not world.is_skill_name_taken("疾風腿")
    if art:
        assert world.recipe_keys() == {FIST_FENG} and len(after_two.arts) == 1
    else:
        assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")).name == "旋風腿"
        assert after_two.insights == ["feng", "huo", "旋風腿"]
        assert after_two.stamina == pytest.approx(before.stamina - 10, abs=0.01)  # 只扣一次合併的體力


def test_a_second_tab_that_spends_the_xinde_while_naming_leaves_the_first_forge_refused_and_free():
    """Infra 第 2 點：B 段在鎖外等模型的時候，同一個角色在另一個分頁把同一份心得花在另一爐；C 段進鎖重驗，
    心得不夠了就整個不做：不登記配方、不扣東西、不寫紀錄，告訴玩家變了什麼。"""
    game = _forger(xinde=5)
    depth = []

    def reply(model, messages):
        if not depth:
            depth.append(1)
            server.forge(game, "jichu_quanjiao", ["huo"])  # 另一個分頁：完整的一爐（它自己的取名是下面那一句）
            return "旋風腿"
        return "烈火拳"

    with _model(reply):
        msgs = server.forge(game, "jichu_quanjiao", ["feng"])
    saved = open_characters().load("沈青衫").player
    fire = open_world().lookup_recipe(fusion.fuse_key("jichu_quanjiao", "huo"))
    assert fire.name == "烈火拳" and saved.arts == [fire.id] and saved.stats["xinde"] == 0
    assert any("心得不足" in m for m in msgs)
    assert open_world().lookup_recipe(FIST_FENG) is None and not open_world().is_skill_name_taken("旋風腿")
    assert len(_crafts("沈青衫")) == 1 and "烈火拳" in _crafts("沈青衫")[0]["tag"]


def test_the_furnace_button_stays_disabled_with_the_wait_line_while_naming():
    """企劃者 2026-10-05：等取名的時候「開爐」鈕關著、寫著爐火正旺，同一個分頁按不了第二下（busy）；
    重新整理之後頁面重畫、按鈕照常能按——伺服器不留任何等待中的狀態，重複扣由 C 段的重驗擋（見上面幾條）。"""
    js = (server.WEB / "app.js").read_text(encoding="utf-8")
    body = _js_function(js, "async function forge(")
    assert "await busy(" in body and "btn.disabled = true" in body and 'btn.textContent = "爐火正旺…"' in body
    assert "取名要花上一分鐘，請稍候" in body
    assert body.index("btn.disabled = true") < body.index('api("/api/menxia/forge"')


def test_the_page_never_polls_twice_at_once():
    """最終審查 Critical 1：取名要等的時候伺服器的執行緒還在跑；輪詢若不等上一次回來就再打一次 /api/main，
    卡住的請求會越疊越多、把執行緒池用光。poll() 有一個「還在等」的旗子，上一次沒回來就不打。"""
    js = (server.WEB / "app.js").read_text(encoding="utf-8")
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
    assert view["slot_cards"][0]["price"] == 1


def test_menxia_view_rows_carry_what_the_pages_need(client):
    """每門武學一列：身上的在前、功法卡已轉成 HTML、修練與熔煉按不按得下去與為什麼；意境一列一個。"""
    _a_player_with_insights(client)
    view = client.get("/api/menxia").json()
    breath, fist = view["owned_arts"]
    assert (breath["worn"], fist["worn"], breath["kind"], fist["kind"]) == (True, True, "內功", "武學")
    assert breath["level"] == 1 and breath["insight"] is None and breath["card"].startswith("<")
    assert breath["cultivate"]["ok"] is False and "沒有融過意境" in breath["cultivate"]["note"]
    assert breath["melt"]["ok"] is False
    assert [(i["id"], i["name"], i["melt"]) for i in view["insights"]] == [("feng", "風", 10), ("huo", "火", 10)]


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
    assert cards["武學"]["price"] == 9


def test_forge_cultivate_and_melt_through_the_endpoints(client):
    _a_player_with_insights(client)
    r = client.post("/api/menxia/forge", json={"art": "jichu_quanjiao", "insights": ["feng"]}).json()
    assert "衍生出" in r["message"]
    new = r["menxia"]["owned_arts"][-1]
    assert new["insight"] == "風" and new["cultivate"]["ok"] and new["worn"] is False
    r = client.post("/api/menxia/cultivate", json={"art": new["id"]}).json()
    assert "修練" in r["message"]
    assert open_characters().load("沈青衫").player.stamina < server.CONTENT.config.stamina_max  # 花了體力
    r = client.post("/api/menxia/melt", json={"art": new["id"]}).json()
    assert "熔成了心得" in r["message"]
    assert all(row["id"] != new["id"] for row in r["menxia"]["owned_arts"])


def _a_peerless_candidate(client, pills=2):
    """一門融過意境、已經是上品的武學（下一步是絕學）、手上有 pills 枚破境丹、體力夠。回傳（功法 id，Game）。"""
    _a_player_with_insights(client)
    r = client.post("/api/menxia/forge", json={"art": "jichu_quanjiao", "insights": ["feng"]}).json()
    art_id = r["menxia"]["owned_arts"][-1]["id"]
    game = server.game_for("沈青衫")
    game.state.player.art_quality[art_id] = "上品"
    game.state.player.legend_items = pills
    game.state.player.stamina = server.CONTENT.config.stamina_max
    open_characters().save(game.state)
    return art_id, game


def test_the_pill_is_taken_only_when_the_request_ticks_it_with_a_real_true(client):
    """勾了才服：use_legend 只認布林 true。累積了 8 次失敗之後，基本機率 28%、服丹 43%：擲 30%，不服輸、服了贏。"""
    from conftest import FixedRandom

    art_id, game = _a_peerless_candidate(client)
    game.rng = FixedRandom(0.99)
    for odd in (False, None, "true", 1, "yes", [True], {"a": 1}):  # 沒勾，或不是真正的 true：丹留著
        body = {"art": art_id} if odd is None else {"art": art_id, "use_legend": odd}
        out = client.post("/api/menxia/cultivate", json=body).json()
        assert "還差一點火候" in out["message"] and "你服下" not in out["message"], odd
    game.rng = FixedRandom(0.30)
    out = client.post("/api/menxia/cultivate", json={"art": art_id}).json()  # 第 8 次失敗之後的基本機率 25%：輸
    assert "還差一點火候" in out["message"]
    saved = open_characters().load("沈青衫").player
    assert saved.legend_items == 2 and saved.art_quality[art_id] == "上品" and saved.art_mastery[art_id] == 8
    out = client.post("/api/menxia/cultivate", json={"art": art_id, "use_legend": True}).json()  # 同一個 30：28% + 15% 贏
    assert "你服下一枚【破境丹】" in out["message"] and "晉為絕學" in out["message"]
    saved = open_characters().load("沈青衫").player
    assert saved.legend_items == 1 and saved.art_quality[art_id] == "絕學"


def test_a_stale_page_ticking_a_pill_you_no_longer_hold_still_cultivates(client):
    from conftest import FixedRandom

    art_id, game = _a_peerless_candidate(client, pills=0)
    game.rng = FixedRandom(0.10)
    out = client.post("/api/menxia/cultivate", json={"art": art_id, "use_legend": True})
    assert out.status_code == 200 and "你身上已經沒有破境丹了，這一回沒服。" in out.json()["message"]
    saved = open_characters().load("沈青衫").player
    assert saved.legend_items == 0 and saved.art_mastery[art_id] == 1 and saved.stamina < server.CONTENT.config.stamina_max


def test_the_practice_page_offers_the_pill_for_the_peerless_step(client):
    art_id, _ = _a_peerless_candidate(client)
    row = next(r for r in client.get("/api/menxia").json()["owned_arts"] if r["id"] == art_id)
    assert row["cultivate"]["note"] == "4% 晉為絕學・體力 10"
    assert row["cultivate"]["legend"]["label"] == "服下破境丹（+15%，剩 2 枚）"
    assert row["cultivate"]["legend"]["note"] == "19% 晉為絕學（含破境丹 +15%）・體力 10"
    breath = client.get("/api/menxia").json()["owned_arts"][0]
    assert breath["cultivate"]["ok"] is False and breath["cultivate"]["legend"] is None


def test_melting_an_insight_through_the_endpoint(client):
    _a_player_with_insights(client, xinde=0)
    r = client.post("/api/menxia/melt_insight", json={"insight": "feng"}).json()
    assert "化成了心得" in r["message"] and [i["id"] for i in r["menxia"]["insights"]] == ["huo"]
    saved = open_characters().load("沈青衫").player
    assert saved.insights == ["huo"] and saved.stats["xinde"] == 10
    r = client.post("/api/menxia/melt_insight", json={"insight": "feng"}).json()  # 已經沒有了
    assert "沒有這個意境" in r["message"]


def test_the_naming_row_and_the_name_action(client):
    """練成絕學的第一人：修練頁有等著取名的一列；定了名，那一列消失、武學的名字全服一起改。"""
    _a_player_with_insights(client)
    r = client.post("/api/menxia/forge", json={"art": "jichu_quanjiao", "insights": ["feng"]}).json()
    art_id = r["menxia"]["owned_arts"][-1]["id"]
    game = server.game_for("沈青衫")
    game.state.player.naming = art_id
    game.state.player.art_quality[art_id] = "絕學"
    open_characters().save(game.state)
    assert open_world().claim_master(art_id, "沈青衫")
    view = client.get("/api/menxia").json()
    assert view["naming"] == {"id": art_id, "name": view["owned_arts"][-1]["name"]}
    assert view["owned_arts"][-1]["melt"]["ok"] is False and "先替它定名" in view["owned_arts"][-1]["melt"]["note"]
    r = client.post("/api/menxia/name", json={"name": "旋風不歸腿"}).json()
    assert "旋風不歸腿" in r["message"] and r["menxia"]["naming"] is None
    assert r["menxia"]["owned_arts"][-1]["name"] == "旋風不歸腿"
    assert open_characters().load("沈青衫").player.naming is None


def test_a_bad_name_leaves_the_naming_right_in_place(client):
    _a_player_with_insights(client)
    r = client.post("/api/menxia/forge", json={"art": "jichu_quanjiao", "insights": ["feng"]}).json()
    art_id = r["menxia"]["owned_arts"][-1]["id"]
    game = server.game_for("沈青衫")
    game.state.player.naming = art_id
    open_characters().save(game.state)
    assert open_world().claim_master(art_id, "沈青衫")
    r = client.post("/api/menxia/name", json={"name": "a"}).json()
    assert "不行" in r["message"] and r["menxia"]["naming"]["id"] == art_id


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
    assert "基礎拳腳" in wugong["card"] and "第一成" in wugong["card"]  # 第一成／第十成那一行是功法卡才有的
    assert "基礎吐納" in neigong["card"]
    game = server.game_for("沈青衫")
    monkeypatch.setattr(server.CONTENT.config, "starter_skills", [])  # 沒有開局送的武學：讀檔才不會把空著的欄位補回來
    game.state.player.member.neigong_id = None  # 內容改版之後欄位空著的舊角色：卡片照舊說沒有
    open_characters().save(game.state)
    neigong = client.get("/api/menxia").json()["slot_cards"][1]
    assert "你還沒有內功。" in neigong["card"]


def test_the_slot_cards_say_whether_each_slot_holds_an_art_and_its_level(client, monkeypatch):
    """C5：修練頁照目前那一門有沒有功法、練到第幾成，決定鍛鍊鈕亮不亮。
    全程走 API：動作端點會存檔，每次進鎖都從資料庫重讀角色，所以讀到的是存好的那一份。"""
    monkeypatch.setattr(server.CONTENT.config, "practice_injury_chance", 0.0)

    def slots(cards):
        return [(c["kind"], c["learned"], c["level"], c["maxed"]) for c in cards]

    _player(client)
    assert slots(client.get("/api/menxia").json()["slot_cards"]) == [("武學", True, 1, False), ("內功", True, 1, False)]
    game = server.game_for("沈青衫")
    monkeypatch.setattr(server.CONTENT.config, "starter_skills", [])  # 沒有開局送的武學：讀檔才不會把空著的欄位補回來
    game.state.player.member.neigong_id = None  # 欄位空著（內容改版之後的舊角色）：沒學過、第 0 成
    game.state.player.stats["xinde"] = 100  # 練成花心得：第 1 成升到第十成共 45 點，開局的 20 點不夠
    open_characters().save(game.state)
    out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()
    assert slots(out["menxia"]["slot_cards"]) == [("武學", True, 2, False), ("內功", False, 0, False)]
    assert slots(client.get("/api/menxia").json()["slot_cards"]) == [("武學", True, 2, False), ("內功", False, 0, False)]
    for _ in range(8):  # 練到第十成：練滿了沒由伺服器照 team.MAX_LEVEL 說，前端不另外記上限
        out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()
    assert slots(out["menxia"]["slot_cards"]) == [("武學", True, 10, True), ("內功", False, 0, False)]


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
        id=name, name=name, kind="武學", quality="上品", attribute="柔",
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
    assert card.rstrip().endswith("來源：自創（沈浪 所創）</p>")


def test_travel_sets_off_or_stays_on_the_map_and_says_why(client):
    _player(client)
    game = server.game_for("沈青衫")
    out = client.post("/api/travel", json={"place": game.state.player.location}).json()
    assert out["arrived"] is False and out["reason"] and out["map"]["selected"] == game.state.player.location
    nearby = [o["id"][5:] for o in client.get("/api/main").json()["options"] if o["id"].startswith("move:")]
    out = client.post("/api/travel", json={"place": nearby[0]}).json()
    assert out["arrived"] is True
    assert game.state.player.journey.path == [nearby[0]]  # 步行：在路上


def test_the_map_offers_walking_hurrying_and_dashing(game):
    view = server.look(game, lambda g: server.map_view(g, "situation", "yingshui"))
    walk, hurry, dash = view["travel"]
    assert [walk["mode"], hurry["mode"], dash["mode"]] == list(atlas.MODES)
    assert walk["label"].startswith("步行（約 ") and walk["enabled"] is True
    assert hurry["label"].startswith("趕路（約 ") and "體力" in hurry["label"]
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
    walk, hurry, dash = server.look(game, lambda g: server.map_view(g, "situation", "yingshui"))["travel"]
    assert [o["to_jianghu"] for o in (walk, hurry, dash)] == [False, False, False]
    game.state.player.busy_until = game.state.world.time + 3600  # 閉關中：也不能出發，但那不是回江湖頁的事
    (resting,) = server.look(game, lambda g: server.map_view(g, "situation", "yingshui"))["travel"]
    assert resting["enabled"] is False and resting["to_jianghu"] is False


def test_the_other_blocks_settled_on_the_jianghu_page_flag_the_way_back_too(game):
    """FB-063 的餘項：交談中、（求見中）、投靠待確認、答話中也是要回江湖頁了結才解得開，輿圖的灰按鈕同樣帶 to_jianghu；
    原因的話不變，閉關、打坐、賽季結束照舊沒有這個旗標。"""
    p = game.state.player
    content = server.CONTENT  # 進鎖時會清掉指向不存在東西的欄位，所以用真的人物、陣營與伏筆鏈（求見中要在有兩位人物的地方，atlas 的測試涵蓋）
    for setup, reason, to_jianghu in (
        (lambda: setattr(p, "pending_companion", next(iter(content.characters))), "交談中，先告辭才能安排前往", True),
        (lambda: setattr(p, "pending_faction", content.scenario.factions[0].id), "投靠還沒決定，先決定再安排前往", True),
        (lambda: setattr(p, "fs_asking", content.foreshadows.chains[0].id), "正在答話，先作罷才能安排前往", True),
        (lambda: setattr(p, "resting_since", 0.0), "打坐中，先起身才能安排前往", False),
    ):
        p.pending_companion, p.picking_audience, p.pending_faction, p.fs_asking, p.resting_since = None, False, None, None, None
        setup()
        (blocked,) = server.look(game, lambda g: server.map_view(g, "situation", "yingshui"))["travel"]
        assert (blocked["enabled"], blocked["label"], blocked["to_jianghu"]) == (False, reason, to_jianghu)


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
    cost = atlas.travel_stamina(game.content, minutes, "dash")
    assert client.post("/api/travel", json={"place": "yingshui", "mode": "dash"}).json()["arrived"] is True
    assert game.state.player.location == "yingshui"
    assert game.state.player.stamina == game.content.config.stamina_max - cost


def test_reports_and_map_pages_read_without_saving(client, save_dir):
    _player(client)
    with open_characters().db.transaction() as conn:
        conn.execute("DELETE FROM characters")
    assert client.get("/api/reports").json()["list"] == []
    assert client.get("/api/map?layer=enemy").json()["layer"] in {"enemy", server.DEFAULT_LAYER}
    assert not open_characters().exists("沈青衫")


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
            server.act(game, lambda g: server.MAIN_ACTIONS["battle_text"](g, {"text": "直取波才首級"}))
    assert any("直取波才首級" in line for line in game.world.get_battle().narrative_log)


# ── 決戰選項的回話（FB-030）：網頁上要看得到按下去發生了什麼 ──────────────


def _a_showdown_fighter(client, started=False):
    """官軍的新角色，黃巾決戰剛開（started＝集結已經結束、正在打），另有一位黃巾的真人在場、所以回合會等人。"""
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.faction = "guan"
    open_characters().save(game.state)
    definition = server.CONTENT.battles["huangjin_showdown"]
    open_world().start_battle(definition, now=time.time() - (definition.muster_seconds + 1 if started else 0))
    open_world().mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=320.0))
    return definition


def _journal_titles(name="沈青衫"):
    return [e.title for e in open_characters().load(name).journal]


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
    out = client.post("/api/do/battle_text", json={"text": "直取波才首級"}).json()
    assert "等待其他人" in out["message"]
    assert _journal_titles() == before


def test_an_ordinary_option_does_not_come_back_with_a_message(client):
    """它的話已經在江湖紀錄與「剛剛」裡，再跳一句提示會重複。"""
    _player(client)
    out = client.post("/api/choose", json={"id": "act:explore"}).json()
    assert "message" not in out


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
    server.act(fresh, lambda g: server.ADMIN_ACTIONS["open_season"](g, {}))
    assert fresh.world.season_phase() == "running"


def test_preparing_has_no_now_card_and_no_countdown(tmp_path, monkeypatch):
    """FB-049：籌備中時鐘沒走、什麼都不能做：江湖頁不畫「剛剛」（開場那一則寫「賽季開始」、叫人先去探索），
    狀態列不倒數下一件大事；江湖紀錄頁照樣列得到開場那一則。開季之後照常。"""
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", False)
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["路人"])
    fresh = Game.new(server.CONTENT, "路人", world=open_world(tmp_path / "world.db"))
    assert fresh.world.season_phase() == "preparing"
    view = server.main_view(fresh)
    assert view["now"] == "" and "賽季開始" in view["latest"]
    assert view["status"]["calendar"] and view["status"]["next_event"] is None
    assert view["guide"] is None  # 說書人的對話框也不叫人去探索（FB-045～052 審查 I1）
    server.act(fresh, lambda g: server.ADMIN_ACTIONS["open_season"](g, {}))
    view = server.main_view(fresh)
    assert view["now"] and view["status"]["next_event"] is not None and view["guide"] is not None
    # FB-062：下一件寫季曆時刻加現實倒數，畫面（web/app.js）把兩個拼成「宛城之戰・第 9 週・週四 20:44（現實約 4 小時 32 分後）」
    next_event = view["status"]["next_event"]
    assert re.fullmatch(r"第 \d+ 週・週[一二三四五六日] \d\d:\d\d", next_event["at"]) and next_event["in_seconds"] >= 0
    server.act(fresh, lambda g: server.ADMIN_ACTIONS["end_season"](g, {}))
    assert server.main_view(fresh)["guide"] is None  # 休季也一樣


def test_only_admins_can_reset_a_password(client, monkeypatch):
    _player(client)
    player = server.game_for("沈青衫")
    assert server.reset_password(player, "shen_01", "temp-pass") == "（只有管理者能重設密碼。）"
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
    assert server.reset_password(player, "沒這個人", "temp-pass") == "找不到這個帳號或名號。"
    assert server.reset_password(player, "shen_01", "123") == "密碼至少 6 字。"
    out = client.post("/api/admin/reset_password", json={"target": "沈青衫", "temp": "temp-pass"}).json()
    assert out == {"message": "已重設 shen_01 的密碼。"}
    server.login("shen_01", "temp-pass")


# ── 對話在行動鎖外生成（一個玩家的模型呼叫不能讓所有人一起等）────────────


DIALOGUE_TURN = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
)


def _stand_by_a_figure(game):
    """站到正式內容裡盧植所在的地點（盧植營，只有他一位大勢人物：交友直接找他），有他的結識旗標所以見得到；
    福緣設成已領，交友不會先觸發福緣。兩位以上人物的地點（例如廣宗）交友不開口，要「求見」指名。"""
    game.state.player.location = "luzhi_camp"
    game.state.player.flags.add("結識:luzhi")
    game.state.player.fortune = True


@pytest.fixture
def lock_events(monkeypatch):
    """記錄行動鎖「拿到、放掉」的順序，再讓測試把「生成」插進同一條時間線。"""
    events = []
    real = SqliteWorldStore.action_lock

    @contextlib.contextmanager
    def spy(self, timeout=None):
        with real(self, timeout):
            events.append("enter")
            yield
        events.append("exit")

    monkeypatch.setattr(SqliteWorldStore, "action_lock", spy)
    return events


def test_a_dialogue_option_generates_outside_the_action_lock(game, lock_events):
    _stand_by_a_figure(game)

    def generate(client, messages):
        lock_events.append("generate")
        assert not game.world.db.writing()  # 這個執行緒沒拿著寫入交易
        probe = sqlite3.connect(game.world.db.path, timeout=0)
        try:
            probe.execute("BEGIN IMMEDIATE")  # 別的程式也拿得到寫入權：沒有人卡著
            probe.execute("ROLLBACK")
        finally:
            probe.close()
        return DIALOGUE_TURN

    with mock.patch.object(companion_agent, "generate_turn", side_effect=generate) as gen:
        server.choose(game, "act:socialize")
    gen.assert_called_once()
    assert lock_events == ["enter", "exit", "generate", "enter", "exit"]  # 鎖內備料 → 鎖外生成 → 鎖內套用
    assert game.state.player.pending_companion == "luzhi"


def test_the_generated_turn_is_applied_and_saved(game, save_dir):
    _stand_by_a_figure(game)
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN):
        server.choose(game, "act:socialize")
    assert [o.id for o in game.options()] == ["talk:0", "talk:1", "talk:leave"]
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN) as gen, \
            mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("不該在鎖內再生成一次")):
        server.choose(game, "talk:0")
    gen.assert_called_once()
    assert game.state.player.affinities["luzhi"] == 1
    assert game.state.player.stamina < before  # 這一輪對話的體力照扣
    assert game.state.player.dialogue_history["luzhi"][-2:] == [
        {"role": "user", "content": "閒聊幾句"}, {"role": "assistant", "content": "他點了點頭。"},
    ]
    assert "他點了點頭。" in game.state.journal[0].lines
    assert open_characters().exists("測試")


def test_a_failed_generation_ends_the_talk_for_free(game, lock_events):
    _stand_by_a_figure(game)
    before = game.state.player.stamina

    def generate(client, messages):
        lock_events.append("generate")
        raise companion_agent.DialogueUnavailable("連不上")

    with mock.patch.object(companion_agent, "generate_turn", side_effect=generate):
        server.choose(game, "act:socialize")
    assert lock_events == ["enter", "exit", "generate", "enter", "exit"]
    assert game.state.player.pending_companion is None
    assert game.state.player.stamina == before
    assert game.state.journal[0].lines == ["盧植似乎無心多談，你只好先行告辭。"]


def test_a_changed_option_list_while_generating_falls_back_to_generating_in_the_lock(game):
    """生成的那十秒內，選單換了（例如兩個分頁各按一下）：進鎖重驗對不上，丟掉鎖外生成的，改在鎖內現生成。"""
    _stand_by_a_figure(game)
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN):
        server.choose(game, "act:socialize")

    def generate(client, messages):
        # 資料庫是唯一的真實來源（進鎖先重讀）：生成的那十秒裡另一個請求（連點兩下、第二個分頁）存了新的選單
        other = open_characters().load("測試")
        other.player.last_offered_dialogue["luzhi"] = [["換了一句話", "告辭"], ["尋常寒暄", "尋常寒暄"]]
        open_characters().save(other)
        return DIALOGUE_TURN

    fresh = companion_agent.CompanionTurn(
        narrative="他沉吟片刻。", options=["再聊聊", "告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
    )
    with mock.patch.object(companion_agent, "generate_turn", side_effect=generate) as outside, \
            mock.patch.object(companion_agent, "_generate", return_value=fresh) as in_lock:
        server.choose(game, "talk:0")
    outside.assert_called_once()  # 鎖外先生成過一次，但那一份被丟掉了
    in_lock.assert_called_once()
    assert "他沉吟片刻。" in game.state.journal[0].lines


def _stand_in_a_hall(game):
    """站到廣宗（張角、張梁兩位大勢人物：交友不開口，要「求見」指名），有張梁的結識旗標所以見得到他，
    張角名望不到見不到；福緣設成已領。"""
    game.state.player.location = "guangzong"
    game.state.player.flags.add("結識:zhangliang")
    game.state.player.fortune = True


def test_opening_and_closing_the_audience_list_never_asks_the_model(game, lock_events):
    _stand_in_a_hall(game)
    assert "act:socialize" not in [o.id for o in game.options()]  # 廣宗沒有交友事件：兩位人物都要求見
    with mock.patch.object(server, "prepare_dialogue", side_effect=AssertionError("打開或收起名單不必備料")), \
            mock.patch.object(companion_agent, "generate_turn", side_effect=AssertionError("不該呼叫模型")):
        server.choose(game, "act:call")
        assert [o.id for o in game.options()] == ["call:zhangjiao", "call:zhangliang", "call:back"]
        server.choose(game, "call:back")
    assert lock_events == ["enter", "exit", "enter", "exit"]  # 各拿一次鎖，沒有備料那一趟
    assert not game.state.player.picking_audience


def test_calling_on_a_figure_generates_outside_the_action_lock(game, lock_events):
    _stand_in_a_hall(game)
    server.choose(game, "act:call")
    lock_events.clear()

    def generate(client, messages):
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


class _PicksEvent(random.Random):
    """rng.choices 從候選名單裡挑指定 id 的那一則：挑得到就證明它真的是合格的候選。"""

    def __init__(self, wanted: str):
        super().__init__(0)
        self.wanted = wanted

    def choices(self, population, weights=None, *, cum_weights=None, k=1):
        return [next(event for event in population if event.id == self.wanted)]


def test_socializing_at_the_generals_mansion_reaches_yuanshaos_meeting(game):
    """大將軍府有何進、袁紹兩位人物，也有袁紹的結識事件：交友只走事件、從不開口，所以結識事件發得出來。"""
    game.state.player.location = "dajiangjun_fu"
    game.state.player.stats["fame"] = 99  # 兩位都見得到也一樣：交友不找人
    game.state.player.fortune = True
    ids = [o.id for o in game.options()]
    assert "act:socialize" in ids and "act:call" in ids
    assert not game.socialize_starts_dialogue()
    game.rng = _PicksEvent("meet_yuanshao")
    with mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("交友不該開口對話")):
        game.choose("act:socialize")
    assert game.state.pending_event == "meet_yuanshao"
    assert game.state.player.pending_companion is None


def test_a_non_dialogue_option_takes_the_lock_once_and_never_asks_the_model(game, lock_events):
    with mock.patch.object(companion_agent, "generate_turn", side_effect=AssertionError("不該呼叫模型")):
        server.choose(game, "act:explore")
    assert lock_events == ["enter", "exit"]  # 只拿一次鎖，沒有多餘的備料那一趟
    assert game.state.player.stamina < 150


def test_leaving_a_dialogue_does_not_ask_the_model_or_take_an_extra_lock_round_trip(game, lock_events):
    _stand_by_a_figure(game)
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN):
        server.choose(game, "act:socialize")
    lock_events.clear()
    with mock.patch.object(companion_agent, "generate_turn", side_effect=AssertionError("不該呼叫模型")), \
            mock.patch.object(server, "prepare_dialogue", side_effect=AssertionError("告辭不必備料")):
        server.choose(game, "talk:leave")
    assert lock_events == ["enter", "exit"]  # talk:leave 永遠不會生成對話：跟非對話選項一樣只拿一次鎖
    assert game.state.player.pending_companion is None


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


def test_the_versioned_urls_are_served_and_the_browser_must_ask_each_time(client):
    """no-cache：每次都向伺服器確認（/static 有 ETag，沒變就是 304）；改了檔沒重開伺服器也不會被瀏覽器釘住舊檔。"""
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

    from tianxia.content import load_content

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "PROFILE", None)
    server.main([])
    out = capsys.readouterr().out
    assert "設定：預設" in out and str(database.default_path().resolve()) in out
    monkeypatch.setattr(server, "PROFILE", "weekend")
    monkeypatch.setattr(server, "CONTENT", load_content(server.ROOT / "content", profile="weekend"))
    server.main([])
    assert "設定：weekend（第一季濃縮版規則開啟、季長 2.5 天、人數上限 2）" in capsys.readouterr().out


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


# ── --share：把 cloudflared 的輸出讀完、只從有網址的那一行取網址（FB-020）──────────
# cloudflared 第一行是「Requesting new quick Tunnel on trycloudflare.com...」：有網域、沒有 https://。
# 舊的 relay 在那一行 IndexError 就死了，三秒後真正的網址那行沒人讀。

TUNNEL_URL = "https://abc-def-123.trycloudflare.com"
URL_ANNOUNCEMENT = f"公開網址：{TUNNEL_URL}（給手機用；有網址的人都進得來，不要外流）"
NO_URL_NOTICE = "cloudflared 已結束，沒有拿到公開網址。它最後的輸出："
NO_OUTPUT_NOTICE = "cloudflared 沒有任何輸出就結束了。"

CLOUDFLARED_OUTPUT = [
    "2026-10-03T12:00:00Z INF Thank you for trying Cloudflare Tunnel. Doing so, without a Cloudflare account, is a quick way to experiment and try it out.\n",
    "2026-10-03T12:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...\n",
    "2026-10-03T12:00:03Z INF +--------------------------------------------------------------------------------------------+\n",
    "2026-10-03T12:00:03Z INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |\n",
    f"2026-10-03T12:00:03Z INF |  {TUNNEL_URL}                                                  |\n",
    "2026-10-03T12:00:03Z INF +--------------------------------------------------------------------------------------------+\n",
    "2026-10-03T12:00:03Z INF Version 2025.9.0\n",
    "2026-10-03T12:00:04Z INF Registered tunnel connection connIndex=0 location=tpe01 protocol=quic\n",
    "2026-10-03T12:00:05Z INF Registered tunnel connection connIndex=1 location=tpe02 protocol=quic\n",
]


class _CountingLines:
    """像 proc.stdout 一樣一行一行吐；記下總共被讀了幾行（用來證明網址之後的行也被讀完）。"""

    def __init__(self, lines):
        self.lines = list(lines)
        self.read = 0

    def __iter__(self):
        for line in self.lines:
            self.read += 1
            yield line


def test_the_tunnel_url_is_printed_once_from_the_line_that_has_it():
    printed = []
    server.relay_tunnel_output(CLOUDFLARED_OUTPUT, emit=printed.append)
    assert printed == [URL_ANNOUNCEMENT]  # 「Requesting …on trycloudflare.com」那行不是網址；cloudflared 其他輸出照舊安靜


def test_the_relay_keeps_reading_after_the_url_until_the_pipe_ends():
    """網址印出後還要把管線讀乾淨：沒人讀的話緩衝寫滿時 cloudflared 會卡住，隧道跟著停。"""
    lines = _CountingLines(CLOUDFLARED_OUTPUT)
    printed = []
    server.relay_tunnel_output(lines, emit=printed.append)
    assert lines.read == len(CLOUDFLARED_OUTPUT)
    assert printed == [URL_ANNOUNCEMENT]  # 讀完了也沒有再多說一句「沒拿到網址」


def test_a_url_that_cloudflared_prints_again_is_announced_only_once():
    printed = []
    server.relay_tunnel_output(CLOUDFLARED_OUTPUT + CLOUDFLARED_OUTPUT[4:5] * 2, emit=printed.append)
    assert printed == [URL_ANNOUNCEMENT]


def test_an_odd_line_is_skipped_instead_of_killing_the_relay():
    printed = []
    odd = [
        "\n",
        "INF see https:// trycloudflare.com for details\n",  # 有網域、有 https://，但不是一個網址
        "INF https://.trycloudflare.com\n",
        "\ufffd\ufffd INF �\n",
        "INF trycloudflare.com\n",
    ]
    server.relay_tunnel_output(odd + CLOUDFLARED_OUTPUT, emit=printed.append)
    assert printed == [URL_ANNOUNCEMENT]


def test_cloudflared_failing_to_request_a_tunnel_is_not_mistaken_for_the_public_url():
    """要不到隧道時 cloudflared 的錯誤訊息會帶 https://api.trycloudflare.com：那是它自己的服務、不是給手機用的網址。"""
    printed = []
    failed = [
        "2026-10-03T12:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...\n",
        'failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": dial tcp: lookup api.trycloudflare.com: no such host\n',
    ]
    server.relay_tunnel_output(failed, emit=printed.append)
    assert printed == [NO_URL_NOTICE] + [line.rstrip("\n") for line in failed]  # 錯誤訊息本身就是主機端要看的原因


def test_output_that_ends_without_any_url_says_so_instead_of_staying_silent():
    printed = []
    no_url = CLOUDFLARED_OUTPUT[:2] + CLOUDFLARED_OUTPUT[6:7]  # 沒有網址那行
    lines = _CountingLines(no_url)
    server.relay_tunnel_output(lines, emit=printed.append)
    assert lines.read == 3
    assert printed == [NO_URL_NOTICE] + [line.rstrip("\n") for line in no_url]  # 不到 20 行就全印，去掉行尾換行


# 拿不到網址時，「看上面 cloudflared 的輸出」上面其實什麼都沒有（輸出都被吞了）：
# 所以改成記住最後 20 行，結束時還沒有網址就印出來，原因就在眼前；成功時照樣安靜。

def _numbered_output(count):
    return [f"2026-10-03T12:00:{n:02d}Z ERR line {n}\n" for n in range(1, count + 1)]


def test_without_a_url_the_last_twenty_lines_are_printed_after_the_notice():
    assert server.TUNNEL_TAIL_LINES == 20
    output = _numbered_output(25)
    output[-1] = "2026-10-03T12:00:25Z ERR Failed to dial a quic connection: timeout: no recent network activity\n"
    printed = []
    server.relay_tunnel_output(output, emit=printed.append)  # 不丟例外
    assert printed == [NO_URL_NOTICE] + [line.rstrip("\n") for line in output[5:]]  # 第 6～25 行
    assert not any(line.endswith(("ERR line 1", "ERR line 5")) for line in printed)  # 前 5 行不在內


def test_without_a_url_the_tail_skips_blank_lines_and_trailing_newlines():
    printed = []
    server.relay_tunnel_output(["ERR first\r\n", "\n", "   \n", "ERR second\n", "ERR third"], emit=printed.append)
    assert printed == [NO_URL_NOTICE, "ERR first", "ERR second", "ERR third"]


def test_without_a_url_and_without_any_output_it_says_there_was_no_output():
    printed = []
    server.relay_tunnel_output([], emit=printed.append)
    assert printed == [NO_OUTPUT_NOTICE]
    printed.clear()
    server.relay_tunnel_output(["\n", "  \n"], emit=printed.append)  # 只有空行也等於沒有輸出
    assert printed == [NO_OUTPUT_NOTICE]


def test_with_a_url_the_tail_is_not_printed_even_when_the_output_is_long():
    printed = []
    server.relay_tunnel_output(_numbered_output(25) + CLOUDFLARED_OUTPUT + _numbered_output(25), emit=printed.append)
    assert printed == [URL_ANNOUNCEMENT]  # 成功路徑跟以前一樣：只印網址那一句


class _FakeProcess:
    def __init__(self, stdout):
        self.stdout = stdout


def test_start_tunnel_prints_the_url_and_hands_back_the_relay_thread(capsys, monkeypatch):
    import io
    import subprocess

    launched = []

    def fake_popen(command, **kwargs):
        launched.append(command)
        return _FakeProcess(io.StringIO("".join(CLOUDFLARED_OUTPUT)))

    monkeypatch.setattr(server.shutil, "which", lambda name: "C:/fake/cloudflared.exe")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    thread = server.start_tunnel(7890)
    thread.join(timeout=5)
    assert not thread.is_alive()  # 讀到 EOF 就正常結束，不是死在某一行上
    assert launched == [["C:/fake/cloudflared.exe", "tunnel", "--url", "http://127.0.0.1:7890"]]
    assert capsys.readouterr().out.splitlines() == [URL_ANNOUNCEMENT]


def test_start_tunnel_without_cloudflared_says_so_and_starts_nothing(capsys, monkeypatch):
    import subprocess

    monkeypatch.setattr(server.shutil, "which", lambda name: None)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("沒有 cloudflared 不該開子程序"))
    assert server.start_tunnel(7890) is None
    assert "找不到 cloudflared" in capsys.readouterr().out


# ── 主畫面的走法切換（步行／趕路／疾行）──────────────────────
# 頁面記著走法、每個請求都帶上 X-Move-Mode；伺服器在行動鎖裡照它排選單（server.MOVE_MODE），從不存檔。

HURRY = {"X-Move-Mode": "hurry"}


def _moves(options):
    return [o for o in options if o["id"].startswith("move:")]


def test_the_move_mode_header_switches_the_travel_options(client):
    _player(client)
    walking = client.get("/api/main").json()["options"]
    hurrying = client.get("/api/main", headers=HURRY).json()["options"]
    assert len(hurrying) == len(walking)  # 只換「前往」的走法，按鈕數不變
    moves = _moves(hurrying)
    assert moves and all(o["id"].count(":") == 2 and o["id"].endswith(":hurry") for o in moves)
    assert all("趕路" in o["label"] for o in moves)


def test_the_move_mode_lasts_one_request_like_two_tabs(client):
    _player(client)
    client.get("/api/main", headers={"X-Move-Mode": "dash"})
    moves = _moves(client.get("/api/main").json()["options"])  # 另一個分頁沒選走法：照樣步行，不會被上一個請求帶走
    assert moves and all(o["id"].count(":") == 1 and "步行" in o["label"] for o in moves)
    unknown = _moves(client.get("/api/main", headers={"X-Move-Mode": "fly"}).json()["options"])
    assert [o["id"] for o in unknown] == [o["id"] for o in moves]  # 不認得的走法當成步行


def test_a_hurried_move_departs_only_from_the_hurry_menu(client):
    _player(client)
    game = server.game_for("沈青衫")
    start = game.state.player.location
    assert "move:yingshui:hurry" in [o["id"] for o in client.get("/api/main", headers=HURRY).json()["options"]]
    client.post("/api/choose", json={"id": "move:yingshui:hurry"})  # 沒帶走法：步行的選單上沒有這個 id
    assert game.state.player.location == start and game.state.player.journey is None
    minutes = atlas.leg_minutes(game.content, start, "yingshui")
    client.post("/api/choose", json={"id": "move:yingshui:hurry"}, headers=HURRY)
    assert game.state.player.journey.mode == "hurry" and game.state.player.journey.path == ["yingshui"]
    cost = atlas.travel_stamina(game.content, minutes, "hurry")
    assert game.state.player.stamina == game.content.config.stamina_max - cost


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
        back = [o for o in client.get("/api/main", headers=HURRY).json()["options"] if o["id"].startswith("road:back")]
        assert [o["id"] for o in back] == ["road:back:hurry"] and "趕路" in back[0]["label"]
        client.post("/api/choose", json={"id": "road:back:hurry"})  # 沒帶走法：步行的選單上沒有這個 id
        assert game.state.player.journey.path == ["yingshui"]
        client.post("/api/choose", json={"id": "road:back:hurry"}, headers=HURRY)
    j = game.state.player.journey
    assert (j.mode, j.path) == ("hurry", [start])


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
    def assess(client, event, text):
        lock_events.append(f"assess:{text}")
        return 85

    game.rng = random.Random(0)
    def narrate(client, event, text, success, effect_text):
        lock_events.append("narrate")
        return "你扯開嗓子一喊。"

    with mock.patch.object(server.event_llm, "assess_event_success_rate", side_effect=assess), \
            mock.patch.object(server.event_llm, "narrate_event_gamble", side_effect=narrate):
        server.answer_event(game, "大喊官兵來了")
    assert lock_events == ["enter", "exit", "assess:大喊官兵來了", "enter", "exit", "narrate", "enter", "exit"]
    assert game.state.journal[0].lines[1] == "你扯開嗓子一喊。"
    assert game.state.pending_event is None
    assert game.state.journal[0].title == f"{at_a_gamble.title}・隨口應對"
    assert game.state.journal[0].lines[0].startswith("你：「大喊官兵來了」（成算")
    view = server.look(game, server.main_view)
    assert view["event_free_text"] is None


def test_answering_does_nothing_when_the_event_was_dealt_with_meanwhile(game, at_a_gamble):
    def assess(client, event, text):
        server.act(game, lambda g: setattr(g.state, "pending_event", None))  # 另一個分頁先選了別的
        return 85

    with mock.patch.object(server.event_llm, "assess_event_success_rate", side_effect=assess):
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
    assert main["options"][-1] == {"id": "choice:free", "label": "自己想辦法……", "enabled": True}
    assert client.post("/api/answer", json={"text": "  "}).status_code == 400
    with mock.patch.object(server.event_llm, "assess_event_success_rate", return_value=50):
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
    公告卡不畫（這一季的大事結算卡上都有）。江湖紀錄頁照舊列得到季末那則。"""
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


def _season_one_now(game, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))


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


def test_resting_season_sends_no_orders_and_no_cart(game, monkeypatch):
    """FB-045：收季之後（休季）江湖頁不再有本週軍令卡，也不再寫押糧那一行：收季那一週的軍令截止已經過了。"""
    from tianxia.state import Convoy

    _season_one_now(game, monkeypatch)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["測試"])
    game.sync(game.now)  # 拉回蓋了第一季章的那一份季
    game.state.player.faction = "guan"
    game.advance(700)  # 跨過第一個曆時交界：第 1 週發令
    game.state.player.convoy = Convoy(order="x", grain=4, from_loc="xinye", to_loc="wan_city")
    view = server.main_view(game)
    assert view["orders"] and view["convoy"]
    game.admin_end_season(now=game.now)
    assert game.state.world.ended
    view = server.main_view(game)
    assert "orders" not in view and "convoy" not in view
    assert game.orders_view() == [] and game.convoy_line() is None


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


# ── 引導小改版（新手引導重做設計第八節）─────────────────────────


def test_main_view_sends_the_guide_box_and_skipping_hides_it(client):
    """全新角色的 /api/main 帶著對話框：說書人與第一步的話（不用點開任何東西）；略過新手引導後就沒有了。"""
    main = _player(client)["main"]
    tutorial = server.CONTENT.tutorial
    assert main["guide"] == {"speaker": tutorial.speaker, "text": tutorial.steps[0].text, "done": [], "end": False}
    client.post("/api/do/skip_tutorial", json={})
    assert client.get("/api/main").json()["guide"] is None


def test_guide_ack_closes_the_outro(client):
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.tutorial_step = len(server.CONTENT.tutorial.steps)
    game.state.player.guide_outro = True
    open_characters().save(game.state)
    assert client.get("/api/main").json()["guide"]["end"] is True
    client.post("/api/do/guide_ack", json={})
    assert client.get("/api/main").json()["guide"] is None


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
