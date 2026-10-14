"""輿圖升級的網頁（設計第一～八節）：整頁地圖、地圖上的記號、看大局、濾鏡小牌子、抽屜、天下怎麼變。
在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的底圖與疊層；沒有 node 就略過。"""
from __future__ import annotations

import random
import re

import pytest
import test_prologue_web

import server
import webharness
from conftest import classic_rules, real_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES = ["S", "pageMap", "marksSvg", "regionTint", "controlAt", "hudHtml", "chipsHtml", "drawerHtml"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
NOW = "{ k: 1, far: false, layers: new Set(%s), sel: null, week: H.S.mapState.now_week }"


def _game(faction="guan", at="yingchuan", classic=False):
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    if classic:
        classic_rules(c)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    return game


def run(game, script, **S):
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


def marks(game, layers='["control"]', **o):
    extra = "".join(f", {k}: {v}" for k, v in o.items())
    return run(game, f"return H.marksSvg(H.S.mapBase, H.S.mapState, Object.assign({NOW % layers}, {{{extra[2:]}}}));")


def test_marks_draw_every_open_place_with_its_glyph():
    game = _game()
    out = marks(game)
    assert out.count("data-loc=") == len(game.map_base()["places"])
    assert "潁川郊野" in out and ">城<" in out and "（你）" in out


def test_marks_paint_halos_and_fronts_when_territory_is_on():
    out = marks(_game())
    assert "url(#mk-halo-guan)" in out and 'class="front"' in out


def test_marks_without_territory_have_no_halos_or_fronts():
    out = marks(_game(classic=True))
    assert "url(#mk-halo-" not in out.split("</defs>", 1)[1] and 'class="front"' not in out


def test_the_far_view_shows_regions_and_tallies_without_place_names():
    out = marks(_game(), k=2.5, far="true")
    assert "潁川汝南" in out and re.search(r"官 \d", out) and "潁川郊野" not in out


def test_badges_stack_under_the_name():
    out = marks(_game(), layers='["control", "enemy", "route"]')
    assert "分</text>" in out and any(f">{w}</text>" in out for w in ("穩勝", "有把握", "五五波", "難分勝負", "凶險", "必敗"))


def test_the_map_page_is_a_full_page_layer_with_chips():
    out = run(_game(), "return H.pageMap();")
    assert 'class="mapx' in out and 'id="map"' in out and '<g id="mk">' in out and 'id="mdrawer"' in out
    assert all(word in out for word in ("勢力", "軍令", "敵情", "路程", "劇情", "版圖變化", "找地點"))
    assert "<select" not in out and "travel-row" not in out and "map-legend" not in out


def test_region_tint_follows_the_majority():
    out = run(_game(), "return H.regionTint(H.S.mapBase, H.S.mapState, H.S.mapState.now_week, true);")
    assert out["yingru"] in ("#DCE5F0", "#F4E7C2", "#DFEBDD")
    assert run(_game(), "return H.regionTint(H.S.mapBase, H.S.mapState, H.S.mapState.now_week, false);") == {}
