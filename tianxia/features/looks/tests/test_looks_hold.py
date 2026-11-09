"""扣押期（帳號與客服第 208 批；設計 4.3、4.4、6.4）：形象市集上架（鍵 looks_market）。被扣押的帳號上架回那一句；
下架照舊。M 波：買也在花元寶（設計 4.3、4.4「不能花元寶」），買的人被扣押也擋（同一個鍵、同一句）；賣的人被扣押不擋買。
identity 關著一個字不變。"""
from __future__ import annotations

import phone_kit
import pytest
from test_looks import T0
from test_looks_phone_gate import _setup
from test_looks_market import on  # noqa: F401  fixture：商城、市集開著

from tianxia.core.identity_base import HOLD_STALE
from tianxia.features.looks import actions


@pytest.fixture
def keyed(tmp_path, monkeypatch):
    phone_kit.keyed(monkeypatch, tmp_path)


def _stale(content):
    return HOLD_STALE.format(days=content.config.identity.stale_hold_days)


def test_list_blocked_while_held(on, world, keyed):  # noqa: F811
    maker, look, _buyer = _setup(on, world)
    phone_kit.gate(on, on=False)
    phone_kit.hold(world.db, "ray1", T0 + 100)
    assert actions.market_list(maker, look, 800) == [_stale(on)]
    maker.sync(T0 + 100)
    assert "掛到市集了" in actions.market_list(maker, look, 800)[-1]


def test_buy_blocked_while_buyer_held(on, world, keyed):  # noqa: F811
    maker, look, buyer = _setup(on, world)
    phone_kit.gate(on, on=False)
    assert "掛到市集了" in actions.market_list(maker, look, 800)[-1]
    phone_kit.hold(world.db, "ray1", T0 + 100)  # 賣的人被扣押不擋買
    phone_kit.hold(world.db, "ray2", T0 + 100)
    assert actions.market_buy(buyer, look, "mkt-ref-951") == [_stale(on)]
    buyer.sync(T0 + 100)
    assert "買下了" in actions.market_buy(buyer, look, "mkt-ref-951")[-1]


def test_unlist_while_held(on, world, keyed):  # noqa: F811
    maker, look, _buyer = _setup(on, world)
    phone_kit.gate(on, on=False)
    actions.market_list(maker, look, 800)
    phone_kit.hold(world.db, "ray1", T0 + 100)
    assert "撤下了" in actions.market_unlist(maker, look)[-1]


def test_identity_off_list_unchanged(on, world, keyed):  # noqa: F811
    maker, look, _buyer = _setup(on, world)
    phone_kit.gate(on, on=False, identity=False)
    phone_kit.hold(world.db, "ray1", T0 + 100)
    assert "掛到市集了" in actions.market_list(maker, look, 800)[-1]


# ── 第 209 批：花元寶的另外兩個入口（自建形象、招式下單）也擋（同一句、元寶不動；鍵照商城買 mall_buy）──


def _orderer(on, world):  # noqa: F811
    from test_looks import _game
    from test_looks_moves import _art

    from tianxia.models import MallItem

    on.mall["move_basic"] = MallItem(id="move_basic", name="通用絕招", price=60, kind="look", effects={"move_basic": 1})
    maker = _game(on, world=world)
    phone_kit.account(world.db, "沈浪", "ray1")
    _art(maker)
    return maker


def test_order_and_order_move_blocked_while_held(on, world, keyed):  # noqa: F811
    from tianxia.wallet import Wallet

    maker = _orderer(on, world)
    phone_kit.gate(on, on=False)
    phone_kit.hold(world.db, "ray1", T0 + 100)
    before = Wallet(world.db).balance("沈浪")
    assert actions.order(maker, "白衣書生", "白衣書生，背著竹簍", "order-ref-h01") == [_stale(on)]
    assert actions.order_move(maker, "一劍寒光九萬里", "move-ref-h01", basic=True) == [_stale(on)]
    assert Wallet(world.db).balance("沈浪") == before
    maker.sync(T0 + 100)
    actions.order(maker, "白衣書生", "白衣書生，背著竹簍", "order-ref-h02")
    actions.order_move(maker, "一劍寒光九萬里", "move-ref-h02", basic=True)
    assert Wallet(world.db).balance("沈浪") == before - 900 - 60  # 過了扣押照扣


def test_identity_off_orders_unchanged(on, world, keyed):  # noqa: F811
    from tianxia.wallet import Wallet

    maker = _orderer(on, world)
    phone_kit.gate(on, on=False, identity=False)
    phone_kit.hold(world.db, "ray1", T0 + 100)
    before = Wallet(world.db).balance("沈浪")
    actions.order(maker, "白衣書生", "白衣書生，背著竹簍", "order-ref-h03")
    actions.order_move(maker, "一劍寒光九萬里", "move-ref-h03", basic=True)
    assert Wallet(world.db).balance("沈浪") == before - 900 - 60
