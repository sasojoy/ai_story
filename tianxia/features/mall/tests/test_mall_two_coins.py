"""元寶拆成兩種（Joy 2026-11-26「第二種元寶參考中國歷史中有名有價值的貨幣名稱、其他都照建議」，卡上挑了「五銖」；
設計稿 https://claude.ai/artifact/1wAUChQ7ZhkCXBMqZLJGYd）：元寶只能儲值、五銖是遊戲裡送的。開關 Config.mall.two_coins
開著時商品寫 coin "paid" 的只收元寶，其餘先扣五銖；退款退回原來的那一種；月卡回饋與每天的份是五銖。"""
from __future__ import annotations

import pytest
from test_mall import T0, _admin, _game, _rows, _wallet

from tianxia.characters import open_characters
from tianxia.features.mall import actions as mall_actions
from tianxia.features.mall import rules as mall
from tianxia.models import MallItem


@pytest.fixture
def two(content):
    m = content.config.mall
    m.enabled, m.beta_grant, m.two_coins = True, 5000, True
    m.card_daily_ingots, m.card_daily_pills = 60, 1
    content.mall = {i.id: i for i in (
        MallItem(id="pills_5", name="回體丹五顆", price=100, kind="consumable", effects={"pills": 5}),
        MallItem(id="card_30", name="月卡", price=600, kind="card", coin="paid", effects={"card_days": 30, "card_rebate": 300}),
    )}
    content.config.stamina_pills_per_day = 2
    content.config.newbie_pills_per_day = 5
    content.config.admins = ["管理者"]
    return content


def _player(content):
    game = _game(content)
    game.mark_seen(T0)  # 封測發放 5000，算五銖
    return game


def _topup(game, n, ref="topup:test"):
    _wallet(game).post("沈浪", n, "topup", ref, time=T0)


@pytest.mark.smoke
def test_growth_items_take_the_gift_and_paid_items_refuse_it(two):
    player = _player(two)
    assert _wallet(player).balances("沈浪") == {"paid": 0, "gift": 5000}
    msg = mall_actions.buy(player, "pills_5", "a1")[0]
    assert "五銖 -100" in msg and "元寶 0、五銖 4900" in msg
    refused = mall_actions.buy(player, "card_30", "a2")[0]
    assert refused == mall.PAID_SHORT.format(name="月卡", price=600, paid=0)
    view = mall_actions.view(player)
    card = next(i for i in view["items"] if i["id"] == "card_30")
    assert (card["paid"], card["can"], card["split"]) == (True, False, None)
    assert view["coins"] == {"paid": 0, "gift": 4900, "gift_name": "五銖"}
    _topup(player, 600)
    bought = mall_actions.buy(player, "card_30", "a3")[0]
    assert bought.startswith("買下") and "每天領 60 五銖" in bought and "當場回 300 五銖" in bought
    assert mall.perks(two.mall["card_30"], two)[:2] == ["買下當場拿回 300 五銖", "每天上線領 60 五銖＋回體丹 1 顆（沒上線那天不補）"]
    # 月卡只扣元寶；當場回的 300 是五銖（Joy 照建議：不然 600 元寶會變成 2100 元寶）
    assert _wallet(player).balances("沈浪") == {"paid": 0, "gift": 5200}
    assert mall_actions.entry(player)["coins"] == {"paid": 0, "gift": 5200, "gift_name": "五銖"}


def test_a_mixed_payment_is_one_line_and_refunds_to_each_kind(two):
    player = _player(two)
    w = _wallet(player)
    w.post("沈浪", -4950, "revoke", "admin:take", time=T0)  # 五銖只剩 50
    _topup(player, 100)
    assert "元寶 -50、五銖 -50" in mall_actions.buy(player, "pills_5", "m1")[0]
    bought = w.purchases("沈浪")[0]
    assert bought.data["coins"] == {"gift": 50, "paid": 50}
    rec = mall_actions.records(player)
    assert rec["ledger"][0]["delta"] == -100 and rec["ledger"][0]["coins"] == {"paid": -50, "gift": -50}
    admin = _admin(two)
    assert "元寶 +50、五銖 +50" in mall_actions.admin_refund(admin, "沈浪", bought.id, "買錯了")[0]
    assert w.balances("沈浪") == {"paid": 100, "gift": 50}


def test_card_refund_takes_the_rebate_from_the_gift_first(two):
    player = _player(two)
    _topup(player, 600)
    mall_actions.buy(player, "card_30", "c1")
    w = _wallet(player)
    pid = w.purchases("沈浪")[0].id
    w.post("沈浪", -5300, "revoke", "admin:spent", time=T0)  # 五銖全花光了
    mall_actions.admin_refund(_admin(two), "沈浪", pid, "退月卡")
    # 退回 600 元寶，當場回的 300 五銖已經花掉：從元寶裡抵
    assert w.balances("沈浪") == {"paid": 300, "gift": 0}


def test_daily_share_is_gift_and_says_so(two):
    player = _player(two)
    _topup(player, 600)
    mall_actions.buy(player, "card_30", "d1")
    msgs = mall_actions.claim(player)
    assert "五銖 +60" in msgs[0]
    assert _rows(player)[0].coin == "gift"


def test_admin_can_reissue_paid_for_a_lost_topup(two):
    player = _player(two)
    admin = _admin(two)
    msg = mall_actions.admin_reissue(admin, "沈浪", 300, "儲值沒入帳", "r1", "paid")[0]
    assert "300 元寶" in msg
    assert _wallet(player).balances("沈浪") == {"paid": 300, "gift": 5000}
    assert "五銖" in mall_actions.admin_revoke(admin, "沈浪", 100, "發錯", "r2")[0]
    assert _wallet(player).balances("沈浪") == {"paid": 300, "gift": 4900}
    assert "coins" in mall_actions.admin_ledger(admin, "沈浪")


def test_with_the_switch_off_nothing_shows_and_paid_items_sell_for_gifts(two):
    """開關關著（現在線上）：畫面不多任何鍵，字照舊寫元寶，只收元寶的商品照舊兩種都收；帳照樣分兩種記。"""
    two.config.mall.two_coins = False
    player = _player(two)
    assert mall_actions.buy(player, "pills_5", "o1")[0] == "買下「回體丹五顆」：回體丹 5 顆。元寶 -100（還剩 4900）。"
    assert mall_actions.buy(player, "card_30", "o2")[0].startswith("買下")
    view = mall_actions.view(player)
    assert "coins" not in view and all("paid" not in i and "split" not in i for i in view["items"])
    assert "coins" not in mall_actions.entry(player) and "coins" not in mall_actions.records(player)
    assert _wallet(player).balances("沈浪") == {"paid": 0, "gift": 4600}
    open_characters().save(player.state)
