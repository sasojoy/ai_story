"""綁手機才能用（帳號與客服第 205 批；設計 4.5）：商城買（鍵 mall_buy）、封測發放（鍵 mall_grant）。
封測元寶綁了手機那一輪才發，再記一筆 grant:beta:phone:<subject>（mall_ledger.ref UNIQUE）：同一支手機一輩子一次，解綁、換帳號都不放掉；
開閘前發過的不追回、不補手機編號；假人（沒帳號）照舊發；phone_gate 關著一個字不變。"""
from __future__ import annotations

import random

import phone_kit
import pytest

from tianxia.characters import name_key, open_characters
from tianxia.core.identity_base import PHONE_NEEDED
from tianxia.engine import Game
from tianxia.features.mall import actions as mall_actions
from tianxia.features.mall import rules as mall
from tianxia.models import MallItem
from tianxia.state import BotProfile
from tianxia.wallet import Wallet

HOUR = 3600
DAY = 24 * HOUR
T0 = DAY - 8 * HOUR + 20000 * DAY + 9 * HOUR  # 某一天台灣早上九點（同 test_mall）


@pytest.fixture
def on(content, tmp_path, monkeypatch):
    phone_kit.keyed(monkeypatch, tmp_path)
    m = content.config.mall
    m.enabled, m.beta_grant = True, 5000
    content.mall = {i.id: i for i in (
        MallItem(id="pills_5", name="回體丹五顆", price=100, kind="consumable", effects={"pills": 5}, limit={"day": 2}),
        MallItem(id="card_1", name="一日卡", price=10, kind="card", effects={"card_days": 1}),
    )}
    return content


def _game(content, name="沈浪", login="ray1", phone=None, account=True) -> Game:
    game = Game.new(content, name, rng=random.Random(0))
    game.sync(T0)
    open_characters().save(game.state)
    if account:
        phone_kit.account(game.world.db, name, login, phone)
    return game


def _rows(game):
    return [(r.reason, r.delta, r.ref) for r in reversed(Wallet(game.world.db).ledger(name_key(game.state.player.name)))]


def _seed(game, n=1000):
    Wallet(game.world.db).post(name_key(game.state.player.name), n, "topup", f"seed:{game.state.player.name}", time=T0)


def test_purchase_blocked_and_view_greyed(on):
    phone_kit.gate(on, on=True)
    game = _game(on)
    _seed(game)
    pills = game.state.player.stamina_pills
    assert mall_actions.purchase(game, "pills_5", "x1").lines == [PHONE_NEEDED]
    assert Wallet(game.world.db).balance(name_key("沈浪")) == 1000 and game.state.player.stamina_pills == pills
    items = mall_actions.view(game)["items"]
    assert items and all((row["can"], row["why"], row["max"]) == (False, PHONE_NEEDED, 0) for row in items)
    phone_kit.bind(game.world.db, "ray1", phone_kit.PHONE_A)
    assert all(row["can"] for row in mall_actions.view(game)["items"])
    assert mall_actions.purchase(game, "pills_5", "x2").bought == "pills_5"


def test_gate_off_view_and_purchase_unchanged(on):
    phone_kit.gate(on, on=False, identity=False)
    a = _game(on, "沈浪", "ray1")
    _seed(a)
    whole_off = (mall_actions.view(a), mall_actions.purchase(a, "pills_5", "x1").lines)
    phone_kit.gate(on, on=False)
    b = _game(on, "楚留香", "ray2")
    _seed(b)
    assert (mall_actions.view(b), mall_actions.purchase(b, "pills_5", "x1").lines) == whole_off
    assert whole_off[1] != [PHONE_NEEDED]


def test_grant_waits_for_phone(on):
    phone_kit.gate(on, on=True)
    game = _game(on)
    game.own_turn_checks()
    assert _rows(game) == []  # 沒綁：這一輪不發
    phone_kit.bind(game.world.db, "ray1", phone_kit.PHONE_A)
    game.own_turn_checks()
    owner = name_key("沈浪")
    assert _rows(game) == [("grant", 5000, mall.grant_ref(owner)), ("grant", 0, mall.grant_phone_ref(phone_kit.PHONE_A))]
    assert mall.grant_phone_ref(phone_kit.PHONE_A) == f"grant:beta:phone:{phone_kit.PHONE_A}"
    game.own_turn_checks()
    assert len(_rows(game)) == 2


def test_one_phone_one_grant_ever(on):
    phone_kit.gate(on, on=True)
    first = _game(on, "沈浪", "ray1", phone_kit.PHONE_A)
    first.own_turn_checks()
    assert [r[1] for r in _rows(first)] == [5000, 0]
    phone_kit.unbind(first.world.db, "ray1")  # 解綁：帳本不動，那支手機照舊占著
    second = _game(on, "楚留香", "ray2", phone_kit.PHONE_A)
    second.own_turn_checks()
    assert _rows(second) == []
    phone_kit.bind(first.world.db, "ray1", phone_kit.PHONE_B)  # 第一個帳號再綁別支：帳號已經發過了，也不再發
    first.own_turn_checks()
    assert [r[1] for r in _rows(first)] == [5000, 0]
    assert not Wallet(first.world.db).has_ref(mall.grant_phone_ref(phone_kit.PHONE_B))


def test_bot_grant_unchanged_with_gate(on):
    """假人沒有帳號也有錢包，閘開著照舊發、不記手機編號（同 test_mall.test_bots_get_the_same_grant）。"""
    phone_kit.gate(on, on=True)
    game = _game(on, "某假人", account=False)
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    game.own_turn_checks()
    assert _rows(game) == [("grant", 5000, mall.grant_ref(name_key("某假人")))]


def test_old_grant_not_clawed_back(on):
    """開閘前發過的（只有 grant:beta:<主人>）：開閘之後不追回、也不補記手機編號；舊帳照讀。"""
    phone_kit.gate(on, on=False)
    game = _game(on)
    game.own_turn_checks()
    before = _rows(game)
    assert before == [("grant", 5000, mall.grant_ref(name_key("沈浪")))]
    phone_kit.gate(on, on=True)
    game.own_turn_checks()
    phone_kit.bind(game.world.db, "ray1", phone_kit.PHONE_A)
    game.own_turn_checks()
    assert _rows(game) == before and Wallet(game.world.db).balance(name_key("沈浪")) == 5000
    assert not Wallet(game.world.db).has_ref(mall.grant_phone_ref(phone_kit.PHONE_A))
