"""心神（tianxia/core/xinshen.py；設計稿 https://claude.ai/artifact/NbTxoAPdroin7N9cRjCiP3 第 4 版；Joy 2026-11-06「可以 寫」）：
跟人物說話不扣體力、扣心神；免費、月卡、存著的三份分開記，一般交談先扣月卡、再扣免費、最後動存著的，隱線只扣免費；
每位人物每天前幾輪長情誼、之後只聊天，最多 Config.xinshen.turns_per_figure 輪；問酒家另算一天幾次。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from tianxia import companion_agent
from tianxia.characters import name_key
from tianxia.core import xinshen
from tianxia.engine import Game
from tianxia.features.companions import talk_actions
from tianxia.features.mall import actions as mall_actions
from tianxia.features.socialize import view as socialize_view
from tianxia.models import MallItem
from tianxia.wallet import Wallet

HOUR = 3600
DAY = 24 * HOUR
T0 = DAY - 8 * HOUR + 20000 * DAY + 9 * HOUR  # 某一天台灣早上九點（同 test_mall）

WARM = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["請教兵法", "就此告辭"], option_tags=["真誠請教", "尋常寒暄"],
)


@pytest.fixture
def on(content):
    content.config.xinshen.enabled = True
    return content


# ── 純規則 ────────────


def test_the_card_goes_first_then_free_then_the_bank(on, game):
    s, day = game.state, 100
    assert xinshen.purse(s, on, day, True, 7) == xinshen.Purse(free=6, card=4, bank=7)
    assert xinshen.spend(s, on, day, True, 7, 5) == 0  # 月卡 4 ＋ 免費 1
    assert xinshen.purse(s, on, day, True, 7) == xinshen.Purse(free=5, card=0, bank=7)
    assert xinshen.spend(s, on, day, True, 7, 8) == 3  # 免費 5，其餘 3 點從存著的扣（呼叫端寫帳號）
    assert xinshen.purse(s, on, day, True, 4) == xinshen.Purse(free=0, card=0, bank=4)
    assert xinshen.spend(s, on, day, True, 4, 5) is None  # 不夠：什麼都不動
    assert xinshen.purse(s, on, day + 1, True, 4) == xinshen.Purse(free=6, card=4, bank=4)  # 隔天補滿，用不完的不留


def test_free_only_never_touches_the_card_or_the_bank(on, game):
    s, day = game.state, 100
    assert xinshen.spend(s, on, day, True, 50, 6, free_only=True) == 0
    assert xinshen.purse(s, on, day, True, 50) == xinshen.Purse(free=0, card=4, bank=50)
    assert xinshen.spend(s, on, day, True, 50, 1, free_only=True) is None


def test_no_card_means_no_card_share_and_a_new_card_counts_the_same_day(on, game):
    s, day = game.state, 100
    xinshen.spend(s, on, day, False, 0, 2)
    assert xinshen.purse(s, on, day, False, 0) == xinshen.Purse(free=4, card=0, bank=0)
    assert xinshen.purse(s, on, day, True, 0).card == 4  # 買卡那一刻當天就有


def test_tavern_asks_count_per_day_only_when_on(content, game):
    s = game.state
    assert xinshen.asks_left(s, content, 100) is None  # 關著不限
    content.config.xinshen.enabled = True
    for left in (3, 2, 1):
        assert xinshen.asks_left(s, content, 100) == left
        xinshen.note_ask(s, content, 100)
    assert xinshen.asks_left(s, content, 100) == 0
    assert xinshen.asks_left(s, content, 101) == 3


# ── 對話 ────────────


def _talking(on, game):
    on.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=WARM):
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"
    return game


def test_a_talk_turn_spends_xinshen_not_stamina(on, game):
    _talking(on, game)
    labels = {o.id: o.label for o in game.options()}
    assert "心神 1" in labels["talk:0"] and "心神 2" in labels["talk:say"] and "體力" not in labels["talk:0"]
    stamina = game.state.player.stamina
    with mock.patch.object(companion_agent, "_generate", return_value=WARM):
        game.choose("talk:0")
    assert game.state.player.stamina == stamina
    assert game.xinshen_purse().daily == 5
    assert game.status_data()["xinshen"] == {"name": "心神", "now": 5, "cap": 6, "bank": 0}


def test_out_of_xinshen_greys_the_talk_but_not_leaving(on, game):
    _talking(on, game)
    game.state.player.xinshen_free, game.state.player.xinshen_free_day = 0, game._pill_day()
    opts = {o.id: o for o in game.options()}
    assert not opts["talk:0"].enabled and not opts["talk:say"].enabled and opts["talk:leave"].enabled
    assert not opts["talk:short"].enabled and "明早" in opts["talk:short"].label
    assert talk_actions.talk(game, "0") == [xinshen.short_line(on)]


def test_after_the_affinity_turns_the_talk_goes_on_without_affinity(on, game):
    _talking(on, game)
    game.state.player.xinshen_free_day, game.state.player.xinshen_free = game._pill_day(), 99
    cap, full = game._talk_cap(), socialize_view.talk_full_cap(game)
    assert full == on.config.xinshen.turns_per_figure > cap
    with mock.patch.object(companion_agent, "_generate", return_value=WARM):
        for _ in range(cap):
            game.choose("talk:0")
        grown = game.state.player.affinities["mate"]
        assert grown > 0
        assert "今天的情誼已到頂" in {o.id: o.label for o in game.options()}["talk:0"]
        for _ in range(full - cap):
            game.choose("talk:0")
    assert game.state.player.affinities["mate"] == grown  # 閒聊的那幾輪情誼不動
    assert game.state.player.pending_companion is None  # 聊滿 8 輪送客
    assert game._talks_used("mate") == full


def test_switch_off_keeps_the_stamina_cost(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=WARM):
        game.choose("act:socialize")
        before = game.state.player.stamina
        game.choose("talk:0")
    assert game.state.player.stamina == before - content.config.talk_stamina
    assert "xinshen" not in game.status_data()


# ── 凝神香（帳號） ────────────


@pytest.fixture
def shop(on):
    on.config.mall.enabled, on.config.mall.beta_grant = True, 5000
    on.mall = {i.id: i for i in (
        MallItem(id="card_30", name="月卡", price=600, kind="card", effects={"card_days": 30}),
        MallItem(id="xinshen_5", name="凝神香", price=30, kind="consumable", effects={"xinshen": 5}, on_sale={"rule": "xinshen"}),
    )}
    on.config.admins = ["管理者"]
    return on


def _buyer(shop) -> Game:
    from tianxia.characters import open_characters

    game = Game.new(shop, "沈浪", rng=random.Random(0))
    game.sync(T0)
    open_characters().save(game.state)
    game.mark_seen(T0)
    return game


def test_incense_is_stored_on_the_account_and_spent_last(shop):
    game = _buyer(shop)
    mall_actions.buy(game, "xinshen_5", "x1")
    assert game.xinshen_purse() == xinshen.Purse(free=6, card=0, bank=5)
    assert game.xinshen_spend(8)
    assert game.xinshen_purse() == xinshen.Purse(free=0, card=0, bank=3)
    assert Wallet(game.world.db).purchases(name_key("沈浪"))[0].data[xinshen.SPENT] == 2
    assert not game.xinshen_spend(1, free_only=True)  # 隱線不能用買的
    game.now = T0 + DAY
    assert game.xinshen_purse() == xinshen.Purse(free=6, card=0, bank=3)  # 隔天：免費補滿，存著的還在


def test_the_card_adds_four_a_day(shop):
    game = _buyer(shop)
    mall_actions.buy(game, "card_30", "c1")
    assert game.xinshen_purse() == xinshen.Purse(free=6, card=4, bank=0)
    assert game.xinshen_view()["cap"] == 10


def test_incense_is_off_the_shelf_while_the_switch_is_off(shop):
    game = _buyer(shop)
    assert any(row["id"] == "xinshen_5" for row in mall_actions.view(game)["items"])
    shop.config.xinshen.enabled = False
    assert all(row["id"] != "xinshen_5" for row in mall_actions.view(game)["items"])


def test_refund_takes_back_only_what_is_still_stored(shop):
    game = _buyer(shop)
    mall_actions.buy(game, "xinshen_5", "x1")
    game.xinshen_spend(8)  # 免費 6 ＋ 存著的 2
    admin = Game.new(shop, "管理者", rng=random.Random(0))
    admin.sync(T0)
    from tianxia.characters import open_characters

    open_characters().save(admin.state)
    pid = Wallet(game.world.db).purchases(name_key("沈浪"))[0].id
    msgs = mall_actions.admin_refund(admin, "沈浪", pid, "測試退款")
    assert any("收回 3 點" in m for m in msgs) and any("用掉的 2 點不追" in m for m in msgs)
    assert xinshen.bank(Wallet(game.world.db), name_key("沈浪")) == 0
    mall_actions.buy(game, "xinshen_5", "x2")  # 再買：不會被之前用掉的吃掉
    assert xinshen.bank(Wallet(game.world.db), name_key("沈浪")) == 5


def test_the_howto_page_says_talk_spends_xinshen(on, game):
    from tianxia import howto

    text = howto.page(on, game.state.world, recruitable=False)
    assert "扣心神：按選項 1 點、自己說 2 點" in text and "還能聊到第 8 輪" in text


def test_the_real_incense_goes_on_sale_with_the_switch():
    """凝神香直接上架（Joy 2026-11-07「凝神香要直接上架」）：正式內容只看心神的開關，不等日期。"""
    from conftest import real_content

    content = real_content()
    for item_id in ("xinshen_5", "xinshen_30"):
        sale = content.mall[item_id].on_sale
        assert sale.rule == xinshen.EFFECT and sale.start is None and sale.end is None
