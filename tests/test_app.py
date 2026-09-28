import gradio as gr

import app
from tianxia.engine import Game


def test_render_matches_outputs():
    game = Game.new(app.CONTENT, "測試")
    assert len(app.render(game)) == app.N_OUTPUTS


def test_option_handler_acts_and_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    ids = [o.id for o in game.options()]
    out = app.make_option_handler(ids.index("act:explore"))(game, ids)
    assert len(out) == app.N_OUTPUTS
    assert (tmp_path / "測試.json").exists()
    assert game.state.player.stamina < 150


def test_save_path_strips_unsafe_characters(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    assert app.save_path("沈/浪?").name == "沈_浪_.json"


def test_build_demo():
    assert app.build_demo() is not None


def test_render_includes_quest_and_map():
    game = Game.new(app.CONTENT, "測試")
    out = app.render(game)
    assert any(isinstance(x, str) and x.startswith("### 主線") for x in out)
    assert any(isinstance(x, str) and x.startswith("<svg") for x in out)


def test_map_view_handler_advances_tutorial(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    game.state.player.tutorial_step = 1  # 第二步是「打開地圖」
    out = app.map_view_handler(game)
    assert len(out) == app.N_OUTPUTS
    assert game.state.player.tutorial_step == 2


def test_skip_tutorial_handler_finishes_tutorial(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    out = app.skip_tutorial_handler(game)
    assert len(out) == app.N_OUTPUTS
    assert game.state.player.tutorial_step == len(app.CONTENT.tutorial.steps)


def test_new_event_switches_main_tabs_to_scene(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    ids = [o.id for o in game.options()]
    out = app.make_option_handler(ids.index("act:explore"))(game, ids)
    assert game.state.pending_event is not None  # 揚州城探索必定遇到城鎮事件
    assert out[app.MAIN_TABS_INDEX] == gr.update(selected="scene")


def test_tick_never_switches_main_tabs(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    game.choose("act:explore")
    out = app.tick_handler(game)
    assert out[app.MAIN_TABS_INDEX] == gr.update()


def test_render_includes_team_skills_and_report():
    game = Game.new(app.CONTENT, "測試")
    out = app.render(game)
    assert "（隊長）" in out[app.TEAM_INDEX]
    assert "家傳劍法" in out[app.TEAM_INDEX + 1] and "吐納法" in out[app.TEAM_INDEX + 1]
    assert out[app.REPORT_INDEX] == "（還沒有戰報。）"


def test_loadout_handler_moves_skill_between_members(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    assert game.state.player.loadouts["player"] == ["tuna", "changquan"]
    out = app.loadout_handler(game, "hantie", "1", "tuna")
    assert len(out) == app.N_OUTPUTS
    assert game.state.player.loadouts["hantie"][0] == "tuna"
    assert game.state.player.loadouts["player"] == [None, "changquan"]


def test_loadout_handler_skips_when_no_skill_chosen_and_empty_choice_unequips(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    out = app.loadout_handler(game, "player", "1", None)  # 武學下拉還沒選任何東西
    assert out == [gr.skip()] * app.N_OUTPUTS
    assert game.state.player.loadouts["player"] == ["tuna", "changquan"]
    assert not (tmp_path / "測試.json").exists()
    app.loadout_handler(game, "player", "1", "")  # 選了「（空）」：卸下
    assert game.state.player.loadouts["player"] == [None, "changquan"]


def test_upgrade_and_dispel_handlers(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    game.state.player.stats["xinde"] = 100
    app.upgrade_handler(game, "skill:tuna")
    assert game.state.player.skills["tuna"] == 2
    app.dispel_handler(game, "skill:tuna")
    assert game.state.player.skills["tuna"] == 1


def test_incompatible_old_save_is_backed_up(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    (tmp_path / "測試.json").write_text("{}", encoding="utf-8")
    out = app.start("測試")
    game = out[0]
    assert game.state.player.name == "測試"
    backups = list((tmp_path / "backup").glob("測試-*.json"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "{}"
    assert any("已備份" in line for line in game.state.log)
