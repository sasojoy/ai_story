"""FB-563／FB-564（QA 複驗 FB-560～562 開的兩張，PM 2026-10-20 裁決）。

FB-563：管理者提早開的時刻表決戰，輿圖要照「開的那一刻」判斷到了沒、歸在哪一週（WorldState.showdown_opened_at，照季分）：
- 跨過週界：開在第 N 週最後幾分鐘、收場在第 N+1 週，列在第 N 週的那一列，不跟著收場（或此刻）換到下一週；
- 管理者取消的決戰（WorldState.showdowns_cancelled）不列，取消之後排定的時刻過了也不列。
FB-564：「避開半夜」挪時刻時，天命之爭一定排在那一季最後一場時刻表決戰（廣宗）的集結加打一幕之後（開季、換季蓋章、管理者
「這一季立刻蓋章」三條路）；挪不開半夜時寫進管理者那一行。21 天、7 天、週三開季的週末（預設排定）一個字都不變。
三種照週算的季（週末、21 天、7 天）都測。"""
from __future__ import annotations

import datetime
import random

import pytest
from conftest import real_content

from tianxia import calendar, mapdata, timetable
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import TimelineResult
from tianxia.world_state import fresh_season, stamp_season

pytestmark = pytest.mark.slow  # 每一條都載真實內容、開一季

HOUR, DAY = 3600, 86400
PROFILES = ("weekend", "season21", "week7")
TW = datetime.timezone(datetime.timedelta(hours=8))
MON = datetime.datetime(2026, 10, 19, 0, 0, tzinfo=TW).timestamp()  # 週一 00:00（台灣）
ADMIN = "管"


def _game(profile, tmp_path, start=MON):
    """開好一季的管理者 Game（網頁按鈕呼叫的同一批 admin_*）。"""
    content = real_content(profile)
    content.config.admins = [ADMIN]
    world = open_world(tmp_path / "world.db")
    admin = Game.new(content, ADMIN, rng=random.Random(1), world=world)
    admin.client = None
    admin.sync(start)
    admin.admin_open_season(start)
    return content, world, admin, start


def _event(content, event_id):
    return next(e for e in content.timetable if e.id == event_id)


def _real_at(content, admin, start, world_time):
    """世界秒 world_time 對應的現實秒（開季那一刻是 start，世界秒 0）。"""
    return start + world_time / content.config.time_scale


def _advance(content, world, admin, real):
    admin.sync(real)
    Game.for_world(content, world).world_tick(real)
    admin.sync(real)


def _settle_before(world, *event_ids):
    """前面的決戰當作打完了（時間軸上有結果、開過），一口氣推時間時不會一場一場開集結擋住後面那一場。"""
    def _apply(season):
        for event_id in event_ids:
            season.showdowns_opened[event_id] = event_id
            season.timeline[event_id] = TimelineResult(key="guan:大勢", time=0.0)
    world.mutate_season(_apply)


def _listed(content, admin, title, week):
    return title in mapdata._titles(admin.state, content, week, calendar.point(admin.state.world.time, content, admin.state.world).week)


# ── FB-563：另記開的那一刻 ───────────────────────────────


@pytest.mark.parametrize("profile", PROFILES)
def test_a_showdown_opened_just_before_a_week_ends_stays_in_that_week(profile, tmp_path):
    """修前重現：開在第 N 週最後 2 分鐘（世界秒）的決戰，過了週界列的週跟著此刻（開了還沒收場）或收場那一刻換成第 N+1 週，
    第 N 週那一列沒有了。現在記開的那一刻，一直列在第 N 週。"""
    content, world, admin, start = _game(profile, tmp_path)
    _settle_before(world, "changshe_fire", "wancheng")
    guangzong = _event(content, "guangzong")
    season = admin.state.world
    scheduled = season.schedule["guangzong"]
    sched_week = calendar.point(scheduled, content, season).week
    assert sched_week >= 2
    boundary = calendar.week_start(sched_week, content, season)
    opening = boundary - 120
    assert opening < scheduled
    _advance(content, world, admin, _real_at(content, admin, start, opening))
    admin.admin_start_showdown("guangzong", _real_at(content, admin, start, opening))
    assert "guangzong" in admin.world.get_season().showdowns_opened
    admin.sync(_real_at(content, admin, start, opening))
    title = guangzong.title
    assert _listed(content, admin, title, sched_week - 1)
    assert not _listed(content, admin, title, sched_week)
    # 過了週界（集結中），再過到打完／收場之後：始終列在開的那一週
    for later in (boundary + 5 * 60, boundary + HOUR, boundary + 6 * HOUR):
        _advance(content, world, admin, _real_at(content, admin, start, later))
        assert admin.state.world.time >= boundary
        assert _listed(content, admin, title, sched_week - 1), later
        assert not _listed(content, admin, title, sched_week), later
    state = admin.map_state()
    rows = {row["week"]: row["events"] for row in state["weeks"]}
    assert title in rows[sched_week - 1] and title not in rows[sched_week]
    opened_at = admin.state.world.showdown_opened_at["guangzong"]  # 記的就是開的那一刻
    assert abs(opened_at - opening) < 60 and calendar.point(opened_at, content, admin.state.world).week == sched_week - 1


@pytest.mark.parametrize("profile", PROFILES)
def test_a_cancelled_showdown_is_not_listed_on_the_map(profile, tmp_path):
    """修前重現：開過的記號（showdowns_opened）留著，取消的決戰從取消那一刻起一直列在「本週大事」，沒有結果也列。
    現在取消的不列，排定的時刻過了也不列；取消之前（開打中）照舊列。"""
    content, world, admin, start = _game(profile, tmp_path)
    changshe = _event(content, "changshe_fire")
    season = admin.state.world
    scheduled = season.schedule["changshe_fire"]
    week = calendar.point(scheduled, content, season).week
    opening = max(calendar.week_start(week, content, season), 1800.0) + 1800
    assert opening < scheduled - HOUR / 2
    real = _real_at(content, admin, start, opening)
    _advance(content, world, admin, real)
    admin.admin_start_showdown("changshe_fire", real)
    admin.sync(real)
    title = changshe.title
    assert _listed(content, admin, title, week) and title in admin.map_state()["events"]
    admin.admin_cancel_battle()
    admin.sync(real + 600)
    assert "changshe_fire" in admin.world.get_season().showdowns_opened and "changshe_fire" not in admin.world.get_season().timeline
    for at in (opening + 600, scheduled - 60, scheduled + 60, scheduled + 3 * HOUR):
        _advance(content, world, admin, _real_at(content, admin, start, at))
        now_week = calendar.point(admin.state.world.time, content, admin.state.world).week
        for w in range(1, now_week + 1):
            assert not _listed(content, admin, title, w), (at, w)
        assert title not in admin.map_state()["events"], at
        assert all(title not in row["events"] for row in admin.map_state()["weeks"]), at


def test_a_cancelled_showdown_the_admin_later_settles_is_listed_again():
    """取消之後管理者「定結果」了（時間軸上有結果）：那就是發生了，照有結果的寫法列（取排定的時刻與定結果那一刻較早的）。"""
    from tianxia.state import new_game_state

    content = real_content("weekend")
    state = new_game_state(content, "甲")
    state.world = fresh_season(content)
    stamp_season(state.world, content, now=MON)
    w = state.world
    event = _event(content, "guangzong")
    done = calendar.week_start(event.week - 2, content, w) + 3000  # 週末一週 18000 世界秒
    week = calendar.point(done, content, w).week
    w.showdowns_opened["guangzong"] = "guangzong"
    w.showdown_opened_at["guangzong"] = done - 600
    w.showdowns_cancelled.append("guangzong")
    w.time = done - 60
    assert event.title not in mapdata._titles(state, content, week, week)
    w.timeline["guangzong"] = TimelineResult(key="guan:大勢", time=done)
    w.time = done + 60
    assert event.title in mapdata._titles(state, content, week, week)


@pytest.mark.parametrize("profile", PROFILES)
def test_the_opened_moment_is_recorded_when_the_muster_opens(profile, tmp_path):
    """自然開的（時間到了）也記：記的是開的那一刻（不早於排定的時刻），輿圖照排定的時刻到了沒（跟以前一樣）。"""
    content, world, admin, start = _game(profile, tmp_path)
    season = admin.state.world
    scheduled = season.schedule["changshe_fire"]
    week = calendar.point(scheduled, content, season).week
    _advance(content, world, admin, _real_at(content, admin, start, scheduled - 60))
    assert "changshe_fire" not in admin.state.world.showdown_opened_at
    assert not _listed(content, admin, "長社火攻", week)
    _advance(content, world, admin, _real_at(content, admin, start, scheduled + 30))
    stored = admin.world.get_season()
    assert "changshe_fire" in stored.showdowns_opened
    assert scheduled - 1 <= stored.showdown_opened_at["changshe_fire"] <= scheduled + 60
    assert _listed(content, admin, "長社火攻", week)
    assert timetable.happened_at(stored, content, _event(content, "changshe_fire")) == scheduled


# ── FB-564：天命之爭一定排在最後一場時刻表決戰之後 ──────────


def _span_world(content):
    return timetable.showdown_span(content, _event(content, "guangzong")) * content.config.time_scale


def _stamp_now(content, now, season_time=0.0):
    """管理者「這一季立刻蓋章」那條路（Game.admin_seal_mandate("now")）：照開季那一刻排好、再蓋天命之季的章、再避開半夜。
    season_time 是蓋章那一刻季的時間，now 是那一刻的現實秒。"""
    start = now - season_time / content.config.time_scale
    season = fresh_season(content)
    stamp_season(season, content, now=start)
    timetable.avoid_quiet_hours(season, content, start)
    season.time = season_time
    season.mandate = True
    season.schedule["tianming"] = timetable.default_time(timetable.find(content, "tianming"), content, season)
    timetable.avoid_quiet_hours(season, content, now)
    return season


def _stamp_at_season_change(content, now):
    """換季蓋章那條路（SqliteWorldStore.next_season）：新的一季一開始就蓋天命之季的章，再避開半夜。"""
    season = fresh_season(content, now=now)
    season.mandate = True
    season.schedule["tianming"] = timetable.default_time(timetable.find(content, "tianming"), content, season)
    timetable.avoid_quiet_hours(season, content, now)
    return season


def _mandate_notes(content, season, now):
    """管理者那一行裡關於天命之爭的話（別的決戰挪不開的不算）。"""
    return [n for n in timetable.quiet_notes(season, content, now) if "天命之爭" in n]


def _ordered(content, season):
    span = _span_world(content)
    schedule = season.schedule
    return schedule["guangzong"] + span <= schedule["tianming"] and schedule["tianming"] < schedule["finale"]


def test_the_weekend_mandate_stamp_after_a_monday_midnight_open_lands_after_guangzong(tmp_path):
    """QA 重現（FB-564）：週一 00:00 開季的週末，管理者「這一季立刻蓋章」，修前天命之爭被挪到第 10 週・週四 06:00，
    廣宗決戰被挪到第 12 週・週二 10:00（約晚 9 個現實小時）。現在天命之爭排在廣宗決戰收尾之後。"""
    content, world, admin, start = _game("weekend", tmp_path)
    admin.admin_seal_mandate("now")
    season = admin.world.get_season()
    assert season.mandate
    assert _ordered(content, season), {k: calendar.stamp_text(v, content, season) for k, v in season.schedule.items()}
    assert _mandate_notes(content, season, start) == []  # 排得下，不碰半夜，管理者那一行沒有挪不開的話


@pytest.mark.parametrize("hour", [0, 1, 23, 12])
def test_the_season_change_route_through_the_store_keeps_the_order(hour, tmp_path):
    """換季蓋章那條路整條走一遍（管理者收季、開下一季，天命之季的章在 SqliteWorldStore.next_season 蓋）：換季那一刻不論落在
    當地幾點，天命之爭都在廣宗收尾之後、季末之前。"""
    content, world, admin, start = _game("weekend", tmp_path)
    admin.admin_seal_mandate("next")
    admin.admin_end_season(start + 100)
    admin.admin_next_season(start + 3 * DAY + hour * HOUR)
    season = world.get_season()
    assert season.mandate and "tianming" in season.schedule
    assert _ordered(content, season), {k: calendar.stamp_text(v, content, season) for k, v in season.schedule.items()}


@pytest.mark.parametrize("route", ["now", "season-change"])
@pytest.mark.parametrize("profile", PROFILES)
def test_whatever_hour_the_season_opens_the_mandate_battle_comes_after_guangzong(profile, route):
    """每 15 分鐘的開季時刻掃七天（672 個），兩條蓋章的路：天命之爭都在廣宗決戰的集結加打一幕之後、季末之前。"""
    content = real_content(profile)
    bad = []
    for day in range(7):
        for minute in range(0, 24 * 60, 15):
            now = MON + day * DAY + minute * 60
            season = _stamp_now(content, now) if route == "now" else _stamp_at_season_change(content, now)
            if not _ordered(content, season):
                bad.append((day, minute // 60, minute % 60))
    assert bad == []


@pytest.mark.parametrize("profile", PROFILES)
def test_a_mid_season_stamp_never_puts_the_mandate_battle_before_guangzong(profile):
    """管理者在季中某一刻蓋章（廣宗還沒打）：開季的各種時刻 × 蓋章在第一場決戰之前、廣宗之前一週。"""
    content = real_content(profile)
    guangzong = _event(content, "guangzong")
    bad = []
    for day in range(7):
        for minute in range(0, 24 * 60, 60):
            start = MON + day * DAY + minute * 60
            probe = fresh_season(content)
            stamp_season(probe, content, now=start)
            at = calendar.week_start(max(1, guangzong.week - 1), content, probe) + HOUR
            season = _stamp_now(content, start + at / content.config.time_scale, season_time=at)
            if not _ordered(content, season):
                bad.append((day, minute // 60))
    assert bad == []


@pytest.mark.parametrize("profile", PROFILES)
def test_a_guangzong_the_admin_scheduled_late_pushes_the_mandate_battle_behind_it(profile):
    """修前重現：管理者先把廣宗排得比天命之爭預設時刻只早 10 分鐘（集結加打一幕要 39 分鐘，疊在一起）或更晚，再蓋章：
    天命之爭預設沒碰半夜，所以不動，排在廣宗前面或跟它疊在一起。現在一定排在廣宗收尾之後（白天，管理者那一行沒有話）。"""
    content = real_content(profile)
    scale = content.config.time_scale
    now = MON  # 21 天、7 天季的日曆貼著現實的天（預設 20:00、22:00），不碰半夜；週末下面換成正午
    if profile == "weekend":
        probe = fresh_season(content)
        stamp_season(probe, content, now=MON)
        default = timetable.default_time(timetable.find(content, "tianming"), content, probe)
        now = 20_000 * DAY + 12 * HOUR - default / scale - content.config.pill_day_utc_offset_hours * HOUR  # 天命之爭預設落在當地正午
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    default = timetable.default_time(timetable.find(content, "tianming"), content, season)
    season.schedule["guangzong"] = default - 10 * 60 * scale
    season.mandate = True
    season.schedule["tianming"] = default
    timetable.avoid_quiet_hours(season, content, now)
    assert season.schedule["guangzong"] == default - 10 * 60 * scale  # 廣宗不動
    assert _ordered(content, season)
    assert season.schedule["tianming"] - default <= 2 * calendar.cal_hour_seconds(content, season) + _span_world(content)  # 只往後挪一點
    assert _mandate_notes(content, season, now) == []


def _frozen_guangzong_season(local_clock_hours, finale_after, tianming_after=600):
    """週末季：廣宗已經開過（凍住，不再挪）、當地時間 local_clock_hours 點整；天命之爭預設排在廣宗之後 tianming_after 世界秒
    （比廣宗集結加一幕還早，所以得往後挪）；季末排在廣宗之後 finale_after 世界秒。回（內容, 季, now）。"""
    content = real_content("weekend")
    probe = fresh_season(content)
    stamp_season(probe, content, now=MON)
    g = probe.schedule["guangzong"]
    scale = content.config.time_scale
    now = 20_000 * DAY + local_clock_hours * HOUR - g / scale - content.config.pill_day_utc_offset_hours * HOUR
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    assert season.schedule["guangzong"] == g
    season.showdowns_opened["guangzong"] = "guangzong"
    season.mandate = True
    season.schedule["tianming"] = g + tianming_after * scale
    season.schedule["finale"] = g + finale_after * scale
    return content, season, now


def test_when_only_the_small_hours_are_left_behind_guangzong_the_order_still_wins():
    """廣宗當地 01:00（集結加打一幕到 01:39）、季末當地 07:00：天命之爭後面只剩半夜可排。先後不能亂：排在廣宗收尾之後
    最近的曆時（碰到半夜），管理者那一行寫出來（FB-564：挪不開半夜時寫進那一行）。"""
    content, season, now = _frozen_guangzong_season(1, 6 * HOUR)
    timetable.avoid_quiet_hours(season, content, now)
    g, floor = season.schedule["guangzong"], season.schedule["guangzong"] + _span_world(content)
    assert floor < season.schedule["tianming"] <= floor + calendar.cal_hour_seconds(content, season)
    assert season.schedule["tianming"] < season.schedule["finale"]
    notes = _mandate_notes(content, season, now)
    assert len(notes) == 1 and "排時間" in notes[0] and "廣宗" in notes[0]


def test_when_there_is_no_room_behind_guangzong_the_time_stays_and_the_admin_line_says_so():
    """廣宗當地正午、季末只在廣宗之後 25 分鐘（放不下集結加打一幕）：天命之爭排不進去，照原時間不動，管理者那一行寫出來。"""
    content, season, now = _frozen_guangzong_season(12, 1500)
    before = season.schedule["tianming"]
    stuck = timetable.avoid_quiet_hours(season, content, now)
    assert "tianming" in [e.id for e in stuck] and season.schedule["tianming"] == before
    notes = _mandate_notes(content, season, now)
    assert len(notes) == 1 and "排時間" in notes[0] and "廣宗" in notes[0]


def test_a_clear_slot_behind_guangzong_needs_no_words():
    """廣宗當地正午、季末還有六小時：天命之爭排在廣宗之後的白天，管理者那一行沒有話。"""
    content, season, now = _frozen_guangzong_season(12, 6 * HOUR)
    timetable.avoid_quiet_hours(season, content, now)
    assert _ordered(content, season)
    assert _mandate_notes(content, season, now) == []


# ── 不變：預設的排定 ─────────────────────────────────────


@pytest.mark.parametrize("profile", PROFILES)
def test_the_default_schedules_do_not_move(profile):
    """沒碰半夜的預設排定（週三 14:00 開季的週末、21 天、7 天）：蓋章之後天命之爭還在預設時刻，其餘決戰與季末一個字不動。"""
    content = real_content(profile)
    wed = datetime.datetime(2026, 10, 21, 14, 0, tzinfo=TW).timestamp()
    plain = fresh_season(content)
    stamp_season(plain, content, now=wed)
    timetable.avoid_quiet_hours(plain, content, wed)
    for route in (_stamp_now(content, wed), _stamp_at_season_change(content, wed)):
        for key, value in plain.schedule.items():
            assert route.schedule[key] == value, key
        assert route.schedule["tianming"] == timetable.default_time(timetable.find(content, "tianming"), content, route)
