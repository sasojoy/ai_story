"""FB-608（QA 驗輿圖第三版第 1 批）：推滿易手的那一下、守到歸零的那一下，軍令記不到。

`Game._squad_encounter` 與 `_sortie_hold` 都是先推進度、後記軍令，`orders._counts` 讀的是推完之後的清單（`conquest.focus_blocks`）：
易手的那一塊已經是自家的、在冷卻，不在攻的清單；拉到零的那一塊沒有條，不在守的清單——卡上列的地方，最關鍵的那一下反而不算。
修法（PM 2026-10-21）：記不記照出陣**之前**的清單判（列與記同一個判斷，同 FB-531、FB-565）。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, go, join, win_sortie
from tianxia import conquest, orders
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _order(game, template: str, side: str) -> Order:
    s, c = game.state, game.content
    s.world.orders.clear()  # 開季發的軍令清掉，只剩這一道
    order = Order(id=f"t:{side}:{template}", template=template, faction=side, week=orders.period_of(s, c), front="yingru",
                  quota=99, text="（測試）")
    s.world.orders.append(order)
    return order


def test_the_win_that_fills_the_bar_and_flips_counts_for_the_siege_order():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    w, c = game.state.world, game.content
    order = _order(game, "siege", "guan")
    conquest.push(w, c, "hilltop_wilds", "guan", "先鋒", 99.5, "attack")
    assert orders.siege_places(c, "guan", "yingru", w) == ["hilltop_wilds"]  # 卡上寫的就是這裡
    win_sortie(game)
    assert conquest.holder(game.state.world, c, "hilltop_wilds") == "guan"  # 這一下推滿、當場易手
    assert order.progress.get(game.state.player.name) == 1  # 修前 0：推完那一塊已經是自家的、在冷卻，不在攻的清單


def test_a_plain_win_still_counts_once():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    order = _order(game, "siege", "guan")
    win_sortie(game)
    assert conquest.holder(game.state.world, game.content, "hilltop_wilds") is None
    assert order.progress.get(game.state.player.name) == 1


def test_the_hold_that_pulls_the_last_bit_to_zero_counts_for_the_defend_order():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    w, c = game.state.world, game.content
    order = _order(game, "defend", "huang")
    conquest.push(w, c, "runan", "guan", "敵將", 0.4, "attack")
    assert orders.defend_places(c, w, order) == ["runan"]  # 卡上寫的就是這裡
    msgs = game.choose("act:train")  # 自家的區塊：出陣・守
    assert conquest.bars(game.state.world, "runan") == {}  # 這一下拉到零
    assert any("全數歸零" in m for m in msgs)
    assert order.progress.get(game.state.player.name) == 1  # 修前 0：拉到零的那一塊沒有條，不在守的清單


def test_a_hold_where_nobody_pushes_still_counts_nothing():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    order = _order(game, "defend", "huang")
    game.choose("act:train")
    assert order.progress == {}  # 沒人在推：出陣前就不在清單上，照舊記不到
