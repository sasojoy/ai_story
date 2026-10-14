"""核心玩法重整第 1 塊 QA 的回饋（docs/superpowers/feedback/試玩回饋.md 的 FB-248～254，PM 2026-10-15 定的修法）。正式內容、週末設定。"""
from __future__ import annotations

import random

from conftest import classic_rules, real_content
from tianxia import atlas, orders, territory
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import Order


def _game(faction=None, at="yingshui", name="沈浪", content=None):
    c = content or real_content("weekend")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    game = Game.new(c, name, rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    p.tutorial_step = len(c.tutorial.steps)
    p.visited.add(at)
    return game


def _sortie(game):
    return next((o for o in game.options() if o.id == "act:train"), None)


# ── FB-248：截糧的地點一律在戰線上，糧隊只在那一處 ─────────────────────


def _intercept(game, faction, location):
    order = Order(id=f"1:{faction}:intercept:x", template="intercept", faction=faction, week=orders.week_of(game.state, game.content),
                  front=territory.line_of(game.content, location), location=location, quota=99, text="")
    game.state.world.orders = [o for o in game.state.world.orders if o.template != "intercept"] + [order]
    return order


def test_fb248_every_intercept_slot_is_a_front_place():
    c = real_content()
    for front, sides in c.orders.slots.items():
        for side, slot in sides.items():
            assert territory.line_of(c, slot.intercept) == front, (front, side, slot.intercept)


def test_fb248_the_convoy_stands_only_at_the_intercept_place():
    """官軍截糧汝南荒野那一週：汝南荒野有黃巾糧隊、出陣攻打得到；相鄰的長社（官軍大本營）照舊是守，不變成攻糧隊。"""
    game = _game("guan", "changshe")
    _intercept(game, "guan", "runan_wilds")
    convoy = game.content.orders.convoy_squads["huang"]
    assert orders.extra_enemies(game.state, game.content, "changshe", "guan") == []
    assert _sortie(game).label.startswith("出陣・守")
    game.state.player.location = "runan_wilds"
    assert convoy in orders.extra_enemies(game.state, game.content, "runan_wilds", "guan")
    assert convoy in game._sortie_foes(game.content.locations["runan_wilds"])
    assert orders.win_counts(game.state, game.content, "guan", "runan_wilds")
    assert not orders.win_counts(game.state, game.content, "guan", "changshe")
    assert orders.targets(game.state, game.content, "guan") == ["runan_wilds"]


def test_fb248_the_intercept_card_names_only_the_place():
    game = _game("guan", "changshe")
    order = _intercept(game, "guan", "runan_wilds")
    assert atlas.order_how(game.state, game.content, order) == atlas.INTERCEPT_SORTIE.format(place="汝南荒野")
    assert "附近" not in atlas.order_how(game.state, game.content, order)


def _strike_bounty():
    from tianxia.state import Bounty

    return Bounty(id="b1", kind="strike", faction="guan", week=1, expires=1e12, silver=20, deeds=1, location="yanshan_foot", squad="louluo")


def test_fb249_the_strike_bounty_says_sortie_or_gathering():
    from tianxia import bounties

    c = real_content("weekend")
    line = bounties.how(c, _strike_bounty())
    assert "遊歷" not in line and "燕山腳" in line and "黃巾" in line
    assert bounties.STRIKE_SORTIE in line and bounties.STRIKE_GATHER in line
    c.config.explore_modes.enabled = False
    assert bounties.STRIKE_GATHER not in bounties.how(c, _strike_bounty())
    old = classic_rules(real_content("weekend"))
    assert bounties.how(old, _strike_bounty()) == "到燕山腳遊歷，打贏一場黃巾軍的隊伍"


def test_fb248_with_the_sortie_off_the_neighbours_still_meet_the_convoy():
    game = _game("guan", "changshe", content=classic_rules(real_content("weekend")))
    _intercept(game, "guan", "runan_wilds")
    assert orders.extra_enemies(game.state, game.content, "changshe", "guan") == [game.content.orders.convoy_squads["huang"]]
