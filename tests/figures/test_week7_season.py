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
from tianxia import calendar, duel, explore_modes, howto, orders, renown, rules, seats, timetable, world, yuedan
from tianxia.state import Order, YuedanEntry, new_game_state
import re
import test_prologue_web
import server
import webharness
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia import calendar, seal, seats, timetable
from tianxia import calendar, rules
from tianxia.world_state import fresh_season, season_length_days, stamp_season

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
    assert real_content("season21").config.season_segments == []
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
    # 第 4 階 870 → 600：企劃者 2026-10-22 選甲（開著領地爭奪的季貢獻累得比關著慢，戰書要季中就下得了；計畫 2026-10-22-7天季領地爭奪調整.md 第七節）
    assert [ranks.threshold(c7, r) for r in (2, 3, 4)] == [130, 430, 600]
    assert cfg.figure_treasure_cap == 1 and cfg.figure_treasure_weekly == 1 and cfg.sortie.treasure_cap == 1
    assert cfg.late_exp_step == 0.03 and cfg.duel.per_boss_week == 2 and cfg.haoqiang_allied
    assert figures.upkept(c7, state.world)
    assert cfg.season21_daily == real_content("season21").config.season21_daily  # 每天的那一批照天，跟 21 天季一樣


def test_week7_shortens_the_calendar_day_spans_pm_ruling_5():
    """PM 裁決第 5 條（2026-10-20，照「佔一季幾成」縮）：人物被打退後 1 天回來、復仇／追剿懸賞 2 天、求援 1 天；新手期不動。
    設定覆寫檔是淺層合併（content._config）：figure_life 只寫兩個鍵，其餘照預設——跟 21 天季的 figure_life 只差這兩個。"""
    c7, c21, c14 = real_content("week7"), real_content("season21"), real_content()
    cfg = c7.config
    assert cfg.figure_return_days == 1
    assert (cfg.figure_life.revenge_cal_days, cfg.figure_life.rally_cal_days) == (2, 1)
    for other in (c21, c14):  # 21 天季、14 天照舊：3 天、7 天、3 天
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


# ── 原 test_fb501_week7_words.py（整檔搬進來） ──
# FB-501（7 天濃縮季 QA 第 7 件清單，PM 2026-10-20）：7 天季還寫「週」的地方換成段（或軍令的「今日／每天」）。
# 季曆有段的季（calendar.week7_on）才換字，換字一律走 calendar.week_word／week_label（網頁走 week_words 送的那一份）；
# 21 天季、週末、14 天一個字都不變（例外：暫停再繼續那一句照季寫季長，21 天季照舊）。字待 joy 潤。
# FB-502（PM 2026-10-20）推翻「21 天季不動」的軍令那幾個字：21 天季的軍令也每天一道，照「今日／每天」寫，見
# test_fb502_season21_order_words；這裡 21 天季只驗段以外的「週」照舊。

WED14_fb501 = 1792549800 + 3.5 * HOUR  # 2026-10-21 週三 14:00（台灣）


BOSS = "段鐵頭"  # 頭目次數用完那一句的名字（FB-672：explore_modes.boss_gone 多一個 name）


def _content(profile):
    return real_content(profile) if profile else real_content()


def _state(content, now=MON):
    state = new_game_state(content, "甲")
    state.world = _season(content, now)
    return state


# ── 同一個函式：calendar.week_word／week_label／week_words ──


def test_week7_names_segments_with_their_days():
    c7 = real_content("week7")
    s7 = _season(c7)
    assert [calendar.segment_days(w, c7) for w in (1, 2, 3)] == [(1, 2), (3, 4), (5, 7)]
    assert [calendar.week_label(w, c7, s7) for w in (1, 2, 3)] == [
        "第 1 段（第 1～2 天）", "第 2 段（第 3～4 天）", "第 3 段（第 5～7 天）"]
    assert calendar.week_label(1, c7, s7, form="tight") == "第 1 段（第 1～2 天）"
    assert calendar.week_label(2, c7, s7, form="end") == "第 2 段末（第 4 天）"
    assert calendar.week_label(2, c7, s7, form="inner") == "第 2 段・第 3～4 天"
    assert [calendar.week_word(k, c7, s7) for k in ("this", "this_one", "each", "order_this", "order_that", "order_each")] == [
        "這一段", "這一段", "每段", "今日", "今天", "每天"]
    words = calendar.week_words(c7, s7)
    assert words["this"] == "這一段" and words["names"][2] == "第 3 段（第 5～7 天）" and words["ends"][0] == "第 1 段末（第 2 天）"


@pytest.mark.parametrize("profile", ["season21", None])
def test_other_seasons_keep_their_week_words(profile):
    content = _content(profile)
    season = _season(content)
    assert [calendar.week_label(2, content, season, form=f) for f in ("", "tight", "end", "inner")] == [
        "第 2 週", "第2週", "第 2 週週末", "第 2 週"]
    assert [calendar.week_word(k, content, season) for k in ("this", "this_one", "each")] == ["本週", "這一週", "每週"]
    assert calendar.week_word("this", content, None) == "本週"  # 沒有季（上一季的江湖史）照原本的字
    if profile != "season21":  # 21 天季的軍令每天一道，軍令的字與 words 照「今日／每天」（FB-502，test_fb502_season21_order_words）
        assert calendar.week_words(content, season) is None
        assert [calendar.week_word(k, content, season) for k in ("order_this", "order_that", "order_each")] == ["本週", "這週", "每週一"]


# ── 4. 練功鈕「這一週他不再現身」──


def test_the_boss_line_names_the_next_segment_day():
    c7 = real_content("week7")
    state = _state(c7)
    # FB-672：這一句多帶頭目的名字（「這一段他不再現身」→「這一段頭目某某不再現身」）；哪一天再來、哪一種季寫哪個詞這一張沒動
    state.world.time = DAY + HOUR  # 第 2 天：第 1 段，下一段第 3 天
    assert explore_modes.boss_gone(state, c7, BOSS) == "這一段頭目段鐵頭不再現身，第 3 天 00:00 再來"
    state.world.time = 3 * DAY + HOUR  # 第 4 天：第 2 段，下一段第 5 天
    assert explore_modes.boss_gone(state, c7, BOSS) == "這一段頭目段鐵頭不再現身，第 5 天 00:00 再來"
    state.world.time = 5 * DAY  # 第 6 天：最後一段，季末之前不再重算
    assert explore_modes.boss_gone(state, c7, BOSS) == explore_modes.BOSS_GONE_SEASON.format(name=BOSS)


def test_the_boss_line_reads_the_live_option_on_week7():
    """引擎那一顆練功鈕（Game._practice_option 的頭目分支）走 boss_gone：用滿這一段的次數就寫段。"""
    c7 = real_content("week7")
    state = _state(c7, now=WED14_fb501)
    boss = next(iter(c7.duels))
    state.player.duel_tally[duel.week_key(state, c7, boss)] = c7.config.duel.per_boss_week
    assert duel.used_up(state, c7, boss)
    assert explore_modes.boss_gone(state, c7, BOSS).startswith("這一段頭目段鐵頭不再現身，第 3 天")


@pytest.mark.parametrize("profile,line", [("season21", explore_modes.BOSS_GONE_WEEK), (None, explore_modes.BOSS_GONE_SEASON)])
def test_other_seasons_keep_the_boss_line(profile, line):
    content = _content(profile)
    assert explore_modes.boss_gone(_state(content), content, BOSS) == line.format(name=BOSS)


# ── 5. 名聲：每週通緝、每週海捕文書 ──


def test_renown_perks_say_each_segment_on_week7():
    c7 = real_content("week7")
    s7 = _season(c7)
    fame = [p for t in range(1, 5) for p in renown.fame_perks(c7, t, s7)]
    kou = [p for t in range(1, 5) for p in renown.virtue_perks(c7, "寇", t, s7)]
    assert "敵方陣營每段通緝你" in fame and not any("每週" in p for p in fame)
    assert any(p.startswith("官府每段貼你的海捕文書") for p in kou) and not any("每週" in p for p in kou)
    howto_text = "".join(howto.renown_lines(c7, s7))
    assert "每段通緝你" in howto_text and "官府每段貼你" in howto_text


@pytest.mark.parametrize("profile", ["season21", None])
def test_renown_perks_keep_each_week_elsewhere(profile):
    content = _content(profile)
    season = _season(content)
    for t in range(1, 5):
        assert renown.fame_perks(content, t, season) == renown.fame_perks(content, t)
        for way in renown.PATHS:
            assert renown.virtue_perks(content, way, t, season) == renown.virtue_perks(content, way, t)


# ── 3. 主線與玩法說明：軍令每天一道 ──


def test_howto_says_orders_come_every_day_on_week7():
    c7 = real_content("week7")
    state = _state(c7)
    quest = "".join(howto.war_help(state, c7)["quest"])
    assert "投靠陣營之後每天有軍令" in quest and "每週一" not in quest
    join = "".join(howto.join_lines(c7, state.world))
    assert "**軍令**：每天發令" in join and "今日的軍令卡在江湖頁行動列底下" in join
    assert "每週一" not in join and "本週" not in join


# ── 11. 軍令的字（content/orders.json 的 {本週}{這週}）──


def _order(world_state):
    return Order(id="o1", template="intercept", faction="guan", week=1, quota=10, text="")


def test_order_text_slots_follow_the_season():
    """21 天季（軍令也每天一道）見 test_fb502_season21_order_words（FB-502）。"""
    c7 = real_content("week7")
    s7 = _state(c7)
    raw = "{地點}，{本週}截斷它；{人物}{這週}連敗幾陣。"
    assert orders.fill(s7, c7, _order(s7), raw).endswith("，今日截斷它；今天連敗幾陣。")


def test_issued_orders_read_today_on_week7_only():
    c7 = real_content("week7")
    for content, want, never in ((c7, "今日", "本週"),):
        season = _season(content)
        world.settle_season_start(season, content, random.Random(0))
        texts = [o.text for o in season.orders]
        assert texts and not any("{" in t for t in texts)
        assert not any(never in t for t in texts)
        intercept = [t for t in texts if "截斷它" in t]
        assert all(f"{want}截斷它" in t for t in intercept)


# ── 12. 月旦評、第 4 階席次 ──


def _publish_yuedan(content, week):
    state = _state(content)
    state.world.yuedan = [YuedanEntry(week=week, name="乙", board="名人", line="名動四方，一時無兩", at=0.0)]
    yuedan.publish(state, content)
    return state.world.rumors[-1].text


def test_yuedan_head_names_the_segment_on_week7():
    assert _publish_yuedan(real_content("week7"), 2).startswith("許劭月旦評（第 2 段・第 3～4 天）：")
    assert _publish_yuedan(real_content("season21"), 2).startswith("許劭月旦評（第 2 週）：")


def test_seat_rotation_rumor_says_this_segment_on_week7():
    for profile, head in (("week7", "這一段在任的"), ("season21", "本週在任的")):
        content = _content(profile)
        state = _state(content)
        state.world.seat_ledger = {"guan": {"乙": {1: 5}}}
        seats.rotate(state, content, 2)
        assert any(r.text.startswith(head) for r in state.world.rumors), profile


# ── 9、10. 管理者：時刻表、開季、暫停再繼續 ──


def test_default_dates_follow_the_week7_timetable():
    assert timetable.default_dates_note(real_content("week7")) == "預設在第 2、4、7 天 20:00、季末第 7 天過完"
    assert timetable.default_dates_note(_content(None)) is None


def test_default_dates_follow_the_season21_timetable():
    """修前重現：21 天季這一句 None，網頁退回週末的「預設在第 6、9、11 週中、第 12 週末」（21 天季只有 3 週；PM 2026-10-20）。
    寫的要跟開季真正排進 schedule 的時刻對得上。"""
    c21 = real_content("season21")
    assert timetable.default_dates_note(c21) == "預設在第 1、2、3 週週六 20:00、季末第 3 週週日過完"
    season = _season(c21)
    for e in (e for e in c21.timetable if e.kind == "showdown"):
        p = calendar.point(timetable.when_in(season, c21, e), c21, season)
        assert (p.week, calendar.WEEKDAYS[p.weekday], p.hour) == (e.week, "六", 20), e.id
    finale = next(e for e in c21.timetable if e.kind == "finale")
    assert timetable.when_in(season, c21, finale) == calendar.calendar_end(c21, season)  # 最後一週週日過完
    assert calendar.point(calendar.calendar_end(c21, season) - 60, c21, season).week == finale.week


def test_resume_line_names_the_season_length():
    c7, c21 = real_content("week7"), real_content("season21")
    assert world.resume_skip_text(_season(c7), c7, 3600) == "7 天的季：季曆對回現實的日子，暫停期間的大事在這一刻一起發生，季末照原本的日期"
    assert world.resume_skip_text(_season(c21), c21, 3600) == world.RESUME_SKIP_REAL
    assert world.RESUME_SKIP_REAL == "21 天的季：季曆對回現實的星期，暫停期間的大事在這一刻一起發生，季末照原本的日期"


# ── 網頁的那一份：status.calendar.words、管理者那一份 ──


def _game(profile, opened=MON):
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    content = _content(profile)
    content.config.admins = ["甲"]
    content.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(content)
    game = Game.new(content, "甲", rng=random.Random(0), world=store)
    game.client = None
    game.admin_open_season(opened)
    game.state.player.faction = "guan"
    game.sync(opened)
    return game


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_status_sends_the_words_only_on_week7(profile):
    cal = _game(profile).status_data()["calendar"]
    if profile == "week7":
        assert cal["words"]["names"][0] == "第 1 段（第 1～2 天）" and cal["words"]["order_this"] == "今日"
    elif profile == "season21":  # 只有軍令的字（FB-502）：沒有段的名字，網頁的「週」照原本的字
        assert "names" not in cal["words"] and "this" not in cal["words"] and cal["words"]["order_this"] == "今日"
    else:
        assert "words" not in cal


ADMIN = {  # 管理者時刻表第一列與最後一列的開頭、暫停那一句、開季問句括號裡那一句
    "week7": ("第 1 段（第 1～2 天）　三十六方起義", "第 3 段（第 5～7 天）　", {"days": "7", "unit": "日子"},
              "預設在第 2、4、7 天 20:00、季末第 7 天過完"),
    "season21": ("第1週　三十六方起義", "第3週　", {"days": "21", "unit": "星期"},
                 "預設在第 1、2、3 週週六 20:00、季末第 3 週週日過完"),
}


@pytest.mark.parametrize("profile", list(ADMIN))
def test_admin_view_labels_and_lines(profile, monkeypatch):
    """一個資料庫一季：照季各開一個測試（同一個測試開兩季會讀到同一份季）。"""
    import server

    first, last, realign, dates = ADMIN[profile]
    game = _game(profile, opened=WED14_fb501 if profile == "week7" else MON)
    monkeypatch.setattr(server, "CONTENT", game.content)  # 伺服器整理管理者資料讀的是 server.CONTENT
    rows = server.timetable_choices(game)["timetable"]
    assert rows[0]["label"] == first and rows[-1]["label"].startswith(last)
    view = server.admin_choices(game)
    assert view["realign"] == realign and view["default_dates"] == dates


# ── 原 test_fb501_week7_words_web.py（整檔搬進來） ──
# FB-501 的網頁那一半（7 天濃縮季 QA 第 7 件清單）：軍令卡、大事小標、季末結算卡、輿圖（天下怎麼變、總覽、地點的易手、正在看第幾段、
# 比第幾段）、管理者（每週的事、立刻發軍令、開季、暫停、繼續、重發軍令、輪替席次）在 7 天季照段（或今日）寫；21 天季、週末照原本的字。
# 在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的資料；沒有 node 就略過。

# 輿圖第三版第 4 批：總覽（overviewHtml）挪到卡底下（cardExtras）、地點的卡換成 placeCard、「天下」那一條（hudHtml）拿掉了，
# 比第幾段改看版圖變化那一格（timelineHtml 的處數底下）
NAMES = ["S", "ordersHtml", "trendsTopHtml", "resultHtml", "timelineHtml", "cardExtras", "placeCard", "mapChrome",
         "sheetHtml", "adminAsk"]


DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)


ORDERS = [{"title": "守城", "text": "守住", "progress": 1, "quota": 5, "done": False, "mine": 0, "deadline": "第 2 天 00:00"}]


RESULT = {"title": "黃天當立", "text": "<p>終</p>", "stances": [], "fronts": [], "rankings": [],
          "timeline": [{"week": 1, "title": "三十六方起義", "text": "<p>起</p>", "locked_by": None},
                       {"week": 3, "title": "廣宗決戰", "text": "<p>戰</p>", "locked_by": None}]}


def _game_fb501(profile):
    content = real_content(profile)
    content.config.admins = ["甲"]
    content.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(content)
    game = Game.new(content, "甲", rng=random.Random(0), world=store)
    game.client = None
    game.admin_open_season(MON)
    game.state.player.faction = "guan"
    game.sync(MON + DAY + HOUR)  # 第 2 天：第 1 段
    return game


def _map_state(game):
    """輿圖的疊層：照伺服器給的，再補第 1、2 段的快照與一次易手、一則大事（開季第 2 天還沒有易手），看段的字。"""
    st = game.map_state()
    control = {p: "guan" for p in st["places"]}
    st.update(now_week=2, start=None, events=["三十六方起義"], territory=True,
              weeks=[{"week": 1, "control": control, "ropes": {}, "geju": None, "events": ["三十六方起義"], "changed": []},
                     {"week": 2, "control": control, "ropes": {}, "geju": None, "events": [], "changed": []}])
    place = next(iter(st["places"]))
    st["places"][place]["flips"] = [{"week": 1, "from": "huang", "to": "guan"}]
    return st, place


def _render(game, monkeypatch, app=None):
    """畫一輪這一季的那幾處，回一個 dict（名字 → 字）。app 給了就用那一份 app.js（對照舊版用）。"""
    monkeypatch.setattr(server, "CONTENT", game.content)
    st, place = _map_state(game)
    m = {**server.main_view(game), "admin": True, "bulletin": ["<p>甲事</p>"]}
    script = """
      const st = H.S.mapState, base = H.S.mapBase, fb = H.S.fb501;
      H.S.mapMode = "timeline"; H.S.mapWeek = 1;
      return {
        orders: H.ordersHtml(fb.orders, 1, null),
        board: (/<h3>(.*?)<\\/h3>/.exec(H.trendsTopHtml(m)) || [])[1],  // 本週江湖大事（減法季批 1 搬到見聞・大事・大勢最上面）
        result: H.resultHtml(fb.result),
        timeline: H.timelineHtml(base, st, 1),
        overview: H.cardExtras(base, st),
        place: H.placeCard(base, st, fb.place),
        hud: H.timelineHtml(base, st, 2),
        chrome: H.mapChrome(),
        sheet: H.sheetHtml(),
        open: H.adminAsk("open_season", {})[0],
        next: H.adminAsk("next_season", {})[0],
        pause: H.adminAsk("pause_clock", {})[0],
        resume: H.adminAsk("resume_clock", {})[0],
        issue: H.adminAsk("issue_orders", {})[0],
        rotate: H.adminAsk("rotate_seats", {})[0],
      };"""
    payload = {"m": m, "script": script, "menxia": None, "stored": {}, "responses": {},
               "S": {"mapBase": game.map_base(), "mapState": st, "admin": server.admin_choices(game),
                     "fb501": {"orders": ORDERS, "result": RESULT, "place": place}}}
    if app is not None:
        payload["app"] = str(app)
    return webharness.run(DRIVER, payload)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_week7_pages_say_segments_and_today(monkeypatch):
    out = _render(_game_fb501("week7"), monkeypatch)
    assert "📜 今日軍令（1）" in out["orders"]
    assert out["board"] == "這一段江湖大事"
    assert "<b>第 1 段（第 1～2 天）・三十六方起義</b>" in out["result"] and "<b>第 3 段（第 5～7 天）・廣宗決戰</b>" in out["result"]
    assert "<small>第 1 段末（第 2 天）</small>" in out["timeline"] and "<h4>第 1 段（第 1～2 天）</h4>" in out["timeline"]
    assert "<h4>這一段大事</h4>" in out["overview"]
    assert "易手：第 1 段（第 1～2 天） " in out["place"]
    assert "比第 1 段（第 1～2 天）" in out["hud"]
    assert "正在看第 1 段（第 1～2 天）" in out["chrome"]
    assert "每天、每段的事（照 00:00 的做法立刻再做一次；之後照常）" in out["sheet"] and "立刻發今日軍令" in out["sheet"]
    assert "（預設在第 2、4、7 天 20:00、季末第 7 天過完）" in out["open"] and "（預設在第 2、4、7 天 20:00、季末第 7 天過完）" in out["next"]
    assert "7 天的季：繼續時季曆會對回現實的日子" in out["pause"] and "7 天的季的季曆對回現實的日子" in out["resume"]
    assert out["issue"].startswith("立刻發今日軍令：今天還沒達成的軍令") and "明天 00:00 照常發令" in out["issue"]
    assert "照上一段的貢獻" in out["rotate"] and "下一段第一天 00:00 照常再排" in out["rotate"]
    assert not any("週" in v for v in out.values() if isinstance(v, str) and v is not out["sheet"])


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_timeline_head_keeps_the_segment_end_on_one_line():
    """實機 375 寬：「第 1 段末（第 2 天）」拆在括號裡（「（第」／「2 天）」）；那一小行不折行，整段換到下一行（CSS，幾何在瀏覽器量過）。"""
    css = (webharness.ROOT / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.m-tl-head small \{([^}]*)\}", css)
    assert rule and "white-space: nowrap" in rule.group(1)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.parametrize("profile", ["season21"])
def test_other_seasons_keep_the_week_words(profile, monkeypatch):
    out = _render(_game_fb501(profile), monkeypatch)
    assert out["board"] == "本週江湖大事"
    assert "<b>第 1 週・三十六方起義</b>" in out["result"]
    assert "<small>第 1 週週末</small>" in out["timeline"] and "<h4>第 1 週</h4>" in out["timeline"]
    assert "<h4>本週大事</h4>" in out["overview"] and "易手：第 1 週 " in out["place"]
    assert "比第 1 週" in out["hud"] and "正在看第 1 週" in out["chrome"]
    # 開季問句括號裡的預設時刻照這一種季自己的時刻表寫：21 天季「週六 20:00」三場、週末「週中」（dev/small-1020 改了 21 天這一句，FB-560）
    default_dates = "（預設在第 1、2、3 週週六 20:00、季末第 3 週週日過完）" if profile == "season21" else "（預設在第 6、9、11 週中、第 12 週末）"
    assert default_dates in out["open"]
    assert "照上一週的貢獻" in out["rotate"]
    if profile == "season21":
        assert "21 天的季：繼續時季曆會對回現實的星期" in out["pause"] and "21 天的季的季曆對回現實的星期" in out["resume"]
    else:
        assert "天的季" not in out["pause"] and "天的季" not in out["resume"]


# ── 原 test_fb503_week7_segment_leaks.py（整檔搬進來） ──
# FB-503（7 天濃縮季第二輪，PM 2026-10-20）：FB-501 清單外還寫「週」的地方，7 天季照段寫（calendar.week_word／week_label）：
# 第 3、4 階行動「這週已經做滿 N 次」、補上第 4 階席次「到下週一為止」、管理者輪替席次的回話、管理者「這一季立刻蓋天命之季的章」
# 問句裡天命之爭的時刻。21 天季、週末、14 天一個字都不變（例外：天命之爭那一句 PM 2026-10-20 改成 21 天季也照時刻表寫
# 「第 3 週週日 20:00」，不再寫週末的「第 12 週週一 20:00」；週末、14 天照舊）。字待 joy 潤。

# ── 第 3、4 階行動：做滿了 ──


def _rank_option(profile):
    game = _game(profile)
    c, p = game.content, game.state.player
    p.faction, p.rank, p.location, p.stamina = "huang", 3, "runan", 100
    week = calendar.point(game.state.world.time, c, game.state.world).week
    weekly = next(a for a in c.orders.rank_actions if a.id == "incite").weekly
    p.rank_action_weeks = {f"{week}:incite": weekly}
    return next(o for o in game.options(odds=False) if o.id == "act:rank:incite")


@pytest.mark.parametrize("profile,word", [("week7", "這一段"), ("season21", "這週")])
def test_the_rank_action_cap_names_the_segment_on_week7(profile, word):
    option = _rank_option(profile)
    assert not option.enabled and option.label == f"在一地煽動起事（{word}已經做滿 3 次）"


# ── 補上第 4 階席次：到什麼時候為止 ──


def _seat_line(profile, at):
    content = _content(profile)
    state = _state(content)
    state.world.time = at
    p = state.player
    p.faction, p.qualified = "guan", True
    return seats.report(state, content)


def test_a_filled_seat_lasts_until_the_next_segment_on_week7():
    assert _seat_line("week7", DAY + HOUR) == ["你補上了校尉的缺，到第 3 天 00:00 為止。"]  # 第 1 段
    assert _seat_line("week7", 3 * DAY + HOUR) == ["你補上了校尉的缺，到第 5 天 00:00 為止。"]  # 第 2 段
    assert _seat_line("week7", 5 * DAY + HOUR) == ["你補上了校尉的缺，到季末為止。"]  # 最後一段沒有下一段


@pytest.mark.parametrize("profile", ["season21"])
def test_a_filled_seat_lasts_until_next_monday_elsewhere(profile):
    assert _seat_line(profile, DAY + HOUR) == ["你補上了校尉的缺，到下週一為止。"]


# ── 管理者：輪替第 4 階席次的回話 ──


def _rotate(profile, at):
    game = _game(profile)
    game.sync(MON + at / game.content.config.time_scale)
    return game.admin_rotate_seats()[0]


def test_admin_rotation_reply_names_segments_on_week7():
    assert _rotate("week7", DAY + HOUR) == "（第 1 段沒有上一段的貢獻可排；空缺照常由有資格的人補上。）"


def test_admin_rotation_reply_in_the_second_segment():
    msg = _rotate("week7", 3 * DAY + HOUR)
    assert msg.startswith("已照第 1 段（第 1～2 天）的貢獻輪替第 4 階席次（下一段第一天 00:00 照常再排）——"), msg


def test_admin_rotation_reply_in_the_last_segment():
    msg = _rotate("week7", 5 * DAY + HOUR)
    assert msg.startswith("已照第 2 段（第 3～4 天）的貢獻輪替第 4 階席次（這是最後一段，季末之前不再排）——"), msg


@pytest.mark.parametrize("profile", ["season21"])
def test_admin_rotation_reply_unchanged_elsewhere(profile):
    assert _rotate(profile, HOUR) == "（第 1 週沒有上一週的貢獻可排；空缺照常由有資格的人補上。）"


# ── 管理者：這一季立刻蓋天命之季的章 ──


def test_mandate_note_reads_the_week7_timetable():
    c7 = real_content("week7")
    assert timetable.mandate_note(c7, _season(c7)) == "第 7 天 22:00"
    content = _content(None)
    assert timetable.mandate_note(content, _season(content)) is None


def test_mandate_note_reads_the_season21_timetable():
    """修前重現：21 天季這一句 None，網頁退回週末的「第 12 週週一 20:00」（21 天季只有 3 週，天命之爭排在第 3 週週日 20:00）。"""
    c21 = real_content("season21")
    assert timetable.mandate_note(c21, _season(c21)) == "第 3 週週日 20:00"


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_the_mandate_ask_names_the_time_the_stamp_really_schedules(profile):
    """問句寫的就是「這一季立刻蓋章」真正會排的時刻（timetable.default_time 排進 schedule）：蓋完看排進去的世界秒換成季曆的時刻。
    問句括號裡另寫了「現實時間落在半夜會盡量挪開」，所以週末（一週只有現實 5 小時，預設時刻常落在半夜）比的是挪之前的預設時刻；
    照現實天的季（21 天季、7 天季）預設時刻不落在半夜，排進去的就是它。"""
    game = _game(profile, opened=WED14_fb501 if profile == "week7" else MON)
    c = game.content
    game.admin_seal_mandate("now")
    at = timetable.default_time(seal.mandate_event(c), c, game.state.world)
    assert game.state.world.schedule["tianming"] == at
    p = calendar.point(at, c, game.state.world)
    if profile == "week7":
        really = f"第 {p.cal_day} 天 {p.hour:02d}:{p.minute:02d}"
    else:
        really = f"第 {p.week} 週週{calendar.WEEKDAYS[p.weekday]} {p.hour:02d}:{p.minute:02d}"
    assert timetable.mandate_note(c, game.state.world) == really


@pytest.mark.parametrize("profile,when", [("week7", "第 7 天 22:00"), ("season21", "第 3 週週日 20:00")])
def test_the_admin_mandate_ask_names_the_week7_time(profile, when, monkeypatch):
    game = _game(profile)
    monkeypatch.setattr(server, "CONTENT", game.content)
    admin = server.admin_choices(game)
    assert admin["mandate_at"] == when
    payload = {"m": {**server.main_view(game), "admin": True}, "menxia": None, "stored": {}, "responses": {},
               "script": 'return H.adminAsk("seal_mandate", {when: "now"})[0];', "S": {"admin": admin}}
    asked = webharness.run(DRIVER, payload)
    assert f"天命之爭排在{when}（" in asked


# ── 原 test_fb505_day_turn_nominal_end.py（整檔搬進來） ──
# FB-505（7 天濃縮季第二輪，PM 2026-10-20；同 FB-500 那一類）：rules.day_turn 比名義季長 × DAY。照現實天的季有開季偏移
# （週三 14:00 開的 7 天季，季曆終點是 7 天減 14 小時）：管理者把季末往後排時，最後一天的換日落在季曆終點，卻比季長 × DAY 早，
# 判成 "at"、寫「第 7 天 23:59」（季曆夾在最後一刻）——那一刻其實已經在季曆之外，該寫 "later"（過一陣子）。修成比
# calendar.nominal_end（同 FB-500）。週末、14 天的季偏移是 0，照舊比季長 × DAY，一個字都不變。

WED10 = 1792549800  # 2026-10-21 週三 10:30（台灣）


WED14_fb505 = WED10 + 3.5 * HOUR  # 2026-10-21 週三 14:00（台灣）


def _season_fb505(content, now):
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    return season


def test_week7_last_day_turn_is_later_when_the_admin_pushed_the_finale():
    """修前重現：週三 14:00 開的 7 天季，季末往後排 6 小時，第 7 天的換日寫成「第 7 天 23:59」（"at"）。"""
    c7 = real_content("week7")
    season = _season_fb505(c7, WED14_fb505)
    assert season.cal_offset == 14 * HOUR
    season.schedule["finale"] += 6 * HOUR
    season.time = calendar.day_start(7, c7, season) + HOUR
    assert rules.day_turn(c7, season) == ("later", None)
    season.time = calendar.day_start(6, c7, season) + HOUR  # 第 6 天的換日（第 7 天 00:00）照舊寫得出來
    assert rules.day_turn(c7, season) == ("at", "第 7 天 00:00")


def test_week7_last_day_without_a_push_is_the_season_end():
    c7 = real_content("week7")
    season = _season_fb505(c7, WED14_fb505)
    season.time = calendar.day_start(7, c7, season) + HOUR
    assert rules.day_turn(c7, season) == ("season", None)


def test_season21_last_day_turn_is_later_when_the_admin_pushed_the_finale():
    """21 天季同一個錯（週三 10:30 開，偏移 2 天 10.5 小時）。"""
    c21 = real_content("season21")
    season = _season_fb505(c21, WED10)
    season.schedule["finale"] += 6 * HOUR
    season.time = calendar.day_start(21, c21, season) + HOUR
    assert rules.day_turn(c21, season) == ("later", None)
    season.time = calendar.day_start(20, c21, season) + HOUR
    assert rules.day_turn(c21, season) == ("at", "第 3 週・週日 00:00")


@pytest.mark.parametrize("profile", [None])
def test_weekend_and_fourteen_day_compare_with_the_season_length_as_before(profile):
    """週末、14 天的季沒有偏移：季末往後排一天，最後幾天每一刻跟改之前（季長 × DAY）同一個答案。"""
    content = real_content(profile) if profile else real_content()
    season = _season_fb505(content, MON)
    assert season.cal_offset == 0 and not calendar.season21_on(season, content)
    assert calendar.nominal_end(content, season) == season_length_days(season, content) * DAY
    from tianxia.world import season_end_time

    length = season_length_days(season, content) * DAY
    season.schedule["finale"] = length + DAY  # 週末照排定的季末；14 天的季沒有時刻表，季末照季長（season_end_time）
    step = rules.day_seconds(content, season) / 4
    kinds = set()
    for k in range(-8, 6):
        season.time = length + k * step
        kind, _ = rules.day_turn(content, season)
        end = rules.day_ends(content, season)
        old = "season" if end >= season_end_time(season, content) - calendar.EPS_SECONDS else (
            "later" if end >= length - calendar.EPS_SECONDS else "at")
        assert kind == old, k
        kinds.add(kind)
    assert kinds >= ({"at", "later"} if profile == "week7" else {"at", "season"})  # 兩種季的交界都量到了
