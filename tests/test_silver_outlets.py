"""正式季整合第 9 批：銀兩出口（設計 6.5；12.3 第 39、40、42 條）。只在 21 天季（season21 設定），週末與 14 天一個字都不變。
畫面這一批不做新版面：五樣都放在「此地還能做」。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia import economy, silver
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR


def _game(profile="season21", at="changshe", faction="guan", money=500):
    c = real_content(profile)
    c.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)  # 同一個測試第二次開：季已經開著（同一份暫存資料庫），照用
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction = at, faction
    p.tutorial_step = len(c.tutorial.steps)
    p.stats["silver"] = money
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


# ── Task 1：捐銀兩 ──


def test_donating_silver_counts_ten_to_a_point():
    game = _game()
    p, w = game.state.player, game.state.world
    option = _ids(game)["act:silver_donate"]
    assert option.enabled and "100 兩" in option.label
    msgs = game.choose("act:silver_donate")
    assert p.stats["silver"] == 400 and p.donated_today == 10
    assert game.state.world.armaments["guan"]["慢"] == 10 and p.contrib == 10
    assert any("銀兩 -100" in m for m in msgs)


def test_silver_and_materials_share_the_daily_cap():
    game = _game()
    p = game.state.player
    p.donate_day, p.donated_today = game.econ_day(), 95
    day = game.econ_day()
    assert silver.donate_amount(game.state, game.content, day, economy.donate_room(game.state, game.content, day)) == 50
    game.choose("act:silver_donate")
    assert p.stats["silver"] == 450 and p.donated_today == 100


def test_silver_donate_refused():
    game = _game(money=5)
    option = _ids(game)["act:silver_donate"]
    assert not option.enabled and "還差" in option.label
    game.choose("act:silver_donate")
    assert game.state.player.stats["silver"] == 5
    rich = _game()
    rich.state.player.donate_day, rich.state.player.donated_today = rich.econ_day(), 100
    assert not _ids(rich)["act:silver_donate"].enabled


def test_weekend_has_no_silver_outlets():
    game = _game("weekend")
    assert not silver.on(game.content, game.state.world)
    assert not any(i.startswith(("act:silver_donate", "act:mentor", "act:furnace", "act:buy_legend", "act:bribe")) for i in _ids(game))


def test_old_save_without_outlet_fields_loads():
    from tianxia.state import PlayerState

    raw = _game().state.player.model_dump()
    for key in ("mentor_day", "mentor_ready", "furnace_day", "furnace_ready", "legend_bought", "bribed"):
        raw.pop(key, None)
    p = PlayerState.model_validate(raw)
    assert not p.mentor_ready and not p.furnace_ready and p.legend_bought == 0 and p.bribed == {}
