import pytest

from tianxia.models import Check, Condition, Effect
from tianxia.rules import (
    add_world_flags, apply_effect, check_chance, check_condition, current_day, learn_skill,
)


def test_new_state(state):
    assert state.player.location == "town"
    assert state.player.stamina == 150
    assert state.world.trends == {"kou": 30, "bao": 0}
    assert state.world.revealed == {"kou"}
    assert state.player.team == ["player", "mate"]


def test_empty_condition_passes(state):
    assert check_condition(Condition(), state)


def test_condition_stats_and_flags(state):
    state.player.flags.add("token")
    assert check_condition(Condition(min_stats={"str": 5}, flags_all=["token"]), state)
    assert not check_condition(Condition(min_stats={"str": 6}), state)
    assert not check_condition(Condition(flags_none=["token"]), state)


def test_condition_sect_and_skills(state):
    assert check_condition(Condition(no_sect=True), state)
    assert not check_condition(Condition(sects=["cloud"]), state)
    state.player.sect = "cloud"
    assert check_condition(Condition(sects=["cloud"]), state)
    assert not check_condition(Condition(no_sect=True), state)
    assert check_condition(Condition(skills_none=["fist"]), state)


def test_condition_world(state):
    assert check_condition(Condition(trend_min={"kou": 30}, trend_max={"kou": 30}), state)
    assert not check_condition(Condition(trend_min={"kou": 31}), state)
    state.world.flags.add("blocked")
    assert check_condition(Condition(world_flags_all=["blocked"]), state)
    assert not check_condition(Condition(world_flags_none=["blocked"]), state)


def test_check_chance_scales_and_clamps(state):
    assert check_chance(Check(stat="str", difficulty=5), state) == 0.5
    assert check_chance(Check(stat="str", difficulty=7), state) == pytest.approx(0.3)
    assert check_chance(Check(stat="str", difficulty=50), state) == 0.05
    assert check_chance(Check(stat="str", difficulty=-50), state) == 0.95


def test_apply_stats_clamps_at_zero(state, content):
    msgs = apply_effect(Effect(text="你撿到錢。", stats={"silver": 10, "evil": -3}), state, content)
    assert state.player.stats["silver"] == 60
    assert state.player.stats["evil"] == 0
    assert msgs[0] == "你撿到錢。"
    assert "銀兩 +10" in msgs


def test_apply_stamina_clamps(state, content):
    apply_effect(Effect(stamina=50), state, content)
    assert state.player.stamina == 150
    apply_effect(Effect(stamina=-500), state, content)
    assert state.player.stamina == 0


def test_hidden_trend_revealed_by_positive_push(state, content):
    msgs = apply_effect(Effect(trend={"bao": 20}), state, content)
    assert "bao" in state.world.revealed
    assert state.world.trends["bao"] == 20
    assert any("寶藏" in m for m in msgs)


def test_hidden_trend_ignores_negative_push(state, content):
    apply_effect(Effect(trend={"bao": -5}), state, content)
    assert "bao" not in state.world.revealed
    assert state.world.trends["bao"] == 0


def test_trend_clamped(state, content):
    apply_effect(Effect(trend={"kou": 500}), state, content)
    assert state.world.trends["kou"] == 100
    apply_effect(Effect(trend={"kou": -500}), state, content)
    assert state.world.trends["kou"] == 0


def test_rumor_respects_anonymity(state, content):
    apply_effect(Effect(rumor="{name}撿到了殘卷！", chronicle="{name}發現殘卷。"), state, content)
    state.player.anonymous = True
    apply_effect(Effect(rumor="{name}又出手了！"), state, content)
    assert [r.text for r in state.world.rumors] == ["沈浪撿到了殘卷！", "某位少俠又出手了！"]
    assert state.world.chronicle[0].text == "沈浪發現殘卷。"


def test_join_sect_learns_starter_skills(state, content):
    msgs = apply_effect(Effect(join_sect="cloud"), state, content)
    assert state.player.sect == "cloud"
    assert state.player.skills["sword"] == 1
    assert any("流雲派" in m for m in msgs)


def test_leave_sect_sets_flag(state, content):
    state.player.sect = "cloud"
    apply_effect(Effect(leave_sect=True), state, content)
    assert state.player.sect is None
    assert "叛出:cloud" in state.player.flags


def test_learn_skill_starts_at_first_level(state, content):
    msgs = learn_skill(state, content, "fist")
    assert state.player.skills["fist"] == 1
    assert "長拳" in msgs[0]
    assert learn_skill(state, content, "fist") == []


def test_current_day(state):
    assert current_day(state) == 1
    state.world.time = 86400 * 2 + 5
    assert current_day(state) == 3


def test_condition_day_range(state):
    state.world.time = 86400 * 4  # 第 5 天
    assert check_condition(Condition(day_min=5), state)
    assert not check_condition(Condition(day_min=6), state)
    assert not check_condition(Condition(day_max=4), state)


def test_condition_revealed(state):
    assert check_condition(Condition(revealed_all=["kou"], revealed_none=["bao"]), state)
    state.world.revealed.add("bao")
    assert not check_condition(Condition(revealed_none=["bao"]), state)


def test_condition_any_of(state):
    assert check_condition(Condition(any_of=[Condition(min_stats={"str": 99}), Condition(day_min=1)]), state)
    assert not check_condition(Condition(any_of=[Condition(min_stats={"str": 99})]), state)


def test_world_flag_age(state):
    add_world_flags(state, ["cave_open"])
    cond = Condition(flag_age_hours={"cave_open": 2})
    assert not check_condition(cond, state)
    state.world.time = 7200
    assert check_condition(cond, state)
    add_world_flags(state, ["cave_open"])  # 已存在：不重設時間
    assert state.world.flag_times["cave_open"] == 0


def test_effect_world_flags_record_time(state, content):
    state.world.time = 3600
    apply_effect(Effect(world_flags_add=["x"]), state, content)
    assert "x" in state.world.flags
    assert state.world.flag_times["x"] == 3600
