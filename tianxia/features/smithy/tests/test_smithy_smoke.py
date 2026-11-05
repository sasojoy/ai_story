"""鐵匠鋪包的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：測試內容的城鎮、兵器防具都開著，走進鐵匠鋪（act:smith 的 Verb）、
買一把（choose 的 smith: 掛鉤、鐵匠順口那一擲）、切到防具頁，再看一遍 /api/smith_line 經包的 routes 掛在殼上、假人的分數（bot_pick）與紀錄標題。"""
import random

import pytest

from tianxia import rules
from tianxia.core import features as features_core
from tianxia.core.registry import FEATURES
from tianxia.engine import Game


def _game(content, world, name="鐵匠煙霧"):
    content.config.weapons.enabled = content.config.armor.enabled = True
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, "sword")
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.stats["wis"] = "town", 100.0, 300, 5
    p.member.wugong_id = "sword"
    p.materials = {"gang_1": 4, "gang_2": 1, "kuai_1": 2}
    game.sync(0.0)
    return game


@pytest.mark.smoke
def test_a_wanderer_enters_the_smithy_buys_a_blade_and_the_package_owns_the_hooks(content, world):
    feature = next(f for f in FEATURES if f.name == "smithy")
    game = _game(content, world)
    assert feature.prefix == "smith" and feature.enabled(game) is True
    assert feature.player_fields == ("picking_smith", "smith_page", "smith_draft", "smith_rule", "smith_rules_told")
    assert [v.verb for v in feature.verbs()] == ["smith"] and feature.shops() == ()
    # act:smith：入口在「此地還能做」（核心原位），按下去由包的 Verb 開店，紀錄標題「鐵匠鋪・此地」
    assert "act:smith" in [o.id for o in game.options()]
    assert game._action_title("act", "smith").startswith("鐵匠鋪・")
    assert "鐵匠鋪" in game.choose("act:smith")[0]
    p = game.state.player
    assert p.picking_smith is True
    # smith:buy：choose 的掛鉤接走，標題與動作照原本
    owner = features_core.owner_of("smith:buy:劍")
    assert owner is feature
    buy = next(o.id for o in game.options() if o.id.startswith("smith:buy:") and o.enabled)
    silver_before = p.stats["silver"]
    game.choose(buy)
    assert p.stats["silver"] < silver_before and game.state.journal[0].title == "鐵匠鋪"
    # 切頁（只換一頁，不寫紀錄）與離開
    count = len(game.state.journal)
    game.choose("smith:page:armor")
    assert p.smith_page == "armor" and len(game.state.journal) == count
    game.choose("smith:back")
    assert p.picking_smith is False


@pytest.mark.smoke
def test_the_forge_line_route_is_mounted_by_the_package_and_the_bot_scores_the_leave_button(content, world):
    import server

    feature = next(f for f in FEATURES if f.name == "smithy")
    paths = {r.path for router in features_core.routers(server) for r in router.routes}
    assert "/api/smith_line" in paths
    assert feature.routes(server).routes[0].path == "/api/smith_line"
    game = _game(content, world, "鐵匠假人")
    game.choose("act:smith")
    options = {o.id: o for o in game.options()}
    from tianxia.features.smithy import bots

    want = bots.want(game)  # 假人此刻最該按的那一顆（換、買、修，或打造的下一步）拿 SMITH_SCORE；離開 0.0；其餘不按
    assert want in options and feature.bot_pick(game, options[want]) == bots.SMITH_SCORE
    assert feature.bot_pick(game, options["smith:back"]) == 0.0
    assert feature.bot_pick(game, options["smith:page:armor"]) is None
