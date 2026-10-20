"""領地爭奪：每天 22:00 換天的掛鉤（Game._conquest_tick → conquest_day.day_turn）。翻地與爭搶（輿圖簡化設計 4.4，PM 2026-10-20 第 1、2 條）之後
投票與 22:00 的公告結算拿掉了：換天只作罷前幾天沒開成的攻城、清掉打完的，不再自己排攻城；這個掛鉤留著給〈天下形勢〉每天一篇。
日子只准往前走（Review Focus 2）；暫停繼續時還沒開的攻城照原本的現實時間挪；軍令照「此刻進度最高的那一塊」列與記；救場。"""
from __future__ import annotations

import calendar as pycal
from datetime import datetime

import pytest

from conquest_kit import announce, conquest_game, join, plain_game
from tianxia import conquest, conquest_day, howto, orders
from tianxia.state import Order
from tianxia.world import keep_showdowns_on_time

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _tw(y, mo, d, h, mi=0) -> float:
    """台灣時間 → 現實 epoch 秒。"""
    return float(pycal.timegm(datetime(y, mo, d, h, mi).timetuple())) - 8 * 3600


def _game(now: float, name: str = "沈浪", world=None):
    game = join(conquest_game("season21", name=name, world=world), "huang")
    game.now = now
    return game


def _tick(game, now: float):
    game.now = now
    game._conquest_tick()
    game.state.world = game.world.get_season()
    return game.state.world.conquest


def test_first_sync_only_records_the_key():
    game = _game(_tw(2026, 10, 20, 10))
    state = _tick(game, game.now)
    assert state.settled_key == conquest_day.day_key(game.now, game.content.config)
    assert state.schedule == []
    assert not [r for r in game.state.world.rumors if "攻" in r.text and r.layer == "world"]


def test_the_day_turns_once_and_never_schedules_sieges_by_itself():
    game = _game(_tw(2026, 10, 20, 10))
    _tick(game, game.now)
    state = _tick(game, _tw(2026, 10, 20, 22, 1))  # 換天
    assert state.settled_key == conquest_day.day_key(game.now, game.content.config)
    assert state.schedule == [] and state.day_log == []  # 沒有主將定奪、沒有投票：沒人下戰書就照推
    assert not [r for r in game.state.world.rumors if r.layer == "world" and "攻" in r.text]
    again = _tick(game, _tw(2026, 10, 20, 23))
    assert again.settled_key == state.settled_key


def test_settle_only_moves_forward():
    a = _game(_tw(2026, 10, 20, 10), name="甲某")
    _tick(a, a.now)
    b = _game(_tw(2026, 10, 20, 10), name="乙某", world=a.world)
    b.advanced_real = 86400.0  # b 快轉過一天：它認為已經是明天
    _tick(b, _tw(2026, 10, 20, 22, 1))  # b 的「今天」是 10/21 22:01
    ahead = a.world.get_season().conquest
    a.state.world = a.world.get_season()
    slot = announce(a, "hilltop_wilds", "huang")
    slot.key = ahead.settled_key
    a._save_season()
    behind = _tick(a, _tw(2026, 10, 20, 22, 1))  # a 天數小：不倒退、不作罷今天的
    assert behind.settled_key == ahead.settled_key
    assert [s.status for s in behind.schedule] == ["planned"]


def test_switch_off_tick_never_touches_world():
    game = join(plain_game("season21"), "huang")
    before = game.state.world.model_dump_json()
    game.now = _tw(2026, 10, 20, 22, 1)
    assert game._conquest_tick() == []
    assert game.state.world.conquest is None
    assert before == game.state.world.model_dump_json()


def test_sync_and_world_tick_turn_the_day():
    game = _game(_tw(2026, 10, 20, 10))
    game.sync(game.now)
    game.sync(game.now + 60)  # 季推進一下（第一次推進才算地盤、領地爭奪）
    assert game.state.world.conquest.settled_key == conquest_day.day_key(game.now, game.content.config)
    from tianxia.engine import Game

    ticker = Game.for_world(game.content, game.world)
    ticker.world_tick(_tw(2026, 10, 20, 22, 1))
    assert game.world.get_season().conquest.settled_key == conquest_day.day_key(_tw(2026, 10, 20, 22, 1), game.content.config)


def test_admin_letter_opens_soon_and_cancel_voids_it():
    game = _game(_tw(2026, 10, 20, 23), name="Rayal")
    _tick(game, game.now)
    msgs = game.admin_conquest_letter("hilltop_wilds", "huang")
    state = game.world.get_season().conquest
    assert len(state.schedule) == 1 and msgs and "攻荒丘" in msgs[0]
    w = game.world.get_season()
    assert state.schedule[0].muster_at - w.time <= 60  # 集結馬上開
    game.admin_conquest_cancel(state.schedule[0].id)
    assert game.world.get_season().conquest.schedule[0].status == "void"


def test_resume_shifts_planned_slots():
    game = _game(_tw(2026, 10, 20, 10))
    _tick(game, game.now)
    announce(game, "hilltop_wilds", "huang")
    season = game.state.world
    before = [(s.at, s.muster_at) for s in season.conquest.schedule]
    keep_showdowns_on_time(season, game.content, 600.0, season.time)
    assert [(s.at, s.muster_at) for s in season.conquest.schedule] == [(a - 600, m - 600) for a, m in before]


def test_siege_and_defend_orders_follow_the_highest_block():
    game = _game(_tw(2026, 10, 20, 10))
    w, c = game.state.world, game.content
    assert orders.siege_places(c, "huang", "yingru", w) == ["hilltop_wilds"]  # 潁川汝南黃巾推得動的只有荒丘（全是 0：每一塊都算）
    held = [loc for loc in conquest.blocks(c) if conquest.capturable(c, loc) and conquest.holder(w, c, loc) == "guan"
            and conquest.line_of(w, c, loc) == "yingru"]
    week = orders.period_of(game.state, c)
    w.orders.append(Order(id="d1", template="defend", faction="guan", week=week, front="yingru", quota=5, text="守"))
    assert not any(orders.duty_counts(game.state, c, "guan", loc) for loc in held)  # 沒人在推官軍的地方：沒有可守的
    conquest.push(w, c, held[0], "huang", "某", 20, "attack")
    conquest.push(w, c, held[1], "huang", "某", 30, "attack")
    assert orders.duty_counts(game.state, c, "guan", held[1])  # 被推得最高的那一塊
    assert not orders.duty_counts(game.state, c, "guan", held[0])


def test_howto_has_the_flip_rules():
    game = conquest_game("season21")
    lines = " ".join(howto.territory_lines(game.content, True, game.state.world))
    assert "推滿" in lines and "戰書" in lines and "投票" not in lines
