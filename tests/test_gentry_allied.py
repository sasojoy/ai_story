"""第一季豪強分屬兩軍（docs/superpowers/specs/2026-10-15-第一季豪強分屬兩軍-design.md）。

用真實內容的週末設定（第一季規則與豪強分屬兩軍都開著）；舊規則的對照另外關掉開關。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content, third_party_gentry
from tianxia import allied, rules
from tianxia.engine import Game
from tianxia.state import PlayerState, WorldState


@pytest.fixture
def wk():
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _game(content, name="甲", faction=None, ally=None, at=None):
    game = Game.new(content, name, rng=random.Random(0))
    p = game.state.player
    p.faction, p.ally = faction, ally
    if at is not None:
        p.location = at
    return game


def _old_rules():
    c = third_party_gentry(real_content("weekend"))
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


# ── Task 1：開關、蓋章、敵我與名冊鍵 ─────────────────────────────


def test_weekend_profile_turns_it_on(wk):
    assert wk.config.haoqiang_allied is True
    assert real_content().config.haoqiang_allied is False
    assert [f.allies for f in wk.scenario.factions if f.id == "haoqiang"] == [["guan", "huang"]]


def test_old_saves_load_without_the_new_fields():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.ally, p.pending_ally) == (None, None)
    assert WorldState().haoqiang_allied is False


def test_stamp_and_rule(wk):
    game = _game(wk)
    assert game.state.world.haoqiang_allied is True
    assert allied.on(wk, game.state.world) and rules.haoqiang_allied(wk, game.state.world)


def test_fourteen_day_season_keeps_the_third_party():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.haoqiang_allied = True  # 設定打開了，可是 14 天的季沒有第一季的章
    game = _game(c, faction="haoqiang", ally="guan")
    assert not allied.on(c, game.state.world)
    assert allied.side_of(game.state, c) == "haoqiang"


def test_side_of(wk):
    game = _game(wk, faction="haoqiang", ally="huang")
    assert allied.side_of(game.state, wk) == "huang" and rules.side_of(game.state, wk) == "huang"
    game.state.player.faction, game.state.player.ally = "guan", None
    assert allied.side_of(game.state, wk) == "guan"
    game.state.player.faction = None
    assert allied.side_of(game.state, wk) is None


def test_needs_ally(wk):
    game = _game(wk, faction="haoqiang")
    assert allied.needs_ally(game.state, wk)
    game.state.player.ally = "guan"
    assert not allied.needs_ally(game.state, wk)
    assert not allied.needs_ally(_game(wk, name="丙", faction="guan").state, wk)


# 舊規則的對照各自一支測試：同一支測試裡的 Game 共用同一個資料庫，第一個開的季蓋什麼章，後面的都讀同一季


def test_old_rules_need_no_ally():
    off = _old_rules()
    assert not allied.needs_ally(_game(off, name="乙", faction="haoqiang").state, off)


def test_roll_keys():
    assert allied.roll_key("guan", None) == "guan"
    assert allied.roll_key("haoqiang", "huang") == "haoqiang@huang"
    assert allied.split_key("haoqiang@huang") == ("haoqiang", "huang")
    assert allied.split_key("guan") == ("guan", None)
    assert allied.side_of_key("haoqiang@huang") == "huang" and allied.side_of_key("guan") == "guan"
    assert allied.side_of_key(None) is None
    rolls = {"guan": 9, "haoqiang@guan": 3, "huang": 7, "haoqiang@huang": 2, "haoqiang": 1}
    assert allied.faction_totals(rolls) == {"guan": 9, "haoqiang": 6, "huang": 7}
    assert allied.side_totals(rolls) == {"guan": 12, "huang": 9, "haoqiang": 1}
    assert allied.gentry_totals(rolls) == {"guan": 3, "huang": 2}


def test_roster_counts_by_side_and_by_faction(wk):
    game = _game(wk)
    w = game.world
    w.record_faction("甲", "haoqiang@guan")
    w.record_faction("乙", "guan")
    w.record_faction("丙", "huang")
    assert w.faction_of("甲") == "guan" and w.roll_of("甲") == "haoqiang@guan"
    assert w.faction_of("乙") == "guan" and w.faction_of("無名") is None
    assert w.faction_counts() == {"guan": 1, "haoqiang": 1, "huang": 1}
    assert w.roll_counts() == {"guan": 1, "haoqiang@guan": 1, "huang": 1}


def test_geju_is_gone(wk):
    game = _game(wk)
    w = game.state.world
    assert not rules.trend_shown(wk, w, rules.GEJU)
    assert rules.resolve_trend(wk, w, rules.GEJU) is None
    assert rules.GEJU not in w.trends


def test_old_rules_keep_geju():
    off = _old_rules()
    w = _game(off, name="乙").state.world
    assert rules.trend_shown(off, w, rules.GEJU) and rules.GEJU in w.trends


def test_allies_must_be_real_other_factions(wk):
    from tianxia.content import ContentError, validate

    hao = next(f for f in wk.scenario.factions if f.id == "haoqiang")
    hao.allies = ["guan", "nobody"]
    with pytest.raises(ContentError, match="allies"):
        validate(wk)
    hao.allies = ["haoqiang", "huang"]
    with pytest.raises(ContentError, match="allies"):
        validate(wk)
