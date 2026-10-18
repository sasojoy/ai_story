"""正式季第 1 批：季的骨架（正式季整合設計第一章、12.3 第 41 條）。21 天的季（season21 設定）季曆就是現實的三週，錨在開季那一週的台灣週一；
週末與 14 天的季一個字都不變。"""
from __future__ import annotations

from conftest import real_content

from tianxia import calendar, world
from tianxia.world_state import fresh_season, stamp_season

HOUR, DAY = 3600, 86400
WEEK = 7 * DAY
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
WED = 1792549800  # 2026-10-21 週三 10:30（台灣）
WED_OFFSET = 2 * DAY + 10.5 * HOUR


def _season(content, now=None):
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    return season


# ── Task 1：開關、章與季曆的錨點 ──


def test_the_season21_profile_turns_the_frame_on_and_nothing_else_does():
    c21 = real_content("season21")
    cfg = c21.config
    assert cfg.season21 and cfg.season_weeks == 3 and cfg.season_days == 21
    assert cfg.newbie_real_hours == 48  # 新手期 48 小時已經上線（Joy 2026-10-17），只核對
    assert not real_content().config.season21 and not real_content("weekend").config.season21


def test_the_anchor_is_the_taiwan_monday_of_the_opening_week():
    c21 = real_content("season21")
    assert calendar.anchor_offset(WED, c21) == WED_OFFSET
    assert calendar.anchor_offset(MON, c21) == 0


def test_a_wednesday_opening_reads_wednesday_and_ends_on_the_third_sunday():
    c21 = real_content("season21")
    season = _season(c21, now=WED)
    assert season.season21 and season.cal_offset == WED_OFFSET
    assert calendar.stamp_text(0, c21, season) == "第 1 週・週三 10:30"
    assert calendar.week_start(2, c21, season) == WEEK - WED_OFFSET
    finale = season.schedule["finale"]
    assert finale == 3 * WEEK - WED_OFFSET
    assert calendar.stamp_text(finale, c21, season) == "第 3 週・週日 23:59"
    assert world.season_end_time(season, c21) == finale


def test_the_weekend_season_ignores_the_opening_moment():
    wk = real_content("weekend")
    season = _season(wk, now=WED)
    plain = _season(wk)
    assert not season.season21 and season.cal_offset == 0
    assert calendar.stamp_text(0, wk, season) == "第 1 週・週一 00:00"
    assert season.schedule == plain.schedule


def test_calendar_hours_tick_on_the_hour_after_an_odd_opening():
    c21 = real_content("season21")
    season = _season(c21, now=WED)
    assert calendar.next_hour_mark(0, c21, season) == 1800
    wk = real_content("weekend")
    weekend = _season(wk)
    for t in (0.0, 123.4, 5000.0):
        assert calendar.next_hour_mark(t, wk, weekend) == world._to_next_cal_hour(t, calendar.cal_hour_seconds(wk, weekend))


def test_an_event_due_at_noon_is_settled_at_noon_after_a_mid_hour_opening():
    """Review Focus 5：10:30 開季，季曆 12:00 的大事在 12:00 那一刻結算，不是 12:30。"""
    import random

    c21 = real_content("season21")
    season = _season(c21, now=MON + 10.5 * HOUR)  # 週一 10:30 開季
    world.settle_season_start(season, c21, random.Random(0))
    court = next(e for e in c21.timetable if e.id == "court_mobilizes")  # 週二 12:00
    due = calendar.event_time(court, c21, season)
    world.advance_world_state(season, c21, due - season.time, random.Random(0))
    assert "court_mobilizes" in season.timeline


def test_open_season_stamps_the_anchor(world):
    c21 = real_content("season21")
    store = world
    store.seed_first_season(c21)
    assert store.open_season(c21, WED)
    assert store.get_season().cal_offset == WED_OFFSET


def test_a_weekend_program_warns_on_a_season21_season():
    """Review Focus 2：21 天季蓋的章、這個程式卻用週末的設定開著：啟動時要印對不上那一行。"""
    c21, wk = real_content("season21"), real_content("weekend")
    season = _season(c21, now=WED)
    assert calendar.profile_warning(wk, season) is not None
    assert calendar.profile_warning(c21, season) is None


# ── Task 2：21 天季的時刻表、出兵與伏筆照天數 ──

ORDER21 = ["uprising", "court_mobilizes", "zhangmancheng_wan", "bocai_routs_zhujun", "changshe_fire", "luzhi_siege",
           "qinjie_slays_zhangmancheng", "wancheng", "luzhi_jailed", "zhangjiao_dies", "guangzong", "xiaquyang"]
GENERALS = ("huangfusong", "zhujun", "luzhi", "sunjian", "fuxie", "qinjie")


def test_season21_has_its_own_timetable_in_time_order():
    from tianxia import timetable

    c21 = real_content("season21")
    assert [e.id for e in c21.timetable] == ORDER21
    season = _season(c21, now=MON)
    at = {e.id: timetable.when_in(season, c21, e) for e in c21.timetable}
    assert at["court_mobilizes"] == 1.5 * DAY and at["changshe_fire"] == 5 * DAY + 20 * HOUR
    assert at["wancheng"] == WEEK + 5 * DAY + 20 * HOUR and at["luzhi_jailed"] == 2 * WEEK + 0.5 * DAY
    assert at["guangzong"] == 2 * WEEK + 5 * DAY + 20 * HOUR and at["xiaquyang"] == 3 * WEEK
    [tianming] = c21.mandate_timetable
    assert timetable.default_time(tianming, c21, season) == 2 * WEEK + 6 * DAY + 20 * HOUR


def test_the_weekend_timetable_is_untouched():
    import json
    from pathlib import Path

    raw = json.loads((Path(__file__).parent.parent / "content" / "timetable.json").read_text(encoding="utf-8"))
    expected = [(e["id"], e["week"], e.get("day", 0)) for e in raw if not e.get("mandate_only")]
    assert [(e.id, e.week, e.day) for e in real_content("weekend").timetable] == expected


def _opened(content, now):
    import random

    season = _season(content, now=now)
    world.settle_season_start(season, content, random.Random(0))
    return season


def test_a_thursday_opening_settles_the_week_so_far_in_order():
    """週一以外開季（1.1【PM】）：已經過了的一般大事在開季那一刻照時間順序一起結算。"""
    c21 = real_content("season21")
    season = _opened(c21, MON + 3 * DAY + 13 * HOUR)  # 週四 13:00
    assert {"uprising", "court_mobilizes", "zhangmancheng_wan", "bocai_routs_zhujun"} <= set(season.timeline)
    assert "changshe_fire" not in season.timeline and "changshe_fire" not in season.showdowns_waiting


def test_a_sunday_opening_after_the_first_battle_does_not_break():
    """Review Focus 1：週六的長社已經過了才開季：一般大事照樣結算，長社照「時間到了卻沒開成」那條路排著。"""
    c21 = real_content("season21")
    season = _opened(c21, MON + 6 * DAY + 21 * HOUR)  # 週日 21:00
    assert {"uprising", "court_mobilizes", "zhangmancheng_wan", "bocai_routs_zhujun"} <= set(season.timeline)
    assert "changshe_fire" in season.showdowns_waiting


def test_the_generals_march_out_by_day_in_season21():
    from tianxia import figures

    c21 = real_content("season21")
    state = world._season_vehicle(c21, _season(c21, now=MON))
    for fid in GENERALS:
        assert not figures.started(state, c21, fid, 1.4 * DAY) and figures.started(state, c21, fid, 1.6 * DAY), fid
    assert figures.started(state, c21, "bocai", 0.0)
    wk = real_content("weekend")
    weekend = world._season_vehicle(wk, _season(wk))
    week2 = calendar.week_start(2, wk, weekend.world)
    assert not figures.started(weekend, wk, "huangfusong", week2 - 60) and figures.started(weekend, wk, "huangfusong", week2 + 60)


def test_the_two_buyers_foreshadow_is_open_by_day_in_season21():
    from tianxia.rules import check_condition

    c21, wk = real_content("season21"), real_content("weekend")
    cond = c21.events["fs_ev_two_buyers"].condition.model_copy(update={"factions": []})
    state = world._season_vehicle(c21, _season(c21, now=MON))
    opened = {}
    for day in (5, 6, 11, 12):
        state.world.time = (day - 1) * DAY + HOUR
        opened[day] = check_condition(cond, state, c21)
    assert opened == {5: False, 6: True, 11: True, 12: False}
    weekend = world._season_vehicle(wk, _season(wk))
    wcond = wk.events["fs_ev_two_buyers"].condition.model_copy(update={"factions": []})
    for week, ok in ((3, False), (4, True), (6, True), (7, False)):
        weekend.world.time = calendar.week_start(week, wk, weekend.world) + 60
        assert check_condition(wcond, weekend, wk) is ok, week


def test_season21_content_must_carry_the_day_versions():
    import pytest

    from tianxia.content import ContentError, validate

    def broken(edit):
        c21 = real_content("season21")
        edit(c21)
        with pytest.raises(ContentError):
            validate(c21)

    broken(lambda c: setattr(c.timetable[1], "real", None))
    broken(lambda c: setattr(c.figures["huangfusong"], "active_from_day", None))
    broken(lambda c: setattr(c.events["fs_ev_two_buyers"].condition, "cal_day_min", None))
    broken(lambda c: setattr(c.config, "season_days", 14))


# ── Task 3：不提前收季、態勢卡那一句與結局提示 ──


def _late(content, week, fronts, now=None):
    from tianxia import rules

    season = _season(content, now=now)
    for front in rules.front_ids(content):
        season.trends[front] = fronts
    season.time = calendar.week_start(week, content, season) + 1
    return season, world._season_vehicle(content, season)


def test_season21_never_ends_early():
    from tianxia import rules

    c21 = real_content("season21")
    for fronts in (90, 10):
        season, vehicle = _late(c21, 3, fronts, now=MON)
        assert world.decisive_ending(vehicle, c21) is None, fronts
    assert rules.decisive_week(season, c21) > c21.config.season_weeks


def test_the_stance_note_says_no_early_end_and_only_a_mandate_season_says_mandate():
    from tianxia import rules

    c21 = real_content("season21")
    season, vehicle = _late(c21, 1, 50, now=MON)
    note = rules.stance_rule_note(vehicle, c21)
    assert note.startswith("這一季不會提前收場") and rules.MANDATE_RULE not in note
    assert "黃巾的態勢在 85 以上" in note and "官軍的態勢在 85 以上" in note  # 85 照樣算，只是到季末才判（1.1）
    season.mandate = True
    assert rules.stance_rule_note(vehicle, c21) == rules.MANDATE_RULE
    wk = real_content("weekend")
    _, weekend = _late(wk, 1, 50)
    assert rules.stance_rule_note(weekend, wk).startswith("第 10 週起")


def test_the_season21_ending_hints_drop_week_ten():
    from tianxia import guide

    c21 = real_content("season21")
    _, vehicle = _late(c21, 1, 50, now=MON)
    text = guide.quest_text(vehicle, c21)
    assert "第 10 週" not in text and "季末黃巾的態勢在 85 以上。" in text and "季末官軍的態勢在 85 以上。" in text
    wk = real_content("weekend")
    _, weekend = _late(wk, 1, 50)
    assert "第 10 週起，黃巾的態勢一到 85" in guide.quest_text(weekend, wk)



def test_season_clock_resume_refuses_a_profile_without_the_season21_switch():
    """主機端 season_clock.py resume 拿章當設定檔的指紋：21 天季的 season_weeks 由 season21 的章加季長釘住（content.validate：
    season_weeks × 7 == season_days），所以章上是 21 天季、讀的設定沒開，也要拒絕。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    import season_clock

    c21 = real_content("season21")
    season = _season(c21, now=WED)
    assert season_clock._profile_mismatch(season, c21) is None
    off = real_content("season21")
    off.config.season21 = False  # 第一季規則開、季長 21 天都對得上，只差 21 天季
    assert season_clock._profile_mismatch(season, off) is not None
