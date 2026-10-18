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


def test_fixture_and_switched_off_content_are_off(content):
    season = fresh_season(content)
    stamp_season(season, content)
    assert not precise.on(content, season)
    c = real_content("weekend")
    c.config.precise_actions = False
    season = fresh_season(c)
    stamp_season(season, c)
    assert not precise.on(c, season)
