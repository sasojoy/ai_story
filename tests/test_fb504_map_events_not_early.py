"""FB-504（7 天濃縮季第二輪，PM 2026-10-20）：輿圖「這一段大事」「天下怎麼變」把還沒發生的大事提早列出（第 1 天就列出長社火攻）。
mapdata._titles 用 calendar.event_time：時刻表決戰只寫了星期與鐘點（day 是 0），被當成那一週（段）第一天就到了；季末也一樣。
修成照這一件真正的時刻（timetable.when_in：決戰照 WorldState.schedule，季末照排定的季末，其餘照季曆）判斷到了沒。21 天季同一個錯
（決戰從那一週週一、季末從第 3 週週一就列出來），一起修。
週末（PM 2026-10-20 改修）同一個錯：FB-504 當時 PM 定週末一字不變所以沒動，週末的決戰那一週週一 00:00 就列出那一場，季末在最後一週週一就列出；
現在週末也照 timetable.when_in 判斷到了沒（決戰照排定的時刻、季末照排定的季末，其餘照季曆，跟 21 天季、7 天季同一個寫法）。
週末除了決戰與季末，其他大事列的時刻一個字都不變。"""
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


def _weekend():
    cw = real_content("week7")
    return cw, fb501._state(cw)


def test_weekend_does_not_list_the_changshe_battle_on_its_week_monday():
    """修前重現：週末第 6 週週一 00:00 起「這一段大事」就列出長社火攻（週四 20:00 才開集結）。"""
    cw, state = _weekend()
    changshe = next(e for e in cw.timetable if e.id == "changshe_fire")
    battle = timetable.when_in(state.world, cw, changshe)
    monday = calendar.week_start(changshe.week, cw, state.world)
    assert monday < battle
    # 改之前的寫法（calendar.event_time）：決戰的 day 是 0，那一週一開始就到了
    assert calendar.event_time(changshe, cw, state.world) <= monday + 1
    for at in (monday + 60, (monday + battle) / 2, battle - 60):
        state.world.time = at
        week = calendar.point(at, cw, state.world).week
        assert week == changshe.week
        assert "長社火攻" not in mapdata._titles(state, cw, week, week), at
    state.world.time = battle
    assert "長社火攻" in mapdata._titles(state, cw, changshe.week, changshe.week)


def test_weekend_follows_the_schedule_the_admin_moved():
    """管理者把長社往後排：照排的時刻，預設的時刻到了也不列；排的時刻到了才列。"""
    cw, state = _weekend()
    changshe = next(e for e in cw.timetable if e.id == "changshe_fire")
    default = timetable.when_in(state.world, cw, changshe)
    later = default + 7200  # 往後排兩個現實小時（週末一週是 5 小時，仍在第 6 週裡）
    state.world.schedule["changshe_fire"] = later
    for at, listed in ((default, False), (later - 60, False), (later, True)):
        state.world.time = at
        week = calendar.point(at, cw, state.world).week
        assert week == changshe.week
        assert ("長社火攻" in mapdata._titles(state, cw, week, week)) is listed, at


def test_weekend_lists_the_finale_only_after_the_season_end():
    """修前重現：週末最後一週（第 12 週）週一 00:00 起就列出「下曲陽・季末」；現在要等到排定的季末。"""
    cw, state = _weekend()
    finale = next(e for e in cw.timetable if e.kind == "finale")
    end = timetable.when_in(state.world, cw, finale)
    monday = calendar.week_start(finale.week, cw, state.world)
    assert monday < end
    assert calendar.event_time(finale, cw, state.world) <= monday + 1  # 改之前的寫法：那一週一開始就到了
    for at in (monday + 60, (monday + end) / 2, end - 60):
        state.world.time = at
        week = calendar.point(at, cw, state.world).week
        assert week == finale.week
        assert "下曲陽・季末" not in mapdata._titles(state, cw, week, week), at
    state.world.time = end
    assert "下曲陽・季末" in mapdata._titles(state, cw, finale.week, finale.week)
    # 管理者把季末往後排：排的時刻到了才列
    state.world.schedule["finale"] = end + 3600
    state.world.time = end + 60
    assert "下曲陽・季末" not in mapdata._titles(state, cw, finale.week, finale.week)
    state.world.time = end + 3600
    assert "下曲陽・季末" in mapdata._titles(state, cw, finale.week, finale.week)


def test_weekend_past_weeks_list_the_battle_once_it_has_happened():
    """「天下怎麼變」逐週列大事：以前的週列的是已經打過的決戰（過了排定的時刻），管理者往後排到還沒到的不列。"""
    cw, state = _weekend()
    guangzong = next(e for e in cw.timetable if e.id == "guangzong")
    battle = timetable.when_in(state.world, cw, guangzong)
    monday = calendar.week_start(guangzong.week + 1, cw, state.world)
    assert battle < monday
    state.world.time = monday + 60
    assert "廣宗決戰" in mapdata._titles(state, cw, guangzong.week, guangzong.week + 1)
    state.world.schedule["guangzong"] = monday + 3600  # 管理者往後排到下一週
    assert "廣宗決戰" not in mapdata._titles(state, cw, guangzong.week, guangzong.week + 1)


def test_weekend_changes_only_the_showdowns_and_the_finale():
    """週末除了決戰與季末，每一刻列出來的大事跟改之前的寫法（以前的週全列、這一週照 calendar.event_time）一模一樣；
    決戰與季末照 timetable.when_in。整季從頭到尾每 20 分鐘看一次（現實 20 分鐘 ≈ 11 季曆小時，每一週都跨得到）。"""
    cw, state = _weekend()
    special = {e.title for e in cw.timetable if e.kind in ("showdown", "finale")}
    assert special == {"長社火攻", "宛城之戰", "廣宗決戰", "下曲陽・季末"}
    end = calendar.nominal_end(cw, state.world)
    at = 0.0
    seen_special = 0
    while at <= end:
        state.world.time = at
        now_week = calendar.point(at, cw, state.world).week
        for week in range(1, now_week + 1):
            new = mapdata._titles(state, cw, week, now_week)
            old = [e.title for e in timetable.events(state.world, cw)
                   if e.week == week and (week < now_week or calendar.event_time(e, cw, state.world) <= at)]
            assert [t for t in new if t not in special] == [t for t in old if t not in special], (at, week)
            due = [e.title for e in timetable.events(state.world, cw)
                   if e.week == week and e.title in special and timetable.when_in(state.world, cw, e) <= at]
            assert [t for t in new if t in special] == due, (at, week)
            seen_special += len(due)
        at += 1200
    assert seen_special > 0


def test_the_fourteen_day_season_has_no_timetable_in_the_map():
    """14 天的預設季沒有第一季規則，輿圖沒有這一段大事（跟以前一樣）。"""
    c14 = real_content()
    state = fb501._state(c14)
    state.world.time = 6 * DAY
    assert mapdata._titles(state, c14, 6, 6) == []
