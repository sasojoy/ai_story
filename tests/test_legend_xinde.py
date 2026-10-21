"""以心得衝關（Joy 2026-10-18「大量心得可以換一次破境機會，讓玩家後期更好轉功法」；10-21「心得不是「換」破境丹，是可以直接拿來衝關」）。
上品到了極處（cultivation.ready）才衝得了；機會同服一枚破境丹（force_odds），價錢這一季每衝一次漲。"""
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


class Fixed(random.Random):
    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def random(self):
        return self.value


def test_each_breakthrough_by_xinde_costs_more(game):
    p = game.state.player
    art_id = _ready_for_jue(game)
    p.stats["xinde"], p.stamina = 1000, 200
    game.rng = Fixed(0.99)  # 擲 99：沒衝開，火候還在
    assert cultivation.legend_price(game.state, game.content) == 300
    msgs = game.cultivate(art_id, use_xinde=True)
    assert p.stats["xinde"] == 700 and p.legend_bought == 1 and p.legend_items == 0
    assert "心得 -300" in msgs[0] and "彈了回來" in msgs[1]
    assert cultivation.legend_price(game.state, game.content) == 400
    game.cultivate(art_id, use_xinde=True)
    assert p.stats["xinde"] == 300
    refused = game.cultivate(art_id, use_xinde=True)  # 第三次要 500
    assert p.stats["xinde"] == 300 and p.legend_bought == 2
    assert "心得不足" in refused[0] and "500" in refused[0]


def test_xinde_has_the_same_odds_as_the_pill(game):
    p = game.state.player
    art_id = _ready_for_jue(game)
    p.stats["xinde"], p.stamina = 1000, 200
    odds = cultivation.force_odds(game.state, game.content, game.world, art_id)
    game.rng = Fixed((odds - 0.5) / 100)  # 剛好在機會之內：衝開
    msgs = game.cultivate(art_id, use_xinde=True)
    assert any("晉為絕學" in m for m in msgs) and p.legend_items == 0


def test_off_by_default_in_test_content(tmp_path):
    content = load_content(FIXTURE)
    g = Game.new(content, "試丹", rng=random.Random(1), world=open_world(tmp_path / "w.db"), graduated=True)
    g.state.player.stats["xinde"] = 5000
    assert cultivation.legend_price(g.state, content) is None
    assert "不能拿心得衝關" in (cultivation.xinde_problem(g.state, content) or "")
    assert howto.legend_buy_lines(content) == []
    assert not hasattr(g, "buy_legend") and not hasattr(cultivation, "buy_legend")  # 換丹拿掉了（10-21）


def test_the_howto_line_talks_about_breaking_through(game):
    """玩法說明：心得直接衝關那一句（數字讀 Config）。"""
    lines = howto.legend_buy_lines(game.content)
    assert len(lines) == 1 and "300" in lines[0] and "100" in lines[0] and "衝關" in lines[0] and "換一枚" not in lines[0]


def test_button_shows_only_on_the_last_step(game):
    p = game.state.player
    p.stats["xinde"], p.stamina = 1000, 200
    row = lambda: next(r for r in skillview.art_rows(game.state, game.content, game.world) if r["id"] == p.member.wugong_id)
    assert all(r["cultivate"]["xinde"] is None for r in skillview.art_rows(game.state, game.content, game.world))  # 還沒有到極處的
    art_id = _ready_for_jue(game)
    xd = row()["cultivate"]["xinde"]
    assert xd["ok"] and xd["price"] == 300 and xd["odds"] == cultivation.force_odds(game.state, game.content, game.world, art_id)
    assert "花心得強行衝關" in row()["cultivate"]["note"]
    p.stats["xinde"] = 100
    xd = row()["cultivate"]["xinde"]
    assert not xd["ok"] and "心得不足" in xd["why"]
    p.member.wugong_level = 9  # 還沒第十成：還沒到極處，心得衝關那一顆不畫（評分不是門檻，Joy 2026-10-20）
    p.art_levels[art_id] = 9
    assert row()["cultivate"]["xinde"] is None


def test_bot_breaks_through_with_xinde_when_it_has_no_pill(game):
    p = game.state.player
    assert bot.break_way(game, p.member.wugong_id) == {}  # 還沒有到極處的：不衝
    art_id = _ready_for_jue(game)
    p.stats["xinde"] = 1000
    assert bot.break_way(game, art_id) == {"use_xinde": True}
    p.legend_items = 1
    assert bot.break_way(game, art_id) == {"use_legend": True}  # 手上有丹先服丹
    p.legend_items, p.stats["xinde"] = 0, 300  # 衝完不到 TEACH_RESERVE：先不衝
    assert bot.break_way(game, art_id) == {}


def test_bot_takes_the_pill_only_at_the_last_step(game):
    """機器人勾不勾「服下破境丹」：手上有丹、那一門到了極處才勾（別的門用不上丹）。"""
    p = game.state.player
    art_id = _ready_for_jue(game)
    assert not bot.takes_the_pill(game, art_id)  # 沒有丹
    p.legend_items = 1
    assert bot.takes_the_pill(game, art_id)
    p.art_levels[art_id] = p.member.wugong_level = 9
    assert not bot.takes_the_pill(game, art_id)  # 還沒第十成
