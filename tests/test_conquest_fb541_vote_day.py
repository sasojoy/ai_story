"""FB-541：票是替「此刻的下一天」投的（Game._vote_key＝conquest_day.day_key＋1），一天從 22:00 起算，所以 22:00～24:00 投的票排的是
後天的攻城，回話與錯誤訊息卻寫「明日」「明天」。回話與 VOTE_BAD_SLOT 照那一場真正排到的日子寫（calendar.stamp_text，同公告的寫法）。"""
from __future__ import annotations

import calendar as pycal
from datetime import datetime

import pytest

from conquest_kit import conquest_game, join
from tianxia import conquest, conquest_day

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _tw(y, mo, d, h, mi=0) -> float:
    """台灣時間 → 現實 epoch 秒（同 test_conquest_settle._tw）。"""
    return float(pycal.timegm(datetime(y, mo, d, h, mi).timetuple())) - 8 * 3600


def _game(now: float):
    game = join(conquest_game("season21"), "huang")
    game.now = now
    game._conquest_tick()  # 這一季第一次只記下今天
    return game


def _walk(game, now: float):
    """現實時間走到 now，世界時間跟著走（同伺服器每次 sync），再看要不要結算。"""
    game.state.world.time += (now - game.now) * game.content.config.time_scale
    game.now = now
    game._conquest_tick()
    game.state.world = game.world.get_season()


def _at(game, real: float) -> str:
    """現實的那一刻在季曆上怎麼寫（同公告：calendar.stamp_text）。"""
    return game.stamp(game.state.world.time + (real - game.now) * game.content.config.time_scale)


def _pick(game):
    """一塊能投的目標、一個開得了的時段（替下一天投的那一批）。"""
    w, c = game.state.world, game.content
    key = conquest_day.day_key(game.pill_now(), c.config) + 1
    return conquest.targets(w, c, "huang")[0], conquest_day.slots(w, c, key, game.pill_now())[0]


def test_vote_after_ten_says_the_day_after_tomorrow():
    game = _game(_tw(2026, 10, 20, 10))
    _walk(game, _tw(2026, 10, 20, 22, 1))  # 10/20 22:01 結算：排 10/21 的攻城
    _walk(game, _tw(2026, 10, 20, 23))  # 10/20 23:00 投的票替 10/21 22:00 那一次結算投（排 10/22）
    loc, minute = _pick(game)
    hh, mm = divmod(minute, 60)
    line = game.conquest_vote(loc, minute)[-1]
    assert "明日" not in line  # 修前「你投了一票：明日 HH:MM 攻某地。」——明日是 10/21，那一天的攻城早就排好了
    when = _at(game, _tw(2026, 10, 22, hh, mm))
    assert when in line and _at(game, _tw(2026, 10, 21, hh, mm)) not in line
    _walk(game, _tw(2026, 10, 21, 22, 1))  # 10/21 22:01 結算：照這一票排
    slot = next(s for s in game.state.world.conquest.schedule if s.loc == loc and "huang" in s.attackers and s.status == "planned")
    assert game.stamp(slot.at) == when  # 回話寫的就是公告的那一刻


def test_vote_after_midnight_names_the_same_day():
    """00:00 以後投的「明日」本來就對：照樣寫那一天（10/21 00:30 投的也排在 10/22）。"""
    game = _game(_tw(2026, 10, 20, 10))
    _walk(game, _tw(2026, 10, 20, 22, 1))
    _walk(game, _tw(2026, 10, 21, 0, 30))
    loc, minute = _pick(game)
    hh, mm = divmod(minute, 60)
    line = game.conquest_vote(loc, minute)[-1]
    assert _at(game, _tw(2026, 10, 22, hh, mm)) in line


def test_bad_slot_names_the_day_it_is_for():
    game = _game(_tw(2026, 10, 20, 10))
    _walk(game, _tw(2026, 10, 20, 22, 1))
    _walk(game, _tw(2026, 10, 20, 23))
    loc, _ = _pick(game)
    line = game.conquest_vote(loc, 11 * 60)[-1]  # 11:00 不在 12:00～21:00
    assert "時辰" in line and "明天" not in line  # 修前「只能挑明天 12:00～21:00 的整點或半點」
    assert _at(game, _tw(2026, 10, 22, 12)) in line  # 那一天（10/22）的 12:00 起
    assert game.state.world.conquest.votes.get("huang", {}) == {}
