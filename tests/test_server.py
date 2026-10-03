import contextlib
import random
import sqlite3
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import server
from conftest import at
from tianxia import atlas, battle_instance, companion_agent, craft, database
from tianxia.accounts import NAME_TAKEN
from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.journal import WORLD_NEWS
from tianxia.martial_arts import MartialArt
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


def test_menxia_view_falls_back_to_no_person_for_an_unknown_one(game):
    view = server.look(game, lambda g: server.menxia_view(g, "沒這個人"))
    assert view["person"] is None and view["person_card"] is None
    assert view["roster"][0]["key"] == "player"
    assert view["per_craft"] == 2


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
    assert server.look(game, server.menxia_view)["xinde"] == 0
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


def test_menxia_create_practice_and_heal(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "practice_injury_chance", 0.0)
    _player(client)
    out = client.post("/api/menxia/create", json={"kind": "武學", "name": "流雲手"}).json()
    assert "流雲手" in out["message"]
    assert "流雲手" in out["menxia"]["player_card"]
    out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()
    assert "第2成" in out["message"]
    out = client.post("/api/menxia/heal", json={}).json()
    assert out["message"]
    assert out["main"]["status"]["name"] == "沈青衫"


def test_roster_pick_and_team_toggle_ignore_people_you_do_not_have(client):
    _player(client)
    assert client.get("/api/menxia?person=nobody").json()["person"] is None
    out = client.post("/api/menxia/join", json={"person": "nobody"})
    assert out.status_code == 400 and out.json() == {"error": "名冊裡沒有這個人。"}


def test_craft_line_previews_without_crafting(client):
    _player(client)
    game = server.game_for("沈青衫")
    mid = next(iter(server.CONTENT.materials))
    game.state.player.materials = {mid: 2}
    open_characters().save(game.state)  # 資料庫是唯一的真實來源：進鎖先重讀，只改記憶體的話下一個請求就看不到
    out = client.post("/api/craft_line", json={"materials": [mid, mid], "kind": "武學"}).json()
    assert "煉製" in out["line"]
    assert game.state.player.materials == {mid: 2}
    assert open_characters().load("沈青衫").player.materials == {mid: 2}
    view = client.get("/api/menxia").json()
    assert view["materials"][0]["id"] == mid and view["materials"][0]["count"] == 2


def _a_player_with_a_material(client, count, xinde=100):
    """新角色，背包裡某一種要花心得的（靈品）素材 ×count；存進資料庫（進鎖會重讀）。回傳素材 id。"""
    _player(client)
    game = server.game_for("沈青衫")
    mid = next(m.id for m in server.CONTENT.materials.values() if m.tier == 2)
    assert game.craft_cost([mid, mid]) > 0  # 要花心得，下面「心得有沒有被扣」才說明得了事情
    assert game.state.player.member.wugong_id is None and game.state.player.arts == []
    game.state.player.materials = {mid: count}
    game.state.player.stats["xinde"] = xinde
    open_characters().save(game.state)
    return mid


def test_the_forge_takes_the_same_material_twice_when_there_are_two(client):
    """FB-005：煉製可以重複丟同一樣素材（網頁版的素材格子本來就允許）；伺服器這一端也要收，兩樣都從背包扣。
    不連模型：conftest 把 chat_structured 假成連不上，首次發現的配方走退路字表取名。"""
    mid = _a_player_with_a_material(client, 2)
    price = server.game_for("沈青衫").craft_cost([mid, mid])
    out = client.post("/api/menxia/craft", json={"materials": [mid, mid], "kind": "武學"})
    assert out.status_code == 200
    saved = open_characters().load("沈青衫").player
    assert saved.materials.get(mid, 0) == 0
    assert saved.stats["xinde"] == 100 - price
    art = open_world().lookup_recipe(craft.recipe_key([mid, mid], "武學"))
    assert art is not None and saved.member.wugong_id == art.id  # 武學欄本來是空的，煉出來的直接配上身
    assert art.name == craft.fallback_name(server.CONTENT, craft.recipe_key([mid, mid], "武學"), "武學")  # 沒問模型


def test_the_forge_does_not_craft_the_same_material_twice_with_only_one(client):
    mid = _a_player_with_a_material(client, 1)
    out = client.post("/api/menxia/craft", json={"materials": [mid, mid], "kind": "武學"})
    assert out.status_code == 200 and "不夠" in out.json()["message"]
    saved = open_characters().load("沈青衫").player
    assert saved.materials == {mid: 1}
    assert saved.stats["xinde"] == 100
    assert saved.member.wugong_id is None and saved.arts == []


# ── 功法卡（FB-006）與功法庫先看卡再改練（QA L4）────────────────


def test_the_practice_page_gets_a_card_for_each_worn_art(client):
    _player(client)
    client.post("/api/menxia/create", json={"kind": "武學", "name": "流雲手"})
    cards = client.get("/api/menxia").json()["slot_cards"]
    assert [c["kind"] for c in cards] == list(server.KINDS)
    wugong, neigong = cards
    assert "流雲手" in wugong["card"] and "第一成" in wugong["card"]  # 第一成／第十成那一行是功法卡才有的
    assert "你還沒有內功。" in neigong["card"]


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
    (item,) = client.get("/api/menxia").json()["arts"]
    assert item["id"] == "沉柳纏勁"
    assert "【沉柳纏勁】" in item["card"] and "第1成" in item["card"]
    assert "以柔勁纏住兵刃，&lt;b&gt;借力&lt;/b&gt;卸力。" in item["card"]  # 模型寫的說明句也一律跳脫


def test_a_library_art_without_a_note_leaves_no_blank_line(client):
    """退路字表取名的功法沒有說明句：整行省略，不出現 None、不留空的 <br> 行（FB-006 驗收）。"""
    _a_player_with_library_arts(client, _library_art("鐵柳纏勁", ""))
    card = client.get("/api/menxia").json()["arts"][0]["card"]
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
    assert [b["id"] for b in choices["battles"]] == list(server.CONTENT.battles)
    assert len(choices["events"]) == len(server.CONTENT.scenario.thresholds) + len(server.CONTENT.scenario.world_events)
    assert [t["id"] for t in choices["trends"]] == [t.id for t in server.CONTENT.scenario.trends]


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
                     ("fast_forward", {"hours": 24}), ("open_season", {})):
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


def test_open_season_only_works_for_admins(tmp_path, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", False)
    fresh = Game.new(server.CONTENT, "路人", world=open_world(tmp_path / "world.db"))
    assert fresh.world.season_phase() == "preparing"
    monkeypatch.setattr(server.CONTENT.config, "admins", ["路人"])
    server.act(fresh, lambda g: server.ADMIN_ACTIONS["open_season"](g, {}))
    assert fresh.world.season_phase() == "running"


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
    """站到正式內容裡盧植所在的地點（盧植營，只有他一位大勢人物：交遊直接找他），有他的結識旗標所以見得到；
    福緣設成已領，交遊不會先觸發福緣。兩位以上人物的地點（例如廣宗）交遊不開口，要「求見」指名。"""
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
    """站到廣宗（張角、張梁兩位大勢人物：交遊不開口，要「求見」指名），有張梁的結識旗標所以見得到他，
    張角名望不到見不到；福緣設成已領。"""
    game.state.player.location = "guangzong"
    game.state.player.flags.add("結識:zhangliang")
    game.state.player.fortune = True


def test_opening_and_closing_the_audience_list_never_asks_the_model(game, lock_events):
    _stand_in_a_hall(game)
    assert "act:socialize" not in [o.id for o in game.options()]  # 廣宗沒有交遊事件：兩位人物都要求見
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
    """大將軍府有何進、袁紹兩位人物，也有袁紹的結識事件：交遊只走事件、從不開口，所以結識事件發得出來。"""
    game.state.player.location = "dajiangjun_fu"
    game.state.player.stats["fame"] = 99  # 兩位都見得到也一樣：交遊不找人
    game.state.player.fortune = True
    ids = [o.id for o in game.options()]
    assert "act:socialize" in ids and "act:call" in ids
    assert not game.socialize_starts_dialogue()
    game.rng = _PicksEvent("meet_yuanshao")
    with mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("交遊不該開口對話")):
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


def test_starting_the_server_prints_the_database_path(capsys, monkeypatch):
    """跟 run_bots.py 要開同一個資料庫：啟動時印出路徑，TIANXIA_DB 設錯時一眼看得出來（只印路徑，不印任何名號）。"""
    import uvicorn

    ran = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: ran.append(kwargs["port"]))
    server.main([])
    assert ran == [server.PORT]
    assert str(database.default_path().resolve()) in capsys.readouterr().out


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
