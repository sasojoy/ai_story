"""扣押期（帳號與客服第 208 批；設計 4.3、4.4、6.4）：商城買（鍵 mall_buy）。被扣押的帳號買不了、貨架每一件灰掉寫那一句；
identity 關著照舊能買；假人（沒帳號）不受影響；phone_gate 也開著、沒綁手機時先說手機那一句。"""
from __future__ import annotations

import phone_kit
import pytest
from test_mall_phone_gate import T0, _game, _seed
from test_mall_phone_gate import on  # noqa: F401  fixture：商城開著、兩件商品、金鑰讀得到

from tianxia.characters import name_key
from tianxia.core import identity_base
from tianxia.core.identity_base import HOLD_STALE, PHONE_NEEDED
from tianxia.features.mall import actions as mall_actions
from tianxia.state import BotProfile
from tianxia.wallet import Wallet


def _stale(content):
    return HOLD_STALE.format(days=content.config.identity.stale_hold_days)


def test_purchase_blocked_and_view_greyed_while_held(on):  # noqa: F811
    phone_kit.gate(on, on=False)
    game = _game(on)
    _seed(game)
    phone_kit.hold(game.world.db, "ray1", T0 + 100)
    pills = game.state.player.stamina_pills
    assert mall_actions.purchase(game, "pills_5", "x1").lines == [_stale(on)]
    assert Wallet(game.world.db).balance(name_key("沈浪")) == 1000 and game.state.player.stamina_pills == pills
    items = mall_actions.view(game)["items"]
    assert items and all((row["can"], row["why"], row["max"]) == (False, _stale(on), 0) for row in items)
    game.sync(T0 + 100)  # 扣押過了
    assert all(row["can"] for row in mall_actions.view(game)["items"])
    assert mall_actions.purchase(game, "pills_5", "x2").bought == "pills_5"


def test_identity_off_buys_as_before(on):  # noqa: F811
    phone_kit.gate(on, on=False, identity=False)
    game = _game(on)
    _seed(game)
    phone_kit.hold(game.world.db, "ray1", T0 + 100)
    assert identity_base.hold_reason(game, "mall_buy") is None
    assert all(row["can"] for row in mall_actions.view(game)["items"])
    assert mall_actions.purchase(game, "pills_5", "x1").bought == "pills_5"


def test_bot_not_held(on):  # noqa: F811
    phone_kit.gate(on, on=False)
    game = _game(on, account=False)
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    _seed(game)
    assert all(row["can"] for row in mall_actions.view(game)["items"])
    assert mall_actions.purchase(game, "pills_5", "x1").bought == "pills_5"


def test_phone_first_then_hold(on):  # noqa: F811
    phone_kit.gate(on, on=True)
    game = _game(on)
    _seed(game)
    phone_kit.hold(game.world.db, "ray1", T0 + 100)
    assert mall_actions.purchase(game, "pills_5", "x1").lines == [PHONE_NEEDED]
    assert all(row["why"] == PHONE_NEEDED for row in mall_actions.view(game)["items"])
    phone_kit.bind(game.world.db, "ray1", phone_kit.PHONE_A)
    assert mall_actions.purchase(game, "pills_5", "x2").lines == [_stale(on)]
    assert all(row["why"] == _stale(on) for row in mall_actions.view(game)["items"])
