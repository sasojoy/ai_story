"""地盤每一週的快照（輿圖升級設計第九節）：territory.update 每次重算把「這一週」那一格蓋成此刻的樣子。"""
from __future__ import annotations

import random

from conftest import classic_rules, real_content, third_party_gentry
from tianxia import calendar, territory
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import TerritoryState


def _world(classic=False):
    c = third_party_gentry(real_content("weekend"))  # 快照記割據：豪強是第三方的規則（豪強分屬兩軍見 test_gentry_allied.py）
    c.config.auto_open_first_season = True
    if classic:
        classic_rules(c)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    return game.state.world, c


def test_each_recompute_writes_this_weeks_snapshot():
    w, c = _world()
    territory.update(w, c)
    snap = w.territory.weeks[1]
    assert snap.control == w.territory.control
    assert set(snap.fronts) == set(c.scenario.territory.lines) and snap.geju is not None


def test_a_later_week_keeps_the_earlier_ones():
    w, c = _world()
    territory.update(w, c)
    w.time = calendar.week_start(3, c, w) + 60
    w.trends["yingru"] = 90  # 潁川汝南推到黃巾那頭：官軍大營也歸黃巾
    territory.update(w, c)
    assert w.territory.weeks[1].control["guan_camp"] == "guan"
    assert w.territory.weeks[3].control["guan_camp"] == "huang" and w.territory.weeks[3].fronts["yingru"] == 90
    assert territory.week_at(w, 2) is w.territory.weeks[1]  # 沒記到的週照前一週補
    assert territory.week_at(w, 3) is w.territory.weeks[3]


def test_assigning_a_place_updates_the_snapshot():
    w, c = _world()
    territory.update(w, c)
    territory.assign(w, c, {"runan_wilds": "guan"})
    assert w.territory.weeks[1].control["runan_wilds"] == "guan"


def test_no_territory_no_snapshot():
    w, c = _world(classic=True)
    territory.update(w, c)
    assert w.territory is None and territory.week_at(w, 1) is None


def test_an_old_territory_loads_without_weeks():
    t = TerritoryState.model_validate({"control": {"changshe": "guan"}})
    assert t.weeks == {}
    w, c = _world()
    w.territory = t
    assert territory.week_at(w, 5) is None
