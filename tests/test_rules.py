import pytest

from tianxia.models import Check, Condition, Effect
from tianxia.rules import add_skill_exp, apply_effect, check_chance, check_condition, learn_skill


def test_new_state(state):
    assert state.player.location == "town"
    assert state.player.stamina == 150
    assert state.world.trends == {"kou": 30, "bao": 0}
    assert state.world.revealed == {"kou"}


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


def test_join_sect_learns_and_equips(state, content):
    msgs = apply_effect(Effect(join_sect="cloud"), state, content)
    assert state.player.sect == "cloud"
    assert "sword" in state.player.skills
    assert state.player.equipped[1] == "sword"
    assert any("流雲派" in m for m in msgs)


def test_leave_sect_sets_flag(state, content):
    state.player.sect = "cloud"
    apply_effect(Effect(leave_sect=True), state, content)
    assert state.player.sect is None
    assert "叛出:cloud" in state.player.flags


def test_learn_skill_fills_first_matching_empty_slot(state, content):
    learn_skill(state, content, "fist")
    learn_skill(state, content, "sword")
    assert state.player.equipped == [None, "fist", "sword", None]
    assert learn_skill(state, content, "fist") == []


def test_skill_exp_levels_up_and_caps(state, content):
    learn_skill(state, content, "fist")
    msgs = add_skill_exp(state, content, "fist", 250)
    prog = state.player.skills["fist"]
    assert (prog.level, prog.exp) == (3, 50)
    assert len(msgs) == 2
    add_skill_exp(state, content, "fist", 10_000)
    assert (prog.level, prog.exp) == (10, 0)
