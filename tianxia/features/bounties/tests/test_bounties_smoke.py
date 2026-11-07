"""懸賞榜包的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：測試內容補三個陣營，城裡打開榜（act:bounties）、揭一張（choose 的 bounty: 掛鉤）、放回去、返回，
看一遍包登記的事件、世界層、你這一步、叛投的格與假人的分數（bot_pick）。"""
import random

import pytest

from tianxia.core import bounty_base
from tianxia.core import features as features_core
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.features.bounties import rules
from tianxia.models import FactionDef
from tianxia.state import Bounty


def _game(content, world, name="懸賞煙霧"):
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.state.player.location = "town"
    game.sync(0.0)
    return game


@pytest.mark.smoke
def test_a_wanderer_opens_the_board_takes_a_bill_and_the_package_owns_the_hooks(content, world):
    feature = next(f for f in FEATURES if f.name == "bounties")
    game = _game(content, world)
    assert feature.prefix == "bounty" and feature.enabled(game) is True
    assert feature.player_fields == ("picking_bounty", "bounty_pick", "bounties_done") and feature.carried == ()
    assert [v.verb for v in feature.verbs()] == ["bounties"] and feature.shops() == ()
    # 掛一張打探：入口在「此地還能做」（核心原位），按下去由包的 Verb 開榜，紀錄標題「懸賞榜・此地」
    w = game.state.world
    w.bounties.append(Bounty(id="b1", kind="scout", faction="guan", week=1, expires=w.time + 86400.0, silver=10, deeds=0, quota=3, location="lake"))
    game._save_season()
    assert "act:bounties" in [o.id for o in game.options()]
    assert game._action_title("act", "bounties").startswith(f"{bounty_base.BOARD}・")
    assert "看上面貼了些什麼" in game.choose("act:bounties")[0]
    assert game.state.player.picking_bounty is True
    # bounty:take、drop、back：choose 的掛鉤接走，標題「懸賞榜」
    assert features_core.owner_of("bounty:take:b1") is feature
    assert feature.choose(game, "bounty", "back").title == bounty_base.BOARD
    assert any("揭下了" in m for m in game.choose("bounty:take:b1"))
    assert any("放回了榜上" in m for m in game.choose("bounty:drop:b1"))
    assert game.choose("bounty:back") and game.state.player.picking_bounty is False


def test_the_package_takes_its_slots_and_the_base_is_the_same_object(content, world):
    feature = next(f for f in FEATURES if f.name == "bounties")
    assert [(h.event, h.slot) for h in feature.bus()] == [(e, "bounties") for e in ("win", "outing", "explore", "arrive", "raid_win", "aid")]
    assert [(h.at, h.slot) for h in feature.world()] == [(a, "bounties") for a in ("step", "week", "day", "start")]
    assert [(h.slot, h.ref) for h in feature.steps()] == [("commission", "errand"), ("bounty", "bounty")]
    assert [(h.at, h.slot) for h in feature.defection()] == [("stranded", "bounties")]
    # 別人讀的那一半在核心：包 re-export 同一個物件；舊名是包 rules 的別名
    from tianxia.features.bounties import rules as old
    assert old is rules
    for name in ("title", "how", "issuer", "mine", "hunting", "post_rally", "post_figure", "drop_stranded", "BOARD", "ENEMY"):
        assert getattr(rules, name) is getattr(bounty_base, name), name


def test_a_bot_takes_a_bill_and_leaves_but_keeps_what_it_holds(content, world):
    from tianxia import bot_policy
    from tianxia.core.option import Option

    game = _game(content, world)
    owned, value = features_core.bot_pick(game, Option(id="bounty:take:b1", label="揭下"))
    assert owned and value == bot_policy.BOUNTY_SCORE
    assert features_core.bot_pick(game, Option(id="bounty:back", label="返回")) == (True, 0.0)
    assert features_core.bot_pick(game, Option(id="bounty:drop:b1", label="放棄")) == (True, None)  # 不放棄手上的
