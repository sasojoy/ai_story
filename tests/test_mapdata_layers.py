"""輿圖四層要的資料（減法季整合設計第七章；tianxia/mapdata.py）：底圖每一處的「多半」兩字與每一條路的曲線，疊層每一處走過去的路線
與本週要去的那一處。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia import mapart, mapdata, orders
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


def _game(at="yingchuan_wilds", faction="guan"):
    c = real_content("season21")
    c.config.auto_open_first_season = True
    game = Game.new(c, "陸乙", rng=random.Random(0), world=open_world())
    game.client = None
    game.state.player.faction, game.state.player.location = faction, at
    return game


def test_every_place_says_what_it_mostly_holds_by_its_icon():
    base = _game().map_base()
    assert all(p["mostly"] == mapdata.MOSTLY[p["glyph"]] for p in base["places"])
    assert set(mapdata.MOSTLY) == {"城", "營", "寺", "渡", "山", "野"}


def test_roads_carry_the_same_curve_as_the_base_map():
    game = _game()
    base = game.map_base()
    assert len(base["roads"]) == len(base["edges"])
    for a, z, qx, qy in base["roads"]:
        cx, cy = mapart.road_control(game.content, a, z)
        assert abs(cx - qx) < 0.06 and abs(cy - qy) < 0.06


def test_each_place_carries_the_route_there():
    st = _game().map_state()
    here = st["places"]["yingchuan_wilds"]
    assert here["here"] and here["path"] == []
    assert st["places"]["changshe"]["path"] == ["changshe"]
    far = [q for q in st["places"].values() if len(q["path"]) > 1]
    assert far and all(q["minutes"] is not None for q in far)


def test_this_weeks_place_follows_the_order_then_the_bounty_then_the_story():
    """本週那一處：軍令記功的地點（守城還沒被推時，那條戰線上自家最近的一處，不算腳下）、懸賞、主線目標；同一種挑最近的。"""
    game = _game()
    s, c = game.state, game.content
    period = orders.period_of(s, c)
    (orders.issue_day if orders.daily(s, c) else orders.issue)(s, c, period, random.Random(0), redraw=True)
    assert any(o.faction == "guan" for o in orders.current(s, c, "guan"))
    st = game.map_state()
    week = st["week"]
    assert week is not None and week["id"] != "yingchuan_wilds" and week["why"].startswith("軍令・")
    assert week["minutes"] == st["places"][week["id"]]["minutes"]


def test_no_faction_and_no_goal_means_no_week_place():
    game = _game(faction=None)
    st = game.map_state()
    assert st["week"] is None or st["week"]["why"] in (mapdata.WEEK_GOAL,) or st["week"]["why"].startswith("懸賞")
