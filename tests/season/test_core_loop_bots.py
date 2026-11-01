"""假人與整季機器人照出陣、探索三選一走（出陣探索與地盤設計第七節）。正式內容、週末設定。
這一份先放出陣那一半（PM 2026-10-14：Task 4 另外平行做，探索三顆的部分等它合進來再補）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from jianfa_kit import classic_explore
from tianxia import bot, bot_policy
from tianxia.engine import Game, Option
from tianxia.sqlite_world import open_world
from tianxia.state import BotProfile, Order
import server


def _game(faction=None, at="yingshui"):
    c = real_content("week7")  # 地盤拔河、出陣推線的舊規則（領地爭奪 PM 2026-10-22 起正式內容打開）
    classic_explore(c)  # 探索三選一的入口與三顆（減法季探索一顆開著時只剩一顆，tests/test_explore_one.py）
    c.config.auto_open_first_season = True
    c.config.precise_actions = False  # 一類一顆之前的三選一（新規則的假人分數在 tests/test_precise_actions.py，設計 8.4）
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    return game


def _profile(game):
    return BotProfile(personality="普通", seed=1, faction=game.state.player.faction, season_number=1)


def _score(game, option_id):
    return bot_policy.score(game, Option(id=option_id, label=""), _profile(game))


def test_the_season_bot_never_presses_the_bare_explore():
    game = _game()
    options = [o for o in game.options(odds=False) if o.enabled]
    picks = {bot.pick(game, options, random.Random(seed)) for seed in range(40)}
    assert "act:explore" not in picks and any(p.startswith("explore:") for p in picks)


@pytest.mark.smoke
def test_explore_choice_prefers_gathering():
    assert bot.explore_choice({"act:explore", "explore:gather", "explore:seek"}) == "explore:gather"
    assert bot.explore_choice({"act:explore"}) == "act:explore"
    assert bot.explore_choice({"move:yingchuan"}) is None


def test_server_bots_score_the_three_ways_and_skip_the_bare_explore():
    game = _game()
    assert _score(game, "act:explore") is None
    assert _score(game, "explore:gather") >= bot_policy.GATHER_SCORE > _score(game, "explore:seek") > _score(game, "explore:sense") > 0


def test_server_bots_count_a_scout_bounty_for_all_three_ways():
    from tianxia.state import Bounty

    game = _game()
    plain = {m: _score(game, f"explore:{m}") for m in ("gather", "seek", "sense")}
    game.state.world.bounties.append(Bounty(id="b1", kind="scout", faction="guan", week=1, expires=1e12, silver=20, deeds=1,
                                            location="yingshui", takers=["沈浪"]))
    assert all(_score(game, f"explore:{m}") == pytest.approx(plain[m] + bot_policy.BOUNTY_SCORE) for m in plain)


def test_server_bots_gather_more_when_short_of_materials():
    game = _game()
    game.state.player.materials = {}
    short = _score(game, "explore:gather")
    first = next(m for m in game.content.materials.values() if m.tier == 1)
    game.state.player.materials = {first.id: bot_policy.NEED_MATERIAL_BELOW}
    assert short == pytest.approx(_score(game, "explore:gather") + bot_policy.NEED_MATERIAL_SCORE)


def test_the_gentry_does_not_stir_a_line_sitting_at_the_middle():
    gentry = _game("haoqiang", "runan_wilds")
    gentry.state.world.trends["yingru"] = 50
    assert _score(gentry, "act:train") is None


def test_the_page_knows_whether_sorties_are_on():
    assert server.main_view(_game())["sortie"] is True


@pytest.mark.slow
def test_a_season_bot_plays_the_new_loop_on_the_real_content():
    game = bot.play_season(real_content(), seed=1, max_steps=600, world=open_world())
    titles = [e.title for e in game.state.journal]
    assert any(t.startswith(("找素材", "找事件", "靜心感悟")) for t in titles)
