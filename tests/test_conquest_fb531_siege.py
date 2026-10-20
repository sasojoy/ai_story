"""FB-531：攻城軍令的地點只列打贏真的記得到的區塊（軍令卡、記功、假人同一個判斷）。

第二批起攻城地點是今天公告的目標（裁決 11），裁決 20（PM 2026-10-21）讓中立駐軍也算。翻地與爭搶（PM 2026-10-20 第 1 條）之後改讀成
「這一邊此刻進度最高、推得動的那一塊」：這幾條先把要比的區塊推到最高再比；列與記功照舊同一個判斷（FB-531 的教訓不變）。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, go, join, plain_game, win_sortie
from tianxia import atlas, conquest, orders
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _siege(game, faction="guan", front="yingru"):
    s, c = game.state, game.content
    order = Order(id=f"t:{faction}:siege:{front}", template="siege", faction=faction, week=orders.period_of(s, c), front=front,
                  quota=6, text="（測試）")
    s.world.orders.append(order)
    return order


def _hilltop_to_huang(game):
    w, c = game.state.world, game.content
    assert conquest.set_control(w, c, "hilltop_wilds", "huang")  # QA：管理者把荒丘定給黃巾
    for loc in ("hilltop_wilds", "runan_wilds"):  # 兩塊並列官軍此刻進度最高
        conquest.push(w, c, loc, "guan", "某", 20, "attack")
    return w, c


def test_a_captured_neutral_block_is_a_siege_place_since_ruling_20():
    game = conquest_game("season21")
    w, c = _hilltop_to_huang(game)
    assert orders.siege_places(c, "guan", "yingru", w) == ["hilltop_wilds", "runan_wilds"]  # 裁決 20：中立駐軍也算


def test_the_card_names_only_where_a_win_counts():
    game = join(conquest_game("season21"), "guan")
    _hilltop_to_huang(game)
    order = _siege(game)
    how = atlas.siege_how(game.state, game.content, order)
    assert "汝南荒野" in how and "荒丘" in how and "嵩山深處" not in how


def test_bots_go_where_a_win_counts():
    game = join(conquest_game("season21"), "guan")
    s, c = game.state, game.content
    _hilltop_to_huang(game)
    _siege(game)
    assert orders.win_counts(s, c, "guan", "hilltop_wilds") and orders.win_counts(s, c, "guan", "runan_wilds")
    assert not orders.win_counts(s, c, "guan", "deep_mountain")  # 進度不是最高：記不到
    assert "hilltop_wilds" in orders.targets(s, c, "guan")


def test_every_listed_place_credits_a_sortie_win():
    """列出來的地方打贏一定記得到：在汝南荒野出陣攻打贏，那一道攻城記一次。"""
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    conquest.push(game.state.world, game.content, "runan_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    assert "runan_wilds" in orders.siege_places(game.content, "guan", "yingru", game.state.world)
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1


def test_a_siege_is_issued_where_only_captured_neutral_blocks_are_enemy_held():
    """一條線上敵方只佔了中立地（黃巾在南陽拿下南陽官道）：照樣發攻城（中立駐軍也算）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "nanyang_road", "huang")
    conquest.push(w, c, "nanyang_road", "guan", "某", 10, "attack")
    assert orders.siege_places(c, "guan", "nanyang", w) == ["nanyang_road"]


def test_switch_off_siege_places_unchanged():
    """關著：照修之前（a73c111e 上量的）一個字都不變——地盤照控制方、沒給 world 照地點的 enemies。"""
    game = plain_game("season21")
    w, c = game.state.world, game.content
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds", "huangjin_camp"]
    assert orders.siege_places(c, "guan", "jizhou", w) == ["juma_river", "yanshan_foot", "julu_altar", "guangzong"]
    assert orders.siege_places(c, "huang", "nanyang", w) == ["yu_river", "nanyang_wilds"]
    assert orders.siege_places(c, "guan", "yingru") == ["yingchuan_wilds", "changshe", "runan_wilds", "huangjin_camp"]
    assert orders.siege_places(c, "huang", "jizhou") == ["luzhi_camp", "baima_ford"]
