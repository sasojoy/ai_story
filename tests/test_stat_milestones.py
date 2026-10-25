"""屬性五段加點（減法季整合設計 4.5；主機側實作計畫 Task 2-5）的純規則：到第 10、20、30、40、50 級各給 5 點、每點的效果加倍、
假人照名號挑一條路配滿一項再配下一項。

批 0 的 `Config.jianfa` 還沒到：數字吃 `tianxia/jianfa_numbers.py` 的 `JianfaNumbers`，這裡直接建它。引擎接線（`team.points_between`
開著時走里程碑、`main.milestone`、每點效果讀 `stat_rates`、`bot.allocate_points` 照路配、`event_bump` 打折）在批 0 之後。"""
import pytest
from pydantic import ValidationError

from conftest import real_content
from tianxia import growth, team
from tianxia.jianfa_numbers import JianfaNumbers

CFG = JianfaNumbers()


# ── 五段加點 ──────────────────────────────────────────────────


def test_no_points_before_level_10():
    assert growth.milestone_points(CFG, 1, 9) == 0
    assert [growth.milestone_points(CFG, lv, lv + 1) for lv in range(1, 9)] == [0] * 8


def test_five_points_at_each_milestone_and_25_by_level_50():
    assert growth.milestone_points(CFG, 1, 10) == 5
    assert growth.milestone_points(CFG, 9, 10) == 5
    assert growth.milestone_points(CFG, 10, 19) == 0
    assert growth.milestone_points(CFG, 1, 50) == 25
    assert sum(growth.milestone_points(CFG, lv, lv + 1) for lv in range(1, 50)) == 25


def test_jumping_past_two_milestones_at_once_gives_both():
    assert growth.reached(CFG, 9, 21) == [10, 20]
    assert growth.milestone_points(CFG, 9, 21) == 10
    assert growth.reached(CFG, 20, 20) == []


def test_the_last_milestone_is_past_the_battle_only_cap():
    """第 50 級那一次要靠打出來的經驗（設計 4.5、4.2）：最後一段在 45 級之後，事件的經驗到不了。"""
    assert max(CFG.milestone_levels) == 50 > CFG.drill_level_cap
    assert growth.capped_exp(CFG, 49, 10_000, growth.OTHER, room=0) == (0, 10_000)


def test_milestones_must_climb():
    with pytest.raises(ValidationError):
        JianfaNumbers(milestone_levels=[10, 30, 20])
    with pytest.raises(ValidationError):
        JianfaNumbers(milestone_levels=[10, 10, 20])
    with pytest.raises(ValidationError):
        JianfaNumbers(milestone_levels=[0, 10])
    assert growth.milestone_points(JianfaNumbers(milestone_levels=[5, 15], stat_points_per_milestone=3), 1, 20) == 6


# ── 每點加倍 ──────────────────────────────────────────────────


def test_each_point_is_worth_twice_what_it_is_now():
    """設計 4.5：stat_bonus_per_point 3%→6%、dodge_per_point 2%→4%、sense_rate_per_wis 3→6、holding_per_lore_point 2→4。"""
    now = real_content("season21").config
    rates = CFG.stat_rates
    assert (rates.bonus_per_point, rates.dodge_per_point, rates.sense_rate_per_wis, rates.holding_per_lore_point) == (
        pytest.approx(2 * now.stat_bonus_per_point), pytest.approx(2 * now.dodge_per_point),
        2 * now.sense_rate_per_wis, 2 * now.holding_per_lore_point,
    )
    assert (rates.bonus_per_point, rates.dodge_per_point, rates.sense_rate_per_wis, rates.holding_per_lore_point) == (0.06, 0.04, 6, 4)


def test_stat_rates_reject_unknown_keys():
    with pytest.raises(ValidationError):
        JianfaNumbers(stat_rates={"bonus_per_point": 0.06, "parry_per_point": 0.1})
    assert JianfaNumbers(stat_rates={"bonus_per_point": 0.05}).stat_rates.dodge_per_point == 0.04


def test_the_rise_bump_on_events_is_halved_by_default():
    assert CFG.event_bump_scale == 0.0  # 量過（主機側計畫 Task 2-6）：減法季事件不再加難
    with pytest.raises(ValidationError):
        JianfaNumbers(event_bump_scale=-0.1)


# ── 假人照路配點 ───────────────────────────────────────────────


def test_a_path_orders_all_five_stats_and_depends_only_on_the_name():
    assert growth.STATS == team.COMBAT_STATS
    path = growth.stat_path("沈浪")
    assert sorted(path) == sorted(team.COMBAT_STATS)
    assert growth.stat_path("沈浪") == path
    firsts = {growth.stat_path(f"俠客{i}")[0] for i in range(60)}
    assert firsts == set(team.COMBAT_STATS)  # 五條路（力、巧、韌、悟、博）都有人走


def test_points_fill_the_first_stat_to_the_cap_before_the_second():
    path = ("str", "agi", "con", "wis", "lore")
    fresh = dict.fromkeys(path, 5)
    assert growth.plan_points(fresh, 5, 15, path) == ["str"] * 5
    assert growth.plan_points(fresh, 25, 15, path) == ["str"] * 10 + ["agi"] * 10 + ["con"] * 5
    assert growth.plan_points({**fresh, "str": 14}, 3, 15, path) == ["str", "agi", "agi"]


def test_points_stop_when_every_stat_is_full():
    path = ("str", "agi", "con", "wis", "lore")
    full = dict.fromkeys(path, 15)
    assert growth.plan_points(full, 5, 15, path) == []
    assert growth.plan_points({**full, "lore": 13}, 5, 15, path) == ["lore", "lore"]
    assert growth.plan_points({}, 20, 15, path) == ["str"] * 15 + ["agi"] * 5  # 沒寫的屬性當 0（同 bot.allocate_points）
    assert growth.plan_points(dict.fromkeys(path, 5), 0, 15, path) == []


def test_a_named_bot_fills_its_own_first_stat():
    name = "沈浪"
    path = growth.stat_path(name)
    got = growth.plan_points(dict.fromkeys(team.COMBAT_STATS, 5), 10, 15, path)
    assert got == [path[0]] * 10
