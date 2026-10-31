"""輿圖升級的底圖（設計第二、九節）：只有紙、大區、山河、路、大區名，不畫地點與字；官道雙線、州界點劃線、絹紋與四角壓暗。"""
from __future__ import annotations

import random
import re

import pytest

from conftest import real_content
from tianxia import mapart, mapview
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


def _game(profile="week7"):
    c = real_content(profile)
    c.config.auto_open_first_season = True
    return Game.new(c, "沈浪", rng=random.Random(0), world=open_world())


def test_the_base_has_paper_regions_and_roads_but_no_places():
    game = _game()
    s, c = game.state, game.content
    svg = mapview.render_base(s, c)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert f'id="{mapart.SILK_ID}"' in svg and f"url(#{mapart.VIGNETTE_ID})" in svg
    assert all(f'data-region="{r.id}"' in svg for r in c.map.regions)
    assert mapart.BORDER_DASH in svg
    assert svg.count('class="tx-region-name"') == len(c.map.regions)  # 看大局時網頁照這個 class 藏起來
    assert "data-loc" not in svg and "潁川郊野" not in svg  # 地點與名字是網頁照疊層畫的


@pytest.mark.smoke
def test_official_roads_are_double_lines():
    game = _game()
    s, c = game.state, game.content
    shown = set(mapview.open_places(s, c))
    official = sum(1 for a_id, a in c.locations.items() for b_id in a.connections
                   if a_id < b_id and {a_id, b_id} <= shown and a.road_to(b_id) == "官道")
    svg = mapview.render_base(s, c)
    assert official and svg.count(f'stroke="{mapart.ROAD_CORE}"') == official


def test_a_locked_place_and_its_roads_appear_once_opened():
    game = _game(None)  # 14 天的季：南華觀要等 xi_open（第一季開季就開，season_one_off.unlocks）
    s, c = game.state, game.content
    assert "jade_cave" not in mapview.open_places(s, c)
    before = len(re.findall(r'<path d="M[^"]*Q', mapview.render_base(s, c)))
    s.world.flags.add("xi_open")
    assert "jade_cave" in mapview.open_places(s, c)
    after = len(re.findall(r'<path d="M[^"]*Q', mapview.render_base(s, c)))
    assert after > before


def test_every_place_kind_has_a_glyph():
    c = _game().content
    assert {mapart.icon_kind(loc) for loc in c.locations.values()} <= set(mapview.GLYPHS)


def test_minimap_places_can_be_tapped():
    """江湖頁的小地圖點到一個地點：打開輿圖、選好它（設計第八節）。網頁照 data-loc 認是哪一處。"""
    game = _game()
    game.state.player.location = "yingchuan"
    svg = mapview.render_minimap(game.state, game.content)
    assert 'data-loc="yingchuan"' in svg and 'data-loc="yingchuan_wilds"' in svg
