from tianxia.engine import Game
from tianxia.save import load_game, save_game


def test_roundtrip(tmp_path, game):
    game.choose("act:socialize")
    game.choose("choice:0")
    game.state.world.flags.add("blocked")
    game.state.player.members["mate"].neili = 12.5
    path = tmp_path / "saves" / "沈浪.json"
    save_game(game.state, path)
    assert load_game(path) == game.state


def test_stale_references_are_dropped(content, game):
    s = game.state
    s.pending_event = "removed_event"
    s.player.location = "removed_place"
    s.player.skills["removed_skill"] = 3
    s.player.loadouts["player"][1] = "removed_skill"
    s.player.team.append("ghost")
    fresh = Game(content, s)
    assert fresh.state.pending_event is None
    assert fresh.state.player.location == "town"
    assert fresh.state.player.loadouts["player"][1] is None
    assert "removed_skill" not in fresh.state.player.skills
    assert fresh.state.player.team == ["player", "mate"]
