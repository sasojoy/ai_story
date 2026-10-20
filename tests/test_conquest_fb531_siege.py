"""FB-531：攻城軍令的地點只列打得到敵方陣營隊伍、打贏真的記得到的區塊（軍令卡、記功、假人同一個判斷）。

被敵方佔下的中立地站的是中立駐軍與流寇（沒有陣營），在那裡打贏記不到攻城，所以不列。第二批起攻城地點是今天公告的目標
（裁決 11），合併時疊起來（計畫 6.2「合併 conquest-1 修正」）：這幾條先把要比的區塊公告了再比。
輿圖重製第 1 批（新天下）：中原那一條線上全是中立地、外圈的陣營區塊不算進任何一條線，正式內容裡找不到「線上的敵方陣營區塊」；
這幾條把汝南荒野改回 v1 的黃巾陣營區塊（conquest_kit.conquest_game_with）來量同一條規則。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, conquest_game_with, go, join, plain_game, win_sortie
from tianxia import atlas, conquest, orders
from tianxia.state import Order

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


def _hilltop_to_huang(game):
    w, c = game.state.world, game.content
    assert conquest.set_control(w, c, "hilltop_wilds", "huang")  # QA：管理者把荒丘定給黃巾
    announce(game, "hilltop_wilds", "guan")  # 第二批：兩塊都是官軍今天公告的目標
    announce(game, "runan_wilds", "guan")
    return w, c


def test_a_captured_neutral_block_is_not_a_siege_place():
    game = _game()
    w, c = _hilltop_to_huang(game)
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds"]  # 修前多了荒丘


def test_the_card_names_only_where_a_win_counts():
    game = join(_game(), "guan")
    _hilltop_to_huang(game)
    order = _siege(game)
    how = atlas.siege_how(game.state, game.content, order)
    assert "汝南荒野" in how and "荒丘" not in how  # 修前「到荒丘或汝南荒野出陣」


def test_bots_are_not_sent_where_a_win_does_not_count():
    game = join(_game(), "guan")
    s, c = game.state, game.content
    _hilltop_to_huang(game)
    _siege(game)
    assert not orders.win_counts(s, c, "guan", "hilltop_wilds")  # 修前 True
    assert orders.win_counts(s, c, "guan", "runan_wilds")
    assert "hilltop_wilds" not in orders.targets(s, c, "guan")


def test_every_listed_place_credits_a_sortie_win():
    """列出來的地方打贏一定記得到：在汝南荒野出陣攻打贏，那一道攻城記一次。"""
    game = go(join(_game(), "guan"), "runan_wilds")
    announce(game, "runan_wilds", "guan")
    order = _siege(game)
    assert "runan_wilds" in orders.siege_places(game.content, "guan", "yingru", game.state.world)
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1


def test_no_siege_is_issued_where_only_captured_neutral_blocks_are_enemy_held():
    """一條線上敵方只佔了中立地（新天下：黃巾拿下中原的荒丘；中原那一條線上沒有黃巾的陣營區塊）：不發攻城。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "hilltop_wilds", "huang")
    announce(game, "hilltop_wilds", "guan")
    assert orders.siege_places(c, "guan", "yingru", w) == []  # 修前 ["hilltop_wilds"]


def test_switch_off_siege_places_unchanged():
    """關著：照修之前的寫法——地盤照控制方、沒給 world 照地點的 enemies（地點的名單照新天下的內容）。"""
    game = plain_game("season21")
    w, c = game.state.world, game.content
    assert orders.siege_places(c, "guan", "yingru", w) == SWITCH_OFF["guan_yingru_world"]
    assert orders.siege_places(c, "guan", "jizhou", w) == SWITCH_OFF["guan_jizhou_world"]
    assert orders.siege_places(c, "huang", "nanyang", w) == SWITCH_OFF["huang_nanyang_world"]
    assert orders.siege_places(c, "guan", "yingru") == SWITCH_OFF["guan_yingru"]
    assert orders.siege_places(c, "huang", "jizhou") == SWITCH_OFF["huang_jizhou"]


SWITCH_OFF = {  # 新天下量的（舊拔河只剩中原那一條；南陽、冀州的舊線只剩大本營與 fixed，第 5 批三條線變一條）
    "guan_yingru_world": ["nanyang_huangjin_camp", "guandu", "jiwu"],
    "guan_jizhou_world": ["julu_altar", "guangzong"],
    "huang_nanyang_world": ["wan_city"],
    "guan_yingru": ["yingchuan_wilds", "changshe", "nanyang_huangjin_camp", "runan_wilds", "huangjin_camp"],
    "huang_jizhou": [],  # 冀州那條舊線上沒有站官軍的地點了（v1 是盧植營、白馬津，搬進了東郡）
}
