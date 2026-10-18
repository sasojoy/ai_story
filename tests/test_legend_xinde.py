"""以心得換破境丹（Joy 2026-10-18「大量心得可以換一次破境機會，讓玩家後期更好轉功法」）。"""
from __future__ import annotations

import random

import pytest

from tianxia import bot, cultivation, howto, skillview, team
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

from conftest import FIXTURE
from test_cultivation import kicker_art
from test_practice_hardening import harden


@pytest.fixture
def game(tmp_path):
    content = harden(load_content(FIXTURE))
    content.config.legend_xinde_price = 300
    content.config.legend_xinde_step = 100
    world = open_world(tmp_path / "w.db")
    g = Game.new(content, "試丹", rng=random.Random(1), world=world, graduated=True)
    return g


def _ready_for_jue(g):
    """身上換上一門融了風的旋風腿，練到上品、十成、火候滿了。"""
    p, c = g.state.player, g.content
    g.world.claim_skill_name(kicker_art())
    art_id = "旋風腿"
    p.insights = ["feng"]
    p.member.wugong_id = art_id
    p.art_quality[art_id] = "上品"
    p.member.wugong_level = 10
    p.art_mastery[art_id] = c.config.breakthrough.heat
    return art_id


def test_buying_costs_more_each_time(game):
    p = game.state.player
    p.stats["xinde"] = 1000
    assert cultivation.legend_price(game.state, game.content) == 300
    msgs = game.buy_legend()
    assert p.legend_items == 1 and p.stats["xinde"] == 700 and p.legend_bought == 1
    assert "心得 -300" in msgs[0]
    assert cultivation.legend_price(game.state, game.content) == 400
    game.buy_legend()
    assert p.legend_items == 2 and p.stats["xinde"] == 300
    refused = game.buy_legend()  # 第三枚要 500
    assert p.legend_items == 2 and p.stats["xinde"] == 300
    assert "心得不足" in refused[0] and "500" in refused[0]


def test_off_by_default_in_test_content(tmp_path):
    content = load_content(FIXTURE)
    g = Game.new(content, "試丹", rng=random.Random(1), world=open_world(tmp_path / "w.db"), graduated=True)
    g.state.player.stats["xinde"] = 5000
    g.buy_legend()
    assert g.state.player.legend_items == 0 and g.state.player.stats["xinde"] == 5000
    assert howto.legend_buy_lines(content) == []


def test_button_shows_only_on_the_last_step(game):
    p = game.state.player
    p.stats["xinde"] = 1000
    row = lambda: next(r for r in skillview.art_rows(game.state, game.content, game.world) if r["id"] == p.member.wugong_id)
    assert all(r["cultivate"]["buy"] is None for r in skillview.art_rows(game.state, game.content, game.world))  # 還沒有衝絕學的
    _ready_for_jue(game)
    buy = row()["cultivate"]["buy"]
    assert buy["ok"] and buy["price"] == 300
    p.stats["xinde"] = 100
    buy = row()["cultivate"]["buy"]
    assert not buy["ok"] and "心得不足" in buy["why"]


def test_bought_pill_forces_the_breakthrough(game):
    p = game.state.player
    art_id = _ready_for_jue(game)
    p.stats["xinde"] = 1000
    game.buy_legend()
    game.state.player.stamina = 200
    game.cultivate(art_id, use_legend=True)
    assert p.legend_items == 0  # 服下去了（成不成看機會）


def test_bot_buys_when_waiting_for_a_chance(game):
    p = game.state.player
    _ready_for_jue(game)
    p.stats["xinde"] = 1000
    assert bot.buy_pill(game)
    assert p.legend_items == 1
    assert not bot.buy_pill(game)  # 手上有丹就不再換


# ── 以心得修練（Joy 2026-10-18 決策卡「心得修練」）──────────────────────────────


@pytest.fixture
def xgame(game):
    game.content.config.cultivate_xinde_price = 40
    game.content.config.cultivate_xinde_step = 4
    return game


def test_cultivating_with_xinde_costs_no_stamina_and_climbs(xgame):
    p = xgame.state.player
    art_id = _ready_for_jue(xgame)
    p.art_mastery[art_id] = 0  # 還在添火候
    p.stamina, p.stats["xinde"] = 0, 200
    xgame.cultivate(art_id, by_xinde=True)
    assert p.stamina == 0 and p.stats["xinde"] == 160 and p.art_mastery[art_id] == 1
    assert cultivation.xinde_price(xgame.state, xgame.content) == 44
    xgame.cultivate(art_id, by_xinde=True)
    assert p.stats["xinde"] == 116 and p.art_mastery[art_id] == 2


def test_without_enough_xinde_nothing_moves(xgame):
    p = xgame.state.player
    art_id = _ready_for_jue(xgame)
    p.art_mastery[art_id] = 0
    p.stats["xinde"] = 39
    msgs = xgame.cultivate(art_id, by_xinde=True)
    assert "心得不足" in msgs[0] and p.stats["xinde"] == 39 and p.art_mastery[art_id] == 0 and p.xinde_cultivations == 0


def test_row_offers_xinde_when_stamina_runs_out(xgame):
    p = xgame.state.player
    art_id = _ready_for_jue(xgame)
    p.art_mastery[art_id] = 0
    p.stamina, p.stats["xinde"] = 0, 100
    row = next(r for r in skillview.art_rows(xgame.state, xgame.content, xgame.world) if r["id"] == art_id)
    assert not row["cultivate"]["ok"]  # 體力不足
    assert row["cultivate"]["xinde"]["ok"] and row["cultivate"]["xinde"]["price"] == 40
    p.art_mastery[art_id] = xgame.content.config.breakthrough.heat  # 火候滿了、沒丹：等契機，心得修不了（改看換丹那一顆）
    row = next(r for r in skillview.art_rows(xgame.state, xgame.content, xgame.world) if r["id"] == art_id)
    assert row["cultivate"]["xinde"] is None and row["cultivate"]["buy"] is not None


def test_bot_spends_spare_xinde_on_its_own_arts_first(xgame):
    p = xgame.state.player
    art_id = _ready_for_jue(xgame)
    p.art_mastery[art_id] = 0
    p.stats["xinde"] = 1000
    assert bot.cultivate_by_xinde(xgame) == bot.XINDE_CULTIVATE_MAX
    assert p.art_mastery[art_id] == bot.XINDE_CULTIVATE_MAX


def test_off_in_test_content(tmp_path):
    content = harden(load_content(FIXTURE))
    g = Game.new(content, "試丹", rng=random.Random(1), world=open_world(tmp_path / "w.db"), graduated=True)
    assert cultivation.xinde_price(g.state, content) is None
    assert all(r["cultivate"]["xinde"] is None for r in skillview.art_rows(g.state, content, g.world))
