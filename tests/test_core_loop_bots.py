"""假人與整季機器人照出陣、探索三選一走（出陣探索與地盤設計第七節）。正式內容、週末設定。
這一份先放出陣那一半（PM 2026-10-14：Task 4 另外平行做，探索三顆的部分等它合進來再補）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import bot_policy
from tianxia.engine import Game, Option
from tianxia.sqlite_world import open_world
from tianxia.state import BotProfile, Order
import server


def _game(faction=None, at="yingshui"):
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    return game


def _profile(game):
    return BotProfile(personality="普通", seed=1, faction=game.state.player.faction, season_number=1)


def _score(game, option_id):
    return bot_policy.score(game, Option(id=option_id, label=""), _profile(game))


def test_server_bots_hold_their_camp_for_the_defend_order_and_the_gentry_stir():
    huang = _game("huang", "huangjin_camp")
    huang.state.world.orders = []  # 開季自動發的軍令先拿掉，只看這一道守城
    plain = _score(huang, "act:train")
    huang.state.world.orders.append(Order(id="1:huang:defend:yingru", template="defend", faction="huang", week=1,
                                          front="yingru", quota=99, text=""))
    assert _score(huang, "act:train") == pytest.approx(plain + bot_policy.ORDER_SCORE)
    gentry = _game("haoqiang", "runan_wilds")
    assert _score(gentry, "act:train") == bot_policy.STIR_SCORE


def test_the_gentry_does_not_stir_a_line_sitting_at_the_middle():
    gentry = _game("haoqiang", "runan_wilds")
    gentry.state.world.trends["yingru"] = 50
    assert _score(gentry, "act:train") is None


def test_a_used_up_sortie_stops_pulling_bots_to_the_front():
    """出陣用完了：那個戰線地點對假人不再有大勢分（往那裡走不加 TRAIN_MOVE_SCORE），改去探索練功（設計第七節）。"""
    game = _game("guan", "yingchuan_wilds")
    profile = _profile(game)
    assert bot_policy._train_value(game, profile, "huangjin_camp") > 0
    game.state.player.sortie_day, game.state.player.sorties_today = game._pill_day(), 5
    assert bot_policy._train_value(game, profile, "huangjin_camp") == 0


def test_the_page_knows_whether_sorties_are_on():
    assert server.main_view(_game())["sortie"] is True
