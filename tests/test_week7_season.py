"""7 天濃縮測試季（企劃者 2026-10-20，計畫 docs/superpowers/plans/2026-10-20-七天濃縮季.md）：week7 設定走 21 天季那一套骨架
（照現實天的季曆、現實天換日、照天排的時刻表、每天的軍令懸賞推線、簽到、銀兩出口、第 6 批的上限與人物回復），季曆分三段
（第 1～2、3～4、5～7 天）當三「週」，大決戰在第 2、4、7 天。21 天季、週末的季一個字都不變。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import calendar, checkin, figures, orders, ranks, rules, silver, timetable, treasures, world
from tianxia.state import new_game_state
from tianxia.world_state import fresh_season, stamp_season

pytestmark = pytest.mark.slow  # 每一條都載真實內容、開一季

HOUR, DAY = 3600, 86400
WEEK = 7 * DAY
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
WED = 1792549800  # 2026-10-21 週三 10:30（台灣）
WED_OFFSET = 2 * DAY + 10.5 * HOUR
WED14 = WED + 3.5 * HOUR  # 2026-10-21 週三 14:00（台灣）
ORDER = ["uprising", "court_mobilizes", "zhangmancheng_wan", "bocai_routs_zhujun", "changshe_fire", "luzhi_siege",
         "qinjie_slays_zhangmancheng", "wancheng", "luzhi_jailed", "zhangjiao_dies", "guangzong", "xiaquyang"]
GENERALS = ("huangfusong", "zhujun", "luzhi", "sunjian", "fuxie", "qinjie")


def _season(content, now=MON):
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    return season


def _vehicle(content, now=MON):
    season = _season(content, now)
    world.settle_season_start(season, content, random.Random(0))
    return world._season_vehicle(content, season)


def _advance(vehicle, content, to):
    world.advance_world_state(vehicle.world, content, to - vehicle.world.time, random.Random(0))


def _player(content, now=MON):
    state = new_game_state(content, "甲")
    state.world = _season(content, now)
    return state


# ── Task 1：季曆照段、錨點與畫面上的時刻 ──


def test_the_week7_profile_turns_on_the_real_day_frame_in_three_segments():
    cfg = real_content("week7").config
    assert cfg.season21 and cfg.season_days == 7 and cfg.season_weeks == 3 and cfg.season_segments == [2, 2, 3]
    assert real_content("season21").config.season_segments == [] and real_content("weekend").config.season_segments == []
    assert real_content().config.season_segments == []


def test_an_afternoon_opening_still_has_seven_days():
    """Review Focus 1：週三 14:00 開季，開季那天就是第 1 天；季末第 8 天 00:00（畫面寫第 7 天 23:59）。"""
    c7 = real_content("week7")
    season = _season(c7, now=WED14)
    assert season.season21 and season.cal_offset == 14 * HOUR and calendar.week7_on(season, c7)
    assert calendar.stamp_text(0, c7, season) == "第 1 天 14:00"
    finale = season.schedule["finale"]
    assert finale == 7 * DAY - 14 * HOUR
    assert calendar.stamp_text(finale, c7, season) == "第 7 天 23:59"
    assert world.season_end_time(season, c7) == finale


def test_segments_split_the_calendar():
    """Review Focus 2：第 1～2、3～4、5～7 天三段；季末之後夾在第 7 天。"""
    c7 = real_content("week7")
    season = _season(c7)

    def at(day, hour=0, minute=0):
        return calendar.point((day - 1) * DAY + hour * HOUR + minute * 60, c7, season)

    assert [at(1).week, at(2, 23, 59).week, at(3).week, at(4, 23, 59).week, at(5).week, at(7, 23, 59).week] == [1, 1, 2, 2, 3, 3]
    assert [at(1).cal_day, at(3).cal_day, at(7, 12).cal_day] == [1, 3, 7]
    assert [calendar.week_start(w, c7, season) for w in (1, 2, 3, 4)] == [0, 2 * DAY, 4 * DAY, 7 * DAY]
    assert calendar.point(10 * DAY, c7, season).cal_day == 7
    assert calendar.total_days(c7) == 7 and calendar.cal_scale(c7, season) == 1
    assert calendar.week_seconds(c7, season) == pytest.approx(7 * DAY / 3)


def test_season21_and_weekend_calendars_unchanged():
    """Review Focus 4：21 天季、週末同一刻的字、週初與「一週」跟以前一樣。"""
    c21 = real_content("season21")
    s21 = _season(c21, now=WED)
    assert not calendar.week7_on(s21, c21)
    assert calendar.stamp_text(0, c21, s21) == "第 1 週・週三 10:30"
    assert calendar.week_start(2, c21, s21) == WEEK - WED_OFFSET and calendar.total_days(c21) == 21
    assert calendar.week_seconds(c21, s21) == WEEK
    wk = real_content("weekend")
    swk = _season(wk)
    assert calendar.stamp_text(0, wk, swk) == "第 1 週・週一 00:00" and calendar.total_days(wk) == 84
    assert calendar.week_seconds(wk, swk) == WEEK / calendar.cal_scale(wk, swk)
    assert calendar.point_text(calendar.point(5 * HOUR, wk, swk)) == calendar.stamp_text(5 * HOUR, wk, swk)


def test_a_season21_program_warns_on_a_week7_season():
    """Review Focus 5：兩邊都是照現實天的季，季長不一樣也要印對不上那一行（season_weeks 不在章上）。"""
    c7, c21 = real_content("week7"), real_content("season21")
    assert calendar.profile_warning(c21, _season(c7, now=WED14)) is not None
    assert calendar.profile_warning(c7, _season(c7, now=WED14)) is None
    assert calendar.profile_warning(c7, _season(c21, now=WED)) is not None
    assert calendar.profile_warning(c21, _season(c21, now=WED)) is None


# ── Task 2：7 天的時刻表、出兵與伏筆照天 ──


def test_week7_has_its_own_timetable_with_battles_on_days_2_4_7():
    c7 = real_content("week7")
    assert [e.id for e in c7.timetable] == ORDER
    season = _season(c7)
    at = {e.id: timetable.when_in(season, c7, e) for e in c7.timetable}
    assert [at["uprising"], at["court_mobilizes"], at["zhangmancheng_wan"], at["bocai_routs_zhujun"]] == [
        0, 12 * HOUR, 20 * HOUR, DAY + 12 * HOUR]
    assert [at["luzhi_siege"], at["qinjie_slays_zhangmancheng"], at["luzhi_jailed"], at["zhangjiao_dies"]] == [
        2 * DAY + 12 * HOUR, 3 * DAY + 12 * HOUR, 4 * DAY + 12 * HOUR, 5 * DAY + 12 * HOUR]
    battles = [at["changshe_fire"], at["wancheng"], at["guangzong"]]
    assert battles == [DAY + 20 * HOUR, 3 * DAY + 20 * HOUR, 6 * DAY + 20 * HOUR]
    assert [calendar.stamp_text(t, c7, season) for t in battles] == ["第 2 天 20:00", "第 4 天 20:00", "第 7 天 20:00"]
    assert at["xiaquyang"] == 7 * DAY
    [tianming] = c7.mandate_timetable
    assert timetable.default_time(tianming, c7, season) == 6 * DAY + 22 * HOUR


def test_season21_timetable_is_unchanged():
    c21 = real_content("season21")
    season = _season(c21)
    at = {e.id: timetable.when_in(season, c21, e) for e in c21.timetable}
    assert at["changshe_fire"] == 5 * DAY + 20 * HOUR and at["wancheng"] == WEEK + 5 * DAY + 20 * HOUR
    assert at["guangzong"] == 2 * WEEK + 5 * DAY + 20 * HOUR and at["xiaquyang"] == 3 * WEEK


def test_an_afternoon_opening_settles_the_morning_in_order():
    """第 1 天 14:00 開季：00:00 起義、12:00 朝廷出兵在開季那一刻結算，20:00 那一件還沒到。"""
    c7 = real_content("week7")
    v = _vehicle(c7, now=MON + 14 * HOUR)
    assert {"uprising", "court_mobilizes"} <= set(v.world.timeline) and "zhangmancheng_wan" not in v.world.timeline


def test_the_generals_march_out_at_noon_of_day_one():
    c7 = real_content("week7")
    state = world._season_vehicle(c7, _season(c7))
    for fid in GENERALS:
        assert not figures.started(state, c7, fid, 11.9 * HOUR) and figures.started(state, c7, fid, 12 * HOUR), fid
    assert figures.start_text(state, c7, GENERALS[0]) == "（第 1 天 12:00 起）"


def test_the_two_buyers_come_between_changshe_and_wancheng():
    c7 = real_content("week7")
    cond = c7.events["fs_ev_two_buyers"].condition.model_copy(update={"factions": []})
    state = _player(c7)
    seen = []
    for day in (1, 2, 4, 5):
        state.world.time = (day - 1) * DAY + 13 * HOUR
        seen.append(rules.check_condition(cond, state, c7))
    assert seen == [False, True, True, False]


# ── Task 3：每天的批次、簽到、銀兩出口與上限照 7 天 ──


def test_orders_and_bounties_come_every_day():
    c7 = real_content("week7")
    v = _vehicle(c7)
    assert orders.daily(v, c7)
    live = [o for o in v.world.orders if not o.done]
    assert {"guan", "huang"} <= {o.faction for o in live} and {o.week for o in live} == {1}
    assert {b.day for b in v.world.bounties if b.day} == {1}
    _advance(v, c7, 2 * DAY + 60)
    assert {o.week for o in v.world.orders if not o.done} == {3}
    assert 3 in {b.day for b in v.world.bounties if b.day}


def test_the_bounty_notice_counts_days():
    from tianxia import bounties

    c7 = real_content("week7")
    v = _vehicle(c7)
    b = next(b for b in v.world.bounties if b.day == 1 and b.kind == "strike")
    assert b.expires == 2 * DAY
    assert bounties.due_short(b, c7, v.world).startswith("到第 2 天・剩 ")


def _hang_day_less(content, now, day=2):
    """沒有「第幾天」（b.day 是 0）的那幾種懸賞，各走真正掛單的函式掛一張，掛在季曆第 day 天 12:00（週末、14 天的季是第 day 天 12:00）：
    系統掛的陣營通緝與官府通緝（post_auto）、玩家押錢掛的通緝（post）、大勢人物的追剿與復仇（post_figure）。回 (季, {名字: 那一張})。"""
    from tianxia import bounties

    season = _season(content, now)
    state = new_game_state(content, "甲")
    state.world = season
    start = calendar.day_start(day, content, season) if calendar.season21_on(season, content) else (day - 1) * DAY
    season.time = start + 12 * HOUR
    me = state.player
    me.faction, me.joined_at = "guan", -1e9  # 過了新手期
    me.stats.update({"fame": 1000, "evil": 100, "silver": 1000})  # 名聲、惡名夠高：陣營與官府都掛
    foe = new_game_state(content, "乙")
    foe.world = season
    foe.player.faction, foe.player.joined_at = "huang", -1e9
    assert bounties.post_auto(state, content)
    assert bounties.post(state, content, foe, 100)[0].startswith("你押了")
    for motive in ("追剿", "復仇"):
        assert bounties.post_figure(state, content, "qinjie", motive, "nanyang", "wan_city") is not None
    hung = {}
    for b in season.bounties:
        label = b.motive or (f"{b.auto_by}通緝" if b.auto_by else "押錢通緝")
        hung[label] = b
    assert set(hung) >= {"陣營通緝", "押錢通緝", "追剿", "復仇"}
    assert {b.day for b in hung.values()} == {0}  # 這幾種都沒有第幾天（FB-506 的前提）
    return season, hung


def test_day_less_bounty_notices_count_days_on_week7_fb506():
    """FB-506（7 天季複驗）：追剿、復仇、系統掛的通緝、玩家押錢掛的通緝沒有 b.day，告示掉到第一季那一支照週次寫「期限 第 2 週・剩 1」
    （7 天季的週是段，對不上任何東西），點開的紙上卻寫「第 4 天 12:00」。修後告示照到期那一刻寫第幾天，跟每天掛的那一批一個寫法：
    00:00 到期寫最後還有效的那一天（「到第 2 天」）、其他時刻寫「期限 第 4 天」。"""
    from tianxia import bounties

    c7 = real_content("week7")
    season, hung = _hang_day_less(c7, WED14)  # 第 2 天 12:00 掛
    assert calendar.stamp_text(season.time, c7, season) == "第 2 天 12:00"
    want = {  # 名字: (紙上, 告示)
        "陣營通緝": ("第 3 天 00:00", "到第 2 天・剩 1"),  # 掛在第 1 段，第 2 段（第 3 天）00:00 到期
        "官府通緝": ("第 3 天 00:00", "到第 2 天・剩 1"),
        "押錢通緝": ("第 4 天 20:00", "期限 第 4 天・剩 1"),
        "追剿": ("第 4 天 12:00", "期限 第 4 天・剩 1"),  # 追剿、復仇掛 2 個季曆天
        "復仇": ("第 4 天 12:00", "期限 第 4 天・剩 1"),
    }
    assert {name: (bounties.due_text(b, c7, season), bounties.due_short(b, c7, season)) for name, b in hung.items()} == want


def test_day_less_bounties_hung_in_the_last_segment_say_season_end_on_week7():
    """最後一段（第 5～7 天）掛的系統通緝撐到季末（到期在季曆終點）：告示與紙上都寫「到季末」，不寫成「第 8 天」或週次。"""
    from tianxia import bounties

    c7 = real_content("week7")
    season, hung = _hang_day_less(c7, WED14, day=6)
    for name in ("陣營通緝", "官府通緝"):
        b = hung[name]
        assert bounties.due_text(b, c7, season) == bounties.SEASON_END
        assert bounties.due_short(b, c7, season) == f"{bounties.SEASON_END}・剩 1"


@pytest.mark.parametrize("profile, want", [
    ("season21", ["到第 1 週・剩 1", "期限 第 2 週・剩 1", "期限 第 2 週・剩 1", "期限 第 2 週・剩 1"]),  # 21 天季：週就是週，不動
    ("weekend", ["到第 8 週・剩 1", "到第 8 週・剩 1", "期限 第 9 週・剩 1", "期限 第 9 週・剩 1", "期限 第 9 週・剩 1"]),
    (None, ["期限 第3天・剩 1"] * 5),  # 14 天的季只寫第幾天
])
def test_day_less_bounty_notices_are_unchanged_outside_week7_fb506(profile, want):
    """21 天季、週末、14 天的季：沒有第幾天的懸賞告示一個字不變（拿掉 b.day 的條件只動 7 天季那一支）。"""
    from tianxia import bounties

    content = real_content(profile) if profile else real_content()
    season, hung = _hang_day_less(content, WED14)
    notices = [bounties.due_short(b, content, season) for b in season.bounties]
    assert notices == want


def test_check_in_runs_seven_days_with_pills_on_days_3_and_6():
    c7 = real_content("week7")
    state = _player(c7)
    assert checkin.on(c7, state.world) and checkin.last_day(c7, state.world) == 7
    assert [checkin.gifts(c7, d) for d in range(1, 8)] == [
        ("silver",), ("material",), ("pills",), ("silver",), ("material",), ("pills", "tier4"), ("silver",)]
    view = checkin.view(state, c7, state.world)
    assert [cell["day"] for cell in view["week"]] == [1, 2, 3, 4, 5, 6, 7]
    state.world.time = 6 * DAY + HOUR
    assert checkin.view(state, c7, state.world)["next"] is None
    afternoon = _player(c7, now=WED14)
    assert checkin.last_day(c7, afternoon.world) == 7  # 開季那天不是週一也是七天


def test_silver_outlets_and_season_caps_are_a_third():
    c7 = real_content("week7")
    state = _player(c7)
    cfg = c7.config
    assert silver.on(c7, state.world) and silver.legend_left(state, c7) == 1
    assert [ranks.threshold(c7, r) for r in (2, 3, 4)] == [130, 430, 870]
    assert cfg.figure_treasure_cap == 1 and cfg.figure_treasure_weekly == 1 and cfg.sortie.treasure_cap == 1
    assert cfg.late_exp_step == 0.03 and cfg.duel.per_boss_week == 2 and cfg.haoqiang_allied
    assert figures.upkept(c7, state.world)
    assert cfg.season21_daily == real_content("season21").config.season21_daily  # 每天的那一批照天，跟 21 天季一樣


def test_week7_shortens_the_calendar_day_spans_pm_ruling_5():
    """PM 裁決第 5 條（2026-10-20，照「佔一季幾成」縮）：人物被打退後 1 天回來、復仇／追剿懸賞 2 天、求援 1 天；新手期不動。
    設定覆寫檔是淺層合併（content._config）：figure_life 只寫兩個鍵，其餘照預設——跟 21 天季的 figure_life 只差這兩個。"""
    c7, c21, wk, c14 = real_content("week7"), real_content("season21"), real_content("weekend"), real_content()
    cfg = c7.config
    assert cfg.figure_return_days == 1
    assert (cfg.figure_life.revenge_cal_days, cfg.figure_life.rally_cal_days) == (2, 1)
    for other in (c21, wk, c14):  # 21 天季、週末、14 天照舊：3 天、7 天、3 天
        o = other.config
        assert (o.figure_return_days, o.figure_life.revenge_cal_days, o.figure_life.rally_cal_days) == (3, 7, 3)
    assert cfg.figure_life.model_copy(update={"revenge_cal_days": 7.0, "rally_cal_days": 3.0}) == c21.config.figure_life
    assert cfg.newbie_real_hours == c21.config.newbie_real_hours == 48  # 新手期 48 小時不動


def test_the_weekly_treasure_cap_resets_each_segment():
    """Review Focus 3：照週的上限照段重算（第 3 天 00:00）。一季上限 1 件時第二段就不再掉，所以這裡把一季上限放開來看段。"""
    c7 = real_content("week7")
    state = _player(c7)
    c7.config.treasures.challenge_chance = 1.0
    c7.config.figure_treasure_cap = 0
    figs = list(c7.figures)

    def drops(fids, start):
        return [treasures.challenge_drop(state, c7, fid, 1, start + i + 1)[0] is not None for i, fid in enumerate(fids)]

    assert drops(figs[:2], 0) == [True, False]
    state.world.time = 2 * DAY - 60
    assert drops(figs[2:3], 10) == [False]  # 第 2 天 23:59 還是第 1 段
    state.world.time = 2 * DAY
    assert drops(figs[3:5], 20) == [True, False]


def test_the_boss_tally_resets_each_segment():
    from tianxia import duel

    c7 = real_content("week7")
    state = _player(c7)
    boss = next(iter(c7.duels))
    state.player.duel_tally[duel.week_key(state, c7, boss)] = 2
    assert duel.used_up(state, c7, boss)
    state.world.time = 2 * DAY
    assert not duel.used_up(state, c7, boss)


def test_a_week_is_a_segment_for_week_long_spans():
    from tianxia import bounties

    c7 = real_content("week7")
    v = _vehicle(c7)
    assert bounties.week_seconds(v, c7) == pytest.approx(7 * DAY / 3)
    c21 = real_content("season21")
    assert bounties.week_seconds(_vehicle(c21), c21) == WEEK
