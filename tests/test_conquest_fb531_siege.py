"""FB-531：攻城軍令的地點只列打得到敵方陣營隊伍、打贏真的記得到的區塊（軍令卡、記功、假人同一個判斷）。

被敵方佔下的中立地站的是中立駐軍與流寇（沒有陣營），在那裡打贏記不到攻城，所以不列。第二批起攻城地點是今天公告的目標
（裁決 11），合併時疊起來（計畫 6.2「合併 conquest-1 修正」）：這幾條先把要比的區塊公告了再比。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join, plain_game, win_sortie
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
    announce(game, "hilltop_wilds", "guan")  # 第二批：兩塊都是官軍今天公告的目標
    announce(game, "runan_wilds", "guan")
    return w, c


def test_a_captured_neutral_block_is_not_a_siege_place():
    game = conquest_game("season21")
    w, c = _hilltop_to_huang(game)
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds"]  # 修前多了荒丘


def test_the_card_names_only_where_a_win_counts():
    game = join(conquest_game("season21"), "guan")
    _hilltop_to_huang(game)
    order = _siege(game)
    how = atlas.siege_how(game.state, game.content, order)
    assert "汝南荒野" in how and "荒丘" not in how  # 修前「到荒丘或汝南荒野出陣」


def test_bots_are_not_sent_where_a_win_does_not_count():
    game = join(conquest_game("season21"), "guan")
    s, c = game.state, game.content
    _hilltop_to_huang(game)
    _siege(game)
    assert not orders.win_counts(s, c, "guan", "hilltop_wilds")  # 修前 True
    assert orders.win_counts(s, c, "guan", "runan_wilds")
    assert "hilltop_wilds" not in orders.targets(s, c, "guan")


def test_every_listed_place_credits_a_sortie_win():
    """列出來的地方打贏一定記得到：在汝南荒野出陣攻打贏，那一道攻城記一次。"""
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    announce(game, "runan_wilds", "guan")
    order = _siege(game)
    assert "runan_wilds" in orders.siege_places(game.content, "guan", "yingru", game.state.world)
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1


def test_no_siege_is_issued_where_only_captured_neutral_blocks_are_enemy_held():
    """一條線上敵方只佔了中立地（黃巾在南陽拿下南陽官道；官軍那一側南陽沒有黃巾的陣營區塊碰得到）：不發攻城。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "nanyang_road", "huang")
    announce(game, "nanyang_road", "guan")
    assert orders.siege_places(c, "guan", "nanyang", w) == []  # 修前 ["nanyang_road"]


def test_switch_off_siege_places_unchanged():
    """關著：照修之前（a73c111e 上量的）一個字都不變——地盤照控制方、沒給 world 照地點的 enemies。"""
    game = plain_game("season21")
    w, c = game.state.world, game.content
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds", "huangjin_camp"]
    assert orders.siege_places(c, "guan", "jizhou", w) == ["juma_river", "yanshan_foot", "julu_altar", "guangzong"]
    assert orders.siege_places(c, "huang", "nanyang", w) == ["yu_river", "nanyang_wilds"]
    assert orders.siege_places(c, "guan", "yingru") == ["yingchuan_wilds", "changshe", "runan_wilds", "huangjin_camp"]
    assert orders.siege_places(c, "huang", "jizhou") == ["luzhi_camp", "baima_ford"]
