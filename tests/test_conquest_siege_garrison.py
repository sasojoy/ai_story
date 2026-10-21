"""領地爭奪：攻城軍令打贏那裡的守軍就記功，中立駐軍也算（計畫第八節裁決 20，PM 2026-10-21）。軍令卡列的、記功的、假人往哪裡走、發不發攻城
照舊問同一個判斷（`orders.siege_win`），不會列了卻記不到、或記得到卻沒列。翻地與爭搶（PM 2026-10-20 第 1 條）之後地點改讀成「這一邊此刻
進度最高、推得動的那一塊」（第二批是今天公告的目標）；開關關著一個字都不變（test_conquest_fb531_siege 的最後一條）。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, go, join, win_sortie
from tianxia import atlas, conquest, orders
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _siege(game, faction="guan", front="yingru"):
    s, c = game.state, game.content
    order = Order(id=f"t:{faction}:siege:{front}", template="siege", faction=faction, week=orders.period_of(s, c), front=front,
                  quota=6, text="（測試）")
    s.world.orders.append(order)
    return order


def test_the_top_neutral_target_is_listed_and_credited():
    """官軍在荒丘（還沒人佔的中立地）的進度最高：在那裡打贏中立駐軍記攻城一次，軍令卡寫得出荒丘。"""
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    s, c = game.state, game.content
    assert conquest.holder(s.world, c, "hilltop_wilds") is None
    conquest.push(s.world, c, "hilltop_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]
    assert orders.win_counts(s, c, "guan", "hilltop_wilds") and "hilltop_wilds" in orders.targets(s, c, "guan")
    how = atlas.siege_how(s, c, order)
    assert "荒丘" in how and "黃巾" not in how
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


def test_a_captured_neutral_block_held_by_the_enemy_counts_too():
    """被敵方佔下的中立地站的照舊是中立駐軍：進度最高，打贏也算。"""
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    s, c = game.state, game.content
    assert conquest.set_control(s.world, c, "hilltop_wilds", "huang")
    conquest.push(s.world, c, "hilltop_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


def test_a_line_with_only_neutral_targets_still_issues_a_siege():
    """一條線上碰得到的只有中立地（官軍在南陽）：照樣發得出攻城（_issuable 先看的就是 siege_places）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert "nanyang_road" in orders.siege_places(c, "guan", "nanyang", w)


def test_lower_blocks_do_not_count_until_they_are_the_top():
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    s, c = game.state, game.content
    conquest.push(s.world, c, "hilltop_wilds", "guan", "某", 20, "attack")
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]
    win_sortie(game)
    assert s.player.name not in order.progress
    conquest.push(s.world, c, "runan_wilds", "guan", "某", 30, "attack")
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["runan_wilds"]
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


def test_card_without_a_pushable_place_does_not_point_anywhere():
    """這條線此刻沒有推得動的地方（全都剛易手）：卡上不指「到某一帶敵方的地盤出陣」——那裡打贏記不到。"""
    game = join(conquest_game("season21"), "guan")
    s, c = game.state, game.content
    for loc in conquest.targets(s.world, c, "guan"):
        conquest._fight(s.world, c, loc).flipped_at = s.world.time
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == []
    how = atlas.siege_how(s, c, order)
    assert "地盤出陣" not in how and "推得動" in how


def test_own_and_unknown_factions_never_count():
    """判斷本身：中立（沒有陣營）的隊伍只在領地爭奪開著時算；自家、豪強的隊伍兩邊都不算。"""
    assert orders.siege_win("guan", None, True) and not orders.siege_win("guan", None)
    assert orders.siege_win("guan", "huang", True) and orders.siege_win("guan", "huang")
    assert not orders.siege_win("guan", "guan", True)
    assert not orders.siege_win("guan", "cao", True)
