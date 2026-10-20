"""領地爭奪：第一批的修正（FB-531、裁決 18）合進第二批之後疊起來的規則（計畫 6.2「合併 conquest-1 修正」，PM 2026-10-20）。

- 攻城軍令記得到功、軍令卡列得出來的地方＝今天公告的目標裡、`orders.siege_win` 也成立的那幾塊：公告了的中立地站的是中立駐軍，
  打贏記不到，不列。**裁決 20（PM 2026-10-21）推翻了這一半**：今天公告的目標打贏那裡的守軍就記功，中立駐軍也算；下面鎖住舊做法的
  兩條斷言照裁決翻過來，新規則的測試在 test_conquest_siege_garrison.py。
- 敵方大本營與廣宗（搶不下來）不會被公告成目標：票投到那裡不算，主將也不挑；就算時程表上硬塞一場，也不列成攻城地點。
輿圖重製第 1 批（新天下）：中原那一條線上全是中立地，外圈的陣營區塊與大本營不算進任何一條線，大本營開季也不跟對方直通；
量「線上的敵方陣營區塊」的幾條把汝南荒野改回 v1 的黃巾陣營區塊（conquest_kit.conquest_game_with）。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, conquest_game_with, go, join, win_sortie
from tianxia import conquest, conquest_day, orders
from tianxia.state import Order, Pick

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

V1_RUNAN = {"runan_wilds": ("huang", "yingru")}  # v1：汝南荒野是黃巾的陣營區塊、在潁川汝南那一條線上


def _game():
    return conquest_game_with(V1_RUNAN)


def _siege(game, faction="guan", front="yingru"):
    s, c = game.state, game.content
    order = Order(id=f"t:{faction}:siege:{front}", template="siege", faction=faction, week=orders.period_of(s, c), front=front,
                  quota=6, text="（測試）")
    s.world.orders.append(order)
    return order


def _out_of_contest(game) -> list[str]:
    c = game.content
    return [loc for loc in conquest.blocks(c) if not conquest.capturable(c, loc)]


def test_an_announced_neutral_target_is_a_siege_place_again():
    game = _game()
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "hilltop_wilds") is None and conquest.line_of(w, c, "hilltop_wilds") == "yingru"
    announce(game, "hilltop_wilds", "guan")
    announce(game, "runan_wilds", "guan")
    assert orders.siege_places(c, "guan", "yingru", w) == ["hilltop_wilds", "runan_wilds"]  # 裁決 20：回到第二批原本的兩塊都列


def test_a_win_at_an_announced_neutral_target_credits_the_siege():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    announce(game, "hilltop_wilds", "guan")
    order = _siege(game)
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1  # 裁決 20：記一次（合併 conquest-1 的時候不記）
    assert orders.win_counts(game.state, game.content, "guan", "hilltop_wilds")


def test_a_win_at_an_announced_enemy_block_credits_the_siege():
    game = go(join(_game(), "guan"), "runan_wilds")
    announce(game, "runan_wilds", "guan")
    order = _siege(game)
    assert orders.win_counts(game.state, game.content, "guan", "runan_wilds")
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1


def test_an_unannounced_enemy_block_still_does_not_count():
    """第二批照留：沒公告的敵方陣營區塊不列、不記（第一批是此刻歸敵方就算）。"""
    game = go(join(_game(), "guan"), "runan_wilds")
    order = _siege(game)
    assert orders.siege_places(game.content, "guan", "yingru", game.state.world) == []
    win_sortie(game)
    assert game.state.player.name not in order.progress


NEXT_TO_ENEMY_BASE = {"guan": "baima_ford", "huang": "nanyang_huangjin_camp"}  # 挨著對方大本營（鉅鹿道壇、廣宗／宛城）的中立地


@pytest.mark.parametrize("side", ["guan", "huang"])
def test_enemy_bases_and_guangzong_are_never_scheduled(side):
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    c.config.conquest.two_per_day_ratio = 0.01  # 一天兩塊：多給主將一個名額去挑
    conquest.set_control(w, c, NEXT_TO_ENEMY_BASE[side], side)  # 新天下的大本營在外圈深處，開季不跟對方直通：先佔下挨著的那一塊
    out = _out_of_contest(game)
    mine = {loc for loc in conquest.blocks(c) if conquest.holder(w, c, loc) == side}
    near = [loc for loc in out if conquest.holder(w, c, loc) != side and any(x in mine for x in conquest.adjacent(c, loc))]
    assert near  # 有搶不下來、又跟自家領地直通的敵方區塊，這條才量得到東西
    assert not set(conquest.targets(w, c, side)) & set(out)
    votes = {f"甲{i}": Pick(loc=loc, minute=21 * 60) for i, loc in enumerate(near)}
    picks = conquest_day.plan(w, c, side, 20000, 0.0, votes, set())
    assert picks and not {p.loc for p, _, _ in picks} & set(out)
    assert all(by == conquest_day.COMMANDER for _, by, _ in picks)  # 投到那裡的票都不算，主將補
    many = conquest_day.commander_picks(w, c, side, 99, 20000, set())
    assert not {p.loc for p, _ in many} & set(out)


def test_a_forced_slot_at_an_enemy_base_is_still_not_a_siege_place():
    """時程表上硬塞一場（不經 plan）：鉅鹿道壇出陣沒有對手（裁決 18 的 sortie_foes），不列。新天下的大本營不算進任何一條線，
    這裡把它掛回中原那一條，量的是「沒有對手」那一條排除，不是線對不上。"""
    game = conquest_game_with({**V1_RUNAN, "julu_altar": ("huang", "yingru")})
    w, c = game.state.world, game.content
    announce(game, "julu_altar", "guan")
    announce(game, "runan_wilds", "guan")
    assert "julu_altar" in conquest_day.today(w, c, "guan", "attack")
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds"]
