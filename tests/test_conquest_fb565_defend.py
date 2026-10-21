"""FB-565（PM 2026-10-20，dev/conquest-fix2 開發回報）：領地爭奪開著時，守城軍令卡的做法（atlas.order_how）與輿圖的守城標記
（mapdata._order_marks）要跟實際記得到的一致——只寫、只標「自家今天被公告要攻的那一塊」（裁決 11、24）；今天沒有公告自家的區塊時，
卡上照實說今天沒有可守的，輿圖不標。同 FB-531 的教訓：列與記同一個判斷（orders.defend_places，記功、假人往哪走、卡、輿圖都讀它）。
關著的季（週末、14 天、21 天）一個字都不變。
翻地與爭搶（PM 2026-10-20 第 1 條）之後「被公告要攻的那一塊」換成「自家被推得最高、守得動的那一塊」（conquest.focus_blocks）：
前提從 announce（排進時程表，翻地之後等於那一塊被戰書凍結、守不動）改成對面在那裡推了一截（conquest_kit.press），斷言不動；
「打完、作罷就不算」換成「對面的進度被拉回零就不算」。卡上的字照翻地改（dev/flip-1 收尾）：「今天沒有…被公告要攻」換成「此刻沒有對面在推…」，
「被公告要攻的自家地方」換成「對面推得最高的幾處自家地方」（test_the_card_never_talks_about_announcements）。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, join, plain_game, press
from tianxia import atlas, conquest, mapdata, orders
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

GUAN_BLOCKS = ("yingchuan", "yingshui", "yingchuan_wilds", "songshan_foot", "yingchuan_academy")  # 潁川汝南線上官軍的區塊（不含大本營長社）


def _game(profile: str = "season21"):
    """領地爭奪開著、官軍的人；開季發的軍令清掉，只剩測試自己掛的（不然別的戰線的守城也算進 duty_counts）。"""
    game = join(conquest_game(profile), "guan")
    game.state.world.orders.clear()
    return game


def _defend(game, side="guan", front="yingru") -> Order:
    order = Order(id=f"t:{side}:defend", template="defend", faction=side, week=orders.period_of(game.state, game.content),
                  front=front, quota=5, text="守")
    game.state.world.orders.append(order)
    return order


def _marks(game, side="guan") -> set[str]:
    marks = mapdata._order_marks(game.state, game.content, side)
    return {loc for loc, word in marks.items() if word == mapdata.ORDER_WORDS["defend"]}


def _counts_at(game, order) -> set[str]:
    c, w = game.content, game.state.world
    return {loc for loc in c.locations if orders._counts(c, order, "duty", loc, None, None, None, None, None, w)}


def _agree(game, order, side="guan") -> set[str]:
    """卡上列的（defend_places）、輿圖標的、記得到的、假人往哪走的、duty_counts 的，是同一批地點；回那一批。"""
    c, w = game.content, game.state.world
    listed = set(orders.defend_places(c, w, order))
    assert _marks(game, side) == listed
    assert _counts_at(game, order) == listed
    assert set(orders.targets(game.state, c, side)) == listed
    assert {loc for loc in c.locations if orders.duty_counts(game.state, c, side, loc)} == listed
    return listed


def test_no_block_announced_the_card_says_so_and_the_map_marks_nothing():
    game = _game()
    order = _defend(game)
    assert _agree(game, order) == set()  # 修前輿圖標長社（自家大本營，記不到）
    text = atlas.order_how(game.state, game.content, order)
    assert text == atlas.DEFEND_NONE_CONQUEST.format(front=atlas.trend_name(game.content, "yingru"))
    assert "此刻沒有" in text and "自家的地盤出陣" not in text  # 修前寫「在潁川汝南一帶自家的地盤出陣守一回…做一次記一次」


def test_one_announced_block_is_named_and_marked():
    game = _game()
    order = _defend(game)
    press(game, "yingchuan_wilds", "huang")
    assert _agree(game, order) == {"yingchuan_wilds"}
    text = atlas.order_how(game.state, game.content, order)
    assert "潁川郊野" in text and "做一次記一次" in text and "此刻沒有" not in text
    assert "巡哨" in text and "出陣" in text
    assert mapdata._order_marks(game.state, game.content, "guan")["yingchuan_wilds"] == "守城"


def test_two_announced_blocks_are_both_named():
    game = _game()
    order = _defend(game)
    press(game, "yingchuan_wilds", "huang")
    press(game, "yingshui", "huang")
    assert _agree(game, order) == {"yingchuan_wilds", "yingshui"}
    text = atlas.order_how(game.state, game.content, order)
    assert "潁川郊野" in text and "潁水河畔" in text


def test_many_announced_blocks_say_the_area():
    game = _game()
    order = _defend(game)
    for i, loc in enumerate(GUAN_BLOCKS[:3]):
        press(game, loc, "huang")
    assert _agree(game, order) == set(GUAN_BLOCKS[:3])
    text = atlas.order_how(game.state, game.content, order)
    assert text == atlas.DEFEND_AREA_CONQUEST.format(
        front=atlas.trend_name(game.content, "yingru"), act=atlas.DEFEND_ACT_SORTIE.format(duty="巡哨"))
    assert "對面推得最高" in text


def test_a_siege_that_is_over_or_called_off_no_longer_counts():
    game = _game()
    order = _defend(game)
    press(game, "yingchuan_wilds", "huang")
    assert _agree(game, order) == {"yingchuan_wilds"}
    conquest.push(game.state.world, game.content, "yingchuan_wilds", "guan", "守將", 100, "hold")  # 拉回零
    assert _agree(game, order) == set()
    assert "此刻沒有" in atlas.order_how(game.state, game.content, order)


def test_a_block_my_own_side_is_attacking_is_not_one_to_defend():
    """官軍攻黃巾的區塊：那一塊是官軍要攻的，不是官軍要守的；黃巾那邊才是要守的。"""
    game = _game()
    order = _defend(game)
    huang_order = _defend(game, side="huang")
    press(game, "runan_wilds", "guan")
    assert _agree(game, order) == set()
    assert _agree(game, huang_order, side="huang") == {"runan_wilds"}


def test_other_fronts_are_not_listed():
    game = _game()
    order = _defend(game, front="nanyang")
    press(game, "yingchuan_wilds", "huang")  # 潁川汝南線上的，不是南陽線
    assert _agree(game, order) == set()


def test_every_location_agrees_between_card_map_credit_and_bots():
    """列與記同一個判斷：不管公告了哪幾塊，每一個地點上四個說法都一致（沒有列了卻記不到、記得到卻沒列）。"""
    game = _game()
    order = _defend(game)
    for loc in GUAN_BLOCKS:
        press(game, loc, "huang")
        _agree(game, order)
    assert conquest.holder(game.state.world, game.content, "changshe") == "guan"
    assert "changshe" not in _agree(game, order)  # 自家大本營搶不下來，從來不會被公告，也從來不在守城的地點裡


def test_the_card_never_talks_about_announcements():
    """翻地與爭搶（dev/flip-1 收尾）：投票與每天 22:00 的公告拿掉了，守城卡上不能再寫「被公告要攻」「每天 22:00 公告下一天的」——
    照翻地寫：對面此刻在推的自家地方，沒有就說此刻沒有對面在推的自家地方。"""
    game = _game()
    order = _defend(game)
    texts = [atlas.order_how(game.state, game.content, order)]  # 沒人在推
    for loc in GUAN_BLOCKS[:3]:
        press(game, loc, "huang")
        texts.append(atlas.order_how(game.state, game.content, order))  # 一處、兩處（寫地名）、三處（寫一帶）
    for text in texts:
        assert "公告" not in text and "今天" not in text, text  # 修前「今天沒有自家的地方被公告要攻…每天 22:00 公告下一天的」
    assert texts[0] == atlas.DEFEND_NONE_CONQUEST.format(front=atlas.trend_name(game.content, "yingru"))
    assert texts[-1] == atlas.DEFEND_AREA_CONQUEST.format(
        front=atlas.trend_name(game.content, "yingru"), act=atlas.DEFEND_ACT_SORTIE.format(duty="巡哨"))


@pytest.mark.parametrize("profile", ["weekend", None, "season21"])  # 一個測試只開一季
def test_switch_off_the_defend_card_is_the_old_sentence(profile):
    """領地爭奪關著：卡上照舊那一句、輿圖照舊標自家控制的戰線地點（舊規則整條線都記，不問哪一塊被公告）。"""
    game = join(plain_game(profile), "guan")
    game.state.world.orders.clear()
    order = _defend(game)
    c, w = game.content, game.state.world
    assert orders.defend_places(c, w, order) == []  # 新函式只在領地爭奪生效時有東西
    text = atlas.order_how(game.state, c, order)
    assert "今天沒有" not in text and "被公告" not in text and "此刻沒有" not in text and "對面推得最高" not in text
    assert text.startswith("在潁川汝南一帶") and "巡哨" in text
