from unittest import mock

import gradio as gr
import pytest

import app
from tianxia import battle_instance, roster
from tianxia.engine import Game
from tianxia.save import save_game
from tianxia.state import BotProfile
from tianxia.world_state import WorldStateStore

SKIP = {"__type__": "update"}


@pytest.fixture(autouse=True)
def save_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def season_already_open(monkeypatch):
    """app.CONTENT 是正式內容（預設要管理者開季）；app 的測試要的是一季已經開打的畫面。"""
    monkeypatch.setattr(app.CONTENT.config, "auto_open_first_season", True)


@pytest.fixture
def game():
    return Game.new(app.CONTENT, "測試")


# ── 重畫函式的輸出形狀 ─────────────────────────────────────


def test_render_matches_n_outputs(game):
    assert len(app.render(game)) == app.N_OUTPUTS


def test_render_includes_quest_status_and_minimap(game):
    out = app.render(game)
    assert any(isinstance(x, str) and x.startswith("### 主線") for x in out)
    assert "測試" in out[2]  # status_md
    assert out[app.MINIMAP_INDEX] == game.minimap_svg()
    assert "<svg" in out[app.MINIMAP_INDEX]


def test_render_menxia_shape_and_hint(game):
    out = app.render_menxia(game)
    assert len(out) == app.MENXIA_OUTPUTS
    assert out[3] == app.PERSON_HINT  # 沒選人時顯示提示
    assert out[0].startswith("**心得** 0")
    assert out[5].startswith("**煉製素材**")  # 背包那一塊（還沒撿到任何素材）


def test_render_menxia_with_an_unknown_person_falls_back_to_none(game):
    out = app.render_menxia(game, "ghost", "")
    assert out[3] == app.PERSON_HINT


def test_render_map_page_shape(game):
    out = app.render_map_page(game, "situation", None)
    assert len(out) == app.MAP_OUTPUTS
    assert out[app.MAP_PLACE_INDEX]["value"] == game.state.player.location


# ── save_path ──────────────────────────────────────────


def test_save_path_strips_unsafe_characters():
    assert app.save_path("沈/浪?").name == "沈_浪_.json"


# ── act() 與選項按鈕 ──────────────────────────────────────


def test_act_with_no_game_skips_every_output():
    assert app.act(None, lambda g: None) == [gr.skip()] * app.N_OUTPUTS
    assert app.act(None, lambda g: None, note=True) == [gr.skip()] * (app.N_OUTPUTS + app.MENXIA_OUTPUTS)


def test_act_runs_saves_and_renders(game, save_dir):
    out = app.act(game, lambda g: g.choose("act:explore"))
    assert len(out) == app.N_OUTPUTS
    assert (save_dir / "測試.json").exists()
    assert game.state.player.stamina < 150


def test_act_returning_unchanged_skips_everything(game, save_dir):
    out = app.act(game, lambda g: app.UNCHANGED)
    assert out == [gr.skip()] * app.N_OUTPUTS
    assert not (save_dir / "測試.json").exists()


def test_make_option_handler_dispatches_to_the_right_option(game):
    ids = [o.id for o in game.options()]
    handler = app.make_option_handler(ids.index("act:explore"))
    out = handler(game, ids)
    assert len(out) == app.N_OUTPUTS
    assert game.state.player.stamina < 150


def test_make_option_handler_skips_when_index_is_out_of_range(game):
    ids = [o.id for o in game.options()]
    handler = app.make_option_handler(99)
    assert handler(game, ids) == [gr.skip()] * app.N_OUTPUTS


def test_make_option_handler_skips_with_no_game():
    assert app.make_option_handler(0)(None, []) == [gr.skip()] * app.N_OUTPUTS


def test_make_fast_forward_handler_advances_time_for_admins(game, monkeypatch):
    monkeypatch.setattr(app.CONTENT.config, "admins", ["測試"])
    app.make_fast_forward_handler(8)(game)
    assert game.state.world.time == 8 * 3600


def test_fast_forward_is_refused_for_non_admins(game):
    app.make_fast_forward_handler(8)(game)
    assert game.state.world.time < 3600


def test_seclude_handler(game):
    out = app.seclude_handler(game, 4)
    assert len(out) == app.N_OUTPUTS
    assert game.state.player.busy_until is not None


# ── 門下頁面 ──────────────────────────────────────────────


def test_open_and_close_menxia(game):
    out = app.open_menxia(game)
    assert len(out) == 2 + app.MENXIA_OUTPUTS
    assert out[0] == {"__type__": "update", "visible": False}
    assert out[1] == {"__type__": "update", "visible": True}
    assert app.close_menxia() == [
        {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False},
    ]


def test_open_menxia_with_no_game_skips():
    assert app.open_menxia(None) == [gr.skip()] * (2 + app.MENXIA_OUTPUTS)


def test_roster_pick_shows_the_selected_persons_card(game):
    roster.recruit(game.state, game.content, game.world, "liubei")
    out = app.roster_pick_handler(game, "liubei")
    assert out[2]["value"] == "liubei"
    assert out[3].startswith("### 劉備")


def test_roster_pick_with_no_game_skips():
    assert app.roster_pick_handler(None, "liubei") == [gr.skip()] * app.MENXIA_OUTPUTS


def test_toggle_team_adds_then_removes(game):
    roster.recruit(game.state, game.content, game.world, "liubei")
    assert game.state.player.team == ["liubei"]  # roster.recruit 已經自動加入隊伍
    out = app.toggle_team_handler(game, "liubei")
    assert out[4] == {"value": "加入隊伍", "__type__": "update", "visible": True}
    assert game.state.player.team == []
    out2 = app.toggle_team_handler(game, "liubei")
    assert out2[4] == {"value": "移出隊伍", "__type__": "update", "visible": True}
    assert game.state.player.team == ["liubei"]


def test_toggle_team_with_no_person_or_game_skips(game):
    assert app.toggle_team_handler(game, None) == [gr.skip()] * app.MENXIA_OUTPUTS
    assert app.toggle_team_handler(None, "liubei") == [gr.skip()] * app.MENXIA_OUTPUTS


def test_create_skill_practice_and_heal_handlers(game):
    # 練功受傷是機率、而且沒固定種子，受傷時會多一段內傷訊息、療傷也就不再是「無恙」——
    # 這是這個測試原本 flaky 的原因（CLAUDE.md 有記），關掉受傷機率就完全確定了。
    game.content.config.practice_injury_chance = 0.0
    out = app.create_skill_handler(game, "player", "武學", "龍吟九霄")
    assert out[6] == "你自創了一門武學【龍吟九霄】（中品，屬陰）！"
    out2 = app.practice_handler(game, "player", "武學")
    assert out2[6] == "【龍吟九霄】精進至第2成。"
    out3 = app.heal_handler(game, "player")
    assert out3[6] == "氣血無恙，不用療傷。"


def test_menxia_handlers_with_no_game_skip():
    assert app.create_skill_handler(None, "player", "武學", "x") == [gr.skip()] * app.MENXIA_OUTPUTS
    assert app.practice_handler(None, "player", "武學") == [gr.skip()] * app.MENXIA_OUTPUTS
    assert app.heal_handler(None, "player") == [gr.skip()] * app.MENXIA_OUTPUTS


# ── 戰報頁面 ──────────────────────────────────────────────


def test_report_page_is_empty_with_no_battles(game):
    out = app.open_report_page(game)
    assert len(out) == 4
    assert out[3] == app.REPORT_EMPTY_TEXT


def test_report_page_with_no_game_skips():
    assert app.open_report_page(None) == [gr.skip()] * 4
    assert app.open_report_handler(None) == [gr.skip()] * 4


def test_close_report():
    assert app.close_report() == [
        {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False},
    ]


def test_report_pick_handler_shows_that_records_detail(game):
    assert app.report_pick_handler(None, None) == gr.skip()


# ── 匿名、整頁切換 ────────────────────────────────────────


def test_anonymous_handler_flips_the_flag(game):
    out = app.anonymous_handler(game, True)
    assert len(out) == app.N_OUTPUTS
    assert game.state.player.anonymous is True


def test_show_page_only_shows_the_named_page():
    out = app.show_page("menxia")
    visible = [u["visible"] for u in out]
    assert visible == [name == "menxia" for name in app.PAGES]


# ── 大地圖 ────────────────────────────────────────────────


def test_map_page_handler_selects_a_place(game):
    out = app.map_page_handler(game, "situation", "yingshui")
    assert out[app.MAP_PLACE_INDEX]["value"] == "yingshui"


def test_map_page_handler_with_no_game_skips():
    assert app.map_page_handler(None, "situation", "yingshui") == [gr.skip()] * app.MAP_OUTPUTS


def test_clicked_place_reads_the_loc_attribute():
    class Evt:
        loc = "yingshui"

    assert app.clicked_place(Evt()) == "yingshui"
    assert app.clicked_place(None) is None

    class BadEvt:
        loc = 123

    assert app.clicked_place(BadEvt()) is None


def test_map_click_handler_ignores_an_unknown_place(game):
    class Evt:
        loc = "does-not-exist"

    assert app.map_click_handler(game, "situation", Evt()) == [gr.skip()] * app.MAP_OUTPUTS


def test_map_click_handler_selects_a_known_place(game):
    class Evt:
        loc = "yingshui"

    out = app.map_click_handler(game, "situation", Evt())
    assert out[app.MAP_PLACE_INDEX]["value"] == "yingshui"


def test_open_world_map(game, save_dir):
    out = app.open_world_map(game)
    assert len(out) == app.N_OUTPUTS + len(app.PAGES) + app.MAP_OUTPUTS
    assert (save_dir / "測試.json").exists()


def test_open_world_map_with_no_game_skips():
    n = app.N_OUTPUTS + len(app.PAGES) + app.MAP_OUTPUTS
    assert app.open_world_map(None) == [gr.skip()] * n


def test_travel_handler_succeeds_and_returns_to_the_main_page(game):
    out = app.travel_handler(game, "situation", "yingshui")
    assert len(out) == app.N_OUTPUTS + len(app.PAGES) + app.MAP_OUTPUTS
    assert game.state.player.location == "yingshui"
    pages = out[app.N_OUTPUTS:app.N_OUTPUTS + len(app.PAGES)]
    assert [p.get("visible") for p in pages] == [name == "main" for name in app.PAGES]


def test_travel_handler_refused_stays_on_the_map_and_explains_why(game):
    game.seclude(4)  # 閉關中，安排前往會被擋下
    out = app.travel_handler(game, "situation", "yingshui")
    pages = out[app.N_OUTPUTS:app.N_OUTPUTS + len(app.PAGES)]
    assert [p.get("visible") for p in pages] == [name == "map" for name in app.PAGES]
    detail = out[app.N_OUTPUTS + len(app.PAGES) + app.MAP_DETAIL_INDEX]
    assert "沒能出發" in detail and "閉關中" in detail


def test_travel_handler_with_no_game_skips():
    n = app.N_OUTPUTS + len(app.PAGES) + app.MAP_OUTPUTS
    assert app.travel_handler(None, "situation", "yingshui") == [gr.skip()] * n


def test_close_world_map():
    out = app.close_world_map()
    assert [u["visible"] for u in out] == [name == "main" for name in app.PAGES]


# ── 引導、計時器 ──────────────────────────────────────────


def test_skip_tutorial_handler(game):
    out = app.skip_tutorial_handler(game)
    assert len(out) == app.N_OUTPUTS
    assert game.state.player.tutorial_step == len(app.CONTENT.tutorial.steps)


def test_tick_handler_syncs_and_saves(game, save_dir):
    out = app.tick_handler(game, None)
    assert len(out) == app.N_OUTPUTS + app.MENXIA_OUTPUTS
    assert (save_dir / "測試.json").exists()


def test_tick_handler_with_no_game_skips():
    n = app.N_OUTPUTS + app.MENXIA_OUTPUTS
    assert app.tick_handler(None, None) == [gr.skip()] * n


# ── 開局、讀檔 ────────────────────────────────────────────


def test_open_game_creates_a_new_character_when_no_save_exists(save_dir):
    g = app.open_game("新玩家")
    assert g.state.player.name == "新玩家"


def test_open_game_loads_an_existing_save(save_dir):
    g = app.open_game("新玩家")
    g.state.player.stamina = 42.0
    save_game(g.state, app.save_path("新玩家"))
    reloaded = app.open_game("新玩家")
    assert reloaded.state.player.stamina == 42.0


def test_open_game_backs_up_a_corrupt_save_and_starts_fresh(save_dir):
    bad = app.save_path("壞掉的")
    bad.write_text("{not json", encoding="utf-8")
    g = app.open_game("壞掉的")
    assert g.state.player.name == "壞掉的"
    assert list((save_dir / "backup").glob("壞掉的-*.json"))
    assert any("已備份" in line for line in g.state.log)


# ── 全服即時戰鬥：自訂行動輸入框（設計討論：魯莽該是玩家自己想出來的招）──────────


def test_battle_textbox_is_hidden_outside_a_battle(game):
    out = app.render(game)
    assert out[app.BATTLE_TEXT_INDEX]["visible"] is False
    assert out[app.BATTLE_TEXT_BUTTON_INDEX]["visible"] is False


def test_battle_textbox_shows_the_prompt_once_free_text_is_available(game):
    definition = app.CONTENT.battles["huangjin_showdown"]
    game.state.player.faction = "guan"  # 劇本分陣營：散人只能觀戰，要先投靠才有得加入
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=0.0):
        game.choose("battle:join:guan")
    after_muster = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        out = app.render(game)
    assert out[app.BATTLE_TEXT_INDEX]["visible"] is True
    assert out[app.BATTLE_TEXT_INDEX]["label"] == game.battle_free_text_prompt()
    assert out[app.BATTLE_TEXT_BUTTON_INDEX]["visible"] is True


def test_battle_text_handler_submits_the_custom_action(game, save_dir):
    definition = app.CONTENT.battles["huangjin_showdown"]
    game.state.player.faction = "guan"  # 劇本分陣營：散人只能觀戰，要先投靠才有得加入
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=320.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        out = app.battle_text_handler(game, "直取波才首級")
    assert len(out) == app.N_OUTPUTS
    battle = game.world.get_battle()
    assert any("直取波才首級" in line for line in battle.narrative_log)


def test_battle_text_handler_with_no_game_skips():
    assert app.battle_text_handler(None, "test") == [gr.skip()] * app.N_OUTPUTS


# ── build_demo ────────────────────────────────────────────


def test_build_demo_constructs_without_error():
    assert app.build_demo() is not None


def test_next_season_handler_runs_the_admin_rollover(game, monkeypatch):
    monkeypatch.setattr(app.CONTENT.config, "admins", ["測試"])
    game.advance(app.CONTENT.config.season_days * 86400)
    assert game.state.world.ended
    app.next_season_handler(game)
    assert not game.state.world.ended
    assert game.state.player.season_number == 2


def test_open_season_handler_only_works_for_admins(tmp_path, monkeypatch):
    from tianxia.world_state import WorldStateStore

    monkeypatch.setattr(app.CONTENT.config, "auto_open_first_season", False)
    fresh = Game.new(app.CONTENT, "路人", world=WorldStateStore(tmp_path / "world.json"))
    assert fresh.world.season_phase() == "preparing"
    out = app.open_season_handler(fresh)
    assert len(out) == app.N_OUTPUTS
    assert fresh.world.season_phase() == "preparing"  # 一般玩家按不動
    monkeypatch.setattr(app.CONTENT.config, "admins", ["路人"])
    app.open_season_handler(fresh)
    assert fresh.world.season_phase() == "running"


def test_every_action_takes_the_cross_program_action_lock(game, monkeypatch):
    """伺服器假人設計第九節：伺服器的行動鎖要讓假人程式也看得到，不能只是程式內的執行緒鎖。"""
    calls = []
    real = WorldStateStore.action_lock

    def spy(self, timeout=None):
        calls.append(timeout)
        return real(self, timeout)

    monkeypatch.setattr(WorldStateStore, "action_lock", spy)
    app.act(game, lambda g: None)
    app.tick_handler(game, None)
    assert calls == [None, None]
    assert not hasattr(app, "ACT_LOCK")


def test_open_game_refuses_a_name_that_belongs_to_a_server_bot(save_dir):
    g = app.open_game("周泰安")
    g.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    save_game(g.state, app.save_path("周泰安"))
    with pytest.raises(gr.Error, match="這個名號已有人使用"):
        app.open_game("周泰安")
    assert not (save_dir / "backup").exists()  # 假人的存檔不能被當成壞檔備份走


def test_admin_trigger_handlers(game, monkeypatch):
    monkeypatch.setattr(app.CONTENT.config, "admins", ["測試"])
    out = app.admin_trend_handler(game, "huangjin", 5)
    assert len(out) == app.N_OUTPUTS
    assert game.world.get_season().trends["huangjin"] == app.CONTENT.scenario.trends[0].start + 5
    app.admin_fire_handler(game, "huangjin_50")
    assert "huangjin_50" in game.world.get_season().fired_thresholds
    app.admin_battle_handler(game, "huangjin_showdown")
    assert game.world.get_battle() is not None


def test_admin_trigger_handlers_do_nothing_for_players(game):
    app.admin_battle_handler(game, "huangjin_showdown")
    app.admin_trend_handler(game, "huangjin", 50)
    assert game.world.get_battle() is None
    assert game.world.get_season().trends["huangjin"] == app.CONTENT.scenario.trends[0].start


def test_admin_choices_list_every_battle_great_event_and_trend():
    battles, events, trends = app.admin_choices()
    assert [b[1] for b in battles] == list(app.CONTENT.battles)
    assert [e[1] for e in events] == [th.id for th in app.CONTENT.scenario.thresholds] + [
        ev.id for ev in app.CONTENT.scenario.world_events
    ]
    assert [t[1] for t in trends] == [t.id for t in app.CONTENT.scenario.trends]


# ── 煉製與改練（門下頁第三刀）──────────────────────────────


def test_render_menxia_includes_the_craft_block_and_library(game):
    out = app.render_menxia(game)
    assert out[7]["choices"] == []  # 素材選單（背包是空的）
    assert out[8].startswith("**煉製**")
    assert out[9]["choices"] == []  # 功法庫


def test_craft_busy_locks_the_button_and_warns_about_the_wait():
    button, message = app.craft_busy()
    assert button["interactive"] is False
    assert "一分鐘" in message
    assert app.craft_done()["interactive"] is True


def test_craft_handler_crafts_and_redraws(game):
    from unittest import mock

    from tianxia import craft, materials
    from tianxia.ollama_client import OllamaClient

    materials.grant(game.state, game.content, "gang_1", 2)
    game.state.player.stats["xinde"] = 500
    with mock.patch.object(
        OllamaClient, "chat_structured",
        lambda self, messages, response_model, **kw: craft.CraftedName(name="裂江訣", description="說明。"),
    ):
        out = app.craft_handler(game, "player", ["gang_1", "gang_1"], "武學")
    assert "【裂江訣】" in out[6]
    assert game.state.player.member.wugong_id == "裂江訣"


def test_craft_preview_shows_the_cost_without_crafting(game):
    from tianxia import materials

    materials.grant(game.state, game.content, "gang_3", 2)  # 天品才要心得（凡品免心得）
    line = app.craft_preview_handler(game, ["gang_3", "gang_3"], "武學")
    assert "花" in line and "點心得" in line
    assert game.state.player.materials == {"gang_3": 2}  # 什麼都沒扣


def test_craft_and_switch_handlers_skip_without_a_game():
    assert app.craft_handler(None, "player", [], "武學") == [gr.skip()] * app.MENXIA_OUTPUTS
    assert app.switch_art_handler(None, "player", "x") == [gr.skip()] * app.MENXIA_OUTPUTS
    assert app.switch_art_handler(object(), "player", None) == [gr.skip()] * app.MENXIA_OUTPUTS
    assert app.craft_preview_handler(None, [], "武學") == gr.skip()


def test_switch_art_handler_changes_what_you_practise(game):
    from tianxia import team

    team.create_skill(game.state, game.content, game.world, "龍吟九霄", "武學")
    game.state.player.member.wugong_id = None  # 假裝它只在庫裡
    game.state.player.arts.append("龍吟九霄")
    out = app.switch_art_handler(game, "player", "龍吟九霄")
    assert "改練【龍吟九霄】" in out[6]
    assert game.state.player.member.wugong_id == "龍吟九霄"

# ── 帳號密碼登入（docs/superpowers/specs/2026-10-03-帳號密碼登入-design.md）──────────

ENTRY_OUTPUTS = app.N_OUTPUTS + 2 + len(app.PAGES) + 2  # outputs＋start_col、create_col＋各頁＋admin_group、account_state
START_COL = app.N_OUTPUTS
CREATE_COL = app.N_OUTPUTS + 1


@pytest.fixture(autouse=True)
def fresh_login_failures():
    app.LOGIN_FAILURES.clear()
    yield
    app.LOGIN_FAILURES.clear()


def _pages(out):
    return [p["visible"] for p in out[app.N_OUTPUTS + 2: app.N_OUTPUTS + 2 + len(app.PAGES)]]


def test_register_then_create_a_character_enters_the_game(save_dir):
    out = app.register("Shen_01", "secret-pw", "secret-pw")
    assert len(out) == ENTRY_OUTPUTS
    assert out[START_COL]["visible"] is False and out[CREATE_COL]["visible"] is True
    assert out[-1] == "shen_01"
    out = app.create_character("shen_01", "沈青衫")
    assert len(out) == ENTRY_OUTPUTS
    assert out[START_COL]["visible"] is False and out[CREATE_COL]["visible"] is False
    assert _pages(out) == [name == "main" for name in app.PAGES]
    assert out[-2]["visible"] is False  # 一般玩家看不到管理者區塊
    assert out[-1] == "shen_01"
    assert app.save_path("沈青衫").exists()
    assert app.account_store().get("shen_01").character == "沈青衫"


def test_create_character_requires_a_login_and_a_name(save_dir):
    with pytest.raises(gr.Error, match="請先登入。"):
        app.create_character(None, "沈青衫")
    app.register("shen_01", "secret-pw", "secret-pw")
    with pytest.raises(gr.Error, match="請先輸入你的名號。"):
        app.create_character("shen_01", "  ")


def test_login_with_a_character_goes_straight_in(save_dir):
    app.register("shen_01", "secret-pw", "secret-pw")
    app.create_character("shen_01", "沈青衫")
    out = app.login("SHEN_01", "secret-pw")
    assert len(out) == ENTRY_OUTPUTS
    assert _pages(out) == [name == "main" for name in app.PAGES]
    assert out[-1] == "shen_01"


def test_login_without_a_character_asks_for_a_name(save_dir):
    app.register("shen_01", "secret-pw", "secret-pw")
    out = app.login("shen_01", "secret-pw")
    assert out[START_COL]["visible"] is False and out[CREATE_COL]["visible"] is True


def test_login_errors_read_the_same(save_dir):
    app.register("shen_01", "secret-pw", "secret-pw")
    with pytest.raises(gr.Error, match="帳號或密碼不對。"):
        app.login("shen_01", "wrong-pw")
    with pytest.raises(gr.Error, match="帳號或密碼不對。"):
        app.login("nobody", "secret-pw")


def test_register_checks_the_repeated_password_and_the_format(save_dir):
    with pytest.raises(gr.Error, match="兩次輸入的密碼不一樣。"):
        app.register("shen_01", "secret-pw", "secret-px")
    with pytest.raises(gr.Error, match="帳號只能用英文字母、數字、底線，3～20 字。"):
        app.register("沈", "secret-pw", "secret-pw")
    assert app.account_store().get("shen_01") is None


def test_a_bot_name_a_player_name_and_an_admin_name_are_refused_with_the_same_words(save_dir, monkeypatch):
    monkeypatch.setattr(app.CONTENT.config, "admins", ["掌門"])
    bot = app.open_game("周泰安")
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    save_game(bot.state, app.save_path("周泰安"))
    app.register("first", "secret-pw", "secret-pw")
    app.create_character("first", "沈青衫")
    app.register("second", "secret-pw", "secret-pw")
    messages = []
    for name in ("周泰安", "沈青衫", "掌門"):
        with pytest.raises(gr.Error, match="這個名號已有人使用。") as err:
            app.create_character("second", name)
        messages.append(str(err.value))
    assert len(set(messages)) == 1
    assert app.account_store().get("second").character is None


def test_an_admin_account_sees_the_admin_tools(save_dir, monkeypatch):
    monkeypatch.setattr(app.CONTENT.config, "admins", ["掌門"])
    boss = app.open_game("掌門")
    save_game(boss.state, app.save_path("掌門"))
    store = app.account_store()
    store.register("boss", "secret-pw")
    store.bind_character("boss", "掌門")  # 管理者的帳號由主機端腳本綁（scripts/set_password.py）
    assert app.login("boss", "secret-pw")[-2]["visible"] is True


def test_change_password(save_dir):
    app.register("shen_01", "secret-pw", "secret-pw")
    assert app.change_password_handler("shen_01", "wrong-pw", "new-secret", "new-secret")[0] == "舊密碼不對。"
    assert app.change_password_handler("shen_01", "secret-pw", "new-secret", "new-secreX")[0] == "兩次輸入的密碼不一樣。"
    assert app.change_password_handler("shen_01", "secret-pw", "123", "123")[0] == "密碼至少 6 字。"
    assert app.change_password_handler("shen_01", "secret-pw", "new-secret", "new-secret") == ["密碼已更新。", "", "", ""]
    app.login("shen_01", "new-secret")


def test_change_password_needs_a_login(save_dir):
    assert app.change_password_handler(None, "secret-pw", "new-secret", "new-secret")[0] == "請先登入。"


def test_only_admins_can_reset_a_password(save_dir, monkeypatch):
    app.register("shen_01", "secret-pw", "secret-pw")
    app.create_character("shen_01", "沈青衫")
    player = app.open_game("沈青衫")
    assert app.reset_password_handler(player, "shen_01", "temp-pass") == ["（只有管理者能重設密碼。）", ""]
    assert app.reset_password_handler(None, "shen_01", "temp-pass") == ["（只有管理者能重設密碼。）", ""]
    monkeypatch.setattr(app.CONTENT.config, "admins", ["沈青衫"])
    assert app.reset_password_handler(player, "沒這個人", "temp-pass") == ["找不到這個帳號或名號。", ""]
    assert app.reset_password_handler(player, "shen_01", "123") == ["密碼至少 6 字。", ""]
    assert app.reset_password_handler(player, "沈青衫", "temp-pass") == ["已重設 shen_01 的密碼。", ""]
    app.login("shen_01", "temp-pass")


def test_names_with_invisible_characters_or_too_long_are_refused(save_dir):
    app.register("shen_01", "secret-pw", "secret-pw")
    for bad in ("Ray\u200bal", "\u202eRayal", "名" * 17):
        with pytest.raises(gr.Error, match="名號最多 16 字，也不能有看不見的字元。"):
            app.create_character("shen_01", bad)
    assert app.account_store().get("shen_01").character is None


def test_full_width_letters_count_as_the_same_name(save_dir, monkeypatch):
    monkeypatch.setattr(app.CONTENT.config, "admins", ["Rayal"])
    app.register("shen_01", "secret-pw", "secret-pw")
    with pytest.raises(gr.Error, match="這個名號已有人使用。"):
        app.create_character("shen_01", "Ｒａｙａｌ")
