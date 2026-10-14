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


def test_fb250_a_ranger_on_a_front_sees_why_there_is_no_sortie():
    """散人站在戰線地點（汝南荒野）：出陣那一顆灰著寫真正的原因、底下那一行說投靠之後才有；不在戰線的地方（潁水河畔）照舊沒有那一顆。"""
    from tianxia import sortie

    game = _game(None, "runan_wilds")
    option = _sortie(game)
    assert option is not None and not option.enabled and option.label == f"{sortie.NAME}（{sortie.RANGER_NOTE}）"
    assert game.action_notes([o.id for o in game.options(odds=False)])["act:train"] == sortie.RANGER_LINE
    assert game.choose("act:train") == ["（此刻無法這麼做。）"]
    assert _sortie(_game(None, "yingshui")) is None


def _map(game):
    from tianxia import mapview

    return mapview.render_map(game.state, game.content)


def test_fb251_the_crossed_swords_mark_where_you_can_attack():
    """⚔ 照地盤畫：此刻歸敵方、能出陣攻的戰線地點才有（官軍看：汝南荒野〔黃巾佔著〕有，長社〔自家大本營〕、荒丘〔不是戰線〕沒有）；
    散人不能出陣，哪裡都沒有。圖例那一句改成出陣的說法。出陣關著時照舊照內容的敵人畫。"""
    from tianxia import mapview

    guan = _game("guan", "changshe")
    svg = _map(guan)
    assert "汝南荒野 ⚔" in svg and "長社 ⚔" not in svg and "荒丘 ⚔" not in svg
    assert "⚔" not in _map(_game(None, "changshe", name="散人甲"))
    legend = mapview.legend_data(guan.state, guan.content)
    assert legend["ring"] == mapview.LEGEND_RING_SORTIE and "遊歷" not in legend["ring"]
    old = _game("guan", "changshe", name="舊規則", content=classic_rules(real_content("weekend")))
    assert "長社 ⚔" in _map(old) and mapview.legend_data(old.state, old.content)["ring"] == mapview.LEGEND_RING


def test_fb251_the_challenge_line_says_the_same_stamina_as_a_sortie():
    from tianxia import howto
    from tianxia.world_state import fresh_season

    c = real_content("weekend")
    page = howto.page(c, fresh_season(c), recruitable=False)
    assert "體力同出陣" in page and "體力同遊歷" not in page
    old = classic_rules(real_content("weekend"))
    assert "體力同遊歷" in howto.page(old, fresh_season(old), recruitable=False)


def test_fb248_with_the_sortie_off_the_neighbours_still_meet_the_convoy():
    game = _game("guan", "changshe", content=classic_rules(real_content("weekend")))
    _intercept(game, "guan", "runan_wilds")
    assert orders.extra_enemies(game.state, game.content, "changshe", "guan") == [game.content.orders.convoy_squads["huang"]]
