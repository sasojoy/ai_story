"""faction 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import pytest
from conftest import walk_to
from engine_kit import _install_factions, ids  # noqa: F401

pytestmark = pytest.mark.whole_content


def test_a_free_agent_can_join_a_faction_where_it_recruits(content, game):
    _install_factions(content)
    assert "faction:guan" in ids(game)
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan"
    assert "faction:guan" not in ids(game)


def test_the_join_option_only_shows_at_the_factions_own_places(content, game):
    _install_factions(content)
    walk_to(game, "lake")
    assert not any(i.startswith("faction:") for i in ids(game))


def test_status_text_shows_the_faction_of_a_player_without_a_sect(content, game):
    _install_factions(content)
    assert "散人" in game.status_text()
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert "官軍" in game.status_text() and "散人" not in game.status_text()


def test_joining_a_faction_asks_for_confirmation_and_shows_the_headcount(content, game):
    """伺服器假人設計第八節第 3 項：投靠要確認一次，確認畫面寫明不能改投與三方目前各有幾人。"""
    _install_factions(content)
    game.world.record_faction("別人", "huang")
    game.choose("faction:guan")
    assert game.state.player.faction is None
    assert ids(game) == ["faction:confirm", "faction:cancel"]
    scene = game.scene_text()
    assert "這一季不能改投" in scene
    assert "目前官軍 0 人、黃巾 1 人、地方豪強 0 人" in scene
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan"
    assert game.world.faction_counts() == {"guan": 1, "huang": 1}


def test_the_join_question_is_on_the_scene_only(content, game):
    """FB-046：「投靠後這一季不能改投……確定投靠官軍？」場景上寫著，江湖紀錄那一則（「剛剛」）不再寫一次。"""
    _install_factions(content)
    game.choose("faction:guan")
    entry = game.state.journal[0]
    assert entry.title == "考慮投靠官軍"
    assert "這一季不能改投" in game.scene_text()
    assert "這一季不能改投" not in game.latest_entry_html()
    assert not any("不能改投" in line for line in [entry.tag, *entry.lines])


def test_thinking_again_leaves_you_a_free_agent(content, game):
    _install_factions(content)
    game.choose("faction:guan")
    game.choose("faction:cancel")
    assert game.state.player.faction is None and game.state.player.pending_faction is None
    assert "faction:guan" in ids(game)
    assert game.world.faction_counts() == {}
