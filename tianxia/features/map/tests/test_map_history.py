"""地盤每一週的快照（輿圖升級設計第九節）：territory.update 每次重算把「這一週」那一格蓋成此刻的樣子。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import calendar, territory
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import TerritoryState


def _world(profile="week7"):
    c = real_content(profile)
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    return game.state.world, c


def test_no_territory_no_snapshot():
    w, c = _world(profile=None)  # 沒有第一季規則的季：沒有地盤
    territory.update(w, c)
    assert w.territory is None and territory.week_at(w, 1) is None


def test_an_old_territory_loads_without_weeks():
    t = TerritoryState.model_validate({"control": {"changshe": "guan"}})
    assert t.weeks == {}
    w, c = _world()
    w.territory = t
    assert territory.week_at(w, 5) is None
