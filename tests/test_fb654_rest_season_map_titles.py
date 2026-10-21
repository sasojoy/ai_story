"""FB-654（QA develop 小單 FB-635、636，2026-10-21）：休季時換上新程式、到開下一季之前，輿圖每一週列的大事標題照上一季自己發生過的。

FB-635 只修了季曆（第幾週、一共幾週）：線上那一季是舊程式的 week7（週末式季曆、一天壓成 12 個季曆天），新程式的 week7 是照現實天分三段。
輿圖每一週的大事標題（`mapdata._titles`）還走新程式的時刻表（`content.timetable`，載入時已經換成新程式的週次與日子）：
舊季跑 1.2 天的時候舊程式寫第 1 週「三十六方起義」、第 2 週「朝廷出兵」、第 3 週「張曼成攻殺南陽太守」；新程式的時刻表把前四件全擠進
第 1 週，再列「盧植圍廣宗」「秦頡斬張曼成」在第 2 週——舊季沒發生過的。新程式的時刻表沒有舊季那一份的週次可借
（`content.season21_timetable` 載入時就換掉了），所以不是「換一份時刻表」，而是這一季真正結算過的才列：休季時換了程式的上一季
（`calendar.weekend_style`）一般大事看 `season.timeline`，時刻是結算那一刻，歸週走這一季自己的季曆；決戰與季末的排定時刻本來就存在這一季
的 `schedule`，照舊。還在跑的季、新程式自己開的季、週末與 14 天的程式一個字都不變。
"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import calendar, mapdata, timetable
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.world_state import fresh_season, stamp_season

pytestmark = pytest.mark.slow  # 載真實內容、開一季、跑好幾天

DAY = 86400
T0 = 1_800_000_000.0
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
SPANS = [0.2, 1.2, 3.7, 6.9]  # 舊季跑了幾天就被收季：只有起義、前三件、決戰那一週、幾乎整季


def _old_season(span: float):
    """舊程式的 week7：週末設定、季長 7 天，從開季照時間一路補算到 span 天，再由管理者收季（休季）。回 (舊內容, 世界, 舊程式的 Game)。"""
    old = real_content("weekend")
    old.config.season_days = 7
    old.config.auto_open_first_season = True
    world = open_world()
    admin = Game.new(old, "Rayal", rng=random.Random(0), world=world)
    admin.sync(T0)
    world.catch_up_season(old, T0 + span * DAY / old.config.time_scale, random.Random(0))
    admin.state.world = world.get_season()
    assert not world.get_season().season21 and not world.get_season().ended
    return old, world, admin


def _by_week(game: Game, content, world) -> dict[int, list[str]]:
    state = game.state
    state.world = world.get_season()
    now_week = min(calendar.point(state.world.time, content, state.world).week, calendar.weeks(content, state.world))
    return {week: mapdata._titles(state, content, week, now_week) for week in range(1, now_week + 1)}


@pytest.mark.parametrize("span", SPANS)
def test_a_rested_old_season_lists_what_happened_in_it_under_the_new_program(span):
    old, world, admin = _old_season(span)
    admin.admin_end_season(T0 + 100.0)
    assert world.season_phase() == "resting"
    expect = _by_week(admin, old, world)  # 舊程式自己列的
    new = real_content("week7")
    after = Game.for_world(new, world)
    got = _by_week(after, new, world)
    assert got == expect, (span, got, expect)
    old_map, new_map = admin.map_state(), after.map_state()
    assert [w["events"] for w in new_map["weeks"]] == [w["events"] for w in old_map["weeks"]] == [expect[w] for w in sorted(expect)]
    assert new_map["events"] == old_map["events"]


def test_the_repro_from_the_feedback_row():
    """單上的重現：舊 week7 開季、跑約 1.2 天、收季，換這一版 week7（不開下一季）。修之前第 1 週列了四件、第 2 週列了「盧植圍廣宗、秦頡斬張曼成」。"""
    old, world, admin = _old_season(1.2)
    admin.admin_end_season(T0 + 100.0)
    after = Game.for_world(real_content("week7"), world)
    overlay = after.map_state()
    assert overlay["now_week"] == 3 and overlay["weeks_total"] == 12  # FB-635 修的，照舊
    assert [(w["week"], w["events"]) for w in overlay["weeks"]] == [
        (1, ["三十六方起義"]), (2, ["朝廷出兵"]), (3, ["張曼成攻殺南陽太守"])]
    assert overlay["events"] == ["張曼成攻殺南陽太守"]


def test_events_that_never_settled_in_the_old_season_are_never_listed():
    old, world, admin = _old_season(1.2)
    admin.admin_end_season(T0 + 100.0)
    new = real_content("week7")
    season = world.get_season()
    assert calendar.weekend_style(season, new)
    for event in new.timetable:
        at = timetable.happened_at(season, new, event)
        if event.kind == "finale":  # 季末的排定時刻存在這一季的 schedule 裡，照舊
            assert at == timetable.when_in(season, new, event) == season.schedule["finale"]
        elif event.kind == "showdown":  # 決戰同：還沒開打的就是這一季存的排定時刻（schedule），不是新程式的預設
            assert event.id in season.timeline or at == season.schedule[event.id] != timetable.NEVER
        elif event.id in season.timeline:
            assert at == season.timeline[event.id].time
            assert timetable.happened_week(season, new, event) == calendar.point(at, new, season).week
        else:
            assert at == timetable.NEVER, event.id


def test_a_season_still_running_is_left_alone():
    """只管休季（同 FB-635）：還在跑的舊季，時刻表與曆時交界還是照新設定在跑，標題也照舊（新程式的時刻表）。"""
    old, world, admin = _old_season(1.2)
    new = real_content("week7")
    season = world.get_season()
    assert not season.ended and not calendar.weekend_style(season, new)
    for event in new.timetable:
        if event.kind not in timetable.NOT_BY_SEASON_HOUR:
            assert timetable.happened_at(season, new, event) == timetable.when_in(season, new, event)
            assert timetable.happened_week(season, new, event) == event.week


def test_a_season_the_new_program_opened_is_left_alone():
    new = real_content("week7")
    season = fresh_season(new)
    stamp_season(season, new, now=MON)
    season.time = 2.5 * DAY
    season.ended = True  # 收了季也一樣：蓋了 season21 的章，照段、照新程式的時刻表
    assert season.season21 and not calendar.weekend_style(season, new)
    for event in new.timetable:
        if event.kind not in timetable.NOT_BY_SEASON_HOUR:
            assert timetable.happened_at(season, new, event) == timetable.when_in(season, new, event)
            assert timetable.happened_week(season, new, event) == event.week


@pytest.mark.parametrize("profile", ["weekend", None])
def test_programs_that_were_never_on_the_real_day_frame_see_no_change(profile):
    content = real_content(profile)
    season = fresh_season(content)
    stamp_season(season, content, now=MON)
    season.time = 20 * DAY
    season.ended = True
    assert not calendar.weekend_style(season, content)
    for event in content.timetable:
        if event.kind not in timetable.NOT_BY_SEASON_HOUR:
            assert timetable.happened_at(season, content, event) == timetable.when_in(season, content, event)
            assert timetable.happened_week(season, content, event) == event.week
