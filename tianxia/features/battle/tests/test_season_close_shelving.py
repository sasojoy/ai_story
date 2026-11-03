"""收季的收兵（progress.close_season，核心經接縫掛鉤 on_season_close 叫；全部拆包第 8 批）——dev/battle-4 審查補的（should）。

攻城那一半（管理者收季、休季時開下一季都收兵）原本沒有一條測試守：tests/acts/test_conquest_siege.py::test_season_end_shelves_sieges
只走自然收季那一支（battle_status），tests/core/test_engine.py 管理者收季、開下一季那幾條是測試內容的決戰（沒有攻城）、也不在改這一包時
test_for 挑得到的範圍。這裡用正式內容 week7（領地爭奪）同時擺一場集結中的時刻表決戰（長社火攻）與一場攻城（官軍攻黃巾的新野）：
- 管理者收季：兩場都收兵（battles 表裡是沒打完的那一種、不算勝負），收場時間記收季那一刻的季時間，攻城的參戰者同步補到「未分勝負」那一則。
- 休季時開下一季（季自然結束之後沒人同步過）：兩場都在換季前收起來，收場時間記收掉的那一季的時間——開下一季那一份手上的季過時了也一樣
  （reread：收決戰之前、收攻城之前各讀回一次；拿掉後一次，只有攻城的季就記成過時的時間）。
"""
from __future__ import annotations

import random

import pytest

from conquest_kit import announce, conquest_game, go, join

from tianxia import battle_instance, siege
from tianxia.engine import Game

NOW = 1_792_000_000.0
LOC = "xinye"  # 新野：開季時是黃巾的，官軍攻（同 test_siege_settle）
ADMIN = "管理者"


def _game():
    """沈浪（官軍）站在新野；同一個世界另建一位管理者（沒參戰）。"""
    game = go(join(conquest_game("week7"), "guan"), LOC)
    game.now = NOW
    game.content.config.admins = [ADMIN]
    admin = Game.new(game.content, ADMIN, rng=random.Random(5), world=game.world)
    admin.client = None
    return game, admin


def _siege(game):
    """官軍攻黃巾的新野，排到此刻開集結（同 test_siege_settle._siege），沈浪按加入。回那一場的流水號。"""
    slot = announce(game, LOC, "guan")
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    found = next(s for s in game.state.world.conquest.schedule if s.id == slot.id)
    join_id = next(o.id for o in game.options() if o.id.startswith("battle:join:guan"))
    game.choose(join_id)
    battle = next(b for b in game.world.get_sieges() if b.record_id == found.record_id)
    assert battle.phase == "muster" and game.state.player.name in battle.participants
    return battle.record_id


def _showdown(game):
    """長社火攻開集結（沒人加入：收兵照樣標成沒打完）。回那一場的流水號。"""
    battle = game.world.start_battle(game.content.battles["changshe_fire"], now=NOW)
    assert battle.phase == "muster"
    return battle.record_id


def _shelved(game, rid, end_time):
    ended = game.world.ended_battle(rid)
    assert ended is not None and ended.unfinished, rid  # 收兵了：沒打完的那一種
    assert ended.outcome_title == battle_instance.UNFINISHED_TITLE and ended.outcome_side == ""  # 不算勝負、不易手
    assert ended.end_time == end_time


def _got_the_note(game, now):
    game.sync(now)
    assert any(battle_instance.UNFINISHED_TITLE in e.title for e in game.state.journal)


def test_the_admin_closing_the_season_shelves_the_showdown_and_the_siege():
    game, admin = _game()
    sid = _siege(game)
    bid = _showdown(game)

    admin.admin_end_season(now=NOW)

    assert game.world.season_phase() == "resting"
    assert game.world.get_sieges() == [] and game.world.get_battle() is None
    closed_at = game.world.get_season().time
    _shelved(game, bid, closed_at)
    _shelved(game, sid, closed_at)
    assert not any(battle_instance.UNFINISHED_TITLE in e.title for e in admin.state.journal)  # 管理者沒參戰
    _got_the_note(game, NOW + 10)


def test_the_first_poll_after_the_season_ended_shelves_the_showdown_and_the_siege():
    """季自然收了、還沒人推過：第一個輪詢的人（這裡是攻城的參戰者）那一下兩場都收兵（battle_status 季收了那一支），攻城那一則當場補到
    自己手上。"""
    game, _ = _game()
    sid = _siege(game)
    bid = _showdown(game)
    game.state.world.ended = True

    assert game._battle_status(tick=True) is None

    assert game.world.get_sieges() == [] and game.world.get_battle() is None
    at = game.state.world.time
    _shelved(game, bid, at)
    _shelved(game, sid, at)
    assert any(battle_instance.UNFINISHED_TITLE in e.title for e in game.state.journal)


@pytest.mark.parametrize("with_showdown", [False, True], ids=["只有攻城", "決戰與攻城"])
def test_opening_the_next_season_shelves_what_the_natural_end_left_at_that_seasons_time(with_showdown):
    game, admin = _game()
    sid = _siege(game)
    bid = _showdown(game) if with_showdown else None

    def _end(s):  # 季自然結束：季的時鐘走到季末、沒有人同步過（沒人走到 battle_status 收掉它們）
        s.time += 3600.0
        s.ended, s.ending_title = True, "天下太平"

    game.world.mutate_season(_end)
    ended_at = game.world.get_season().time
    assert admin.state.world.time != ended_at  # 管理者手上那一份季是過時的：收場時間要靠讀回

    admin.admin_next_season(now=NOW + 5)

    assert game.world.get_season_number() == 2
    assert game.world.get_sieges() == [] and game.world.get_battle() is None
    _shelved(game, sid, ended_at)
    if bid is not None:
        _shelved(game, bid, ended_at)
    _got_the_note(game, NOW + 10)
