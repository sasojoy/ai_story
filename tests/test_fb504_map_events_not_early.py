"""FB-504（7 天濃縮季第二輪，PM 2026-10-20）：輿圖「這一段大事」「天下怎麼變」把還沒發生的大事提早列出（第 1 天就列出長社火攻）。
mapdata._titles 用 calendar.event_time：時刻表決戰只寫了星期與鐘點（day 是 0），被當成那一週（段）第一天就到了；季末也一樣。
修成照這一件真正的時刻（timetable.when_in：決戰照 WorldState.schedule，季末照排定的季末，其餘照季曆）判斷到了沒。21 天季同一個錯
（決戰從那一週週一、季末從第 3 週週一就列出來），一起修。週末照舊（同一個寫法在週末也會在決戰那一週的週一就列出來，PM 定週末一字不變，
回報另列）。"""
from __future__ import annotations

import pytest
import test_fb501_week7_words as fb501
from conftest import real_content

from tianxia import calendar, mapdata, timetable

pytestmark = pytest.mark.slow  # 每一條都載真實內容、開一季

HOUR, DAY = 3600, 86400


def _titles(content, at):
    state = fb501._state(content)
    state.world.time = at
    now_week = calendar.point(at, content, state.world).week
    return mapdata._titles(state, content, now_week, now_week), state


def test_week7_day_one_does_not_list_the_changshe_battle():
    """修前重現：00:00 開的 7 天季第 1 天 13:00，「這一段大事」已經列出長社火攻（第 2 天 20:00 才開集結）。"""
    c7 = real_content("week7")
    titles, state = _titles(c7, 13 * HOUR)
    assert "三十六方起義" in titles and "朝廷出兵" in titles
    assert "長社火攻" not in titles
    titles, _ = _titles(c7, DAY + 20 * HOUR - 60)  # 第 2 天 19:59：還沒
    assert "長社火攻" not in titles
    titles, _ = _titles(c7, DAY + 20 * HOUR)  # 第 2 天 20:00：照排定的時刻到了
    assert "長社火攻" in titles


def test_week7_follows_the_schedule_the_admin_moved():
    """管理者把長社往後排到第 2 天 23:00：照排的時刻，20:00 還不列。"""
    c7 = real_content("week7")
    state = fb501._state(c7)
    state.world.schedule["changshe_fire"] = DAY + 23 * HOUR
    state.world.time = DAY + 21 * HOUR
    assert "長社火攻" not in mapdata._titles(state, c7, 1, 1)
    state.world.time = DAY + 23 * HOUR
    assert "長社火攻" in mapdata._titles(state, c7, 1, 1)


def test_week7_last_segment_lists_the_finale_only_after_the_season_end():
    c7 = real_content("week7")
    titles, _ = _titles(c7, 4 * DAY + HOUR)  # 第 5 天 01:00：第 3 段
    assert "廣宗決戰" not in titles and "下曲陽・季末" not in titles


def test_season21_lists_the_saturday_battle_only_on_saturday_night():
    """21 天季同一個錯：週一開的季第 1 週週四 13:00，修前已經列出長社火攻（週六 20:00）。"""
    c21 = real_content("season21")
    titles, _ = _titles(c21, 3 * DAY + 13 * HOUR)
    assert "波才大敗朱儁" in titles and "長社火攻" not in titles
    titles, _ = _titles(c21, 5 * DAY + 20 * HOUR)
    assert "長社火攻" in titles
    titles, _ = _titles(c21, 14 * DAY + 13 * HOUR)  # 第 3 週週一 13:00
    assert "盧植下獄" in titles and "廣宗決戰" not in titles and "下曲陽・季末" not in titles


def test_the_weekend_season_reads_as_before():
    """週末（不是照現實天的季）照舊：決戰那一週的每一刻，列出來的跟改之前的寫法（calendar.event_time）一模一樣。"""
    cw = real_content("weekend")
    state = fb501._state(cw)
    changshe = next(e for e in cw.timetable if e.id == "changshe_fire")
    start = calendar.week_start(changshe.week, cw, state.world)
    for k in range(0, 8):
        at = start + k * calendar.WEEK / 8 / calendar.cal_scale(cw, state.world)
        state.world.time = at
        week = calendar.point(at, cw, state.world).week
        old = [e.title for e in timetable.events(state.world, cw)
               if e.week == week and calendar.event_time(e, cw, state.world) <= at]
        assert mapdata._titles(state, cw, week, week) == old, k
