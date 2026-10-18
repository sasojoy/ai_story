"""正式季第 5 批：21 天的季（season21）每天一道軍令、每天一批懸賞、懸賞照等級長、推線的速度（正式季整合設計第七章、6.1）。
週末與 14 天的季一個字都不變。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia import calendar, orders, push, world
from tianxia.world_state import fresh_season, stamp_season

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
WED = 1792549800  # 2026-10-21 週三 10:30（台灣）


def _vehicle(content, now=MON):
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    world.settle_season_start(season, content, random.Random(0))
    return world._season_vehicle(content, season)


def _advance(vehicle, content, to):
    world.advance_world_state(vehicle.world, content, to - vehicle.world.time, random.Random(0))


def _live(vehicle, faction=None):
    return [o for o in vehicle.world.orders if not o.done and (faction is None or o.faction == faction)]


# ── Task 1：每天一道軍令 ──


def test_each_day_issues_one_order_per_faction():
    c = real_content("season21")
    v = _vehicle(c)
    factions = {o.faction for o in _live(v)}
    assert {"guan", "huang"} <= factions
    assert all(len(_live(v, f)) == c.config.season21_daily.orders_per_day for f in factions)
    assert {o.week for o in _live(v)} == {1}  # 21 天季的軍令照「期」記：季曆第幾天
    assert any(r.text.startswith(orders.ISSUED_DAY) for r in v.world.rumors if r.layer == "faction")
    _advance(v, c, DAY + 60)
    assert {o.week for o in _live(v)} == {2}  # 第 1 天沒達成的清掉


def test_daily_orders_take_turns():
    c = real_content("season21")
    v = _vehicle(c)
    kinds = []
    for day in range(3):
        _advance(v, c, day * DAY + 60)
        kinds += [o.template for o in _live(v, "guan")]
    assert len(set(kinds)) >= 2  # 守、進攻、補給輪流


def test_a_daily_order_applies_a_share_of_its_effect():
    c = real_content("season21")
    v = _vehicle(c)
    o = next(o for o in _live(v, "guan") if o.template in ("siege", "defend", "intercept", "escort"))
    nominal = orders.template_of(c, o).effect.trend
    orders._complete(v, c, o)
    assert o.applied == push.round_half_away(nominal * c.config.season21_daily.order_effect_share)


def test_the_order_card_says_midnight():
    c = real_content("season21")
    v = _vehicle(c)
    o = _live(v, "guan")[0]
    assert calendar.stamp_text(orders.deadline(v, c, o), c, v.world) == "第 1 週・週二 00:00"


def test_a_wednesday_opening_and_a_long_catch_up_issue_only_today():
    """Review Focus 1、2：週三開季只發第 3 天的；一次補算跨過好幾天只發今天的。"""
    c = real_content("season21")
    v = _vehicle(c, now=WED)
    assert {o.week for o in v.world.orders} == {3}
    _advance(v, c, 4 * DAY)  # 開季後四天：第 7 天（週日）
    assert {o.week for o in _live(v)} == {calendar.point(v.world.time, c, v.world).cal_day}
    assert not any(o.week in (4, 5, 6) for o in v.world.orders)


def test_weekend_orders_are_weekly():
    """Review Focus 5：週末的季照舊每週一發、一週最多 orders_per_week 道，寫「本週軍令：」。"""
    c = real_content("weekend")
    v = _vehicle(c)
    assert {o.week for o in v.world.orders} == {1}
    assert all(len(_live(v, f)) <= c.config.orders_per_week for f in ("guan", "huang"))
    assert any(r.text.startswith(orders.ISSUED) for r in v.world.rumors if r.layer == "faction")
    assert not any(r.text.startswith(orders.ISSUED_DAY) for r in v.world.rumors)


def _game(profile="season21", opened=MON):
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = real_content(profile)
    c.config.admins = ["甲"]
    c.config.train_event_chance = 0.0
    w = open_world()
    w.seed_first_season(c)
    game = Game.new(c, "甲", rng=random.Random(0), world=w)
    game.client = None
    game.admin_open_season(opened)  # 同管理者開季：開季那一刻的掛鉤（軍令、懸賞）照跑
    game.state.player.faction = "guan"
    game.sync(opened)
    return game


def test_the_orders_card_reopens_each_day():
    """21 天季的軍令每天一道：軍令卡收起來照「第幾天」記（status.calendar.day），隔天的新軍令重新展開；週末照週記、沒有 day。"""
    import server
    from test_prologue_web import run, with_reveal

    game = _game()
    assert game.status_data()["calendar"]["day"] == 1
    m = with_reveal(server.main_view(game), ["all"])
    shut = run(m, "return H.pageJianghu();", S={"ordersShut": 1})
    assert 'class="fold orders" data-week="1" >' in shut  # 今天收起來的照舊收著
    game.sync(MON + DAY + 60)
    m = with_reveal(server.main_view(game), ["all"])
    reopened = run(m, "return H.pageJianghu();", S={"ordersShut": 1})
    assert 'class="fold orders" data-week="2" open>' in reopened  # 隔天的新軍令展開
    assert "day" not in _game("weekend").status_data()["calendar"]
