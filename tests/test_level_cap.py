"""等級上限 50、30 級以後加陡（企劃者 2026-10-14「50 級加陡」）：升到第 30 級之前一個字都不變；之後每一級要的經驗越來越多，
屬性點與同伴的每級成長改成兩級一點；卡在 30 級的舊角色接著升。"""
from __future__ import annotations

import pytest
from conftest import real_content

from tianxia import team


def test_levels_up_to_thirty_cost_what_they_always_did(content):
    cfg = content.config
    assert [team.level_cost(cfg, n) for n in (1, 10, 29)] == [cfg.level_exp, cfg.level_exp * 10, cfg.level_exp * 29]


def test_past_thirty_each_level_costs_more_and_more(content):
    cfg = content.config
    cfg.level_exp, cfg.late_level_from, cfg.late_exp_step = 10, 30, 0.5
    assert team.level_cost(cfg, 30) == 450  # 300 ×（1＋0.5）
    assert team.level_cost(cfg, 49) == 5390  # 490 ×（1＋0.5 × 20）
    costs = [team.level_cost(cfg, n) for n in range(30, 50)]
    steps = [b - a for a, b in zip(costs, costs[1:])]
    assert all(later > earlier for earlier, later in zip(steps, steps[1:]))  # 越後面越陡


def test_the_real_content_goes_to_fifty_and_the_weekend_is_gentler():
    plain, weekend = real_content().config, real_content("weekend").config
    assert plain.max_level == weekend.max_level == 50
    assert weekend.late_exp_step < plain.late_exp_step  # 2.5 天的季要讓最拚的人碰得到 50 級


def test_stat_points_come_every_two_levels_past_thirty(content):
    cfg = content.config
    assert team.points_between(cfg, 1, 30) == 29
    assert team.points_between(cfg, 30, 31) == 0
    assert team.points_between(cfg, 30, 32) == 1
    assert team.points_between(cfg, 31, 32) == 1
    assert team.points_between(cfg, 1, 50) == 39


def test_an_old_character_stuck_at_thirty_keeps_levelling(state, content, world):
    cfg = content.config
    state.player.member.level, state.player.member.exp = 30, 0
    state.player.stat_points = 0
    msgs = team.add_team_exp(state, content, world, team.level_cost(cfg, 30))
    assert state.player.member.level == 31 and state.player.stat_points == 0
    assert not any("屬性" in m for m in msgs)  # 這一級沒有點：不寫「你有 0 點」
    msgs = team.add_team_exp(state, content, world, team.level_cost(cfg, 31))
    assert state.player.member.level == 32 and state.player.stat_points == 1
    assert any("1 點屬性可以分配" in m for m in msgs)


def test_nobody_passes_fifty(state, content, world):
    state.player.member.level = 49
    team.add_team_exp(state, content, world, 10 ** 9)
    assert state.player.member.level == 50
    assert team.exp_view(content, state.player.member) is None


def test_a_companion_grows_half_as_fast_past_thirty(state, content, world):
    mate = content.characters["mate"]
    world.update_companion("mate", lambda progress: setattr(progress, "level", 34))
    assert team.member_stats(state, content, world, "mate")["str"] == pytest.approx(
        mate.stats["str"] + mate.growth["str"] * (29 + 2))


def test_the_status_bar_says_how_far_the_next_level_is(game):
    p = game.state.player
    p.member.level, p.member.exp = 31, 120
    assert game.status_data()["exp"] == {"have": 120, "need": team.level_cost(game.content.config, 31)}
    p.member.level = game.content.config.max_level
    assert game.status_data()["exp"] is None
