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
