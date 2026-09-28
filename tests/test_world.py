import random

from tianxia.world import check_thresholds, end_season, evaluate_ending, sim_tick


def test_threshold_fires_once_and_sets_flag(state, content):
    state.world.trends["kou"] = 50
    msgs = check_thresholds(state, content)
    assert "blocked" in state.world.flags
    assert msgs == ["【江湖大事】水寇封江！"]
    assert state.world.rumors[-1].text == "水寇封江！"
    assert state.world.chronicle[-1].text == "水寇封江！"
    assert check_thresholds(state, content) == []


def test_ending_threshold_ends_season(state, content):
    state.world.trends["kou"] = 80
    msgs = check_thresholds(state, content)
    assert state.world.ended
    assert state.world.ending_title == "水寇稱霸"
    assert any("賽季落幕" in m for m in msgs)


def test_evaluate_ending_falls_back(state, content):
    assert evaluate_ending(state, content).id == "default"


def test_end_season_is_idempotent(state, content):
    assert end_season(state, content)
    assert end_season(state, content) == []


def test_sim_players_push_trends_and_spread_rumors(state, content):
    msgs = sim_tick(state, content, 3, random.Random(0))
    assert state.world.trends["kou"] == 33
    assert msgs.count("【江湖傳聞】翻江龍又劫了一艘船。") == 3
    assert state.world.trends["bao"] == 0  # 鬼手要等寶藏線浮現


def test_sim_player_waits_for_revealed_trend(state, content):
    state.world.revealed.add("bao")
    sim_tick(state, content, 2, random.Random(0))
    assert state.world.trends["bao"] == 2


def test_sim_player_respects_condition(state, content):
    content.scenario.sim_players[0].condition.world_flags_none.append("blocked")
    state.world.flags.add("blocked")
    sim_tick(state, content, 3, random.Random(0))
    assert state.world.trends["kou"] == 30


def test_threshold_records_flag_time(state, content):
    state.world.time = 5000
    state.world.trends["kou"] = 50
    check_thresholds(state, content)
    assert state.world.flag_times["blocked"] == 5000
