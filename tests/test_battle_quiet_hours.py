"""時刻表決戰避開半夜（企劃者 2026-10-15，經 PM）：照季曆自動排的決戰（開季、換季、天命之季蓋章），現實時間（台灣時間，
照 pill_day_utc_offset_hours）落在 00:00～08:00 的，挪到最近的可開時間：往前到前一天「集結加打一幕」剛好在 00:00 收尾的那一刻，
或往後到 08:00；不打亂時刻表的先後、不挪過季末，兩邊都不行就照原時間（管理者那一行另外說）。管理者自己排的時間不動。
開關 Config.battle_quiet_hours（預設開、測試內容關）。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import calendar, timetable
from tianxia.world_state import fresh_season

DAY, HOUR = 86400, 3600
BASE = 20_000 * DAY  # 隨便一天的當地 00:00（照時區換過的 epoch 秒）
SPAN = 1800 + 3 * 300  # 正式內容的決戰：集結 30 分鐘、打一幕（三回合，每回合最多 5 分鐘）


def _setup(event_id, hh, mm=0, content=None):
    """週末設定的一季，挑 now 讓 event_id 照季曆排的集結開始落在當地 hh:mm（BASE 那一天）。"""
    c = content or real_content("weekend")
    season = fresh_season(c)
    at = season.schedule[event_id]
    now = BASE + hh * HOUR + mm * 60 - at / c.config.time_scale - c.config.pill_day_utc_offset_hours * HOUR
    return c, season, timetable.find(c, event_id), now


def _local(c, season, now, t):
    return now + (t - season.time) / c.config.time_scale + c.config.pill_day_utc_offset_hours * HOUR


def _cal_hour_real(c, season):
    return calendar.cal_hour_seconds(c, season) / c.config.time_scale


def test_the_window_is_the_muster_and_the_first_act():
    c = real_content("weekend")
    assert timetable.showdown_span(c, timetable.find(c, "changshe_fire")) == SPAN
    assert c.config.battle_quiet_hours.enabled and (c.config.battle_quiet_hours.start, c.config.battle_quiet_hours.end) == (0, 8)


def test_two_in_the_morning_moves_back_to_the_evening_before():
    c, season, event, now = _setup("changshe_fire", 2)
    assert timetable.avoid_quiet_hours(season, c, now) == []
    local = _local(c, season, now, season.schedule["changshe_fire"])
    assert BASE - SPAN - _cal_hour_real(c, season) <= local <= BASE - SPAN  # 23:15 收在 00:00 以前（取整到曆時，只會早一點）


def test_half_past_six_moves_forward_to_eight():
    c, season, event, now = _setup("changshe_fire", 6, 30)
    timetable.avoid_quiet_hours(season, c, now)
    local = _local(c, season, now, season.schedule["changshe_fire"])
    assert BASE + 8 * HOUR <= local <= BASE + 8 * HOUR + _cal_hour_real(c, season)


def test_half_past_eleven_is_too_late_to_finish_the_first_act():
    c, season, event, now = _setup("changshe_fire", 23, 30)
    timetable.avoid_quiet_hours(season, c, now)
    local = _local(c, season, now, season.schedule["changshe_fire"])
    assert BASE + DAY - SPAN - _cal_hour_real(c, season) <= local <= BASE + DAY - SPAN


def test_awake_times_are_left_alone():
    for hh, mm in ((20, 0), (8, 0), (23, 15), (12, 34)):
        c, season, event, now = _setup("changshe_fire", hh, mm)
        before = season.schedule["changshe_fire"]
        timetable.avoid_quiet_hours(season, c, now)
        assert season.schedule["changshe_fire"] == before, (hh, mm)  # 別場落在半夜的照挪，這一場不動


def test_it_does_not_jump_over_the_next_event():
    """宛城第 9 週週四、張角病逝第 10 週週一 00:00：週末季兩件只隔現實約 2 小時 16 分。05:30 往後挪到 08:00 會跑到張角病逝之後，
    改往前挪到前一天晚上。"""
    c, season, event, now = _setup("wancheng", 5, 30)
    following = timetable.when_in(season, c, timetable.find(c, "zhangjiao_dies"))
    assert _local(c, season, now, following) < BASE + 8 * HOUR  # 前提：往後挪會越過它
    assert timetable.avoid_quiet_hours(season, c, now) == []
    at = season.schedule["wancheng"]
    assert at < following and _local(c, season, now, at) <= BASE - SPAN


def test_it_does_not_crowd_the_battle_before():
    """一次只打一場：廣宗排在 01:30，宛城（管理者挪過）排在兩小時前的 23:30、往前挪到 23:15。廣宗往前挪到 23:15 會撞上宛城的
    集結與第一幕（排隊、拖過 00:00 才開），改往後挪到 08:00（季末還在後面）。"""
    c, season, event, now = _setup("guangzong", 1, 30)
    season.schedule["wancheng"] = season.schedule["guangzong"] - 2 * HOUR * c.config.time_scale
    assert timetable.avoid_quiet_hours(season, c, now) == []
    assert _local(c, season, now, season.schedule["wancheng"]) <= BASE - SPAN
    guangzong = _local(c, season, now, season.schedule["guangzong"])
    assert BASE + 8 * HOUR <= guangzong <= BASE + 8 * HOUR + _cal_hour_real(c, season)
    assert season.schedule["guangzong"] < season.schedule["finale"]


def test_both_ways_blocked_keeps_the_time_and_says_so():
    """往前會排到此刻之前、往後會越過下一場決戰：照原時間，回報這一件，管理者那一行寫出來。"""
    c = real_content("weekend")
    season = fresh_season(c)
    at = season.schedule["changshe_fire"]
    scale = c.config.time_scale
    season.time = at - HOUR * scale
    season.schedule["wancheng"] = at + 1800 * scale
    now = BASE + 4 * HOUR - HOUR - c.config.pill_day_utc_offset_hours * HOUR  # changshe_fire 落在 04:00
    stuck = timetable.avoid_quiet_hours(season, c, now)
    assert "changshe_fire" in [e.id for e in stuck] and season.schedule["changshe_fire"] == at
    notes = [n for n in timetable.quiet_notes(season, c, now) if "長社" in n]
    assert len(notes) == 1 and "04:00" in notes[0] and "照原時間" in notes[0]


def test_the_last_week_of_a_weekend_season_can_be_too_tight():
    """週末季第 12 週：天命之爭（週一 20:00）前面的廣宗只差現實約 2.9 小時、後面的季末約 4.4 小時。落在 03:00 時往前會越過廣宗、
    往後會越過季末，照原時間（管理者那一行說）。"""
    c = real_content("weekend")
    season = fresh_season(c)
    season.mandate = True
    season.schedule["tianming"] = timetable.default_time(timetable.find(c, "tianming"), c, season)
    at = season.schedule["tianming"]
    now = BASE + 3 * HOUR - at / c.config.time_scale - c.config.pill_day_utc_offset_hours * HOUR
    stuck = timetable.avoid_quiet_hours(season, c, now)
    assert "tianming" in [e.id for e in stuck] and season.schedule["tianming"] == at
    assert season.schedule["guangzong"] < at < season.schedule["finale"]


def test_the_finale_is_never_pushed():
    c, season, event, now = _setup("guangzong", 3)
    finale = season.schedule["finale"]
    timetable.avoid_quiet_hours(season, c, now)
    assert season.schedule["finale"] == finale and season.schedule["guangzong"] < finale


def test_the_mandate_battle_is_moved_too():
    c = real_content("weekend")
    season = fresh_season(c)
    event = timetable.find(c, "tianming")
    season.mandate = True
    season.schedule["tianming"] = timetable.default_time(event, c, season)
    now = BASE + 23 * HOUR + 40 * 60 - season.schedule["tianming"] / c.config.time_scale - c.config.pill_day_utc_offset_hours * HOUR
    timetable.avoid_quiet_hours(season, c, now)
    local = _local(c, season, now, season.schedule["tianming"])
    assert BASE + DAY - SPAN - _cal_hour_real(c, season) <= local <= BASE + DAY - SPAN  # 23:40 往前挪到 23:15


def test_any_opening_hour_leaves_no_battle_at_night():
    """開季時刻掃一天（每 20 分鐘）：週末與 7 天的一般季，三場決戰都挪得開、挪過之後集結加一幕都不碰半夜、時刻表先後不亂、
    季末不動。"""
    for days in (2.5, 7.0):
        c = real_content("weekend")
        c.config.season_days = days
        for minute in range(0, 24 * 60, 20):
            season = fresh_season(c)
            finale = season.schedule["finale"]
            now = BASE + minute * 60 - c.config.pill_day_utc_offset_hours * HOUR
            assert timetable.avoid_quiet_hours(season, c, now) == [], (days, minute)
            assert timetable.quiet_notes(season, c, now) == [], (days, minute)
            evs = timetable.events(season, c)
            ordered = sorted(enumerate(evs), key=lambda p: (timetable.when_in(season, c, p[1]), p[0]))
            assert [e.id for _, e in ordered] == [e.id for e in evs], (days, minute)
            assert season.schedule["finale"] == finale


def test_switch_off_changes_nothing():
    c, season, event, now = _setup("changshe_fire", 2)
    c.config.battle_quiet_hours.enabled = False
    before = dict(season.schedule)
    assert timetable.avoid_quiet_hours(season, c, now) == [] and season.schedule == before
    assert timetable.quiet_notes(season, c, now) == []


def test_opening_the_season_at_the_right_hour_moves_the_night_battle(tmp_path):
    from tianxia.sqlite_world import open_world

    c = real_content("weekend")
    c.config.auto_open_first_season = False
    store = open_world(tmp_path / "tianxia.db")
    store.seed_first_season(c)
    _, probe, _, now = _setup("changshe_fire", 2, content=c)
    assert store.open_season(c, now)
    season = store.get_season()
    local = _local(c, season, now, season.schedule["changshe_fire"])
    assert local <= BASE - SPAN  # 前一天晚上
    assert season.schedule["changshe_fire"] != probe.schedule["changshe_fire"]
    assert calendar.stamp_text(season.schedule["changshe_fire"], c, season) != "第 6 週・週四 20:00"  # 公告、下一件照挪過的時刻寫


def test_the_next_season_is_scheduled_the_same_way(tmp_path):
    from tianxia.sqlite_world import open_world

    c = real_content("weekend")
    c.config.auto_open_first_season = False
    store = open_world(tmp_path / "tianxia.db")
    store.seed_first_season(c)
    _, _, _, first = _setup("changshe_fire", 14, content=c)
    assert store.open_season(c, first)
    store.mutate_season(lambda s: setattr(s, "ended", True))
    _, probe, _, now = _setup("changshe_fire", 6, 30, content=c)
    assert store.next_season(c, now)
    season = store.get_season()
    local = _local(c, season, now, season.schedule["changshe_fire"])
    assert BASE + 8 * HOUR <= local <= BASE + 8 * HOUR + _cal_hour_real(c, season)


def test_an_admin_night_time_is_kept(tmp_path):
    """管理者自己排的時間照他填的，不挪。"""
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = real_content("weekend")
    c.config.auto_open_first_season = False
    c.config.admins = ["管"]
    store = open_world(tmp_path / "tianxia.db")
    store.seed_first_season(c)
    _, _, _, now = _setup("changshe_fire", 14, content=c)
    store.open_season(c, now)
    game = Game.new(c, "管", rng=random.Random(1), world=store)
    game.sync(now)
    night = BASE + 3 * HOUR - c.config.pill_day_utc_offset_hours * HOUR  # 當天 03:00 早就過了：排到隔天 03:00
    night += DAY * (1 + int((now - night) // DAY))
    game.admin_schedule("changshe_fire", night, now)
    season = store.get_season()
    local = _local(c, season, now, season.schedule["changshe_fire"]) % DAY
    assert 3 * HOUR <= local <= 3 * HOUR + _cal_hour_real(c, season)


def test_fb265_stamping_the_mandate_now_says_when_it_cannot_move(tmp_path):
    """FB-265：管理者「這一季立刻蓋上天命之季的章」時，天命之爭落在半夜又兩邊都挪不開（週末季第 12 週太擠），照原時間；
    回的訊息跟開季、開啟下一季一樣多那一行「挪不開、照原時間」。"""
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = real_content("weekend")
    c.config.auto_open_first_season = False
    c.config.admins = ["管"]
    store = open_world(tmp_path / "tianxia.db")
    store.seed_first_season(c)
    probe = fresh_season(c)
    probe.mandate = True
    at = timetable.default_time(timetable.find(c, "tianming"), c, probe)
    now = BASE + 3 * HOUR - at / c.config.time_scale - c.config.pill_day_utc_offset_hours * HOUR  # 天命之爭落在 03:00
    assert store.open_season(c, now)
    game = Game.new(c, "管", rng=random.Random(1), world=store)
    game.sync(now)
    out = game.admin_seal_mandate("now")
    assert any("蓋上天命之季" in line for line in out), out
    assert any("天命之爭" in line and "照原時間" in line and "03:00" in line for line in out), out


def test_fb265_the_confirm_box_does_not_promise_the_move():
    """FB-265：確認框不寫成一定挪得開。"""
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
    box = js[js.index("這一季立刻蓋上天命之季的章："):]
    box = box[: box.index("確定？")]
    assert "現實時間落在半夜就挪開" not in box and "挪不開" in box
