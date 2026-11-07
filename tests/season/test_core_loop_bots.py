"""假人與整季機器人照出陣走（出陣探索與地盤設計第七節；探索三選一第 13 批拿掉）。正式內容。"""
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
    classic_explore(c)  # 舊探索（減法季探索一顆之前）
    c.config.auto_open_first_season = True
    c.config.precise_actions = False  # 一類一顆之前
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    return game


def _profile(game):
    return BotProfile(personality="普通", seed=1, faction=game.state.player.faction, season_number=1)


def _score(game, option_id):
    return bot_policy.score(game, Option(id=option_id, label=""), _profile(game))


@pytest.mark.smoke
def test_explore_choice_is_the_explore_button():
    assert bot.explore_choice({"act:explore"}) == "act:explore"
    assert bot.explore_choice({"move:yingchuan"}) is None


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
    assert any(t.startswith("探索") for t in titles)
