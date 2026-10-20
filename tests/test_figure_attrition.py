"""大勢人物別被二十個人一季打光（PM 2026-10-16，二十人試玩週末第一季官軍六位只剩董卓）：
同一個人同一位人物一天只有第一場打贏扣聲威；被挑戰打退的人物過 figure_return_days 個季曆天以一半聲威回來。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import real_content
from tianxia import calendar, figures, team
from tianxia.calendar import DAY
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import FigureChange
from tianxia.state import GameState, PlayerState
from tianxia.world import advance_world_state
from tianxia.world_state import fresh_season


@pytest.fixture
def real():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.snub_hours = 0
    return c


def _player(content, store, name, faction="guan", at="huangjin_camp") -> Game:
    game = Game.new(content, name, rng=random.Random(0), world=store)
    p = game.state.player
    p.faction, p.location = faction, at
    p.tutorial_step = len(content.tutorial.steps)
    p.visited.add(at)
    game.now = 1000.0
    return game


def _won():
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=120))


def _season(content) -> GameState:
    player = PlayerState(name="", location=content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=fresh_season(content))


def _prestige(game, fid="bocai") -> int:
    return figures.state_of(game.state, game.content, fid).prestige


def test_only_the_first_win_of_the_day_dents_his_prestige(real, world):
    game = _player(real, world, "官甲")
    with _won():
        game.choose("act:challenge:bocai")
        assert _prestige(game) == 55
        game.choose("act:challenge:bocai")
    assert _prestige(game) == 55  # 第二場照拿獎勵，聲威不動
    assert game.state.player.figure_wins["bocai"] == 2
    assert any(figures.DENT_ONCE_LINE.format(name="波才") in line for e in game.state.journal for line in e.lines)
    game.state.world.time += DAY  # 隔一個遊戲日又扣得到
    with _won():
        game.choose("act:challenge:bocai")
    assert _prestige(game) == 50


def test_someone_else_the_same_day_still_dents_him(real, world):
    game = _player(real, world, "官甲")
    game.state.player.figure_dented["bocai"] = int(game.state.world.time // DAY)  # 官甲今天扣過了
    other = _player(real, world, "官乙")
    with _won():
        other.choose("act:challenge:bocai")
    assert _prestige(other) == 55


def test_the_switch_off_dents_every_win(real, world):
    real.config.figure_dent_once_per_day = False
    game = _player(real, world, "官甲")
    with _won():
        game.choose("act:challenge:bocai")
        game.choose("act:challenge:bocai")
    assert _prestige(game) == 50


def test_a_figure_beaten_out_comes_back_at_half_and_takes_his_front_back():
    on = real_content()
    on.config.season_one = True
    s = _season(on)
    s.world.figures["bocai"].prestige = 5
    figures.defeat(s, on, "bocai", 5)
    bocai, pengtuo = s.world.figures["bocai"], s.world.figures["pengtuo"]
    assert bocai.status == "retired" and pengtuo.front == "yingru"
    wait = on.config.figure_return_days * 24 * calendar.cal_hour_seconds(on, s.world)
    assert bocai.back_at == pytest.approx(s.world.time + wait) and bocai.back_front == "yingru"
    s.world.time += wait - 1
    assert figures.revive(s, on) == [] and figures.is_out(s, "bocai")
    s.world.time += 1
    lines = figures.revive(s, on)
    assert lines == [figures.BACK_LINE.format(name="波才", where="，回到中原")]
    assert bocai.status == "active" and bocai.prestige == 30 and bocai.front == "yingru" and bocai.back_at is None
    assert pengtuo.status == "active" and pengtuo.front is None  # 接位的人把戰線交還
    assert figures.commander(s, on, "yingru", "huang") == "bocai" and figures.can_challenge(s, on, "bocai")
    assert s.world.rumors[-1].text == lines[0]


def test_a_destiny_figure_comes_back_too():
    on = real_content()
    on.config.season_one = True
    s = _season(on)
    s.world.figures["sunjian"].prestige = 1
    figures.defeat(s, on, "sunjian", 5)
    assert s.world.figures["sunjian"].status == "crippled"
    s.world.time = s.world.figures["sunjian"].back_at
    figures.revive(s, on)
    start = on.figures["sunjian"].start_prestige
    assert s.world.figures["sunjian"].status == "active" and s.world.figures["sunjian"].prestige == int(start / 2 + 0.5)


def test_the_timetable_writing_him_out_keeps_him_out():
    on = real_content()
    on.config.season_one = True
    s = _season(on)
    s.world.figures["bocai"].prestige = 5
    figures.defeat(s, on, "bocai", 5)
    figures.apply(s, on, "bocai", FigureChange(fate="退場"))
    assert s.world.figures["bocai"].back_at is None
    s.world.time += 100 * DAY
    assert figures.revive(s, on) == [] and figures.is_out(s, "bocai")


def test_the_timetable_writing_him_out_from_the_start_never_comes_back():
    on = real_content()
    on.config.season_one = True
    s = _season(on)
    figures.apply(s, on, "bocai", FigureChange(fate="退場"))
    assert s.world.figures["bocai"].back_at is None


def test_return_days_zero_is_the_old_rule():
    on = real_content()
    on.config.season_one = True
    on.config.figure_return_days = 0
    s = _season(on)
    s.world.figures["bocai"].prestige = 5
    assert figures.defeat(s, on, "bocai", 5)[1] == "波才連吃敗仗，聲威掃地，再也號令不動手下的兵。"
    assert s.world.figures["bocai"].back_at is None


@pytest.mark.parametrize("season_one", [True, False])
def test_the_world_clock_brings_him_back_in_both_kinds_of_season(season_one):
    c = real_content()
    c.config.season_one = season_one
    s = _season(c)
    if not season_one:
        figures._ensure(s, c, "bocai")
    s.world.figures["bocai"].prestige = 5
    figures.defeat(s, c, "bocai", 5)
    assert figures.is_out(s, "bocai")
    days = c.config.figure_return_days + 0.1
    advance_world_state(s.world, c, days * 24 * calendar.cal_hour_seconds(c, s.world), random.Random(0))
    assert not figures.is_out(s, "bocai")
