"""輿圖升級的資料（設計第九節）：底圖的清單與疊層。正式內容、週末設定。"""
from __future__ import annotations

import json
import random

from conftest import classic_rules, real_content
from tianxia import calendar, mapdata, mapview, territory
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


def _game(faction="guan", at="yingchuan", classic=False, profile="weekend"):
    c = real_content(profile)
    c.config.auto_open_first_season = True
    if classic:
        classic_rules(c)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    return game


def test_the_base_lists_open_places_roads_and_regions():
    game = _game(profile=None)
    b = game.map_base()
    ids = [p["id"] for p in b["places"]]
    assert ids == mapview.open_places(game.state, game.content) and "jade_cave" not in ids
    assert all(p["glyph"] in mapview.GLYPHS.values() for p in b["places"])
    assert all({a, z} <= set(ids) for a, z in b["edges"])
    assert [r["id"] for r in b["regions"]] == [r.id for r in game.content.map.regions]
    assert b["key"] == mapdata.base_key(game.state, game.content) and b["svg"].startswith("<svg")


def test_the_state_says_who_holds_each_place():
    st = _game().map_state()
    assert st["places"]["changshe"]["control"] == "guan" and st["places"]["changshe"]["kind"] == "base"
    assert st["places"]["runan_wilds"]["kind"] == "line" and st["places"]["runan_wilds"]["control"] in ("guan", "huang", "haoqiang")
    assert st["places"]["guangzong"]["kind"] == "fixed"
    assert st["places"]["yingshui"]["control"] is None and st["places"]["yingshui"]["kind"] is None
    assert st["here"] == "yingchuan" and st["places"]["yingchuan"]["minutes"] is None
    assert st["places"]["yingchuan_wilds"]["minutes"] >= 1


def test_the_state_suggests_where_to_sortie():
    st = _game().map_state()
    assert 1 <= len(st["suggest"]) <= mapdata.SUGGEST_MAX
    for g in st["suggest"]:
        assert st["places"][g["id"]]["sortie"] == g["sortie"] and g["sortie"] in ("attack", "hold", "stir")
    scores = [g["score"] for g in st["suggest"]]
    assert scores == sorted(scores, reverse=True)


def test_the_state_carries_three_ropes_and_the_weeks():
    game = _game()
    territory.update(game.state.world, game.content)
    st = game.map_state()
    assert [r["id"] for r in st["ropes"]] == ["yingru", "nanyang", "jizhou"]
    assert all(r["beads"] for r in st["ropes"]) and st["geju"] is not None
    assert st["weeks"][0]["week"] == 1 and st["weeks"][0]["control"]["changshe"] == "guan"
    assert len(st["weeks"]) == st["now_week"]


def test_weeks_before_the_first_snapshot_are_empty():
    game = _game()
    w, c = game.state.world, game.content
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    weeks = game.map_state()["weeks"]
    assert [x["control"] is None for x in weeks] == [True, True, False]


def test_a_flip_shows_in_the_week_and_on_the_place():
    game = _game()
    w, c = game.state.world, game.content
    territory.update(w, c)
    w.time = calendar.week_start(2, c, w) + 60
    w.trends["yingru"] = 90
    territory.update(w, c)
    st = game.map_state()
    assert {"id": "guan_camp", "from": "guan", "to": "huang"} in st["weeks"][1]["changed"]
    assert st["places"]["guan_camp"]["flips"] == [{"week": 2, "from": "guan", "to": "huang"}]


def test_the_state_says_where_you_are_heading():
    game = _game()
    game.travel("yingchuan_wilds", "walk")
    st = game.map_state()
    assert st["journey"]["to"] == "yingchuan_wilds" and st["journey"]["minutes"] >= 1
    assert isinstance(st["journey"]["x"], (int, float))


def test_the_state_works_with_every_switch_off():
    st = _game(classic=True).map_state()
    assert st["territory"] is False and st["suggest"] == [] and st["weeks"] == [] and st["chart"] == []
    assert all(p["control"] is None and p["sortie"] is None for p in st["places"].values())


def test_the_fourteen_day_season_has_one_rope():
    st = _game(profile=None).map_state()
    assert len(st["ropes"]) == 1 and st["season_one"] is False


def test_the_state_is_small_and_counts_each_squad_once():
    game = _game()
    calls = []
    real = game.odds
    game.odds = lambda sid: calls.append(sid) or real(sid)
    st = game.map_state()
    assert len(json.dumps(st, ensure_ascii=False).encode()) < 40_000
    assert calls and len(calls) == len(set(calls))
