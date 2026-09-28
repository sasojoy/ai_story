from tianxia.engine import Game
from tianxia.save import load_game, save_game
from tianxia.state import BattleState, SkillProgress


def test_roundtrip(tmp_path, game):
    game.choose("act:socialize")
    game.choose("choice:0")
    game.state.world.flags.add("blocked")
    path = tmp_path / "saves" / "沈浪.json"
    save_game(game.state, path)
    assert load_game(path) == game.state


def test_stale_references_are_dropped(content, game):
    s = game.state
    s.pending_event = "removed_event"
    s.player.location = "removed_place"
    s.player.skills["removed_skill"] = SkillProgress()
    s.player.equipped[1] = "removed_skill"
    fresh = Game(content, s)
    assert fresh.state.pending_event is None
    assert fresh.state.player.location == "town"
    assert fresh.state.player.equipped[1] is None
    assert "removed_skill" not in fresh.state.player.skills


def test_stale_battle_choice_index_is_dropped(content, game):
    s = game.state
    s.battle = BattleState(
        enemy_id="boss", event_id="duel", choice_index=99,
        player_hp=100, player_hp_max=100, enemy_hp=100,
    )
    fresh = Game(content, s)
    assert fresh.state.battle is None
