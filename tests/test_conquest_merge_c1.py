"""領地爭奪：第一批的修正（FB-531、裁決 18）合進第二批之後疊起來的規則（計畫 6.2「合併 conquest-1 修正」，PM 2026-10-20），翻地與爭搶之後的樣子。

- 攻城軍令記得到功、軍令卡列得出來的地方＝這一邊此刻進度最高、推得動的那幾塊（PM 2026-10-20 第 1 條；第二批是今天公告的目標），而且
  `orders.siege_win` 也成立：打贏那裡的守軍就記功，中立駐軍也算（裁決 20）。
- 敵方大本營與廣宗（搶不下來）不是目標：推不動、不列成攻城地點、下不了戰書；就算硬塞一條進度也不列。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, go, join, win_sortie
from tianxia import conquest, orders
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _siege(game, faction="guan", front="yingru"):
    s, c = game.state, game.content
    order = Order(id=f"t:{faction}:siege:{front}", template="siege", faction=faction, week=orders.period_of(s, c), front=front,
                  quota=6, text="（測試）")
    s.world.orders.append(order)
    return order


def _out_of_contest(game) -> list[str]:
    c = game.content
    return [loc for loc in conquest.blocks(c) if not conquest.capturable(c, loc)]


def test_a_neutral_target_and_an_enemy_block_tied_at_the_top_are_both_listed():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "hilltop_wilds") is None and conquest.line_of(w, c, "hilltop_wilds") == "yingru"
    for loc in ("hilltop_wilds", "runan_wilds"):
        conquest.push(w, c, loc, "guan", "某", 15, "attack")
    assert orders.siege_places(c, "guan", "yingru", w) == ["hilltop_wilds", "runan_wilds"]


def test_a_win_at_the_top_neutral_target_credits_the_siege():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    conquest.push(game.state.world, game.content, "hilltop_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1  # 裁決 20：中立駐軍也算
    assert orders.win_counts(game.state, game.content, "guan", "hilltop_wilds")


def test_a_win_at_the_top_enemy_block_credits_the_siege():
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    conquest.push(game.state.world, game.content, "runan_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    assert orders.win_counts(game.state, game.content, "guan", "runan_wilds")
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1


def test_a_lower_block_does_not_count():
    """列與記同一個判斷：進度不是最高的那一塊不列、不記。"""
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    conquest.push(game.state.world, game.content, "hilltop_wilds", "guan", "某", 20, "attack")
    order = _siege(game)
    assert orders.siege_places(game.content, "guan", "yingru", game.state.world) == ["hilltop_wilds"]
    win_sortie(game)
    assert game.state.player.name not in order.progress


@pytest.mark.parametrize("side", ["guan", "huang"])
def test_enemy_bases_and_guangzong_are_never_targets(side):
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    out = _out_of_contest(game)
    mine = {loc for loc in conquest.blocks(c) if conquest.holder(w, c, loc) == side}
    near = [loc for loc in out if conquest.holder(w, c, loc) != side and any(x in mine for x in conquest.adjacent(c, loc))]
    assert near  # 有搶不下來、又跟自家領地直通的敵方區塊（例：官軍的長社挨著黃巾別部營寨），這條才量得到東西
    assert not set(conquest.targets(w, c, side)) & set(out)
    assert not set(conquest.focus_blocks(w, c, side, "attack")) & set(out)
    for loc in near:
        assert conquest.push_problem(w, c, side, loc, "attack") == conquest.WHY_OUT
        assert conquest.letter_problem(w, c, side, loc, 1) == conquest.WHY_OUT


def test_a_forced_bar_at_an_enemy_base_is_still_not_a_siege_place():
    """硬塞一條進度（不經出陣）：黃巾別部營寨搶不下來，照樣不列。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.push(w, c, "huangjin_camp", "guan", "某", 50, "attack")
    conquest.push(w, c, "runan_wilds", "guan", "某", 10, "attack")
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds"]
