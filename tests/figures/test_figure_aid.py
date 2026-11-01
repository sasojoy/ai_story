"""護著大勢人物（Joy 2026-10-17 第 6 條「大勢人物同陣營玩家能不能幫他回復，或是護衛他讓他不要太容易退場」）：
護衛（先過護衛那一關才打得到他本人）、犒軍（補聲威，跟自然回復共用一天的上限）、探望（退下養傷的人早一點回來）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import real_content
from tianxia import encounter, figure_aid, figures, team
from tianxia.calendar import DAY
from tianxia.characters import CharacterStore
from tianxia.encounter import EncounterResult
from tianxia.engine import Game


@pytest.fixture
def real():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.snub_hours = 0
    return c


def _player(content, store, name, faction, at="changshe") -> Game:
    game = Game.new(content, name, rng=random.Random(0), world=store)
    p = game.state.player
    p.faction, p.location = faction, at
    p.tutorial_step = len(content.tutorial.steps)
    p.visited.add(at)
    p.joined_at = -1e9
    p.stamina = 250
    p.stats["silver"] = 100
    game.now = 1000.0
    game._save_season()
    CharacterStore(store.db).save(game.state)
    return game


def _reload(store, content, name) -> Game:
    game = Game(content, CharacterStore(store.db).load(name), random.Random(0), store)
    game.state.world = store.get_season()
    return game


def _tier(tier):
    return EncounterResult(tier=tier, margin=50 if tier == "大勝" else -80, our_power=200, difficulty=120)


def _ids(game, enabled=True):
    return {o.id for o in game.options() if o.enabled or not enabled}


def test_guard_button_only_for_your_own_side(real, world):
    guan = _player(real, world, "官甲", "guan")
    assert "aid:guard:huangfusong" in _ids(guan) and "aid:rally:huangfusong" not in _ids(guan)  # 聲威滿的不必犒
    huang = _player(real, world, "黃甲", "huang")
    assert not any(i.startswith("aid:") for i in _ids(huang, enabled=False))


def test_guarding_costs_stamina_and_blocks_a_challenger(real, world):
    guan = _player(real, world, "官甲", "guan")
    msgs = guan.choose("aid:guard:huangfusong")
    assert guan.state.player.stamina == 250 - real.config.figure_aid.guard_stamina, msgs
    assert [p.name for p in figure_aid.posts(guan.state, real, "huangfusong")] == ["官甲"]
    world.mutate_season(lambda s: setattr(s, "figure_guards", guan.state.world.figure_guards))
    huang = _player(real, world, "黃甲", "huang")
    huang.state.world = world.get_season()
    assert any("身邊有 1 人護衛" in o.label for o in huang.options() if o.id == "act:challenge:huangfusong")
    start = figures.state_of(huang.state, real, "huangfusong").prestige
    with mock.patch.object(encounter, "resolve_encounter", return_value=_tier("落敗")), \
            mock.patch.object(team, "fight", side_effect=AssertionError("不該打到他本人")):
        msgs = huang.choose("act:challenge:huangfusong")
    assert any("官甲擋在皇甫嵩身前" in m for m in msgs)
    assert figures.state_of(huang.state, real, "huangfusong").prestige == start
    assert huang.state.player.figure_wins.get("huangfusong", 0) == 0
    # 護衛下次同步領名望與心得
    back = _reload(world, real, "官甲")
    fame, xinde = back.state.player.stats.get("fame", 0), back.state.player.stats.get("xinde", 0)
    back.sync(1100.0)
    assert back.state.player.stats.get("xinde", 0) == xinde + real.config.figure_aid.guard_xinde
    assert back.state.player.stats.get("fame", 0) > fame
    assert any(figure_aid.CREDIT_LINE.format(name="皇甫嵩", who="黃甲") in line for e in back.state.journal for line in e.lines)


def test_breaking_through_the_guard_then_fighting_him(real, world):
    guan = _player(real, world, "官甲", "guan")
    guan.choose("aid:guard:huangfusong")
    world.mutate_season(lambda s: setattr(s, "figure_guards", guan.state.world.figure_guards))
    huang = _player(real, world, "黃甲", "huang")
    huang.state.world = world.get_season()
    with mock.patch.object(encounter, "resolve_encounter", return_value=_tier("大勝")), \
            mock.patch.object(team, "fight", return_value=_tier("大勝")):
        msgs = huang.choose("act:challenge:huangfusong")
    assert any("擊退了擋在皇甫嵩身前的護衛官甲" in m for m in msgs)
    assert huang.state.player.figure_wins["huangfusong"] == 1
    assert figure_aid.posts(huang.state, real, "huangfusong") == []


@pytest.mark.smoke
def test_a_guard_post_ends_when_the_figure_moves_or_the_shift_is_over(real, world):
    guan = _player(real, world, "官甲", "guan")
    guan.choose("aid:guard:huangfusong")
    s = guan.state
    assert figure_aid.posts(s, real, "huangfusong")
    s.world.time += real.config.figure_aid.guard_hours * 3600
    assert figure_aid.posts(s, real, "huangfusong") == []
    figure_aid.guard(s, real, "huangfusong", 100.0)
    figures._ensure(s, real, "huangfusong").location = "wan_city"  # noqa: SLF001
    assert figure_aid.posts(s, real, "huangfusong") == []


def test_rally_restores_prestige_within_the_shared_daily_cap(real, world):
    guan = _player(real, world, "官甲", "guan")
    s, cfg = guan.state, real.config.figure_aid
    figures._ensure(s, real, "huangfusong").prestige = 40  # noqa: SLF001
    msgs = guan.choose("aid:rally:huangfusong")
    assert figures.state_of(s, real, "huangfusong").prestige == 40 + cfg.rally_points, msgs
    assert s.player.stats["silver"] == 100 - cfg.rally_silver
    guan.choose("aid:rally:huangfusong")
    assert "aid:rally:huangfusong" not in _ids(guan)  # 一個人一天兩次
    # 自然回復跟犒軍共用一天的上限
    figure_aid.restore(s, real, "huangfusong", 100)  # 補到一天的上限為止（不是補到開季值）
    assert figures.state_of(s, real, "huangfusong").prestige < real.figures["huangfusong"].start_prestige
    assert figure_aid.left_today(s, real, "huangfusong") == 0
    assert figure_aid.restore(s, real, "huangfusong", 5) == 0


def test_visit_brings_a_beaten_figure_back_sooner(real, world):
    guan = _player(real, world, "官甲", "guan")
    s = guan.state
    figures._ensure(s, real, "zhujun").prestige = 5  # noqa: SLF001
    figures.defeat(s, real, "zhujun", 5)
    back_at = s.world.figures["zhujun"].back_at
    assert back_at is not None
    assert "aid:visit:zhujun" in _ids(guan)  # 長社是官軍的大本營
    guan.choose("aid:visit:zhujun")
    assert s.world.figures["zhujun"].back_at < back_at
    assert "aid:visit:zhujun" not in _ids(guan)  # 一天一次
    s.world.time = s.world.figures["zhujun"].back_at
    figures.revive(s, real)
    assert "visitcut:zhujun" not in s.world.aid_tally


def test_switch_off_means_no_buttons_and_no_guard_check(real, world):
    real.config.figure_aid.enabled = False
    guan = _player(real, world, "官甲", "guan")
    assert not any(i.startswith("aid:") for i in _ids(guan, enabled=False))
