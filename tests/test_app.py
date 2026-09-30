import gradio as gr
import pytest

import app
from tianxia import roster
from tianxia.engine import Game
from tianxia.save import save_game

SKIP = {"__type__": "update"}


@pytest.fixture(autouse=True)
def save_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    return tmp_path


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
    assert len(out) == 6
    assert out[3] == app.PERSON_HINT  # 沒選人時顯示提示
    assert out[0].startswith("**心得** 0")


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
    assert app.act(None, lambda g: None, note=True) == [gr.skip()] * (app.N_OUTPUTS + 6)


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


def test_make_fast_forward_handler_advances_time(game):
    handler = app.make_fast_forward_handler(8)
    handler(game)
    assert game.state.world.time == 8 * 3600


def test_seclude_handler(game):
    out = app.seclude_handler(game, 4)
    assert len(out) == app.N_OUTPUTS
    assert game.state.player.busy_until is not None


# ── 門下頁面 ──────────────────────────────────────────────


def test_open_and_close_menxia(game):
    out = app.open_menxia(game)
    assert len(out) == 8
    assert out[0] == {"__type__": "update", "visible": False}
    assert out[1] == {"__type__": "update", "visible": True}
    assert app.close_menxia() == [
        {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False},
    ]


def test_open_menxia_with_no_game_skips():
    assert app.open_menxia(None) == [gr.skip()] * 8


def test_roster_pick_shows_the_selected_persons_card(game):
    roster.recruit(game.state, game.content, game.world, "liubei")
    out = app.roster_pick_handler(game, "liubei")
    assert out[2]["value"] == "liubei"
    assert out[3].startswith("### 劉備")


def test_roster_pick_with_no_game_skips():
    assert app.roster_pick_handler(None, "liubei") == [gr.skip()] * 6


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
    assert app.toggle_team_handler(game, None) == [gr.skip()] * 6
    assert app.toggle_team_handler(None, "liubei") == [gr.skip()] * 6


def test_create_skill_practice_and_heal_handlers(game):
    out = app.create_skill_handler(game, "player", "武學", "龍吟九霄")
    assert out[5] == "你自創了一門武學【龍吟九霄】（中品，屬陰）！"
    out2 = app.practice_handler(game, "player", "武學")
    assert out2[5] == "【龍吟九霄】精進至第2成。"
    out3 = app.heal_handler(game, "player")
    assert out3[5] == "氣血無恙，不用療傷。"


def test_menxia_handlers_with_no_game_skip():
    assert app.create_skill_handler(None, "player", "武學", "x") == [gr.skip()] * 6
    assert app.practice_handler(None, "player", "武學") == [gr.skip()] * 6
    assert app.heal_handler(None, "player") == [gr.skip()] * 6


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
    assert len(out) == app.N_OUTPUTS + 6
    assert (save_dir / "測試.json").exists()


def test_tick_handler_with_no_game_skips():
    n = app.N_OUTPUTS + 6
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


def test_start_requires_a_name():
    with pytest.raises(gr.Error):
        app.start("  ")


def test_start_opens_the_main_page(save_dir):
    out = app.start("新玩家")
    assert len(out) == app.N_OUTPUTS + 1 + len(app.PAGES)
    start_col_update = out[app.N_OUTPUTS]
    assert start_col_update["visible"] is False
    pages = out[app.N_OUTPUTS + 1:]
    assert [p["visible"] for p in pages] == [name == "main" for name in app.PAGES]


# ── build_demo ────────────────────────────────────────────


def test_build_demo_constructs_without_error():
    assert app.build_demo() is not None
