"""真實地圖（content/）的結構：五個大區、每區有環、跨區的路、路程目標、地點不擠。
見 docs/superpowers/specs/2026-10-03-地圖擴充與移動-design.md 第四、五節。"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from tianxia.atlas import leg_minutes, region_of, shortest_routes
from tianxia.content import load_content
from tianxia.state import new_game_state

CONTENT_DIR = Path(__file__).parent.parent / "content"

REGIONS = {
    "youzhou": {"zhuo_county", "market_town", "loushang_village", "zhuo_militia_hall", "juma_river", "yanshan_foot"},
    "jizhou": {"julu_altar", "guangzong", "luzhi_camp", "xiaquyang", "haozu_fort", "baima_ford"},
    "luoyang": {"luoyang_road", "baima_temple", "luoyang_palace", "dajiangjun_fu", "beimang_hill", "mengjin_ford"},
    "yingru": {
        "yingchuan", "yingshui", "yingchuan_wilds", "changshe", "yingchuan_academy", "songshan_foot", "deep_mountain",
        "jade_cave", "runan", "runan_academy", "runan_market", "runan_wilds", "hilltop_wilds", "qiao_county",
        "cao_manor", "huangjin_camp",
    },
    "nanyang": {"wan_city", "nanyang_road", "nanyang_huangjin_camp", "yu_river", "xinye", "nanyang_wilds"},
}
NEW_LOCATIONS = {
    "loushang_village", "zhuo_militia_hall", "juma_river", "yanshan_foot",
    "julu_altar", "guangzong", "luzhi_camp", "xiaquyang", "haozu_fort", "baima_ford",
    "luoyang_palace", "dajiangjun_fu", "beimang_hill", "mengjin_ford",
    "nanyang_huangjin_camp", "yu_river", "xinye", "nanyang_wilds",
}
CROSS_ROADS = {  # 設計第五節：跨大區的路 → （路的種類, 步行分鐘）
    frozenset({"zhuo_county", "julu_altar"}): ("官道", 12),
    frozenset({"juma_river", "xiaquyang"}): ("山路", 16),
    frozenset({"baima_ford", "changshe"}): ("官道", 15),
    frozenset({"haozu_fort", "mengjin_ford"}): ("路", 12),
    frozenset({"luoyang_road", "yingchuan"}): ("官道", 8),
    frozenset({"hilltop_wilds", "nanyang_road"}): ("官道", 10),
    frozenset({"luoyang_palace", "nanyang_wilds"}): ("山路", 14),
}


@pytest.fixture(scope="module")
def content():
    return load_content(CONTENT_DIR)


def _region(loc_id: str) -> str:
    return next(r for r, members in REGIONS.items() if loc_id in members)


def _roads(content) -> dict[frozenset, str]:
    """每條路一次：{frozenset({a, b}): 路的種類}。connections 的每一項都是 Connection（str 的子類別，字串本身是目的地），路的種類讀 .road。"""
    roads = {}
    for loc in content.locations.values():
        for c in loc.connections:
            roads[frozenset({loc.id, str(c)})] = getattr(c, "road", "路")
    return roads


def _minutes(content, pair: frozenset, road: str) -> float:
    """一條路的步行分鐘，直接用遊戲自己的算法（atlas.leg_minutes），公式改了測試會跟著走。road 參數留給呼叫端對照，實際種類讀內容。"""
    a, b = sorted(pair)
    return leg_minutes(content, a, b)


def _connected(nodes: set[str], roads) -> bool:
    start = next(iter(nodes))
    seen, stack = {start}, [start]
    while stack:
        here = stack.pop()
        for pair in roads:
            if here in pair:
                (other,) = pair - {here}
                if other in nodes and other not in seen:
                    seen.add(other)
                    stack.append(other)
    return seen == nodes


def _shortest(content, src: str, dst: str) -> float:
    """從 src 走到 dst 最短要幾分鐘：用遊戲自己的最短路程（atlas.shortest_routes，所有地點都開放）。new_game_state 不建全服狀態。"""
    state = new_game_state(content, "測試")
    state.player.location = src
    return shortest_routes(state, content, set(content.locations))[dst].minutes


def test_the_map_has_forty_locations_in_five_regions(content):
    assert set(content.locations) == set().union(*REGIONS.values())
    assert NEW_LOCATIONS <= set(content.locations)
    assert {r.id for r in content.map.regions} == set(REGIONS)
    for loc_id in content.locations:
        assert region_of(content, loc_id).id == _region(loc_id), loc_id


def test_every_region_is_connected_and_has_a_loop(content):
    roads = _roads(content)
    for region, members in REGIONS.items():
        inside = {pair: road for pair, road in roads.items() if pair <= members}
        assert _connected(members, inside), region
        assert len(inside) >= len(members), f"{region} 沒有環"  # 連通的圖，邊數 ≥ 點數才有環


def test_cross_region_roads_are_exactly_the_planned_ones(content):
    cross = {pair: road for pair, road in _roads(content).items() if len({_region(i) for i in pair}) == 2}
    assert cross == {pair: road for pair, (road, _) in CROSS_ROADS.items()}


def test_cutting_any_cross_region_road_keeps_the_map_connected(content):
    roads = _roads(content)
    for pair in CROSS_ROADS:
        rest = {p: r for p, r in roads.items() if p != pair}
        assert _connected(set(content.locations), rest), sorted(pair)


def test_cross_region_roads_take_the_planned_minutes(content):
    for pair, (road, minutes) in CROSS_ROADS.items():
        assert minutes * 0.8 <= _minutes(content, pair, road) <= minutes * 1.2, sorted(pair)


def test_hops_inside_a_region_take_two_to_four_minutes(content):
    for pair, road in _roads(content).items():
        if pair in CROSS_ROADS:
            continue
        assert 1.6 <= _minutes(content, pair, road) <= 4.8, sorted(pair)


def test_the_longest_trips(content):
    assert 24 <= _shortest(content, "guangzong", "wan_city") <= 42  # 設計：約 30～35 分鐘，±20%
    assert 36 <= _shortest(content, "zhuo_county", "wan_city") <= 54  # 設計：約 45 分鐘，±20%


def test_locations_keep_room_for_their_labels(content):
    locs = list(content.locations.values())
    for i, a in enumerate(locs):
        for b in locs[i + 1:]:
            assert math.dist((a.x, a.y), (b.x, b.y)) >= 60, (a.id, b.id)


def test_new_locations_have_a_description_and_tags(content):
    for loc_id in NEW_LOCATIONS:
        loc = content.locations[loc_id]
        assert len(loc.description) >= 20 and loc.tags, loc_id
