"""扣押期（帳號與客服第 208 批；設計 4.3、4.4、6.4）：形象市集上架（鍵 looks_market）。被扣押的帳號上架回那一句；
下架、買照舊（第 208 批計畫：買是 looks_market 的另一個入口，這一批只擋上架）。identity 關著一個字不變。"""
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


def test_unlist_and_buy_not_blocked(on, world, keyed):  # noqa: F811
    maker, look, buyer = _setup(on, world)
    phone_kit.gate(on, on=False)
    assert "掛到市集了" in actions.market_list(maker, look, 800)[-1]
    phone_kit.hold(world.db, "ray1", T0 + 100)
    phone_kit.hold(world.db, "ray2", T0 + 100)
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
