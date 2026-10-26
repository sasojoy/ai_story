"""地盤福利、事件條件與輿圖上色（出陣探索與地盤設計 4.3）。正式內容、週末設定。宛城：官軍的投靠點，有醫館、馬市、鐵匠鋪。"""
from __future__ import annotations

import random

import pytest

from conftest import classic_rules, no_conquest, real_content
from tianxia import atlas, mapview, mounts, rules, smithing, team
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.models import Condition
from tianxia.sqlite_world import open_world


def _game(faction, at="wan_city"):
    c = no_conquest(real_content("week7"))  # 地盤拔河的舊規則（領地爭奪 PM 2026-10-22 起正式內容打開；領地加成在 tests/test_conquest_perks.py）
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    p.visited.add(at)
    return game


@pytest.mark.parametrize(("faction", "heal", "forge", "horse"), [("guan", 9, 18, 90), ("huang", 12, 24, 120), (None, 10, 20, 100)])
def test_your_own_ground_is_cheaper_and_the_enemys_dearer(faction, heal, forge, horse):
    game = _game(faction)
    s, c = game.state, game.content
    s.player.member.injury = 20  # 原價 10 兩
    assert team.heal_cost(c, s.player.member, s) == heal
    assert smithing.price(c, 1, "weapon", s) == forge  # 一階工錢原價 20
    assert mounts.price(s, c) == horse  # 駑馬原價 100


def test_healing_charges_the_local_price():
    game = _game("guan")
    s = game.state
    s.player.member.injury, s.player.stats["silver"] = 20, 100
    game.heal()
    assert s.player.stats["silver"] == 91 and s.player.member.injury == 0


def test_the_switch_off_keeps_the_list_price():
    game = _game("guan")
    s, c = game.state, classic_rules(game.content)
    s.player.member.injury = 20
    assert (team.heal_cost(c, s.player.member, s), smithing.price(c, 1, "weapon", s), mounts.price(s, c)) == (10, 20, 100)


def test_events_can_ask_who_holds_this_place():
    game = _game("guan", at="runan_wilds")  # 開季歸黃巾
    s, c = game.state, game.content
    assert rules.check_condition(Condition(controlled_by=["huang"]), s, c)
    assert not rules.check_condition(Condition(controlled_by=["guan"]), s, c)
    assert not rules.check_condition(Condition(controlled_by=["huang"]), s, None)
    s.player.location = "yingshui"  # 不是戰線地點：沒有控制方
    assert not rules.check_condition(Condition(controlled_by=["huang", "guan", "haoqiang"]), s, c)


def test_an_unknown_side_in_controlled_by_is_refused():
    c = real_content()
    event = next(iter(c.events.values()))
    event.condition.controlled_by = ["nobody"]
    with pytest.raises(ContentError, match="nobody"):
        validate(c)


def test_the_situation_layer_paints_who_holds_each_place():
    game = _game("huang", at="huangjin_camp")
    s, c = game.state, game.content
    svg = mapview.render_map(s, c, "situation")
    assert mapview.CONTROL_DISC["huang"] in svg
    assert mapview.LEGEND_CONTROL in mapview.legend_data(s, c, "situation")["layer"]
    assert "此刻由黃巾軍控制" in atlas.detail_text(s, c, "huangjin_camp", game.odds)
