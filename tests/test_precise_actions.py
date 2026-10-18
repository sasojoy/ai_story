"""正式季整合第 3 批：一類一顆（設計第二章；12.3 第 5～13 條照 PM 提案）。每一顆鈕只給一類東西、按了一定拿到那一類。
開關 Config.precise_actions 照開季蓋章；測試內容關著，這裡用正式內容（週末設定）。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia import precise
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.world_state import fresh_season, stamp_season

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR


def _game(profile="weekend", at="yingchuan", faction=None, stamina=250.0, opened=True):
    c = real_content(profile)
    c.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(c)
    if opened:
        store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, stamina
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


# ── Task 1：開關與蓋章 ──


def test_a_stamped_season_turns_precise_on():
    c = real_content("weekend")
    season = fresh_season(c)
    stamp_season(season, c)
    assert season.precise_actions and precise.on(c, season)


def test_unstamped_season_keeps_the_old_rules():
    c = real_content("weekend")
    season = fresh_season(c)
    stamp_season(season, c)
    season.precise_actions = False  # 設定打開之前就開的季
    assert not precise.on(c, season)


# ── Task 2：找素材一定給、不打仗（2.4）；應召不再換掉（2.10）──


def _press(game, oid):
    game.state.player.stamina = 250.0
    return game.choose(oid)


def test_gathering_always_gives_materials_and_never_fights():
    for at in ("yingchuan", "changshe"):  # 城鎮、城外
        game = _game(at=at)
        for _ in range(40):
            before = sum(game.state.player.materials.values())
            battles = len(game.state.battles)
            _press(game, "explore:gather")
            assert sum(game.state.player.materials.values()) > before, at
            assert len(game.state.battles) == battles and game.state.pending_event is None, at


def test_gathering_at_a_summons_place_still_gathers(monkeypatch):
    from tianxia import ranks

    game = _game(at="changshe")
    monkeypatch.setattr(ranks, "summons_event", lambda *a, **k: next(iter(game.content.events)))
    before = sum(game.state.player.materials.values())
    _press(game, "explore:gather")
    assert sum(game.state.player.materials.values()) > before and game.state.pending_event is None


def test_unstamped_season_still_fights_while_gathering():
    from tianxia import explore_modes

    game = _game(at="changshe")
    game.state.world.precise_actions = False
    game.content.config.explore_modes.encounter_chance = 1.0
    _press(game, "explore:gather")
    assert game.state.battles  # 舊規則：城外撞上一場
    assert explore_modes.on(game.content)


def test_fixture_and_switched_off_content_are_off(content):
    season = fresh_season(content)
    stamp_season(season, content)
    assert not precise.on(content, season)
    c = real_content("weekend")
    c.config.precise_actions = False
    season = fresh_season(c)
    stamp_season(season, c)
    assert not precise.on(c, season)
