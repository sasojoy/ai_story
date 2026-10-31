"""形象市集（功能包 looks 第四批）：做好的自建形象自己定價掛上去、下架；別人買一份（自己的、買過的不能買），買到的換季也在、
可以換上；分成一半押七天才入帳，押著的時候退款就不給；儲值限定的開關開著只准用儲值的元寶；假人不買；一般購買不賣它。"""
from __future__ import annotations

import pytest
from test_looks import T0, _game
from test_looks_orders import _admin, _upload_all

from tianxia.features.looks import actions, market, orders
from tianxia.models import Look, MallItem
from tianxia.wallet import Wallet

DAY = 86400


@pytest.fixture
def on(content):
    content.config.mall.enabled, content.config.mall.beta_grant = True, 5000
    content.looks = {"moying": Look(id="moying", name="墨影", bots=True)}
    content.mall = {i.id: i for i in (
        MallItem(id="look_order", name="自建形象", price=900, kind="look", effects={"look_order": 1}),
        MallItem(id="look_market", name="市集形象", price=600, kind="look", effects={"look_market": 1}),
    )}
    content.config.admins = ["管理者"]
    return content


def _made(on, world):
    """沈浪做好一套「白衣書生」；回（沈浪, 形象 id）。"""
    maker = _game(on, world=world)
    actions.order(maker, "白衣書生", "白衣書生，背著竹簍", "order-ref-m01")
    pid = actions.view(maker)["order"]["list"][0]["id"]
    admin = _admin(on, world)
    _upload_all(admin, pid)
    actions.admin_release(admin, pid)
    return maker, orders.look_id(pid)


@pytest.mark.smoke
def test_list_buy_wear_and_the_share_waits_seven_days(on, world):
    maker, look = _made(on, world)
    assert "掛到市集了，一份 800 元寶；賣出一份你分 400" in actions.market_list(maker, look, 800)[-1]
    buyer = _game(on, name="楚留香", world=world)
    shelf = actions.view(buyer)["market"]["shelf"]
    assert [(x["look"], x["name"], x["seller"], x["price"]) for x in shelf] == [(look, "白衣書生", "沈浪", 800)]
    assert actions.view(maker)["market"]["shelf"] == []  # 自己的不列
    msgs = actions.market_buy(buyer, look, "mkt-ref-001")
    assert "買下了「白衣書生」（沈浪做的）：元寶 -800" in msgs[-1] and Wallet(world.db).balance("楚留香") == 4200
    assert actions.market_buy(buyer, look, "mkt-ref-002")[-1] == market.HAVE
    assert "白衣書生" in actions.wear(buyer, look)[-1] and buyer.arena_look() == look
    assert actions.market_buy(maker, look, "mkt-ref-003")[-1] == market.OWN
    w = Wallet(world.db)
    before = w.balance("沈浪")
    assert market.settle(w, "look_market", "沈浪", T0 + 6 * DAY) == 0  # 還押著
    assert actions.view(maker)["market"]["held"] == 400
    assert market.settle(w, "look_market", "沈浪", T0 + 8 * DAY) == 400
    assert market.settle(w, "look_market", "沈浪", T0 + 9 * DAY) == 0  # 不會入兩次
    assert w.balance("沈浪") == before + 400
    got = actions.view(maker)["market"]
    assert (got["sold"], got["paid"], got["held"]) == (1, 400, 0)


def test_unlist_keeps_what_was_bought(on, world):
    maker, look = _made(on, world)
    actions.market_list(maker, look, 600)
    buyer = _game(on, name="楚留香", world=world)
    actions.market_buy(buyer, look, "mkt-ref-004")
    assert "撤下了" in actions.market_unlist(maker, look)[-1]
    other = _game(on, name="陸小鳳", world=world)
    assert actions.market_buy(other, look, "mkt-ref-005")[-1] == market.NOT_LISTED
    assert look in [lk["id"] for lk in actions.view(buyer)["looks"]]


def test_only_your_own_made_look_at_a_fair_price(on, world):
    maker, look = _made(on, world)
    other = _game(on, name="楚留香", world=world)
    assert actions.market_list(other, look, 600)[-1] == market.NOT_YOURS
    assert actions.market_list(maker, look, 100)[-1] == market.BAD_PRICE.format(lo=market.PRICE_MIN, hi=market.PRICE_MAX)
    assert actions.market_list(maker, "moying", 600)[-1] == market.NOT_YOURS


def test_a_refund_while_held_cancels_the_share(on, world):
    maker, look = _made(on, world)
    actions.market_list(maker, look, 600)
    buyer = _game(on, name="楚留香", world=world)
    actions.market_buy(buyer, look, "mkt-ref-006")
    w = Wallet(world.db)
    sale = market.sales(w, "look_market")[0]
    w.mark_refunded(sale.pid, T0 + DAY)
    assert market.settle(w, "look_market", "沈浪", T0 + 30 * DAY) == 0
    assert look not in [lk["id"] for lk in actions.view(buyer)["looks"]]


def test_paid_only_needs_topped_up_ingots(on, world):
    on.config.mall.market_paid_only = True
    maker, look = _made(on, world)
    actions.market_list(maker, look, 600)
    buyer = _game(on, name="楚留香", world=world)
    assert actions.market_buy(buyer, look, "mkt-ref-007")[-1] == market.PAID_ONLY.format(price=600, paid=0)
    Wallet(world.db).post("楚留香", 600, "topup", "topup:test-1", time=T0)
    assert "買下了" in actions.market_buy(buyer, look, "mkt-ref-008")[-1]


def test_bots_and_the_shelf_never_buy_it(on, world):
    maker, look = _made(on, world)
    actions.market_list(maker, look, 600)
    bot = _game(on, name="假人乙", world=world)
    bot.state.player.bot = True
    assert actions.market_buy(bot, look, "mkt-ref-009")[-1] == market.NOT_OPEN
    assert "look_market" not in [i["id"] for i in maker.mall_view()["items"]]
    assert maker.mall_buy("look_market", "buy-ref-0013")[-1] == "沒有這件商品。"
