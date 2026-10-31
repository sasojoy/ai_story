"""酒肆搬進功能包（主動搬六包第 10 批）守的幾件事：舊名是包裡同一個模組物件（tianxia.tavern、tianxia.tavern_ask；BANNED_WORDS 照舊
拿得到——走一趟那條線照舊從舊名拿，PM 定不搬進 naming.py）、換掉舊名的屬性包裡看得到（test_tavern 換 tavern.find_chance）、
開關在坐著的時候被關掉照樣出得去、假人的分數照舊、tavern:* 由包接走時標題跟搬之前一樣；審查補的：同一對人 hit_pair_hours 內只雇得了一次。"""
from __future__ import annotations

import importlib
import random
import sys

from conftest import real_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


def _seated() -> Game:
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "葉開", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.location, p.tutorial_step = "wan_city", len(c.tutorial.steps)
    p.stats["silver"] = 500
    game.now = 3600.0
    game.choose("act:tavern")
    return game


def test_the_old_names_are_the_package_modules():
    import tianxia.tavern
    import tianxia.tavern_ask
    from tianxia.features.tavern import ask, rules

    assert tianxia.tavern is rules and tianxia.tavern_ask is ask
    assert sys.modules["tianxia.tavern"] is rules and sys.modules["tianxia.tavern_ask"] is ask
    assert importlib.import_module("tianxia.tavern") is rules
    from tianxia.tavern import BANNED_WORDS

    assert BANNED_WORDS is rules.BANNED_WORDS and BANNED_WORDS == ("假人", "機器人", "外掛")
    assert ask.tavern is rules


def test_patching_the_old_name_reaches_the_package(monkeypatch):
    import tianxia.tavern as old
    from tianxia.features.tavern import actions, rules

    monkeypatch.setattr(old, "find_chance", lambda c, reach: 0.25)
    assert rules.find_chance(None, 0) == 0.25 and actions.tavern_rules.find_chance(None, 0) == 0.25


def test_turning_the_tavern_off_while_seated_still_lets_you_leave(monkeypatch):
    """搬之前 choose 的 tavern 那一支、bot_policy.score 的那一段都不看開關：關掉那一刻（還沒 sync 收店）坐著的人照樣按得到「出酒肆」。"""
    from tianxia import bot_policy
    from tianxia.features.tavern import FEATURE, rules
    from tianxia.state import BotProfile

    game = _seated()
    assert game.state.player.picking_tavern
    monkeypatch.setattr(game.content.config.tavern, "enabled", False)
    assert not rules.on(game.content) and FEATURE.enabled(game)
    back = next(o for o in game.options(odds=False) if o.id == rules.BACK_ID)
    assert bot_policy.score(game, back, BotProfile(personality="普通", seed=1)) == 0.0
    assert game.choose(rules.BACK_ID) == [rules.LEFT]
    assert not game.state.player.picking_tavern and not FEATURE.enabled(game)


def test_the_package_takes_the_tavern_ids_with_the_same_title():
    from tianxia.features.tavern import FEATURE, rules

    game = _seated()
    taken = FEATURE.choose(game, "tavern", "news")
    assert taken is not None and taken.title == rules.title_of(game.state, game.content, "news")
    assert FEATURE.choose(game, "act", "tavern") is None
    assert game._action_title("act", "tavern") == rules.sign(game.state, game.content)


def test_the_same_client_hires_on_the_same_target_once_per_pair_window():
    """同一對人 hit_pair_hours 內只雇得了一次（tavern_hit_problem 的 HIT_PAIR）：上一張結了也一樣、被拒不收錢，錯開 hit_pair_hours
    才雇得了。搬之前沒有測試守這一條（酒肆第 10 批審查補的）。"""
    from test_tavern import _content, _feud

    from tianxia.features.tavern import rules

    c = _content()
    me, _ = _feud(open_world(), c)
    me.choose("act:tavern")
    me.tavern_do("seek", "李尋歡")
    me.tavern_do("hit", "李尋歡", "0")
    hit = me.state.world.tavern_hits[-1]
    hit.done, hit.outcome, hit.refunded = True, "平手", True  # 上一張結了：對方身上沒有活的單，擋的不是 HIT_TAKEN
    purse = me.state.player.stats["silver"]
    assert me.tavern_do("hit", "李尋歡", "0") == [rules.HIT_PAIR.format(name="李尋歡")]
    assert me.state.player.stats["silver"] == purse and len(me.state.world.tavern_hits) == 1
    hit.placed_real -= c.config.tavern.hit_pair_hours * 3600 + 10
    assert me._tavern_hit_problem("李尋歡", 0)[0] is None
