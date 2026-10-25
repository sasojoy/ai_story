"""減法季批 3b 收尾：約戰開著時輿圖不畫「出陣・守」（整合設計 4.3「零風險的守拿掉」；計畫 4.0 之四）。

約戰開著的季，自家的地方出陣那一格灰著寫「等對面來約」（守就是應戰），輿圖的疊層（Game.map_state → mapdata.state）也不再給那一處
"sortie": "hold"、不在「今天去哪裡出陣」推薦它（不然推薦卡寫「出陣・守」、還寫「軍令・守城」，按下去卻貼不了）。中立地、敵方的地方照舊
是攻。子開關關著（舊出陣）自家的地方照舊是守。"""
from __future__ import annotations

import pytest

from duel_kit import LOC, duel_content, duel_world, game_of, seat
from tianxia import conquest

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _own_block(c, world, side: str) -> str:
    season = world.get_season()
    return next(loc for loc in conquest.blocks(c)
                if conquest.capturable(c, loc) and conquest.holder(season, c, loc) == side)


def _map(off: bool):
    c = duel_content(off=off)
    world = duel_world(c)
    own = _own_block(c, world, "guan")
    seat(c, world, "甲", "guan", own)
    return game_of(c, world, "甲").map_state(), own


def test_duels_on_the_map_does_not_offer_holding_at_home():
    state, own = _map(off=False)
    assert state["places"][own]["sortie"] is None
    assert own not in {row["id"] for row in state["suggest"]}
    assert state["places"][LOC]["sortie"] == "attack"  # 中立地照舊是攻（貼約戰）
    assert all(row["sortie"] != "hold" for row in state["suggest"])


def test_duels_off_the_map_still_offers_holding_at_home():
    state, own = _map(off=True)
    assert state["places"][own]["sortie"] == "hold"
    assert state["places"][LOC]["sortie"] == "attack"
