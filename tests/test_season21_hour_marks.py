"""FB-331：21 天季開季不在整點時，管理者「排時間」與「跳到下一件」要對齊季曆的整點（季的事在季曆整點跑，calendar.next_hour_mark）。
週末與 14 天的季開季本來就在世界秒 0（季曆整點），結果一個字都不變。"""
from __future__ import annotations

import math
import random

from conftest import real_content

from tianxia import calendar
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
OPEN = MON + 3 * HOUR + 20 * 60  # 週一 03:20 開季


def _game(profile="season21", opened=OPEN):
    c = real_content(profile)
    c.config.admins = ["管"]
    c.config.train_event_chance = 0.0
    world = open_world()
    world.seed_first_season(c)
    assert world.open_season(c, opened)
    game = Game.new(c, "管", rng=random.Random(0), world=world)
    game.client = None
    game.sync(opened)  # 開季那一刻已經過了的大事（季曆週一 03:20 之前的）先結算，同伺服器
    return game


def test_hour_ceil_lands_on_the_calendar_hour():
    game = _game()
    c, season = game.content, game.state.world
    mark = calendar.hour_ceil(10.0, c, season)  # 開季後 10 秒：下一個季曆整點是 04:00，40 分鐘後
    assert mark == 40 * 60 - 0 and calendar.stamp_text(mark, c, season) == "第 1 週・週一 04:00"
    assert calendar.hour_ceil(mark, c, season) == mark  # 剛好在整點上：就是這一刻


def test_scheduling_a_showdown_at_nine_reads_nine_and_musters_at_nine():
    game = _game()
    c = game.content
    saturday_nine = MON + 5 * DAY + 21 * HOUR
    msgs = game.admin_schedule("changshe_fire", saturday_nine, OPEN)
    assert any("週六 21:00" in m for m in msgs), msgs
    at = game.state.world.schedule["changshe_fire"]
    assert calendar.stamp_text(at, c, game.state.world) == "第 1 週・週六 21:00"
    assert calendar.next_hour_mark(at - 1, c, game.state.world) == 1  # 這一刻就是季的事跑的那個交界


def test_scheduling_the_finale_past_the_calendar_end_says_how_far_past():
    """FB-439：管理者把季末排到季曆最後一刻之後，季曆時刻停在那一刻，回覆以前照舊寫「排在第 3 週・週日 23:59」，看起來像沒排過去。
    現在寫季曆最後一刻之後多久、現實的日期時刻（台灣）；排在季曆之內照舊。"""
    game = _game()
    later = MON + 23 * DAY + 3 * HOUR  # 第 4 週週一 00:00 之後 2 天 3 小時：2026-11-11 03:00
    msgs = game.admin_schedule("xiaquyang", later, OPEN)
    assert msgs == ["已把下曲陽・季末排在季曆最後一刻（第 3 週・週日 23:59）之後 2 天 3 小時，現實 11/11 03:00。"], msgs
    inside = game.admin_schedule("xiaquyang", MON + 20 * DAY + 18 * HOUR, OPEN)
    assert inside == ["已把下曲陽・季末排在第 3 週・週日 18:00（季曆）。"], inside


def test_jump_next_stops_on_the_calendar_hour_of_the_next_event():
    game = _game()
    stamp = lambda: calendar.stamp_text(game.state.world.time, game.content, game.state.world)  # noqa: E731
    game.admin_jump_next(game.now)  # 起義（週一 00:00，開季之前就到期）在開季後第一個季曆整點結算：04:00，不是 04:20
    assert stamp() == "第 1 週・週一 04:00"
    game.admin_jump_next(game.now)
    assert stamp() == "第 1 週・週二 12:00"
    game.admin_jump_next(game.now)
    assert stamp() == "第 1 週・週三 12:00"


def test_jumping_to_a_scheduled_showdown_opens_the_muster_at_once():
    game = _game()
    game.admin_schedule("changshe_fire", MON + 5 * DAY + 21 * HOUR, OPEN)
    for _ in range(12):
        battle = game.world.get_battle()
        if battle is not None:
            break
        game.admin_jump_next(game.now)
    battle = game.world.get_battle()
    assert battle is not None and battle.phase == "muster"
    assert calendar.stamp_text(game.state.world.time, game.content, game.state.world) == "第 1 週・週六 21:00"


def test_weekend_and_fourteen_day_marks_are_unchanged():
    for profile in (None,):
        c = real_content(profile)
        from tianxia.world_state import fresh_season, stamp_season

        season = fresh_season(c)
        stamp_season(season, c, now=OPEN)
        hour = calendar.cal_hour_seconds(c, season)
        for t in (0.0, 0.3, 123.4, 5000.0, hour, 7 * hour + 0.5):
            assert calendar.hour_ceil(t, c, season) == math.ceil((t - calendar.EPS_SECONDS) / hour) * hour
            assert calendar.hour_floor(t, c, season) == math.floor(t / hour + 1e-9) * hour
