"""綁手機才能用（帳號與客服第 205 批；設計 4.5）：形象市集的上架與買（鍵 looks_market）；下架不擋；市集沒開先說沒開。
只問動手的那一個人；phone_gate 關著一個字不變。市集的鈕在 web/looks.js，這一批不碰網頁，不灰鈕（按下去回那一句）。"""
from __future__ import annotations

import phone_kit
import pytest
from test_looks import _game
from test_looks_market import _made
from test_looks_market import on  # noqa: F401  fixture：商城、市集開著

from tianxia.core.identity_base import PHONE_NEEDED
from tianxia.features.looks import actions, market
from tianxia.wallet import Wallet


@pytest.fixture
def keyed(tmp_path, monkeypatch):
    phone_kit.keyed(monkeypatch, tmp_path)


def _setup(on, world):  # noqa: F811
    """閘關著做好一套、建好帳號（沈浪綁 ray1、楚留香綁 ray2，都沒綁手機）；回（沈浪, 形象 id, 楚留香）。"""
    maker, look = _made(on, world)
    buyer = _game(on, name="楚留香", world=world)
    phone_kit.account(world.db, "沈浪", "ray1")
    phone_kit.account(world.db, "楚留香", "ray2")
    return maker, look, buyer


def test_market_list_and_buy_blocked(on, world, keyed):  # noqa: F811
    maker, look, buyer = _setup(on, world)
    phone_kit.gate(on, on=True)
    assert actions.market_list(maker, look, 800) == [PHONE_NEEDED]
    assert actions.view(buyer)["market"]["shelf"] == []
    phone_kit.bind(world.db, "ray1", phone_kit.PHONE_A)
    assert "掛到市集了" in actions.market_list(maker, look, 800)[-1]
    before = Wallet(world.db).balance("楚留香")
    assert actions.market_buy(buyer, look, "mkt-ref-901") == [PHONE_NEEDED]
    assert Wallet(world.db).balance("楚留香") == before
    phone_kit.bind(world.db, "ray2", phone_kit.PHONE_B)
    assert "買下了" in actions.market_buy(buyer, look, "mkt-ref-902")[-1]


def test_unlist_not_blocked(on, world, keyed):  # noqa: F811
    maker, look, _ = _setup(on, world)
    actions.market_list(maker, look, 800)
    phone_kit.gate(on, on=True)
    assert "撤下了" in actions.market_unlist(maker, look)[-1]


def test_closed_market_says_closed_first(on, world, keyed):  # noqa: F811
    maker, look, buyer = _setup(on, world)
    phone_kit.gate(on, on=True)
    on.config.mall.enabled = False
    assert actions.market_list(maker, look, 800) == [market.NOT_OPEN]
    assert actions.market_buy(buyer, look, "mkt-ref-903") == [market.NOT_OPEN]


def test_gate_off_market_unchanged(on, world, keyed):  # noqa: F811
    maker, look, buyer = _setup(on, world)
    phone_kit.gate(on, on=False)
    assert "掛到市集了" in actions.market_list(maker, look, 800)[-1]
    assert "買下了" in actions.market_buy(buyer, look, "mkt-ref-904")[-1]
