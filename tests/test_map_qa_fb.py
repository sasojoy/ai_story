"""輿圖升級 QA 的回饋（docs/superpowers/feedback/試玩回饋.md 的 FB-258～264，PM 2026-10-15 定的修法）：疊層的資料那一半。
網頁那一半在 tests/test_map_web.py。正式內容、週末設定。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import atlas, calendar, mapdata, orders, territory
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import Order


def _game(faction="guan", at="yingchuan"):
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    return game


def _order(game, faction, template, **kw):
    order = Order(id=f"1:{faction}:{template}:x", template=template, faction=faction, week=orders.week_of(game.state, game.content),
                  quota=99, text="", **kw)
    game.state.world.orders = [o for o in game.state.world.orders if not (o.faction == faction and o.template == template)] + [order]
    return order


def _intercept(game, faction, location):
    return _order(game, faction, "intercept", front=territory.line_of(game.content, location), location=location)


def _why(st, loc_id):
    return [text for text, _ in next((g["why"] for g in st["suggest"] if g["id"] == loc_id), [])]


# ── FB-258：截糧只在指定的那一處（FB-248），守不記截糧，自家地盤上的截糧對手是運糧隊 ──


def test_fb258_the_intercept_badge_is_only_on_the_intercept_place():
    game = _game("huang", "huangjin_camp")
    _intercept(game, "huang", "changshe")
    st = game.map_state()
    marked = {k for k, p in st["places"].items() if p["order"] and "截糧" in p["order"]}
    assert marked == orders.intercept_spots(game.content, "changshe") == {"changshe"}


def test_fb258_a_hold_never_gives_intercept_as_the_reason():
    game = _game("guan", "changshe")
    _intercept(game, "guan", "runan_wilds")
    st = game.map_state()
    for g in st["suggest"]:
        if g["sortie"] != "attack":
            assert not any("截糧" in t for t in _why(st, g["id"])), g
    runan = st["places"]["runan_wilds"]
    assert runan["sortie"] == "attack" and "軍令・截糧" in _why(st, "runan_wilds")


def test_fb258_an_intercept_on_your_own_ground_is_against_the_convoy():
    """截糧的地點歸自己（官軍截汝南荒野；輿圖重製第 1 批之前是南陽郊野）：出陣是攻，對手是運糧隊；「打得過嗎」照運糧隊算，站著的隊伍也列它。"""
    game = _game("guan", "yingchuan")
    _intercept(game, "guan", "runan_wilds")
    w, c = game.state.world, game.content
    assert territory.controller(w, c, "runan_wilds") == "guan"
    convoy = c.squads[c.orders.convoy_squads["huang"]]
    st = game.map_state()
    p = st["places"]["runan_wilds"]
    assert p["sortie"] == "attack" and p["odds"] is not None
    assert atlas.ODDS_ORDER.index(p["odds"]["word"]) >= atlas.ODDS_ORDER.index(game.odds(convoy.id))  # 最險的算進糧隊
    assert convoy.name in [q["name"] for q in p["squads"]]
    g = next(g for g in st["suggest"] if g["id"] == "runan_wilds")
    assert g["lose"] == (p["odds"]["word"] == mapdata.LOSE_WORD)


# ── FB-259：豪強攪局不打，不標必敗、不畫淡；理由只寫攪局記得到的（什麼軍令都不記）──


def test_fb259_stirring_is_never_marked_losing_and_counts_no_order():
    game = _game("haoqiang", "haozu_fort")
    _order(game, "haoqiang", "strike", figure=next(iter(game.content.figures)))  # 打擊要挑戰本人，攪局不記
    st = game.map_state()
    assert st["suggest"] and all(g["sortie"] == "stir" for g in st["suggest"])
    for g in st["suggest"]:
        assert g["lose"] is False and not any(t == mapdata.LOSE_WORD or t.startswith("軍令") for t, _ in g["why"]), g


# ── FB-264：版圖變化補「開季」的基準，第 1 週的易手才看得到 ──


def test_fb264_the_first_reckoning_in_week_one_keeps_the_season_start():
    game = _game()
    w, c = game.state.world, game.content
    territory.update(w, c)  # 開季：第一次算
    assert w.territory.weeks[0].control == w.territory.weeks[1].control
    territory.assign(w, c, {"nanyang_huangjin_camp": "guan"})  # 第 1 週就易手（輿圖重製第 1 批：開季歸黃巾的是南陽黃巾營）
    assert w.territory.weeks[0].control["nanyang_huangjin_camp"] == "huang" and w.territory.weeks[1].control["nanyang_huangjin_camp"] == "guan"
    st = game.map_state()
    assert st["start"]["nanyang_huangjin_camp"] == "huang"
    assert {"id": "nanyang_huangjin_camp", "from": "huang", "to": "guan"} in st["weeks"][0]["changed"]
    assert {"week": 1, "from": "huang", "to": "guan"} in st["places"]["nanyang_huangjin_camp"]["flips"]


def test_fb264_a_season_first_reckoned_later_has_no_start():
    """中途上線（第一次算在第 3 週）：沒有開季那一刻的樣子，不假裝有。"""
    game = _game()
    w, c = game.state.world, game.content
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    assert 0 not in w.territory.weeks and game.map_state()["start"] is None
