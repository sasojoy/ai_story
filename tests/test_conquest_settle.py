"""領地爭奪第二批 Task 9：每天 22:00 結算、公告、天下大事、說明（計畫第四章 Task 9；Review Focus 1、2；裁決 6、7、9、11）。"""
from __future__ import annotations

import calendar as pycal
from datetime import datetime

import pytest

from conquest_kit import announce, conquest_game, join, plain_game
from tianxia import conquest, conquest_day, howto, orders
from tianxia.state import Order
from tianxia.world import keep_showdowns_on_time

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _tw(y, mo, d, h, mi=0) -> float:
    """台灣時間 → 現實 epoch 秒。"""
    return float(pycal.timegm(datetime(y, mo, d, h, mi).timetuple())) - 8 * 3600


def _game(now: float, name: str = "沈浪", world=None):
    game = join(conquest_game("season21", name=name, world=world), "huang")
    game.now = now
    return game


def _tick(game, now: float):
    game.now = now
    game._conquest_tick()
    game.state.world = game.world.get_season()
    return game.state.world.conquest


def test_first_sync_only_records_the_key():
    game = _game(_tw(2026, 10, 20, 10))
    state = _tick(game, game.now)
    assert state.settled_key == conquest_day.day_key(game.now, game.content.config)
    assert state.schedule == []
    assert not [r for r in game.state.world.rumors if "攻" in r.text and r.layer == "world"]


def test_settle_once_per_day_and_announces_each_siege():
    game = _game(_tw(2026, 10, 20, 10))
    _tick(game, game.now)
    state = _tick(game, _tw(2026, 10, 20, 22, 1))  # 換天：排明天的攻城
    assert state.settled_key == conquest_day.day_key(game.now, game.content.config)
    assert len(state.schedule) == 2  # 一邊一塊（10 塊中立 ÷ 21 天）、主將定奪
    assert {s.minute for s in state.schedule} == {21 * 60}
    assert all(s.by == {s.attackers[0]: conquest_day.COMMANDER} and s.reasons[s.attackers[0]] for s in state.schedule)
    shouts = [r.text for r in game.state.world.rumors if r.layer == "world" and "攻" in r.text]
    assert len(shouts) == 2  # 一場一句天下大事
    for slot in state.schedule:  # 開打的世界秒＝明天 21:00；集結在 30 分鐘前
        assert slot.at == pytest.approx(game.state.world.time + (_tw(2026, 10, 21, 21) - game.now))
        assert slot.at - slot.muster_at == pytest.approx(30 * 60)
    assert len(state.day_log) == 2
    again = _tick(game, _tw(2026, 10, 20, 23))  # 同一天再同步：不重排
    assert [s.id for s in again.schedule] == [s.id for s in state.schedule]
    assert len([r for r in game.state.world.rumors if r.layer == "world" and "攻" in r.text]) == 2


def test_votes_decide_and_are_consumed():
    game = _game(_tw(2026, 10, 20, 10))
    _tick(game, game.now)
    target = conquest.targets(game.state.world, game.content, "huang")[-1]
    game.conquest_vote(target, 19 * 60)
    state = _tick(game, _tw(2026, 10, 20, 22, 1))
    mine = next(s for s in state.schedule if "huang" in s.attackers)
    assert (mine.loc, mine.minute, mine.by["huang"]) == (target, 19 * 60, conquest_day.VOTE)
    assert state.votes == {} or state.votes_for != state.settled_key  # 票吃掉了
    note = next(n for n in state.day_log if n.side == "huang")
    assert note.by == conquest_day.VOTE and note.share == pytest.approx(1.0)


def test_settle_only_moves_forward():
    a = _game(_tw(2026, 10, 20, 10), name="甲某")
    _tick(a, a.now)
    b = _game(_tw(2026, 10, 20, 10), name="乙某", world=a.world)
    b.advanced_real = 86400.0  # b 快轉過一天：它認為已經是明天
    _tick(b, _tw(2026, 10, 20, 22, 1))  # b 的「今天」是 10/21 22:01：結算 10/21 那一天
    ahead = a.world.get_season().conquest
    a.state.world = a.world.get_season()
    target = conquest.targets(a.state.world, a.content, "huang")[0]
    a.conquest_vote(target, 21 * 60)
    behind = _tick(a, _tw(2026, 10, 20, 22, 1))  # a 天數小：不重排、不清票
    assert behind.settled_key == ahead.settled_key
    assert [s.id for s in behind.schedule] == [s.id for s in ahead.schedule]
    assert behind.votes["huang"]["甲某"].loc == target


def test_late_settle_shifts_or_voids_slots():
    game = _game(_tw(2026, 10, 20, 10))
    _tick(game, game.now)
    target = conquest.targets(game.state.world, game.content, "huang")[-1]
    game.conquest_vote(target, 12 * 60)
    state = _tick(game, _tw(2026, 10, 21, 13))  # 22:00 沒人上線，隔天 13:00 才結算（還是同一天的 key）
    mine = next(s for s in state.schedule if "huang" in s.attackers)
    assert mine.minute == 13 * 60 + 30  # 12:00 那場挪到「現在＋集結 30 分鐘」之後的第一個半點
    assert mine.at == pytest.approx(game.state.world.time + 30 * 60)

    late = _game(_tw(2026, 10, 20, 10), name="乙某")
    _tick(late, late.now)
    late.conquest_vote(conquest.targets(late.state.world, late.content, "huang")[-1], 12 * 60)
    state = _tick(late, _tw(2026, 10, 21, 20, 45))  # 20:45 才結算：挪不進 21:00，全部作罷
    assert state.schedule == []
    voided = [r.text for r in late.state.world.rumors if r.layer == "world" and "作罷" in r.text]
    assert len(voided) == 2  # 兩邊各一句


def test_commander_fills_in_with_21_and_20():
    game = _game(_tw(2026, 10, 20, 10))
    game.content.config.conquest.two_per_day_ratio = 0.4  # 一邊一天兩塊
    _tick(game, game.now)
    state = _tick(game, _tw(2026, 10, 20, 22, 1))
    for side in conquest.SIDES:
        assert sorted(s.minute for s in state.schedule if side in s.attackers) == [20 * 60, 21 * 60]


def test_planned_slot_turns_void_next_day_and_progress_resets():
    game = _game(_tw(2026, 10, 20, 10))
    _tick(game, game.now)
    state = _tick(game, _tw(2026, 10, 20, 22, 1))
    slot = state.schedule[0]
    game.state.world.conquest.progress[slot.loc] = 70
    game.world.save_season(game.state.world)
    state = _tick(game, _tw(2026, 10, 21, 22, 1))  # 沒開成（沒有攻城戰的程式碰它）就到了下一天
    assert slot.id not in [s.id for s in state.schedule]
    assert conquest.progress_of(game.state.world, slot.loc) == 50


def test_progress_only_on_todays_targets():
    game = _game(_tw(2026, 10, 20, 10))
    w, c = game.state.world, game.content
    target = conquest.targets(w, c, "huang")[0]
    assert not conquest.progress_open(w, c, target)  # 還沒公告：推不動（第二批起，計畫 2.3）
    announce(game, target, "huang")
    assert conquest.progress_open(w, c, target)


def test_switch_off_tick_never_touches_world():
    game = join(plain_game("season21"), "huang")
    before = game.state.world.model_dump_json()
    game.now = _tw(2026, 10, 20, 22, 1)
    assert game._conquest_tick() == []
    assert game.state.world.conquest is None
    assert before == game.state.world.model_dump_json()


def test_sync_and_world_tick_settle():
    game = _game(_tw(2026, 10, 20, 10))
    game.sync(game.now)
    game.sync(game.now + 60)  # 季推進一下（第一次推進才算地盤、領地爭奪）
    assert game.state.world.conquest.settled_key == conquest_day.day_key(game.now, game.content.config)
    from tianxia.engine import Game

    ticker = Game.for_world(game.content, game.world)
    ticker.world_tick(_tw(2026, 10, 20, 22, 1))
    assert len(game.world.get_season().conquest.schedule) == 2


def test_admin_settle_now_opens_soon():
    game = _game(_tw(2026, 10, 20, 23), name="Rayal")
    _tick(game, game.now)
    msgs = game.admin_conquest_settle_now()
    state = game.world.get_season().conquest
    assert state.schedule and msgs
    w = game.world.get_season()
    assert all(s.muster_at - w.time <= 60 for s in state.schedule if s.status == "planned")  # 集結馬上開
    game.admin_conquest_cancel(state.schedule[0].id)
    assert game.world.get_season().conquest.schedule[0].status == "void"


def test_resume_shifts_planned_slots():
    game = _game(_tw(2026, 10, 20, 10))
    _tick(game, game.now)
    state = _tick(game, _tw(2026, 10, 20, 22, 1))
    season = game.state.world
    before = [(s.at, s.muster_at) for s in state.schedule]
    keep_showdowns_on_time(season, game.content, 600.0, season.time)
    assert [(s.at, s.muster_at) for s in season.conquest.schedule] == [(a - 600, m - 600) for a, m in before]


def test_siege_and_defend_orders_follow_todays_schedule():
    game = _game(_tw(2026, 10, 20, 10))
    w, c = game.state.world, game.content
    holder_block = next(loc for loc in conquest.blocks(c) if conquest.capturable(c, loc) and conquest.holder(w, c, loc) == "guan"
                        and conquest.line_of(w, c, loc) == "yingru")
    assert orders.siege_places(c, "huang", "yingru", w) == []  # 沒公告：沒有攻城的地方
    announce(game, holder_block, "huang")
    assert orders.siege_places(c, "huang", "yingru", w) == [holder_block]
    week = orders.period_of(game.state, c)
    w.orders.append(Order(id="d1", template="defend", faction="guan", week=week, front="yingru", quota=5, text="守"))
    assert orders.duty_counts(game.state, c, "guan", holder_block)  # 自家被公告的那一塊
    other = next(loc for loc in conquest.blocks(c) if conquest.capturable(c, loc) and conquest.holder(w, c, loc) == "guan"
                 and conquest.line_of(w, c, loc) == "yingru" and loc != holder_block)
    assert not orders.duty_counts(game.state, c, "guan", other)


def test_howto_has_the_daily_rhythm():
    game = conquest_game("season21")
    lines = " ".join(howto.territory_lines(game.content, True, game.state.world))
    assert "22:00" in lines and "投票" in lines
