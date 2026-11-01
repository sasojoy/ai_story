"""素材與經濟計畫 B5：整季機器人與伺服器假人賣多的素材、缺三階時升階、在自家大本營捐有剩的。不為了這些繞路。
正式內容、週末設定（Config.economy 預設開）。"""
from __future__ import annotations

import random

import pytest

from conftest import no_week_unlock, real_content
from tianxia import bot, bot_policy
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

TW_MIDNIGHT = 16 * 3600


def _game(at="yingchuan", faction="guan", bag=None, silver=500, same=None):
    c = no_week_unlock(real_content("week7"))
    c.config.auto_open_first_season = True
    c.config.four_tiers.enabled = False  # 素材四階之前的規則；四階的機器人在 test_four_tiers
    if same is not None:
        c.config.economy.upgrade_same_share = same
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.location, p.faction = at, faction
    p.tutorial_step = len(c.tutorial.steps)
    p.stats["silver"] = silver
    p.materials = dict(bag or {})
    game.now = TW_MIDNIGHT + 3600
    return game


@pytest.mark.smoke
def test_upgrade_toward_tier_two_first_then_sell_the_rest_above_the_keep():
    game = _game(bag={"rou_1": 20})
    assert bot.trade_want(game) == ("upgrade", "柔", 2)  # 二階不到 10、一階比留的多 3 個以上
    game.choose("act:smith")
    bot.trade_at_smith(game)
    p = game.state.player
    tier_two = sum(n for mid, n in p.materials.items() if game.content.materials[mid].tier == 2)
    assert p.materials["rou_1"] == bot.TRADE_KEEP[1] and tier_two == 2  # 升兩次（出什麼收什麼），多的一階賣掉
    assert bot.trade_want(game) is None


def test_whatever_attribute_comes_out_the_bot_keeps_it():
    game = _game(bag={"man_2": 25}, same=0)  # 0：一定落到別的屬性
    game.choose("act:smith")
    bot.trade_at_smith(game)
    p = game.state.player
    assert "man_3" not in p.materials and sum(p.materials.get(m, 0) for m in ("gang_3", "rou_3", "kuai_3")) == 1
    assert bot.trade_want(game) is None  # 慢的三階今天換過了，不再試


@pytest.mark.smoke
def test_ten_tier_twos_make_a_tier_three_once_a_day_and_tier_three_is_never_sold():
    game = _game(bag={"man_2": 25, "gang_3": 3}, same=1)
    game.choose("act:smith")
    bot.trade_at_smith(game)
    p = game.state.player
    assert p.materials["man_3"] == 1 and p.materials["gang_3"] == 3  # 一天一個；三階不賣
    assert p.materials["man_2"] == bot.TRADE_KEEP[2]  # 換完之後多的二階賣掉，留 10 個


def test_short_of_silver_keeps_a_reserve():
    game = _game(bag={"man_2": 12}, silver=60)  # 換三階 50 兩，換完剩不到 30 兩
    assert bot.trade_want(game) is None or bot.trade_want(game)[0] != "upgrade"


def test_the_season_bot_trades_when_it_passes_a_smith_and_leaves():
    game = _game(bag={"rou_1": 30, "kuai_2": 14})
    bot.visit_smith(game)
    p = game.state.player
    assert not p.picking_smith
    assert p.materials.get("rou_1", 0) <= bot.TRADE_KEEP[1] + 2 and p.materials["kuai_2"] <= bot.TRADE_KEEP[2]


def test_donating_spare_at_the_base_and_nowhere_else():
    away = _game(at="yingchuan", bag={"rou_1": 30})
    bot.donate_spare(away)
    assert away.state.player.materials == {"rou_1": 30}
    home = _game(at="changshe", bag={"rou_1": 30, "rou_2": 14, "rou_3": 2})
    bot.donate_spare(home)
    p = home.state.player
    assert p.materials == {"rou_1": 12, "rou_2": 10, "rou_3": 2}  # 一階、二階捐到留的量，三階不捐
    assert home.state.world.armaments["guan"]["柔"] == 18 + 4 * 3


def test_donating_respects_the_daily_cap():
    game = _game(at="changshe", bag={"rou_1": 200})
    bot.donate_spare(game)
    assert game.state.player.materials["rou_1"] == 200 - 100


def test_server_bots_trade_in_the_smith_and_donate_at_home_while_looking_after():
    smith = _game(bag={"rou_1": 30})
    smith.choose("act:smith")
    bot_policy.look_after(smith, random.Random(0))
    assert smith.state.player.materials.get("rou_1", 0) <= bot.TRADE_KEEP[1] + 2
    home = _game(at="changshe", bag={"rou_1": 30})
    bot_policy.look_after(home, random.Random(0))
    assert home.state.player.materials["rou_1"] == bot.TRADE_KEEP[1]


def test_switched_off_bots_leave_the_bag_alone():
    game = _game(at="changshe", bag={"rou_1": 30})
    for key in ("sell", "upgrade", "donate"):
        setattr(game.content.config.economy, key, False)
    assert bot.trade_want(game) is None
    bot.donate_spare(game)
    bot_policy.look_after(game, random.Random(0))
    assert game.state.player.materials == {"rou_1": 30}
