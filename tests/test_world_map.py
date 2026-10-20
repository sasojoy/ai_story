"""輿圖重製第 2 批：天下圖的資料（設計 4.1、3.6、4.6）。顏色、圈、沒人佔的顏色從劇本讀；地面照「離哪個地點最近」分，
每一州只拿自己的地點分（tianxia/worldgeo.py）；疊層多 rich（高級資源地）。正式內容。"""
from __future__ import annotations

import random

import pytest
from conftest import classic_rules, real_content
from pydantic import ValidationError

from tianxia import atlas, content as content_mod, conquest, mapdata
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


# ── Task 3：mapdata.base()["world"]、疊層的 rich、繩的兩端 ──
def _shown(game):
    return [p["id"] for p in game.map_base()["places"]]


def test_world_data_has_a_cell_for_every_block():
    game = _game()
    world, c = game.map_base()["world"], game.content
    blocks = conquest.blocks(c)
    assert {cell["id"] for cell in world["cells"]} == {x for x in _shown(game) if x in blocks}  # 不是區塊的（鄉里結社…）不分地面
    assert "zhuo_militia_hall" not in {cell["id"] for cell in world["cells"]}
    for cell in world["cells"]:
        assert cell["region"] == atlas.region_of(c, cell["id"]).id and cell["d"].startswith("M") and cell["d"].endswith("Z")
    assert [r["id"] for r in world["regions"]] == [r.id for r in c.map.regions]
    assert {r["id"]: r["ring"] for r in world["regions"]} == RINGS


def test_world_frame_holds_every_open_place():
    game = _game()
    x, y, w, h = game.map_base()["world"]["frame"]
    c = game.content
    assert 0 <= x and 0 <= y and x + w <= c.map.width and y + h <= c.map.height
    for loc_id in _shown(game):
        loc = c.locations[loc_id]
        assert x < loc.x < x + w and y < loc.y < y + h, loc_id


def test_world_edges_cover_the_luoyang_jizhou_border():
    """外環路上官巾相接的那一道（洛陽↔冀州）：跨州的邊兩邊各是哪一格都寫了；同一州裡的邊帶那一州的 id（網頁照它的輪廓裁）。"""
    game = _game()
    world, c = game.map_base()["world"], game.content
    region = {cell["id"]: cell["region"] for cell in world["cells"]}
    across = [e for e in world["edges"] if e["clip"] is None]
    assert any({region.get(e["a"]), region.get(e["b"])} == {"luoyang", "jizhou"} for e in across)
    inside = [e for e in world["edges"] if e["clip"] is not None]
    assert inside and all(region[e["a"]] == region[e["b"]] == e["clip"] for e in inside)
    assert all(e["d"].startswith("M") and not e["d"].endswith("Z") for e in world["edges"])


def test_world_labels_sit_inside_their_region():
    from tianxia import worldgeo

    game = _game()
    world, c = game.map_base()["world"], game.content
    polys = {r.id: [tuple(p) for p in r.points] for r in c.map.regions}
    x, y, w, h = world["frame"]
    for r in world["regions"]:
        assert 1 <= len(r["spots"]) <= 4, r["id"]
        for lx, ly in r["spots"]:
            assert worldgeo.inside(lx, ly, polys[r["id"]]), r["id"]
            assert x <= lx <= x + w and y <= ly <= y + h
        assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) > 0 for a, b in zip(r["spots"], r["spots"][1:]))


def test_world_sides_come_from_the_scenario_in_its_order():
    world = _game().map_base()["world"]
    assert [s["id"] for s in world["sides"]] == ["guan", "huang", "haoqiang"]
    assert world["sides"][0] == {"id": "guan", "name": "官軍", "short": "官", "color": "#3D5F8F", "soft": "#9DB4D3", "tint": "#DCE5F0"}
    assert world["unheld"] == "#D2CBBC"


def test_a_side_without_ink_gets_a_fallback_colour():
    c = real_content("weekend")
    c.scenario.factions[1].ink = None
    side = next(s for s in _game(content=c).map_base()["world"]["sides"] if s["id"] == "huang")
    assert side["color"] in mapdata.FALLBACK_INKS and side["name"] == "黃巾軍" and side["short"] == "黃"


def test_rich_places_are_the_neutral_blocks():
    game = _game()
    st, c = game.map_state(), game.content
    rich = {x for x, p in st["places"].items() if p["rich"]}
    assert rich == {x for x, b in conquest.blocks(c).items() if b.kind == "neutral" and x in st["places"]}
    assert all(atlas.region_of(c, x).ring != "outer" for x in rich) and len(rich) >= 20


def test_old_tug_of_war_leaves_the_outer_ring_mostly_unheld():
    """設計 4.6：地面一律讀 territory.controller。現在正式內容的季是舊拔河（領地爭奪關著）：外圈只有大本營有控制方。"""
    st = _game().map_state()
    assert st["places"]["dajiangjun_fu"]["control"] == "guan" and st["places"]["luoyang_road"]["control"] is None
    off = _game(classic=True).map_state()  # 地盤關著：整張沒人佔
    assert all(p["control"] is None for p in off["places"].values())
    assert {cell["id"] for cell in _game(classic=True).map_base()["world"]["cells"]}  # 格子照畫（灰）


def test_conquest_paints_the_whole_outer_ring():
    from conquest_kit import conquest_game

    game = conquest_game("weekend")
    st, world = game.map_state(), game.map_base()["world"]
    region = {cell["id"]: cell["region"] for cell in world["cells"]}
    assert {st["places"][x]["control"] for x, r in region.items() if r == "luoyang"} == {"guan"}
    assert {st["places"][x]["control"] for x, r in region.items() if r in ("jizhou", "qingzhou")} == {"huang"}
    assert all(st["places"][x]["control"] is None for x, r in region.items() if r == "core")


def test_the_seal_mark_goes_to_the_core_ring_only_when_shards_are_on():
    assert _game().map_base()["world"]["seal"] == "core"
    c = real_content("weekend")
    c.config.seal.enabled = False
    assert _game(content=c).map_base()["world"]["seal"] is None


def test_ropes_say_which_side_sits_at_each_end():
    rope = _game().map_state()["ropes"][0]
    assert (rope["low"], rope["high"]) == ("guan", "huang")


def test_world_geometry_is_cached_by_content():
    game = _game()
    assert game.map_base()["world"]["cells"] is _game().map_base()["world"]["cells"]  # 同一份內容（另一局）不再算一次
