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
    assert 1 <= len(st["suggest"]) <= mapdata.SUGGEST_MAX + 1  # 打得過的最多三處，再加一處必敗的
    for g in st["suggest"]:
        assert st["places"][g["id"]]["sortie"] == g["sortie"] and g["sortie"] in ("attack", "hold", "stir")
    loses = [g["lose"] for g in st["suggest"]]
    assert loses == sorted(loses)  # 必敗的排在最後（企劃者 10/15 對比 4 選乙）
    for lose in (False, True):
        scores = [g["score"] for g in st["suggest"] if g["lose"] is lose]
        assert scores == sorted(scores, reverse=True)
    assert all(g["lose"] == ((st["places"][g["id"]]["odds"] or {}).get("word") == mapdata.LOSE_WORD) for g in st["suggest"])


def test_a_place_you_can_win_comes_before_one_with_a_big_order_you_would_lose():
    """軍令 +100 的必敗那一處，排在什麼都沒有、打得過的那一處後面。"""
    from tianxia import mapdata as md

    rows = [{"id": "a", "lose": True, "score": 100}, {"id": "b", "lose": False, "score": -3}]
    assert [g["id"] for g in md.rank_suggestions(rows)] == ["b", "a"]


def test_a_losing_place_still_shows_when_three_can_be_won():
    """「必敗的照樣列」：打得過的有三處時，必敗的分數最高那一處淡淡地排第四，不會整個不見。"""
    from tianxia import mapdata as md

    win = [{"id": f"w{i}", "lose": False, "score": -i} for i in range(5)]
    lose = [{"id": "l0", "lose": True, "score": 90}, {"id": "l1", "lose": True, "score": 50}]
    assert [g["id"] for g in md.rank_suggestions(win + lose)] == ["w0", "w1", "w2", "l0"]
    assert [g["id"] for g in md.rank_suggestions(win[:1] + lose)] == ["w0", "l0", "l1"]
    assert [g["id"] for g in md.rank_suggestions(lose)] == ["l0", "l1"]


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


def test_the_sword_marks_follow_fb251():
    """⚔ 只標在看的人此刻能出陣攻的地方，跟舊輿圖同一個判斷（mapview.armed_places，FB-251）；散人、豪強一處都沒有。"""
    game = _game()
    st = game.map_state()
    armed = mapview.armed_places(game.state, game.content)
    assert armed and {k for k, p in st["places"].items() if p["armed"]} == armed & set(st["places"])
    for faction in (None, "haoqiang"):
        assert not any(p["armed"] for p in _game(faction=faction).map_state()["places"].values()), faction


def test_with_sortie_off_the_sword_follows_the_old_rule():
    """出陣關著（armed_places 是 None）：照內容寫的 enemies，同舊輿圖。"""
    game = _game(classic=True)
    st = game.map_state()
    assert {k for k, p in st["places"].items() if p["armed"]} == {k for k in st["places"] if game.content.locations[k].enemies}
