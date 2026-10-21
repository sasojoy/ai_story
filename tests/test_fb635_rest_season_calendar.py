"""FB-635（QA 上線前整合預演，2026-10-21）：休季時換上新程式、到開下一季之前，上一季的時刻全照新季曆寫。

線上那一季是舊程式的 week7（週末式季曆：12 週、每週 7 天，一天現實壓成 12 個季曆天，章上 season21 是 false）；新程式的 week7 是
照現實天、分三段（season21 開著、season_weeks 3、season_segments [2, 2, 3]）。季曆的週數與段不蓋在季上（calendar._week_days
「只看設定」），所以新程式拿自己的設定去算上一季的時刻：同一刻舊程式寫「第 3 週・週一 09:36」，新程式寫「第 1 週・週二 04:48」，
江湖紀錄裡上一季的每一則一起改。修法：這一季開季時沒蓋 season21 的章、設定卻是照現實天的，這一季的季曆一律照週末式（12 週）。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import calendar
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.world_state import fresh_season, stamp_season

pytestmark = pytest.mark.slow  # 載真實內容、開一季

DAY = 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
WED14 = 1792549800 + 3.5 * 3600  # 2026-10-21 週三 14:00（台灣）
TIMES = [0, 1, 3600, 5 * 3600, DAY / 2, DAY, 1.2 * DAY, 2.5 * DAY, 3.7 * DAY, 6.99 * DAY, 7 * DAY, 9 * DAY]


def _old_week7(now: float = MON, *, rested: bool = True):
    """舊程式的 week7：週末設定、季長 7 天（章上 season21 是 false），以及開出來的那一季（預設已經休季：收了季、還沒開下一季）。"""
    old = real_content("weekend")
    old.config.season_days = 7
    season = fresh_season(old)
    stamp_season(season, old, now=now)
    assert not season.season21 and season.length_days == 7
    season.ended = rested
    return old, season


def test_the_new_week7_program_reads_an_old_week7_season_with_the_calendar_it_ran_on():
    """同一季、同一個世界秒：新程式（照現實天）算出來的跟舊程式（週末式）一模一樣——點、週初、季曆最後一刻、夜裡、第幾天。"""
    old, season = _old_week7()
    new = real_content("week7")
    assert new.config.season21 and new.config.season_segments == [2, 2, 3]
    assert calendar.total_days(new, season) == calendar.total_days(old, season) == 84
    assert calendar.cal_scale(new, season) == calendar.cal_scale(old, season) == 12
    assert calendar.weeks(new, season) == calendar.weeks(old, season) == 12
    assert calendar.calendar_end(new, season) == calendar.calendar_end(old, season)
    for week in range(1, 14):
        assert calendar.week_start(week, new, season) == calendar.week_start(week, old, season), week
    for t in TIMES:
        assert calendar.point(t, new, season) == calendar.point(t, old, season), t
        assert calendar.stamp_text(t, new, season) == calendar.stamp_text(t, old, season), t
        assert calendar.is_night(t, new, season) == calendar.is_night(t, old, season), t
        assert calendar.day_index(t, new, season) == calendar.day_index(t, old, season), t
    assert calendar.stamp_text(1.2 * DAY, new, season) == "第 3 週・週一 09:36"  # 單上重現的那一刻（修之前是「第 1 週・週二 04:48」）
    assert not calendar.week7_on(season, new)  # 這一季沒有段：寫「第 N 天」的字只給蓋了章的 7 天季


def test_an_afternoon_opened_old_season_does_not_change_either():
    """舊程式的季曆沒有開季偏移（cal_offset 0）；週三下午開的舊季，新程式也不加偏移。"""
    old, season = _old_week7(now=WED14)
    new = real_content("week7")
    assert season.cal_offset == 0
    for t in TIMES:
        assert calendar.stamp_text(t, new, season) == calendar.stamp_text(t, old, season), t


def test_a_season_still_running_is_left_alone():
    """只管休季：還在跑的舊季（季中換了程式，啟動時 profile_warning 印那一行的那一種）時刻表與曆時交界還是照新設定在跑，
    只換畫面會讓畫面和大事對不上——跟這一批之前一字不差（照新設定算：7 天、三段、cal_scale 1）。"""
    old, season = _old_week7(rested=False)
    new = real_content("week7")
    assert not season.ended and not calendar.weekend_style(season, new)
    assert calendar.total_days(new, season) == 7 and calendar.weeks(new, season) == 3 and calendar.cal_scale(new, season) == 1
    assert calendar.stamp_text(1.2 * DAY, new, season) == "第 1 週・週二 04:48"  # 修之前單上寫的那一個，照舊
    season.ended = True  # 同一季收了，才換成它自己的季曆
    assert calendar.weekend_style(season, new)
    assert calendar.stamp_text(1.2 * DAY, new, season) == calendar.stamp_text(1.2 * DAY, old, season)


def test_a_season_stamped_under_week7_keeps_the_segments():
    """反過來：新程式自己開的 7 天季（蓋了 season21 的章）照段算，不是週末式；21 天季的章配 week7 設定（兩個程式帶錯設定，
    FB-520 那一行警告管的）也不在這一條裡動——只有「沒蓋章、設定卻是照現實天」才換成週末式。"""
    new = real_content("week7")
    season = fresh_season(new)
    stamp_season(season, new, now=MON)
    assert season.season21 and calendar.week7_on(season, new)
    assert calendar.total_days(new, season) == 7 and calendar.cal_scale(new, season) == 1
    assert calendar.weeks(new, season) == 3
    assert calendar.stamp_text(2 * DAY, new, season) == "第 3 天 00:00"
    c21 = real_content("season21")
    s21 = fresh_season(c21)
    stamp_season(s21, c21, now=MON)
    assert calendar.total_days(new, s21) == 7 and calendar.weeks(new, s21) == 3


def test_programs_that_were_never_on_the_real_day_frame_see_no_change():
    """設定沒開 season21 的程式（週末、14 天）不看章：總天數、週數跟以前一樣（84、12）。"""
    for profile in ("weekend", None):
        content = real_content(profile)
        season = fresh_season(content)
        stamp_season(season, content, now=MON)
        assert calendar.total_days(content, season) == calendar.total_days(content) == 84
        assert calendar.weeks(content, season) == 12


def test_the_status_line_and_the_journal_stamp_of_a_rested_old_season_survive_the_new_program():
    """單上的重現步驟：舊 week7 開季、跑 1.2 天、管理者收季（休季），換新 week7 開同一份資料庫——狀態列與 Game.stamp 寫的時刻
    （江湖紀錄、江湖史、傳聞、戰報都走它）跟舊程式同一刻寫的一字不差；開了下一季就照新季曆。"""
    old, _ = _old_week7()
    old.config.auto_open_first_season = True
    new = real_content("week7")
    world = open_world()
    admin = Game.new(old, "Rayal", rng=random.Random(0), world=world)
    admin.sync(1_800_000_000.0)
    world.mutate_season(lambda s: setattr(s, "time", 1.2 * DAY))
    admin.state.world = world.get_season()
    before = admin._calendar_status()["calendar"]
    assert before["text"] == "第 3 週・週一 09:36" and before["weeks"] == 12
    admin.admin_end_season(1_800_000_100.0)
    assert world.season_phase() == "resting"
    rested_at = world.get_season().time  # 收季那一刻（季時間停在這裡）
    assert rested_at == 1.2 * DAY

    after = Game.for_world(new, world)
    status = after._calendar_status()["calendar"]
    assert status["text"] == "第 3 週・週一 09:36", status  # 修之前：第 1 週・週二 04:48
    assert status["weeks"] == 12 and "words" not in status  # 週末式的字：沒有「段」
    overlay = after.map_state()  # 輿圖的「現在是第幾週、一共幾週」也是這一季自己的
    assert overlay["weeks_total"] == 12 and overlay["now_week"] == 3
    for t in TIMES:
        assert after.stamp(t) == admin.stamp(t), t
        assert after.stamp(t, clock=False) == admin.stamp(t, clock=False), t

    admin2 = Game.new(new, "Rayal", rng=random.Random(0), world=world)
    admin2.admin_next_season(1_800_000_200.0)  # 開下一季：新的一季蓋新章，照新季曆
    fresh = world.get_season()
    assert fresh.season21 and calendar.week7_on(fresh, new)
    assert Game.for_world(new, world)._calendar_status()["calendar"]["weeks"] == 3
