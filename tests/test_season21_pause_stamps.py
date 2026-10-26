"""FB-332：21 天季暫停再繼續，季曆對回現實的星期（cal_offset 加上暫停的長度）；以前寫下的時刻（江湖史、傳聞、江湖紀錄、戰報存的
世界秒）照那一刻當時的偏移換成季曆，不跟著往後挪。偏移改過的那一刻記在季裡（WorldState.cal_offset_history），不改資料庫結構。
週末與 14 天的季不受影響。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia import calendar
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
OPEN = MON + 3 * HOUR + 30 * 60  # 週一 03:30 開季
PAUSE = OPEN + 5 * 60  # 03:35 暫停
RESUME = PAUSE + 32.5 * HOUR  # 停了 32.5 小時：週二 12:05 繼續


def _paused_and_resumed(profile="season21"):
    c = real_content(profile)
    c.config.admins = ["管"]
    c.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(c)
    assert store.open_season(c, OPEN)
    game = Game.new(c, "管", rng=random.Random(0), world=store)
    game.client = None
    _at(game, PAUSE)
    game.admin_pause_clock(PAUSE)
    paused_entry = game.state.journal[0]  # 江湖紀錄新的在前面
    _at(game, RESUME)
    game.admin_resume_clock(RESUME)
    return game, paused_entry


def _at(game, now):
    """照伺服器：每一下先補算賽季（暫停中不推），再同步這個角色。"""
    game.world.catch_up_season(game.content, now, random.Random(0))
    game.sync(now)


def _stamp(game, time):
    return calendar.stamp_text(time, game.content, game.state.world)


def test_what_was_written_before_the_pause_keeps_its_time():
    game, paused = _paused_and_resumed()
    assert _stamp(game, 0) == "第 1 週・週一 03:30"  # 開季那一則
    assert _stamp(game, paused.time) == "第 1 週・週一 03:35"  # 按暫停的那一則


def test_what_happens_after_the_resume_reads_the_real_week():
    game, _ = _paused_and_resumed()
    season = game.state.world
    assert _stamp(game, season.time) == "第 1 週・週二 12:05"
    resumed = game.state.journal[0]
    assert resumed.title == "繼續賽季"
    assert _stamp(game, resumed.time) == "第 1 週・週二 12:05"
    court = season.timeline["court_mobilizes"]  # 週二 12:00 的朝廷出兵在繼續那一刻結算
    assert _stamp(game, court.time) == "第 1 週・週二 12:05"


def test_the_offset_history_lives_in_the_season():
    game, _ = _paused_and_resumed()
    season = game.world.get_season()
    assert len(season.cal_offset_history) == 1
    until, old = season.cal_offset_history[0]
    assert old == 3.5 * HOUR and season.cal_offset == old + 32.5 * HOUR


def test_two_pauses_stack_without_moving_the_first_entries():
    game, paused = _paused_and_resumed()
    second = RESUME + 2 * HOUR
    _at(game, second)
    game.admin_pause_clock(second)
    _at(game, second + HOUR)
    game.admin_resume_clock(second + HOUR)
    assert _stamp(game, 0) == "第 1 週・週一 03:30" and _stamp(game, paused.time) == "第 1 週・週一 03:35"
    assert _stamp(game, game.state.world.time) == "第 1 週・週二 15:05"
