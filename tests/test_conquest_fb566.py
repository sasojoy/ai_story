"""FB-566（領地爭奪小單 QA 開的，`97567ff0` 就有）：同一個大區兩場攻城同時集結，排在前面的那一場自己站不進去時，自己站得進去的那一場
沒有加入鈕。重現：官軍攻嵩山深處、黃巾攻荒丘（都是中立地、同一刻開集結），黃巾的人站在荒丘：`_joinable()` 是黃巾那一場，`_battle_now`
卻回排第一的官軍那一場——選單沒有 `battle:` 鈕、場景寫「插不上手」，那一場最後作罷。修法：`_battle_now` 先照自己站得進去的那一場。

合進區塊表 v3（輿圖第三版第 2 批）之後嵩山深處是官軍的、黃巾開季碰不到荒丘：換成官軍攻荒丘、黃巾攻汝南荒野（都是中立地、同一個大區），斷言不動。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join
from tianxia import siege

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0


def _two_sieges(side: str, loc: str):
    game = go(join(conquest_game("season21"), side), loc)
    game.now = NOW
    w = game.state.world
    for slot in (announce(game, "hilltop_wilds", "guan", minute=20 * 60), announce(game, "runan_wilds", "huang", minute=20 * 60)):
        slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return game


@pytest.mark.parametrize(("side", "loc", "target"), [("huang", "runan_wilds", "runan_wilds"), ("guan", "hilltop_wilds", "hilltop_wilds")])
def test_the_siege_you_can_join_is_the_one_you_see(side, loc, target):
    game = _two_sieges(side, loc)
    sieges = game.world.get_sieges()
    assert [b.siege.loc for b in sieges] == ["hilltop_wilds", "runan_wilds"]  # 官軍那一場排在前面
    assert [b.siege.loc for b in game._joinable()] == [target]
    assert game._battle_now().siege.loc == target  # 修前黃巾的人看到的是官軍那一場
    joins = [o for o in game.options() if o.id.startswith(f"battle:join:{side}")]
    assert joins and joins[0].enabled
    assert "插不上手" not in game.scene_text()
    game.choose(joins[0].id)
    joined = next(b for b in game.world.get_sieges() if b.siege.loc == target)
    assert game.state.player.name in joined.participants
