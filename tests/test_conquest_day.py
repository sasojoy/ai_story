"""領地爭奪第二批 Task 7：每天的鐘、投票與時程表（tianxia/conquest_day.py；設計 3.6、4.2、4.3，裁決 6、7、9）。"""
from __future__ import annotations

import calendar as pycal
from datetime import datetime

import pytest

from conquest_kit import conquest_game, plain_game
from tianxia import conquest, conquest_day
from tianxia.state import Pick

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _utc(y, mo, d, h, mi=0, s=0) -> float:
    return float(pycal.timegm(datetime(y, mo, d, h, mi, s).timetuple()))


def test_day_key_turns_at_22_taiwan():
    cfg = conquest_game("season21").content.config
    before, after = _utc(2026, 10, 20, 13, 59, 59), _utc(2026, 10, 20, 14, 0, 0)  # 台灣 21:59:59、22:00:00
    assert conquest_day.day_key(after, cfg) == conquest_day.day_key(before, cfg) + 1
    key = conquest_day.day_key(after, cfg)
    assert conquest_day.key_start(key, cfg) == after
    # 那一天的 12:00 是隔天中午（台灣 10/21 12:00＝UTC 04:00），21:00 也在同一天
    assert conquest_day.slot_real(key, 12 * 60, cfg) == _utc(2026, 10, 21, 4)
    assert conquest_day.slot_real(key, 21 * 60, cfg) == _utc(2026, 10, 21, 13)
    assert conquest_day.slot_text(20 * 60 + 30) == "20:30"


def test_per_day_follows_neutral_count_and_season_length():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    neutral = sum(1 for loc in conquest.blocks(c) if conquest.start_kind(w, c, loc) == conquest.NEUTRAL)
    assert neutral == 8  # 區塊表 v3（計畫「區塊表 v3」那一節）
    assert conquest_day.per_day(c, w) == 1  # 8 ÷ 21 ＜ 0.5（設計 4.2：21 天的季要 11 塊以上才 2 塊）
    c.config.conquest.two_per_day_ratio = 0.3
    assert conquest_day.per_day(c, w) == 2
    weekend = conquest_game("weekend")
    assert conquest_day.per_day(weekend.content, weekend.state.world) == 2  # 週末 2.5 天一律 2 塊


def test_commander_picks_are_deterministic_and_prefer_worked_blocks():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    key = 20000
    first = conquest_day.commander_picks(w, c, "huang", 2, key, set())
    assert first == conquest_day.commander_picks(w, c, "huang", 2, key, set())  # 同一天同一邊挑一樣的
    assert [p.minute for p, _ in first] == [21 * 60, 20 * 60]  # 第二塊用 20:00（裁決 7）
    assert all(why for _, why in first)
    targets = conquest.targets(w, c, "huang")  # 開季黃巾碰得到官軍的涿郡（區塊表 v3），官軍開季碰得到的全是中立地
    neutral = [loc for loc in targets if conquest.start_kind(w, c, loc) == conquest.NEUTRAL]
    enemy = [loc for loc in targets if loc not in neutral]
    assert neutral and enemy
    assert conquest_day.commander_picks(w, c, "huang", 1, key, set())[0][0].loc in neutral  # 進度都在 50：中立先於敵方陣營
    w.conquest.progress[enemy[0]] = 50 + 30 * conquest.direction(c, "huang", enemy[0])  # 那一塊的進度往黃巾偏
    worked = conquest_day.commander_picks(w, c, "huang", 1, key, set())
    assert worked[0][0].loc == enemy[0]
    assert "已佔上風" in worked[0][1]
    assert conquest_day.commander_picks(w, c, "huang", 1, key, {enemy[0]})[0][0].loc != enemy[0]  # 已經定了的不再挑


def test_tally_rank4_votes_weigh_55_percent():
    votes = {"甲": Pick(loc="a", minute=1200), "乙": Pick(loc="b", minute=1200), "丙": Pick(loc="b", minute=1200),
             "丁": Pick(loc="b", minute=1230)}
    assert [p.loc for p in conquest_day.tally(votes, 1, {"甲"}, 0.55)] == ["a"]  # 第 4 階的一票合起來 55%
    assert [p.loc for p in conquest_day.tally(votes, 1, set(), 0.55)] == ["b"]  # 沒有第 4 階：每人一票
    shares = conquest_day.shares(votes, {"甲"}, 0.55)
    assert shares == pytest.approx({"a": 0.55, "b": 0.45})
    assert conquest_day.tally(votes, 1, set())[0].minute == 1200  # 那一塊的時段取票最多的
    only_rank4 = {"甲": Pick(loc="a", minute=1200), "戊": Pick(loc="b", minute=1200)}
    assert conquest_day.tally(only_rank4, 1, {"甲", "戊"}) == []  # 只有一組有人投：每人一樣，平手


def test_tally_boundary_tie_goes_to_the_commander():
    votes = {"甲": Pick(loc="a", minute=1200), "乙": Pick(loc="b", minute=1260)}
    assert conquest_day.tally(votes, 1, set()) == []  # 名額邊上平手：交給主將
    assert {p.loc for p in conquest_day.tally(votes, 2, set())} == {"a", "b"}
    three = {**votes, "丙": Pick(loc="a", minute=1260), "丁": Pick(loc="c", minute=1200)}
    picked = conquest_day.tally(three, 2, set())
    assert [p.loc for p in picked] == ["a"]  # a 兩票穩進；b、c 平手搶第二個名額，都不算
    assert picked[0].minute == 1260  # 時段平手取晚的
    assert conquest_day.tally({}, 2, set()) == []


def test_plan_votes_then_commander_fills():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    c.config.conquest.two_per_day_ratio = 0.3  # 一天兩塊（中立 8 塊 ÷ 21 天）
    target = conquest.targets(w, c, "huang")[-1]
    picks = conquest_day.plan(w, c, "huang", 20000, 0.0, {"甲": Pick(loc=target, minute=19 * 60)}, set())
    assert [(p.loc, p.minute, by) for p, by, _ in picks][0] == (target, 19 * 60, conquest_day.VOTE)
    assert picks[1][1] == conquest_day.COMMANDER and picks[1][0].loc != target and picks[1][0].minute == 21 * 60
    stale = conquest_day.plan(w, c, "huang", 20000, 0.0, {"甲": Pick(loc="changshe", minute=19 * 60)}, set())
    assert all(by == conquest_day.COMMANDER for _, by, _ in stale)  # 投的地方不是目標：不算，主將補


def test_merge_same_block_same_time_is_one_siege():
    plans = {
        "guan": [(Pick(loc="baima_ford", minute=1260), "commander", "x")],
        "huang": [(Pick(loc="baima_ford", minute=1260), "vote", "")],
    }
    rows = conquest_day.merge(plans, 7)
    assert len(rows) == 1 and rows[0].attackers == ["guan", "huang"]
    assert rows[0].by == {"guan": "commander", "huang": "vote"} and rows[0].id == "7-1"


def test_merge_same_block_different_times_keeps_both_in_order():
    plans = {
        "guan": [(Pick(loc="baima_ford", minute=1260), "commander", "x")],
        "huang": [(Pick(loc="baima_ford", minute=1200), "vote", "")],
    }
    rows = conquest_day.merge(plans, 7)
    assert [(r.attackers, r.minute) for r in rows] == [(["huang"], 1200), (["guan"], 1260)]


def test_schedule_is_at_most_four():
    plans = {
        "guan": [(Pick(loc="a", minute=1260), "commander", ""), (Pick(loc="b", minute=1200), "commander", "")],
        "huang": [(Pick(loc="c", minute=1260), "commander", ""), (Pick(loc="d", minute=1200), "commander", "")],
    }
    assert len(conquest_day.merge(plans, 1)) == 4
    plans["huang"][0] = (Pick(loc="a", minute=1260), "vote", "")
    rows = conquest_day.merge(plans, 1)
    assert len(rows) == 3 and next(r for r in rows if r.loc == "a").attackers == ["guan", "huang"]


def test_slots_skip_showdown_window():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    real_now = _utc(2026, 10, 20, 2)  # 台灣 10/20 10:00
    key = conquest_day.day_key(real_now, c.config) + 1  # 明天的時段：10/21 12:00～21:00
    event = next(e for e in c.timetable if e.kind == "showdown")
    w.schedule[event.id] = w.time + (conquest_day.slot_real(key, 20 * 60, c.config) - real_now)  # 決戰排在那一天 20:00
    got = conquest_day.slots(w, c, key, real_now)
    assert 19 * 60 in got and 21 * 60 in got
    assert not {19 * 60 + 30, 20 * 60, 20 * 60 + 30} & set(got)  # 19:30～20:45 拿掉（裁決 6）
    today = conquest_day.day_key(real_now, c.config)  # 今天（10/20 的 12:00～21:00）：10:00 看，12:00 之前的都還開得了集結
    assert conquest_day.slots(w, c, today, _utc(2026, 10, 20, 12))[0] == 20 * 60 + 30  # 台灣 20:00 看：20:30 以前的都來不及


def test_switch_off_plan_is_empty():
    game = plain_game("season21")
    w, c = game.state.world, game.content
    assert not conquest.on(c, w)
    assert conquest_day.plan(w, c, "huang", 20000, 0.0, {"甲": Pick(loc="nanyang_road", minute=1260)}, set()) == []
