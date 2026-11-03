"""管理者「取消一場攻城」收起來之後讀回季那一行（sieges.cancel_siege 的 ctx.state.world = ctx.world.get_season()；全部拆包第 6 批計畫
第五節「交 PM 定的」第 1 條，PM 2026-11-01 定第 7 批補）。

收兵那幾步（mutate_siege、drop_siege、補送）都照資料庫走；admin_conquest_cancel 收完之後在手上那一份季記作罷、存回去。手上那一份要是
收兵之前讀的，這一刻資料庫裡別人剛寫的（另一個行程、收兵時補送寫的）就被蓋掉。前後對照與別的測試都沒走到：正常的路上同步剛讀過季、
收兵那三步也不改季，讀不讀回來都一樣。擺法：開了集結之後、取消之前，資料庫裡的季多一則天下大事（手上那一份沒有）。
"""
from __future__ import annotations

from conquest_kit import announce, conquest_game, go, join

from tianxia import siege
from tianxia.state import Rumor

NOW = 1_792_000_000.0
LOC = "xinye"  # 新野：開季時是黃巾的；官軍來攻
MARK = "（另一個行程剛寫進季裡的一則天下大事）"


def _admin():
    game = go(join(conquest_game("week7", name="Rayal"), "guan"), LOC)  # Rayal 是內容裡的管理者
    game.now = NOW
    return game


def _open(game):
    """官軍攻黃巾的新野，排到此刻開集結（同 test_siege_settle._siege：照 world 的路開，siege.open_waiting）。"""
    slot = announce(game, LOC, "guan")
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    found = next(s for s in game.state.world.conquest.schedule if s.id == slot.id)
    assert found.status == "open" and found.record_id is not None
    return found


def test_cancelling_an_open_siege_reads_the_season_back_before_saving():
    game = _admin()
    slot = _open(game)
    assert slot.record_id in [b.record_id for b in game.world.get_sieges()]
    game.world.mutate_season(lambda s: s.rumors.append(Rumor(time=s.time, text=MARK, layer="world")))
    assert MARK not in [r.text for r in game.state.world.rumors]  # 手上那一份是寫進去之前讀的

    game.admin_conquest_cancel(slot.id)

    season = game.world.get_season()
    assert MARK in [r.text for r in season.rumors]  # 收兵之後讀回季再存：別人剛寫的沒被蓋掉
    assert MARK in [r.text for r in game.state.world.rumors]
    assert next(s for s in season.conquest.schedule if s.id == slot.id).status == "void"
    assert slot.record_id not in [b.record_id for b in game.world.get_sieges()]  # 那一場收起來了
    assert game.world.ended_battle(slot.record_id).unfinished
