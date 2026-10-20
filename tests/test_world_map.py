"""輿圖重製第 2 批：天下圖的資料（設計 4.1、3.6、4.6）。顏色、圈、沒人佔的顏色從劇本讀；地面照「離哪個地點最近」分，
每一州只拿自己的地點分（tianxia/worldgeo.py）；疊層多 rich（高級資源地）。正式內容。"""
from __future__ import annotations

import random

import pytest
from conftest import classic_rules, real_content
from pydantic import ValidationError

from tianxia import atlas, content as content_mod, conquest, mapdata, territory
from tianxia.engine import Game
from tianxia.models import FactionInk
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.slow  # 每一條都載正式內容、建一局

INKS = {  # 跟網頁原本寫死的那一張表一樣（MAP_SIDES）：搬進劇本之後畫面一個字不變
    "guan": ("#3D5F8F", "#9DB4D3", "#DCE5F0", "官", "官軍"),
    "huang": ("#B9821A", "#E7C778", "#F4E7C2", "巾", "黃巾"),
    "haoqiang": ("#4E7D59", "#A5C6A6", "#DFEBDD", "豪", "豪強"),
}
RINGS = {"luoyang": "outer", "nanyang": "outer", "jizhou": "outer", "qingzhou": "outer",
         "yingchuan": "inner", "dongjun": "inner", "chenliu": "inner", "runan": "inner", "core": "core"}


def _game(profile="weekend", classic=False, faction="guan", at="yingchuan", content=None):
    c = content or real_content(profile)
    c.config.auto_open_first_season = True
    if classic:
        classic_rules(c)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    game.state.player.faction, game.state.player.location = faction, at
    return game


def test_the_scenario_carries_side_colours_rings_and_unheld():
    c = real_content("weekend")
    for f in c.scenario.factions:
        ink = f.ink
        assert ink is not None, f.id
        assert (ink.color, ink.soft, ink.tint, ink.short, ink.label) == INKS[f.id]
    assert {r.id: r.ring for r in c.map.regions} == RINGS
    assert c.map.unheld.startswith("#") and len(c.map.unheld) == 7


def test_two_sides_with_the_same_short_word_are_refused():
    c = real_content("weekend")
    c.scenario.factions[1].ink = FactionInk(color="#123456", short="官")
    with pytest.raises(content_mod.ContentError, match="一個字"):
        content_mod.validate(c)
    with pytest.raises(ValidationError):
        FactionInk(color="blue")
