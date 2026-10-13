"""挑戰大勢人物每季都有（docs/superpowers/specs/2026-10-11-挑戰大勢人物每季都有-design.md）。正式內容、預設設定（14 天、第一季規則關著）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import real_content
from tianxia import figures, team
from tianxia.content import ContentError, validate
from tianxia.encounter import EncounterResult
from tianxia.engine import Game


@pytest.fixture
def real():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _player(content, store, name, faction, at, *, now=1000.0) -> Game:
    game = Game.new(content, name, rng=random.Random(0), world=store)
    p = game.state.player
    p.faction, p.location = faction, at
    p.tutorial_step = len(content.tutorial.steps)
    p.visited.add(at)
    game.now = now
    return game


def _ids(game):
    return [o.id for o in game.options()]


def _won(tier="大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=120))


def test_challenge_on_needs_figures_factions_and_the_switch(real, world):
    w = world.get_season()
    assert figures.challenge_on(real, w) and figures.untimed(real, w)
    real.config.figure_challenge_every_season = False
    assert not figures.challenge_on(real, w)
    real.config.season_one = True  # 第一季一定開（打擊軍令靠它交差），就算開關關著
    w.season_one = True
    assert figures.challenge_on(real, w) and not figures.untimed(real, w)


def test_a_fourteen_day_season_draws_the_challenge_buttons(real, world):
    cost = real.config.action_cost["train"]
    guan = _player(real, world, "官甲", "guan", "huangjin_camp")
    bocai = next(o for o in guan.options() if o.id == "act:challenge:bocai")
    assert bocai.enabled and bocai.label.startswith(f"挑戰波才（體力 {cost}・")
    assert figures.difficulty(guan.state, real, "bocai") == 120
    for name, faction, at in (("黃乙", "huang", "huangjin_camp"), ("散丙", None, "huangjin_camp"), ("官丁", "guan", "changshe")):
        assert not any(i.startswith("act:challenge:") for i in _ids(_player(real, world, name, faction, at))), name
    assert {"act:challenge:huangfusong", "act:challenge:zhujun"} <= set(_ids(_player(real, world, "豪戊", "haoqiang", "changshe")))
    assert "act:challenge:dongzhuo" not in _ids(_player(real, world, "黃己", "huang", "mengjin_ford"))  # 戰線空著：沒有時刻表的季不畫
    assert "act:challenge:zhaohong" not in _ids(_player(real, world, "官庚", "guan", "nanyang_huangjin_camp"))
    assert "act:challenge:hejin" in _ids(_player(real, world, "黃辛", "huang", "dajiangjun_fu"))  # challenge_off_front


def test_a_fourteen_day_win_takes_five_prestige_snubs_and_records_no_contribution(real, world):
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    before = game.state.player.affinities.get("bocai", 0) + 10
    game.state.player.affinities["bocai"] = before
    with _won():
        game.choose("act:challenge:bocai")
    s = game.state
    assert figures.state_of(s, real, "bocai").prestige == 55
    assert s.player.affinities["bocai"] == before - real.config.figure_defeat_affinity
    assert s.player.figure_wins == {"bocai": 1} and not s.player.contrib
    assert set(world.get_season().figures) == {"bocai"}  # 第一次打贏才寫進存檔，其他人照人物表讀
    snubbed = next(o for o in game.options() if o.id == "act:challenge:bocai")
    assert not snubbed.enabled
    game.now += real.config.snub_hours * 3600
    assert next(o for o in game.options() if o.id == "act:challenge:bocai").enabled


def test_people_stand_at_their_talk_at_until_someone_retires(real, world):
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    placed = figures.placed_characters(game.state, real)
    for fid, fig in real.figures.items():
        if fig.character is not None and fig.start_status == "active":
            assert placed[fig.character] == real.characters[fig.character].talk_at, fid
    real.config.figure_challenge_every_season = False
    assert figures.placed_characters(game.state, real) == {}


def test_a_retired_figure_leaves_the_audience_list(real, world):
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    figures.defeat(game.state, real, "bocai", 60)
    assert figures.is_out(game.state, "bocai") and "bocai" not in game._figures_here()
    assert figures.state_of(game.state, real, "pengtuo").status == "active"  # 彭脫接手


def test_a_running_fourteen_day_season_gets_the_buttons_at_once(real, world):
    """上線那一刻（設計第六節情形一）：14 天的季已經走到第 8 週、存檔裡沒有人物，一同步就看得到挑戰鈕，人物照開季值。"""
    from tianxia import calendar
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    world.mutate_season(lambda s: setattr(s, "time", calendar.week_start(8, real, s)))
    game.sync(game.now)
    assert world.get_season().figures == {}
    assert next(o for o in game.options() if o.id == "act:challenge:bocai").enabled
    assert figures.state_of(game.state, real, "bocai").prestige == real.figures["bocai"].start_prestige


def test_figures_on_stage_must_start_where_they_are_met(real):
    real.figures["bocai"] = real.figures["bocai"].model_copy(update={"location": "changshe"})
    with pytest.raises(ContentError, match="talk_at"):
        validate(real)
