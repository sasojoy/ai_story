"""商城的引擎那一側（商城架構設計第四節）：封測發放、月卡加回體丹上限、購買與發貨、限購與上架、月卡的日子、管理者工具。
測試內容的商城關著（Config.mall），這裡自己打開、自己放商品。時間：現實秒，台灣 00:00 換日（同回體丹，Game._pill_day）。"""
from __future__ import annotations

import random

import pytest
from conftest import next_season

from tianxia import mall, roster
from tianxia.characters import name_key
from tianxia.engine import Game
from tianxia.models import MallItem
from tianxia.state import BotProfile
from tianxia.wallet import Wallet

HOUR = 3600
DAY = 24 * HOUR
MIDNIGHT_TW = DAY - 8 * HOUR  # 1970-01-02 00:00（台灣）
T0 = MIDNIGHT_TW + 20000 * DAY + 9 * HOUR  # 某一天台灣早上九點
DAY0 = int((T0 + 8 * HOUR) // DAY)


def _items() -> dict[str, MallItem]:
    return {i.id: i for i in (
        MallItem(id="pills_5", name="回體丹五顆", price=100, kind="consumable", effects={"pills": 5}, limit={"day": 2}),
        MallItem(id="pills_30", name="回體丹三十顆", price=500, kind="consumable", effects={"pills": 30}, limit={"season": 1}),
        MallItem(id="card_30", name="月卡", price=600, kind="card", effects={"card_days": 30}, limit={"account": 2}),
        MallItem(id="card_1", name="一日卡", price=10, kind="card", effects={"card_days": 1}),
    )}


@pytest.fixture
def on(content):
    m = content.config.mall
    m.enabled, m.beta_grant = True, 5000
    content.mall = _items()
    content.config.stamina_pills_per_day = 2
    content.config.newbie_pills_per_day = 5
    content.config.admins = ["管理者"]
    return content


def _game(content, name="沈浪", now=T0) -> Game:
    game = Game.new(content, name, rng=random.Random(0))
    game.sync(now)
    return game


def _wallet(game) -> Wallet:
    return Wallet(game.world.db)


def _rows(game) -> list:
    return _wallet(game).ledger(name_key(game.state.player.name))


def _titles(game) -> list[str]:
    return [e.title for e in game.state.journal]


# ── 封測發放 ─────────────────────────────────────


def test_off_means_no_grant_and_no_rows(content):
    content.config.mall.beta_grant = 5000  # 開關關著，數字寫了也不發
    game = _game(content)
    game.mark_seen(T0)
    with game.world.db.snapshot() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mall_ledger").fetchone()[0] == 0
    assert "商城" not in _titles(game)


def test_first_own_turn_grants_once(on):
    game = _game(on)
    game.mark_seen(T0)
    game.mark_seen(T0 + 60)
    rows = _rows(game)
    assert [(r.reason, r.delta, r.ref) for r in rows] == [("grant", 5000, "grant:beta:沈浪")]
    assert _titles(game).count("商城") == 1
    assert _wallet(game).balance("沈浪") == 5000


def test_zero_grant_writes_nothing(on):
    on.config.mall.beta_grant = 0
    game = _game(on)
    game.mark_seen(T0)
    assert _rows(game) == [] and "商城" not in _titles(game)


def test_grant_is_not_repeated_next_season(on):
    game = _game(on)
    game.mark_seen(T0)
    next_season(on, game.world, game)
    game.mark_seen(T0 + DAY)
    assert len(_rows(game)) == 1


def test_bots_get_the_same_grant(on):
    """假人沒有帳號也有錢包（錢包照角色名號），假人程式自己那一輪（own_turn_checks）照樣發：看不出誰是假人。"""
    game = _game(on, "某假人")
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    game.own_turn_checks()
    assert [(r.reason, r.delta) for r in _rows(game)] == [("grant", 5000)]


# ── 月卡加上限 ───────────────────────────────────


def _card(game, start, end):
    _wallet(game).set_card(name_key(game.state.player.name), mall.CARD_KEY, start, end)


def test_card_adds_one_to_the_daily_cap(on, monkeypatch):
    game = _game(on)
    monkeypatch.setattr(roster, "newbie", lambda state, content, days=None: False)
    assert game.pill_cap() == 2
    _card(game, DAY0, DAY0 + 30)
    assert game.pill_cap() == 3 and game.pills_left_today() == 3
    monkeypatch.setattr(roster, "newbie", lambda state, content, days=None: True)
    assert game.pill_cap() == 6  # 新手期 5 → 6


def test_no_cap_stays_no_cap(on):
    on.config.stamina_pills_per_day = 0  # 不限就是不限
    game = _game(on)
    _card(game, DAY0, DAY0 + 30)
    assert game.pill_cap() == 0 and game.pills_left_today() is None


def test_card_bonus_is_ignored_when_the_mall_is_off(on):
    game = _game(on)
    _card(game, DAY0, DAY0 + 30)
    on.config.mall.enabled = False
    assert game.pill_cap() in (2, 5)  # 照原本的（新手期與否），不加
