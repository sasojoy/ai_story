"""領地爭奪：攻城軍令＝今天公告的目標，打贏那裡的守軍就記功，中立駐軍也算（計畫第八節裁決 20，PM 2026-10-21；推翻第一批 FB-531 與
合併 conquest-1 時「只算敵方陣營的隊伍」那一半）。軍令卡列的、記功的、假人往哪裡走、發不發攻城照舊問同一個判斷（`orders.siege_win`），
不會列了卻記不到、或記得到卻沒列。沒公告的地方照舊不列、不記；開關關著一個字都不變（test_conquest_fb531_siege 的最後一條）。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join, win_sortie
from tianxia import atlas, conquest, orders
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _siege(game, faction="guan", front="yingru"):
    s, c = game.state, game.content
    order = Order(id=f"t:{faction}:siege:{front}", template="siege", faction=faction, week=orders.period_of(s, c), front=front,
                  quota=6, text="（測試）")
    s.world.orders.append(order)
    return order


def test_an_announced_neutral_target_is_listed_and_credited():
    """QA（第二批第 8 項）：今天公告官軍攻荒丘（還沒人佔的中立地），在那裡打贏中立駐軍記攻城一次，軍令卡寫得出荒丘。"""
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    s, c = game.state, game.content
    assert conquest.holder(s.world, c, "hilltop_wilds") is None
    announce(game, "hilltop_wilds", "guan")
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]  # 修前 []
    assert orders.win_counts(s, c, "guan", "hilltop_wilds") and "hilltop_wilds" in orders.targets(s, c, "guan")
    how = atlas.siege_how(s, c, order)
    assert "荒丘" in how and "黃巾" not in how  # 修前「到潁川汝南一帶黃巾軍的地盤出陣，打贏一場記一次。」
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1  # 修前沒記


def test_a_captured_neutral_block_held_by_the_enemy_counts_too():
    """被敵方佔下的中立地站的照舊是中立駐軍：今天公告了，打贏也算。"""
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    s, c = game.state, game.content
    assert conquest.set_control(s.world, c, "hilltop_wilds", "huang")
    announce(game, "hilltop_wilds", "guan")
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


def test_a_line_with_only_a_neutral_target_still_issues_a_siege():
    """只公告中立地的那一天，那條線照樣發得出攻城（計畫 6.2 合併那一段第 2 條的代價拿掉了）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    announce(game, "nanyang_road", "guan")
    assert orders.siege_places(c, "guan", "nanyang", w) == ["nanyang_road"]  # _issuable 先看的就是它


def test_enemy_block_and_unannounced_places_are_unchanged():
    """敵方陣營區塊照舊（打贏敵方的兵記一次）；沒公告的照舊不列、不記。"""
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    s, c = game.state, game.content
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == []
    win_sortie(game)
    assert s.player.name not in order.progress
    announce(game, "runan_wilds", "guan")
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["runan_wilds"]
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


def test_card_without_a_target_today_does_not_point_anywhere():
    """這條線今天沒有公告要攻的地方（打完了、或公告在別條線）：卡上不再指「到某一帶敵方的地盤出陣」——那裡打贏記不到。"""
    game = join(conquest_game("season21"), "guan")
    s, c = game.state, game.content
    order = _siege(game)
    how = atlas.siege_how(s, c, order)
    assert "地盤出陣" not in how and "今天" in how  # 修前「到潁川汝南一帶黃巾軍的地盤出陣，打贏一場記一次。」


def test_own_and_unknown_factions_never_count():
    """判斷本身：中立（沒有陣營）的隊伍只在領地爭奪開著時算；自家、豪強的隊伍兩邊都不算。"""
    assert orders.siege_win("guan", None, True) and not orders.siege_win("guan", None)
    assert orders.siege_win("guan", "huang", True) and orders.siege_win("guan", "huang")
    assert not orders.siege_win("guan", "guan", True)
    assert not orders.siege_win("guan", "cao", True)
