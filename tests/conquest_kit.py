"""領地爭奪（第 38 項改版）測試共用的建法（計畫的 Global Constraints：不改 tests/conftest.py，共用的放這裡）。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import territory
from tianxia.engine import Game
from tianxia.models import Content
from tianxia.sqlite_world import open_world


def conquest_rules(content: Content) -> Content:
    """打開領地爭奪（Config.conquest.enabled），回傳同一份內容。"""
    content.config.conquest.enabled = True
    return content


def _new(content: Content, name: str) -> Game:
    content.config.auto_open_first_season = True
    game = Game.new(content, name, rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, content)  # 開季那一下：第一次算，不發天下大事
    return game


def conquest_game(profile: str = "season21", name: str = "沈浪") -> Game:
    """正式內容、開季時就打開領地爭奪的一局（同 test_territory._game 的建法）。"""
    return _new(conquest_rules(real_content(profile)), name)


def plain_game(profile: str = "weekend", name: str = "沈浪") -> Game:
    """同上，領地爭奪關著（正式內容的預設）。"""
    return _new(real_content(profile), name)
