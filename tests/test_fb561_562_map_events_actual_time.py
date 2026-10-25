"""FB-561／FB-562（develop 小單驗收 QA 回報，PM 2026-10-20）：輿圖「這一段大事」「天下怎麼變」列決戰與季末的時刻。

FB-561：管理者「立刻開戰」提早開的時刻表決戰，修前要等到原本排定的時刻才列（開打了、收場了都不列）；現在這一場一開（WorldState.showdowns_opened）
或收場（timeline）就列，列在真的開了的那一週（段）。三種照週算的季（週末、21 天、7 天）都一樣。
FB-562：決戰被「避開半夜」或管理者挪到另一週（段）時，修前照時刻表原本寫的那一週算；現在判斷到了沒、歸到哪一週都照實際排定的時刻
（WorldState.schedule）。
不變：其他大事（非決戰、非季末）列的時刻與舊寫法逐刻一樣；14 天的季沒有這一段清單。"""
from __future__ import annotations

import random

import pytest
import test_fb501_week7_words as fb501
from conftest import real_content

from tianxia import calendar, mapdata, timetable
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import TimelineResult

pytestmark = pytest.mark.slow  # 每一條都載真實內容、開一季

HOUR, DAY = 3600, 86400
PROFILES = ("season21", "week7")
SPECIAL = ("showdown", "finale")


def _setup(profile):
    content = real_content(profile)
    return content, fb501._state(content)


def _event(content, event_id):
    return next(e for e in content.timetable if e.id == event_id)


def _in_week(content, state, week, cal_hours):
    """第 week 週（段）開始之後 cal_hours 個季曆小時的世界秒。"""
    return calendar.week_start(week, content, state.world) + cal_hours * HOUR / calendar.cal_scale(content, state.world)


def _week_of(content, state, at):
    return calendar.point(at, content, state.world).week


def _titles(content, state, at, week, now_week=None):
    state.world.time = at
    return mapdata._titles(state, content, week, now_week if now_week is not None else _week_of(content, state, at))


# ── FB-561：提早開的決戰，一開就列 ───────────────────────


@pytest.mark.parametrize("profile", PROFILES)
def test_an_early_started_showdown_is_listed_from_the_moment_it_opens(profile):
    """修前重現：還沒到排定的時刻，開了集結也不列（只看 timetable.when_in）。"""
    content, state = _setup(profile)
    w = state.world
    changshe = _event(content, "changshe_fire")
    default = timetable.when_in(w, content, changshe)
    early = _in_week(content, state, changshe.week, 6)
    assert early + HOUR < default and _week_of(content, state, early) == changshe.week
    assert "長社火攻" not in _titles(content, state, early, changshe.week)  # 還沒開
    w.showdowns_opened["changshe_fire"] = "changshe_fire"  # 管理者「立刻開戰」：world._claim_showdown 記的就是這個
    for at in (early, early + 60, (early + default) / 2, default - 60):
        titles = _titles(content, state, at, changshe.week)
        assert "長社火攻" in titles, at
        assert "宛城之戰" not in titles and "廣宗決戰" not in titles  # 別場沒開，照排定的時刻
    state.world.time = default + HOUR  # 排定的時刻過了，照舊列
    assert "長社火攻" in mapdata._titles(state, content, changshe.week, changshe.week)


@pytest.mark.parametrize("profile", PROFILES)
def test_a_showdown_opened_and_finished_early_stays_in_the_week_it_happened(profile):
    """時間軸上有了結果（收場了）：列在收場的那一週，之後的週也看得到；排定的那一週不再重複列。"""
    content, state = _setup(profile)
    w = state.world
    guangzong = _event(content, "guangzong")
    default = timetable.when_in(w, content, guangzong)
    week = guangzong.week - 2
    done = _in_week(content, state, week, 8)
    assert done < default and _week_of(content, state, done) == week
    w.showdowns_opened["guangzong"] = "guangzong"
    w.timeline["guangzong"] = TimelineResult(key="guan:大勝", time=done)
    assert "廣宗決戰" in _titles(content, state, done + 60, week)
    after = calendar.week_start(week + 1, content, w) + 60  # 下一週：「天下怎麼變」逐週列，過去的那一週還是有它
    assert "廣宗決戰" in _titles(content, state, after, week, week + 1)
    assert "廣宗決戰" not in _titles(content, state, after, guangzong.week, week + 1)


@pytest.mark.parametrize("profile", PROFILES)
def test_a_showdown_that_was_not_started_waits_for_its_scheduled_time(profile):
    """沒有人開、也沒收場的決戰照舊等排定的時刻（FB-504 不變）。"""
    content, state = _setup(profile)
    changshe = _event(content, "changshe_fire")
    default = timetable.when_in(state.world, content, changshe)
    assert "長社火攻" not in _titles(content, state, default - 60, changshe.week)
    assert "長社火攻" in _titles(content, state, default, changshe.week)


NOW = 1000.0


def test_the_admin_start_button_lists_the_battle_on_the_map_at_once(tmp_path):
    """整條路走一遍（週末）：管理者在排定時刻之前按「立刻開這一場」，輿圖當下就列，「天下怎麼變」那一週也有。"""
    content = real_content("week7")
    content.config.auto_open_first_season = True
    content.config.admins = ["管"]
    admin = Game.new(content, "管", rng=random.Random(0), world=open_world(tmp_path / "admin.db"))
    admin.client = None
    admin.sync(NOW)
    season = admin.world.get_season()
    scheduled = season.schedule["changshe_fire"]
    week = _week_of(content, admin.state, scheduled)
    monday = NOW + calendar.week_start(week, content, season) / content.config.time_scale
    admin.sync(monday + 5)
    assert admin.state.world.time < scheduled - HOUR
    assert "長社火攻" not in admin.map_state()["events"]
    admin.admin_start_showdown("changshe_fire", monday + 5)
    assert "changshe_fire" in admin.world.get_season().showdowns_opened
    state = admin.map_state()
    assert "長社火攻" in state["events"]
    assert any("長社火攻" in row["events"] for row in state["weeks"] if row["week"] == week)


# ── FB-562：挪到另一週的決戰，照實際排定的時刻歸週 ───────


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(("event_id", "step"), [("changshe_fire", 1), ("guangzong", -1), ("xiaquyang", -1)])
def test_a_showdown_moved_to_another_week_is_listed_in_the_week_it_is_really_scheduled(profile, event_id, step):
    """修前重現：往後挪到下一週的，排定的時刻到了卻列在原本那一週的那一列；往前挪到上一週的，早就到了卻要等原本那一週。"""
    content, state = _setup(profile)
    w = state.world
    event = _event(content, event_id)
    title = event.title
    moved_week = event.week + step
    moved = _in_week(content, state, moved_week, 12)
    w.schedule[timetable.schedule_key(event)] = moved
    assert _week_of(content, state, moved) == moved_week
    before = moved - 60
    assert title not in _titles(content, state, before, moved_week, _week_of(content, state, before))
    assert title not in _titles(content, state, before, event.week, _week_of(content, state, before))
    # 排定的時刻到了：列在排定的那一週，不列在時刻表原本寫的那一週
    assert title in _titles(content, state, moved, moved_week)
    assert title not in _titles(content, state, moved, event.week, moved_week)
    # 過了那一週，「天下怎麼變」逐週列：還是在排定的那一週的那一列
    later = calendar.week_start(moved_week + 1, content, w) + 60 if moved_week < content.config.season_weeks else moved + HOUR
    now_week = _week_of(content, state, later)
    assert title in _titles(content, state, later, moved_week, now_week)
    if event.week != moved_week:
        assert title not in _titles(content, state, later, event.week, now_week)


# ── 不變：其他大事、預設的排定、14 天的季 ─────────────────


@pytest.mark.parametrize("profile", PROFILES)
def test_with_the_default_schedule_every_listing_is_the_same_as_the_week_the_timetable_says(profile):
    """預設的排定、沒人開過：每一刻、每一週列出的大事跟時刻表原本寫的那一週、照 timetable.when_in 到了沒一模一樣（其他大事是 calendar.event_time）。"""
    content, state = _setup(profile)
    w = state.world
    end = calendar.nominal_end(content, w)
    step = end / 700
    at = 0.0
    seen = 0
    while at <= end:
        w.time = at
        now_week = _week_of(content, state, at)
        for week in range(1, now_week + 1):
            new = mapdata._titles(state, content, week, now_week)
            old = [e.title for e in timetable.events(w, content) if e.week == week and timetable.when_in(w, content, e) <= at]
            assert new == old, (at, week)
            seen += len(new)
        at += step
    assert seen > 0


def test_the_fourteen_day_season_still_has_no_timetable_in_the_map():
    content = real_content()
    state = fb501._state(content)
    state.world.showdowns_opened["changshe_fire"] = "changshe_fire"
    state.world.time = 6 * DAY
    assert mapdata._titles(state, content, 6, 6) == []
