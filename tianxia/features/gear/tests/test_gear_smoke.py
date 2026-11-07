"""裝備包的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：測試內容四欄全開、小鎮補上「馬市」標籤，走進馬市（act:market 的 Verb）、
買一匹（choose 的 market: 掛鉤）、離開；再看包的宣告（前綴、認領的欄位、內容檔）、假人的分數（bot_pick）與修練頁換上、餵馬、拆解經 Game 的委派走到包。"""
import random

import pytest

from tianxia import mounts
from tianxia.core import features as features_core
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.features.gear import bots as gear_bots


def _game(content, world, name="裝備煙霧"):
    for rule in (content.config.weapons, content.config.armor, content.config.mounts, content.config.treasures):
        rule.enabled = True
    if mounts.MARKET_TAG not in content.locations["town"].tags:
        content.locations["town"].tags.append(mounts.MARKET_TAG)
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"] = "town", 100.0, 300
    return game


@pytest.mark.smoke
def test_a_wanderer_enters_the_market_buys_a_horse_and_the_package_owns_the_hooks(content, world):
    feature = next(f for f in FEATURES if f.name == "gear")
    game = _game(content, world)
    assert feature.prefix == "market" and feature.enabled(game) is True
    assert feature.player_fields == ("picking_market",) and feature.content == ("gear.json",)
    assert [v.verb for v in feature.verbs()] == ["market"] and feature.shops() == ()
    # act:market：入口在「此地還能做」（核心原位），按下去由包的 Verb 開店，紀錄標題「馬市・此地」
    assert "act:market" in [o.id for o in game.options()]
    assert game._action_title("act", "market").startswith(f"{mounts.MARKET}・")
    assert game.choose("act:market")[0] == mounts.ENTERED
    p = game.state.player
    assert p.picking_market is True
    # market:buy：choose 的掛鉤接走，標題與動作照原本
    assert features_core.owner_of(mounts.BUY) is feature
    silver_before = p.stats["silver"]
    game.choose(mounts.BUY)
    assert p.stats["silver"] < silver_before and p.mount is not None and game.state.journal[0].title == mounts.MARKET
    # 離開
    game.choose(mounts.BACK)
    assert p.picking_market is False


@pytest.mark.smoke
def test_the_bot_scores_the_leave_button_and_the_bench_actions_reach_the_package(content, world):
    feature = next(f for f in FEATURES if f.name == "gear")
    game = _game(content, world)
    game.choose("act:market")
    options = {o.id: o for o in game.options(odds=False)}
    assert feature.bot_pick(game, options[mounts.BACK]) == 0.0 and gear_bots.MARKET_SCORE == 8.0
    game.choose(mounts.BUY)
    # 修練頁（Game 的委派 → 包）：餵（吃飽了）、換上不存在的、拆不存在的、批量拆解空串列
    assert game.feed_mount()
    assert game.wield_weapon("騎:99")
    assert game.dismantle_weapon("兵:99")
    assert game.dismantle_many([])
    assert game.gear_rows()["slots"] and game.divine_book_view() == []
