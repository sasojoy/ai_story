import pytest

from tianxia.models import Check, Condition, Effect
from tianxia.rules import (
    add_world_flags, apply_effect, check_chance, check_condition, check_who, current_day, learn_skill,
)
from tianxia.team import check_actor


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


def test_check_chance_scales_and_clamps(state, content):
    assert check_chance(Check(stat="str", difficulty=5, by="self"), state, content) == 0.5
    assert check_chance(Check(stat="str", difficulty=7, by="self"), state, content) == pytest.approx(0.3)
    assert check_chance(Check(stat="str", difficulty=50, by="self"), state, content) == 0.05
    assert check_chance(Check(stat="str", difficulty=-50, by="self"), state, content) == 0.95


def test_team_check_sends_the_member_with_the_highest_stat(state, content):
    check = Check(stat="str", difficulty=5)  # 本人臂力 5、韓鐵 6
    assert check_actor(state, content, check) == "mate"
    assert check_chance(check, state, content) == pytest.approx(0.6)  # 用出手者的屬性算
    assert check_who(check, state, content) == "韓鐵出手"


def test_team_check_tie_goes_to_the_player_first(state, content):
    check = Check(stat="agi", difficulty=5)  # 身法同為 5
    assert check_actor(state, content, check) == "player"
    assert check_who(check, state, content) == "本人出手"
    state.player.team = ["mate", "player"]  # 就算本人不排第一，同分時也是本人先
    assert check_actor(state, content, check) == "player"


def test_team_check_counts_level_growth(state, content):
    check = Check(stat="agi", difficulty=5)
    state.player.members["mate"].level = 2  # 韓鐵身法 5 + 0.2
    assert check_actor(state, content, check) == "mate"
    assert check_chance(check, state, content) == pytest.approx(0.52)


def test_self_check_is_always_the_player(state, content):
    check = Check(stat="con", difficulty=5, by="self")  # 韓鐵根骨 6 比本人高，也輪不到他
    assert check_actor(state, content, check) == "player"
    assert check_chance(check, state, content) == 0.5
    assert check_who(check, state, content) == "本人"


def test_check_on_a_player_only_stat_is_made_by_the_player(state, content):
    state.player.stats["fame"] = 3
    check = Check(stat="fame", difficulty=2)
    assert check_actor(state, content, check) == "player"
    assert check_chance(check, state, content) == pytest.approx(0.6)


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


def test_rumor_is_recorded_where_the_player_stands(state, content):
    state.player.location = "lake"
    apply_effect(Effect(rumor="{name}撿到了殘卷！", chronicle="{name}發現殘卷。"), state, content)
    assert state.world.rumors[-1].location == "lake"
    assert state.world.chronicle[-1].location is None  # 江湖史不記地點
