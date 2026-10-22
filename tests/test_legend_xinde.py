"""心得不能換破境丹、也不能拿來衝關（Joy 2026-10-21「把破境丹也加入商城，取消可以用心得衝」；10-18 起先是以心得換丹）。
到了極處只剩服丹衝關（丹從探索、醫館與萬寶閣來）；機器人有丹才衝、沒丹等契機。"""
from __future__ import annotations

import random

import pytest

from tianxia import bot, cultivation, howto, skillview
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

from conftest import FIXTURE
from test_cultivation import BASICS, kicker_art, ripen
from test_practice_hardening import harden


@pytest.fixture
def game(tmp_path):
    content = harden(load_content(FIXTURE))
    world = open_world(tmp_path / "w.db")
    g = Game.new(content, "試丹", rng=random.Random(1), world=world, graduated=True)
    return g


def _ready_for_jue(g):
    """身上換上一門旋風腿，練到上品、十成、四個基本意境裝滿槽（到了極處）。"""
    p = g.state.player
    g.world.claim_skill_name(kicker_art())
    art_id = "旋風腿"
    p.insights = list(BASICS)
    p.member.wugong_id = art_id
    ripen(g.state, art_id)
    return art_id


def test_no_xinde_way_to_break_through(game):
    """心得換丹、心得衝關都拿掉了：設定、規則、引擎、伺服器都沒有那一條；修練頁那一列的 xinde 一律是 None。"""
    art_id = _ready_for_jue(game)
    p = game.state.player
    p.stats["xinde"], p.stamina = 5000, 200
    assert not hasattr(game.content.config, "legend_xinde_price") and not hasattr(game.content.config, "legend_xinde_step")
    assert not hasattr(cultivation, "legend_price") and not hasattr(cultivation, "buy_legend")
    assert not hasattr(game, "buy_legend") and not hasattr(bot, "buy_pill") and not hasattr(howto, "legend_buy_lines")
    with pytest.raises(TypeError):
        game.cultivate(art_id, use_xinde=True)
    row = next(r for r in skillview.art_rows(game.state, game.content, game.world) if r["id"] == art_id)
    assert row["cultivate"]["xinde"] is None and row["cultivate"]["legend"] is None and not row["cultivate"]["ok"]
    assert "破境丹" in row["cultivate"]["note"]  # 沒丹：等契機或服丹那一句
    assert game.cultivate(art_id) == [cultivation.CHANCE_LINE.format(name="旋風腿", pill="破境丹")]
    assert p.stats["xinde"] == 5000


def test_the_pill_button_shows_only_with_a_pill_in_hand(game):
    p = game.state.player
    art_id = _ready_for_jue(game)
    row = lambda: next(r for r in skillview.art_rows(game.state, game.content, game.world) if r["id"] == art_id)
    assert row()["cultivate"]["legend"] is None
    p.legend_items = 2
    lg = row()["cultivate"]["legend"]
    assert row()["cultivate"]["ok"] and lg["count"] == 2 and lg["bonus"] == cultivation.force_odds(game.state, game.content, game.world, art_id)


def test_bot_breaks_through_only_with_a_pill(game):
    p = game.state.player
    art_id = _ready_for_jue(game)
    p.stats["xinde"] = 5000
    assert bot.break_way(game, art_id) == {}  # 沒丹：等契機，不花心得
    p.legend_items = 1
    assert bot.break_way(game, art_id) == {"use_legend": True}
    p.art_levels[art_id] = p.member.wugong_level = 9
    assert bot.break_way(game, art_id) == {}  # 還沒第十成


def test_bot_takes_the_pill_only_at_the_last_step(game):
    """機器人勾不勾「服下破境丹」：手上有丹、那一門到了極處才勾（別的門用不上丹）。"""
    p = game.state.player
    art_id = _ready_for_jue(game)
    assert not bot.takes_the_pill(game, art_id)  # 沒有丹
    p.legend_items = 1
    assert bot.takes_the_pill(game, art_id)
    p.art_levels[art_id] = p.member.wugong_level = 9
    assert not bot.takes_the_pill(game, art_id)  # 還沒第十成
