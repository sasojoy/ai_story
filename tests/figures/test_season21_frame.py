"""正式季第 1 批：季的骨架（正式季整合設計第一章、12.3 第 41 條）。21 天的季（season21 設定）季曆就是現實的三週，錨在開季那一週的台灣週一；
週末與 14 天的季一個字都不變。"""
from __future__ import annotations

from conftest import real_content

from tianxia import calendar, world
from tianxia.world_state import fresh_season, stamp_season
from tianxia import calendar
import pytest
from tianxia.sqlite_world import open_world
from tianxia.state import WorldState
import run_bots
import server

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
    assert not real_content().config.season21


@pytest.mark.smoke
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


def test_calendar_hours_tick_on_the_hour_after_an_odd_opening():
    c21 = real_content("season21")
    season = _season(c21, now=WED)
    assert calendar.next_hour_mark(0, c21, season) == 1800
    wk = real_content("week7")
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
    c21, wk = real_content("season21"), real_content("week7")
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


# 照週寫的事件條件另寫照天的版本（以前的例子是兩路買家，2026-10-31 跟豪強第三方一起拿掉；正式內容現在沒有照週寫的事件）
WEEK_4_TO_6 = {"week_min": 4, "week_max": 6, "cal_day_min": 6, "cal_day_max": 11, "cal_day_min7": 2, "cal_day_max7": 4}


def test_a_week_condition_is_open_by_day_in_season21():
    from tianxia.models import Condition
    from tianxia.rules import check_condition

    c21 = real_content("season21")
    cond = Condition(**WEEK_4_TO_6)
    state = world._season_vehicle(c21, _season(c21, now=MON))
    opened = {}
    for day in (5, 6, 11, 12):
        state.world.time = (day - 1) * DAY + HOUR
        opened[day] = check_condition(cond, state, c21)
    assert opened == {5: False, 6: True, 11: True, 12: False}


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
    def week_without_days(c):
        from tianxia.models import Condition

        event = next(iter(c.events.values()))
        event.condition = Condition(**{**WEEK_4_TO_6, "cal_day_min": None})

    broken(week_without_days)
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


def test_the_season21_ending_hints_drop_week_ten():
    from tianxia import guide

    c21 = real_content("season21")
    _, vehicle = _late(c21, 1, 50, now=MON)
    text = guide.quest_text(vehicle, c21)
    assert "第 10 週" not in text and "季末黃巾的態勢在 85 以上。" in text and "季末官軍的態勢在 85 以上。" in text


# ── Task 4：「今天」是現實的一天 ──


def test_today_turns_over_at_taiwan_midnight_in_season21():
    from tianxia import rules

    c21 = real_content("season21")
    season = _season(c21, now=WED)  # 週三 10:30 開季：13.5 小時之後是週四 00:00
    midnight = 13.5 * HOUR
    assert rules.game_day(c21, season, 0) == 3 and rules.game_day(c21, season, midnight - 1) == 3
    assert rules.game_day(c21, season, midnight) == 4
    assert rules.day_ends(c21, season, 0) == midnight
    assert rules.day_seconds(c21, season) == DAY
    assert rules.world_day(c21, season, midnight - 1) == 2 and rules.world_day(c21, season, midnight) == 3
    late = season.schedule["finale"] + 2 * DAY  # 管理者把季末往後排：季曆寫到 23:59 為止，「今天」照樣換
    assert rules.game_day(c21, season, late) == 24 and rules.day_ends(c21, season, late) == late + DAY


def test_a_figure_daily_cap_resets_at_midnight_not_24_hours_after_opening():
    from tianxia import figures

    c21 = real_content("season21")
    state = world._season_vehicle(c21, _season(c21, now=WED))
    midnight = 13.5 * HOUR
    state.world.time = midnight - 60
    figures.defeat(state, c21, "bocai", 3, cap=3)
    assert figures.defeat(state, c21, "bocai", 3, cap=3) == [figures.HELD_LINE.format(name=figures.name_of(c21, "bocai"))]
    state.world.time = midnight
    assert figures.defeat(state, c21, "bocai", 3, cap=3) != [figures.HELD_LINE.format(name=figures.name_of(c21, "bocai"))]


def test_season_clock_resume_refuses_a_profile_without_the_season21_switch():
    """主機端 season_clock.py resume 拿章當設定檔的指紋：21 天季的 season_weeks 由 season21 的章加季長釘住（content.validate：
    season_weeks × 7 == season_days），所以章上是 21 天季、讀的設定沒開，也要拒絕。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
    import season_clock

    c21 = real_content("season21")
    season = _season(c21, now=WED)
    assert season_clock._profile_mismatch(season, c21) is None
    off = real_content("season21")
    off.config.season21 = False  # 第一季規則開、季長 21 天都對得上，只差 21 天季
    assert season_clock._profile_mismatch(season, off) is not None


def test_a_season21_program_warns_on_a_season_opened_without_it():
    """season_weeks 不蓋在季上：用 21 天季的設定開著的程式讀到還在跑的週末季（或 14 天季），季曆整個算錯，啟動時也要印對不上那一行
    （另一句，不是第一季規則那一句）。21 天季對 21 天季不印、季收了不印。"""
    c21, wk = real_content("season21"), real_content("week7")
    weekend = _season(wk)
    assert calendar.profile_warning(c21, weekend) == calendar.SEASON21_MISMATCH
    assert calendar.profile_warning(c21, _season(real_content())) == calendar.SEASON21_MISMATCH
    assert calendar.profile_warning(wk, _season(c21, now=WED)) == calendar.SEASON21_MISMATCH
    weekend.ended = True
    assert calendar.profile_warning(c21, weekend) is None


# ── 暫停賽季時鐘（PM 2026-10-19：21 天季的季曆對回現實的星期）──


def _resume(store, content, now):
    import random

    return world.resume_season_clock(store, content, now, random.Random(0), "繼續：{skip}")


def test_resuming_realigns_the_calendar_and_settles_what_was_due(world):
    """週一 10:00 暫停、週三 13:00 繼續：季曆寫週三 13:00，週二、週三中午的大事在繼續那一刻依序結算；長社照舊是週六 20:00，
    季末照原本的日期（第 3 週週日 24:00）。"""
    import random

    from tianxia import world as rules_world

    c21 = real_content("season21")
    store = world
    store.seed_first_season(c21)
    assert store.open_season(c21, MON)
    store.catch_up_season(c21, MON + 10 * HOUR, random.Random(0))
    assert store.pause_clock(MON + 10 * HOUR)
    lines = _resume(store, c21, MON + 2 * DAY + 13 * HOUR)
    season = store.get_season()
    assert calendar.stamp_text(season.time, c21, season) == "第 1 週・週三 13:00"
    assert {"court_mobilizes", "zhangmancheng_wan"} <= set(season.timeline) and "bocai_routs_zhujun" not in season.timeline
    assert calendar.stamp_text(season.schedule["changshe_fire"], c21, season) == "第 1 週・週六 20:00"
    assert season.schedule["finale"] + season.cal_offset == 3 * WEEK  # 季末照原本的現實日期
    assert rules_world.RESUME_SKIP_REAL in lines[0]


# ── 原 test_fb520_mismatch_warning.py（整檔搬進來） ──
# FB-520（7 天測試季整合預演，2026-10-20）：季中換上新程式只印一行 ⚠ 就照跑，那一行叫人「帶開季時那一份設定」，可是設定的名字
# 一樣是 week7、內容換了（週末式 → 照現實天）。PM 定不擋（擋了伺服器起不來更糟），部署說明寫死休季才換；這裡只改那一行的字，讓主機端
# 的人看得懂該怎麼辦（字待 joy 潤）。

@pytest.mark.slow
def test_matching_programs_and_ended_seasons_stay_quiet():
    c7 = real_content("week7")
    season = fresh_season(c7)
    stamp_season(season, c7, now=MON)
    assert calendar.profile_warning(c7, season) is None
    season.ended = True
    assert calendar.profile_warning(real_content("week7"), season) is None


# ── 原 test_fb636_preparing_warning.py（整檔搬進來） ──
# FB-636（QA 上線前整合預演最後一輪，2026-10-21）：全新的資料庫在「籌備中」帶 week7 或 season21 開，伺服器與假人程式啟動時都印
# 「⚠ 正在跑的這一季是用另一種季曆開的……」。籌備中的季還沒蓋 season21 的章（False），跟設定的 True 對不上就回 SEASON21_MISMATCH，
# 可是還沒開過任何一季，什麼都沒換，那一句會叫主機端的人去還原備份。PM 定：籌備中（還沒開過季）不印；季真的在跑而且對不上才印
# （FB-520 那一行的警告不能被這一條弄丟）。

NOW = 1792339200  # 2026-10-19 週一 00:00（台灣）


MARK = calendar.SEASON21_MISMATCH


def _start_server(monkeypatch, capsys, profile: str) -> str:
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "PROFILE", profile)
    content = real_content(profile)
    monkeypatch.setattr(content.config, "world_tick_seconds", 0)  # 只看啟動印的字，不開排程執行緒（正式內容開著）
    monkeypatch.setattr(server, "CONTENT", content)
    server.main([])
    return capsys.readouterr().out


def _start_bots(monkeypatch, capsys, profile: str) -> str:
    monkeypatch.setattr(run_bots.time, "sleep", lambda seconds: None)
    monkeypatch.setenv("TIANXIA_PROFILE", profile)
    run_bots.main(ticks=0)
    return capsys.readouterr().out


@pytest.mark.slow
@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_a_fresh_database_still_in_preparation_prints_no_mismatch(monkeypatch, capsys, profile):
    """還沒種過季的全新資料庫（單上的重現步驟）：兩支程式都不印。"""
    assert open_world().season_phase() == "preparing"
    assert MARK not in _start_server(monkeypatch, capsys, profile)
    assert MARK not in _start_bots(monkeypatch, capsys, profile)


@pytest.mark.slow
@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_a_seeded_but_unopened_season_prints_nothing_either(monkeypatch, capsys, profile):
    """種好了、管理者還沒開季（以前沒帶設定種的，章是 false）：開季時才重新蓋章，這時候什麼都沒換，一樣不印。"""
    old = real_content()  # 以前沒帶設定種的：章上 season21 是 false
    open_world().seed_first_season(old)
    assert open_world().season_phase() == "preparing" and not open_world().get_season().season21
    assert MARK not in _start_server(monkeypatch, capsys, profile)
    assert MARK not in _start_bots(monkeypatch, capsys, profile)


@pytest.mark.slow
@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_a_running_season_opened_with_another_calendar_still_prints_the_fb520_warning(monkeypatch, capsys, profile):
    """FB-520 的警告沒有被弄丟：週末式的季已經開了（章上 season21 是 false），換上照現實天的程式，兩支程式都印。"""
    old = real_content()  # 沒帶設定的程式開的季：章上 season21 是 false
    world = open_world()
    world.seed_first_season(old)
    assert world.open_season(old, NOW)
    assert world.season_phase() == "running"
    assert MARK in _start_server(monkeypatch, capsys, profile)
    assert MARK in _start_bots(monkeypatch, capsys, profile)


@pytest.mark.slow
@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_a_running_season_with_the_matching_calendar_prints_nothing(monkeypatch, capsys, profile):
    content = real_content(profile)
    world = open_world()
    world.seed_first_season(content)
    assert world.open_season(content, NOW)
    assert MARK not in _start_server(monkeypatch, capsys, profile)
    assert MARK not in _start_bots(monkeypatch, capsys, profile)


@pytest.mark.slow
def test_the_warning_function_itself_knows_the_phase():
    """calendar.profile_warning(content, season, phase)：籌備中不印；跑著而且對不上才印；不給 phase 照舊（只看季收了沒）。"""
    c7 = real_content("week7")
    bare = WorldState()  # 全新資料庫讀回來的樣子：沒蓋章
    assert not bare.season21
    assert calendar.profile_warning(c7, bare, "preparing") is None
    assert calendar.profile_warning(c7, bare, "running") == MARK
    assert calendar.profile_warning(c7, bare) == MARK  # 沒給 phase：跟以前一樣
    bare.ended = True
    assert calendar.profile_warning(c7, bare, "resting") is None
    assert calendar.profile_warning(c7, None, "preparing") is None
