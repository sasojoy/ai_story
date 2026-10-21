"""輿圖第三版第 3 批：天下圖的資料（輿圖簡化設計 5.1、3.3、5.6；環形版 dev/map-2 的畫法搬回真實地形）。顏色、沒人佔的顏色從劇本讀；
地面照「離哪個地點最近」分，每一個大區只拿自己的地點分（tianxia/worldgeo.py）；疊層多 rich（高級資源地）。正式內容。"""
from __future__ import annotations

import random

import pytest
from conftest import classic_rules, real_content
from conquest_kit import conquest_game
from pydantic import ValidationError

from tianxia import atlas, content as content_mod, conquest, mapdata, worldgeo
from tianxia.engine import Game
from tianxia.models import FactionInk
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.slow  # 每一條都載正式內容、建一局

INKS = {  # 跟網頁原本寫死的那一張表一樣（MAP_SIDES）：搬進劇本之後畫面一個字不變
    "guan": ("#3D5F8F", "#9DB4D3", "#DCE5F0", "官", "官軍"),
    "huang": ("#B9821A", "#E7C778", "#F4E7C2", "巾", "黃巾"),
    "haoqiang": ("#4E7D59", "#A5C6A6", "#DFEBDD", "豪", "豪強"),
}


def _game(profile="weekend", faction="guan", at="yingchuan", content=None):
    c = content or real_content(profile)
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    game.state.player.faction, game.state.player.location = faction, at
    return game


def test_the_scenario_carries_side_colours_and_unheld():
    c = real_content("weekend")
    for f in c.scenario.factions:
        ink = f.ink
        assert ink is not None, f.id
        assert (ink.color, ink.soft, ink.tint, ink.short, ink.label) == INKS[f.id]
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
    """地面照區塊分（不是區塊的鄉里結社、曹氏莊院這類不分，不然大區裡挖出一個灰洞）；官軍大營在潁川汝南的輪廓外一點，照樣是
    那一區的一格（網頁照那一區的輪廓裁）。"""
    game = _game()
    world, c = game.map_base()["world"], game.content
    blocks = conquest.blocks(c)
    ids = {cell["id"] for cell in world["cells"]}
    assert ids == {x for x in _shown(game) if x in blocks}
    assert "zhuo_militia_hall" not in ids and "cao_manor" not in ids and "guan_camp" in ids
    for cell in world["cells"]:
        assert cell["region"] == atlas.region_of(c, cell["id"]).id and cell["d"].startswith("M") and cell["d"].endswith("Z")
    assert [r["id"] for r in world["regions"]] == [r.id for r in c.map.regions]


def test_real_regions_do_not_touch_so_every_edge_is_inside_a_region():
    """真實地形的五個大區互不相接（環形版九州貼齊）：沒有跨大區的邊，每一條邊都是同一區裡兩格之間、帶那一區的 id（網頁照它的輪廓裁）。"""
    game = _game()
    world = game.map_base()["world"]
    region = {cell["id"]: cell["region"] for cell in world["cells"]}
    assert world["edges"] and all(e["clip"] is not None for e in world["edges"])
    assert all(region[e["a"]] == region[e["b"]] == e["clip"] for e in world["edges"])
    assert all(e["d"].startswith("M") and not e["d"].endswith("Z") for e in world["edges"])
    assert {e["clip"] for e in world["edges"]} == {r.id for r in game.content.map.regions}  # 五個大區都不只一格


def test_world_frame_holds_every_open_place():
    game = _game()
    x, y, w, h = game.map_base()["world"]["frame"]
    c = game.content
    assert 0 <= x and 0 <= y and x + w <= c.map.width and y + h <= c.map.height
    for loc_id in _shown(game):
        loc = c.locations[loc_id]
        assert x < loc.x < x + w and y < loc.y < y + h, loc_id


def test_world_labels_sit_inside_their_region():
    game = _game()
    world, c = game.map_base()["world"], game.content
    polys = {r.id: [tuple(p) for p in r.points] for r in c.map.regions}
    x, y, w, h = world["frame"]
    for r in world["regions"]:
        assert 1 <= len(r["spots"]) <= 4, r["id"]
        for lx, ly in r["spots"]:
            assert worldgeo.inside(lx, ly, polys[r["id"]]), r["id"]
            assert x <= lx <= x + w and y <= ly <= y + h
        assert r["area"] == round(worldgeo.area(polys[r["id"]]))
        assert "ring" not in r  # 三圈作廢（設計 3.1）


def test_world_sides_come_from_the_scenario_in_its_order():
    world = _game().map_base()["world"]
    assert [s["id"] for s in world["sides"]] == ["guan", "huang", "haoqiang"]
    assert world["sides"][0] == {"id": "guan", "name": "官軍", "short": "官", "color": "#3D5F8F", "soft": "#9DB4D3", "tint": "#DCE5F0"}
    assert world["unheld"] == "#D2CBBC" and "seal" not in world  # 核心的「璽」是環形版的，作廢


def test_a_side_without_ink_gets_a_fallback_colour():
    c = real_content("weekend")
    c.scenario.factions[1].ink = None
    side = next(s for s in _game(content=c).map_base()["world"]["sides"] if s["id"] == "huang")
    assert side["color"] in mapdata.FALLBACK_INKS and side["name"] == "黃巾軍" and side["short"] == "黃"
    assert side["soft"].startswith("#") and side["tint"].startswith("#")


def test_rich_places_are_the_neutral_blocks():
    game = _game()
    st, c = game.map_state(), game.content
    rich = {x for x, p in st["places"].items() if p["rich"]}
    assert rich == {x for x, b in conquest.blocks(c).items() if b.kind == "neutral" and x in st["places"]}
    assert rich and "changshe" not in rich


def test_old_tug_of_war_leaves_most_ground_unheld():
    """設計 5.6：地面一律讀 territory.controller。正式內容的季是舊拔河（領地爭奪關著）：只有大本營、拔河地點、廣宗有控制方，
    其餘沒人佔（灰）；不照開季歸屬上色（企劃者挑的）。地盤關著：整張沒人佔。"""
    st = _game().map_state()
    assert st["places"]["changshe"]["control"] == "guan" and st["places"]["julu_altar"]["control"] == "huang"
    assert st["places"]["luoyang_road"]["control"] is None and st["places"]["runan"]["control"] is None
    off = _game(content=classic_rules(real_content("weekend")))
    assert all(p["control"] is None for p in off.map_state()["places"].values())
    assert off.map_base()["world"]["cells"]  # 格子照畫（灰）


def test_conquest_paints_every_block():
    """領地爭奪開著：陣營區塊開季就是自家的地面、中立地沒人佔。"""
    game = conquest_game("weekend")
    st, world, c = game.map_state(), game.map_base()["world"], game.content
    for cell in world["cells"]:
        kind = conquest.blocks(c)[cell["id"]].kind
        assert st["places"][cell["id"]]["control"] == (None if kind == conquest.NEUTRAL else kind), cell["id"]


def test_ropes_say_which_side_sits_at_each_end():
    st = _game().map_state()
    assert [(r["low"], r["high"]) for r in st["ropes"]] == [("guan", "huang")] * len(st["ropes"])
    assert st["geju_side"] == "haoqiang"


def test_world_geometry_is_cached_by_content():
    game = _game()
    assert game.map_base()["world"]["cells"] is _game().map_base()["world"]["cells"]  # 同一份內容（另一局）不再算一次


FLIP_KEYS = {"tug", "melee", "cool"}


def flipping(game):
    """造兩塊正在翻、一塊激戰、一塊剛易手（領地爭奪開著的一局）：汝南荒野（兩邊開季都碰得到的中立地）官軍推 60、黃巾推 25；
    潁川郊野（官軍的）黃巾推 30；荒丘官軍推滿（易手給官軍、冷卻）；汝南（黃巾的）官軍、黃巾這一刻各出陣過一次（激戰）。"""
    w, c = game.state.world, game.content
    conquest.push(w, c, "runan_wilds", "guan", "甲", 60, "attack")
    conquest.push(w, c, "runan_wilds", "huang", "乙", 25, "attack")
    conquest.push(w, c, "yingchuan_wilds", "huang", "丙", 30, "attack")
    conquest.push(w, c, "hilltop_wilds", "guan", "丁", 100, "attack")
    conquest.mark(w, c, "runan", "戊", "guan", "attack", 5)
    conquest.mark(w, c, "runan", "己", "huang", "hold", 5)
    return game


def test_flip_marks_are_the_conquest_card_under_the_map_names():
    """收尾（計畫 1.3、收尾）：天下圖的 tug／melee／cool 不另寫判斷，照翻地那一份畫面資料（conquest.block_view，main_view 的
    conquest.blocks）換名字——tug＝bars 寫出來不是 0 的、melee＝clash、cool＝cooling（沒在冷卻是 None）。每一塊都一樣。"""
    game = flipping(conquest_game("weekend"))
    st, blocks = game.map_state(), game.conquest_view()["blocks"]
    shown = [x for x in blocks if x in st["places"]]
    assert shown
    for loc_id in shown:
        p, row = st["places"][loc_id], blocks[loc_id]
        assert p["tug"] == ({b["side"]: b["value"] for b in row["bars"] if b["value"] > 0} or None), loc_id
        assert p["melee"] is row["clash"] and p["cool"] == (row["cooling"] or None), loc_id
    places = st["places"]
    assert places["runan_wilds"]["tug"] == {"guan": 60, "huang": 25} and places["yingchuan_wilds"]["tug"] == {"huang": 30}
    assert places["hilltop_wilds"]["control"] == "guan" and places["hilltop_wilds"]["tug"] is None
    assert places["hilltop_wilds"]["cool"] == conquest.cooling_minutes(game.state.world, game.content, "hilltop_wilds") >= 1
    assert [x for x in shown if places[x]["melee"]] == ["runan"]
    assert [x for x in shown if places[x]["cool"]] == ["hilltop_wilds"]
    assert not FLIP_KEYS & set(places["cao_manor"])  # 不是區塊的地點沒有這三個鍵


def test_flip_marks_cool_off_when_the_cooldown_ends():
    game = flipping(conquest_game("weekend"))
    w, c = game.state.world, game.content
    w.time += conquest.cooling_left(w, c, "hilltop_wilds") + 1
    assert game.map_state()["places"]["hilltop_wilds"]["cool"] is None


@pytest.mark.parametrize("profile", ["weekend", None, "season21"])
def test_no_flip_marks_when_conquest_is_off(profile):
    """領地爭奪關著的季（週末、14 天、21 天）：疊層沒有 tug／melee／cool 這三個鍵（網頁就不畫；疊層跟 90e52e9b 一樣）。"""
    game = _game(profile=profile)
    assert not conquest.on(game.content, game.state.world)
    assert not any(FLIP_KEYS & set(p) for p in game.map_state()["places"].values())


def test_a_scenario_without_blocks_seeds_every_open_place():
    """劇本沒寫區塊表：開放的地點全部分地面（序章專屬的不算）。"""
    c = real_content("weekend")
    c.scenario.territory.blocks = {}
    game = _game(content=c)
    ids = {cell["id"] for cell in game.map_base()["world"]["cells"]}
    assert ids == {x for x in _shown(game) if not c.locations[x].prologue_only}
    assert "cao_manor" in ids and not any(p["rich"] for p in game.map_state()["places"].values())
