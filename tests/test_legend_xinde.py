"""以心得換破境丹（Joy 2026-10-18「大量心得可以換一次破境機會，讓玩家後期更好轉功法」）。
以心得修練那一半在武學重構（Joy 2026-10-20）時跟著「品級不靠修練」一起拿掉了：換丹只在上品到了極處（cultivation.ready）才有。"""
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
    content.config.legend_xinde_price = 300
    content.config.legend_xinde_step = 100
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


def test_the_howto_line_only_talks_about_the_pill(game):
    """玩法說明：以心得修練那一句拿掉了，只剩換丹那一句（數字讀 Config）。"""
    lines = howto.legend_buy_lines(game.content)
    assert len(lines) == 1 and "300" in lines[0] and "100" in lines[0] and "改付心得" not in lines[0]


def test_button_shows_only_on_the_last_step(game):
    p = game.state.player
    p.stats["xinde"] = 1000
    row = lambda: next(r for r in skillview.art_rows(game.state, game.content, game.world) if r["id"] == p.member.wugong_id)
    assert all(r["cultivate"]["buy"] is None for r in skillview.art_rows(game.state, game.content, game.world))  # 還沒有到極處的
    _ready_for_jue(game)
    buy = row()["cultivate"]["buy"]
    assert buy["ok"] and buy["price"] == 300
    p.stats["xinde"] = 100
    buy = row()["cultivate"]["buy"]
    assert not buy["ok"] and "心得不足" in buy["why"]
    p.member.wugong_level = 9  # 還沒第十成：還沒到極處，換丹那一顆不畫（評分不是門檻，Joy 2026-10-20）
    assert row()["cultivate"]["buy"] is None


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
    assert not bot.buy_pill(game)  # 還沒有到極處的：不換
    _ready_for_jue(game)
    p.stats["xinde"] = 1000
    assert bot.awaits_chance(game)
    assert bot.buy_pill(game)
    assert p.legend_items == 1
    assert not bot.buy_pill(game)  # 手上有丹就不再換


def test_bot_takes_the_pill_only_at_the_last_step(game):
    """機器人勾不勾「服下破境丹」：手上有丹、那一門到了極處才勾（別的門用不上丹）。"""
    p = game.state.player
    art_id = _ready_for_jue(game)
    assert not bot.takes_the_pill(game, art_id)  # 沒有丹
    p.legend_items = 1
    assert bot.takes_the_pill(game, art_id)
    p.art_levels[art_id] = p.member.wugong_level = 9
    assert not bot.takes_the_pill(game, art_id)  # 還沒第十成


def test_no_xinde_cultivation_any_more(game):
    """武學重構：修練不能改付心得了（Game.cultivate 沒有 by_xinde），修練頁那一列的 xinde 一律是 None。"""
    art_id = _ready_for_jue(game)
    assert not hasattr(game.content.config, "cultivate_xinde_price")  # 舊設定也拿掉了
    assert all(r["cultivate"]["xinde"] is None for r in skillview.art_rows(game.state, game.content, game.world))
    with pytest.raises(TypeError):
        game.cultivate(art_id, by_xinde=True)
    assert not hasattr(cultivation, "xinde_price") and not hasattr(bot, "cultivate_by_xinde")
