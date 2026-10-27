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
    c = real_content("week7")  # 地盤拔河的舊規則（領地爭奪 PM 2026-10-22 起正式內容打開）
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


def test_fb264_a_season_first_reckoned_later_has_no_start():
    """中途上線（第一次算在第 3 週）：沒有開季那一刻的樣子，不假裝有。"""
    game = _game()
    w, c = game.state.world, game.content
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    assert 0 not in w.territory.weeks and game.map_state()["start"] is None
