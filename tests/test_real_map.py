"""真實地圖（content/）的結構：五個大區、每區有環、跨區的路、路程目標、地點不擠。
見 docs/superpowers/specs/2026-10-03-地圖擴充與移動-design.md 第四、五節。"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from tianxia.atlas import leg_minutes, region_of, shortest_routes
from tianxia.content import load_content
from tianxia.events import event_matches_location
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


TOWNS_WITHOUT_ENEMIES = {"loushang_village", "luoyang_palace", "dajiangjun_fu", "xinye"}  # 城鎮、官署照現有城鎮的慣例不放敵人
NEW_SQUADS = {
    "guan_patrol", "jun_bing", "beijun_wuzu", "liangzhou_cavalry", "taiping_lishi",
    "huangjin_sishi", "wubao_buqu", "yiyong", "yan_mazei", "he_shuikou",
}


def test_new_squads_exist(content):
    assert NEW_SQUADS <= set(content.squads)


def test_new_locations_outside_towns_have_a_faction_squad(content):
    """設計 7.1：新地點要有標陣營的遊歷隊伍（「遊歷看陣營」要用）。"""
    for loc_id in NEW_LOCATIONS - TOWNS_WITHOUT_ENEMIES:
        squads = [content.squads[s] for s in content.locations[loc_id].enemies]
        assert any(s.faction for s in squads), loc_id


def test_towns_and_offices_have_no_enemies(content):
    for loc_id in TOWNS_WITHOUT_ENEMIES:
        assert content.locations[loc_id].enemies == [], loc_id


FIGURE_PLACES = {  # 設計 7.3、第一季設計 8.1
    "zhangjiao": "guangzong", "zhangbao": "xiaquyang", "zhangliang": "guangzong", "luzhi": "luzhi_camp",
    "dongzhuo": "mengjin_ford", "hejin": "dajiangjun_fu", "yuanshao": "dajiangjun_fu",
    "huangfusong": "changshe", "zhujun": "changshe", "caocao": "qiao_county", "sunjian": "wan_city",
    "liubei": "zhuo_county", "guanyu": "zhuo_county", "zhangfei": "zhuo_county", "taoqian": "runan_market",
    "bocai": "huangjin_camp", "zhangmancheng": "nanyang_huangjin_camp", "zhaohong": "nanyang_huangjin_camp",  # 人物誌 §6
}
JOIN_POINTS = {  # 設計 7.2、第一季設計 5.1
    "guan": {"changshe", "wan_city", "luzhi_camp"},
    "huang": {"huangjin_camp", "julu_altar", "nanyang_huangjin_camp"},
    "haoqiang": {"zhuo_militia_hall", "cao_manor", "haozu_fort"},
}


def test_figures_stand_where_the_design_puts_them(content):
    assert {cid: content.characters[cid].talk_at for cid in FIGURE_PLACES} == FIGURE_PLACES


def test_each_faction_joins_at_three_places(content):
    assert {f.id: set(f.join_at) for f in content.scenario.factions} == JOIN_POINTS


def test_meeting_yuanshao_happens_where_he_now_stands(content):
    assert content.events["meet_yuanshao"].locations == ["dajiangjun_fu"]


APPROVED_TAG_MATCHED_EVENTS = {  # 新地點靠 tags 撞上沒寫 locations 的舊事件，一律要先在這裡核准
    "beggar", "herb", "tavern_brawl", "teahouse", "train_insight", "train_onlooker", "waterfall", "wolves",
    "yingchuan_rule",
}


def test_old_tag_matched_events_on_the_new_places_are_approved(content):
    """事件靠 tags 找地點（沒 tags 也沒 locations 就到處都有），地點只要 id 在 locations 裡也算數，兩者是「或」。
    地圖重排時新地點的 tags 可能撞上舊事件（例如 山林 的玉璽挖寶、水路／渡口 的封鎖），那些劇情是為特定地方寫的。
    能被任何行動（探索／遊歷／交友）抽到、而且不是靠 locations 點名到新地點的事件，集合必須剛好等於核准名單
    （只加 locations 沒拿掉 tags 的事件仍會靠 tags 撞進來，這裡一樣抓得到）。"""
    matched = {
        e.id
        for e in content.events.values()
        if e.actions
        and any(
            loc_id not in e.locations and event_matches_location(e, content.locations[loc_id])
            for loc_id in NEW_LOCATIONS
        )
    }
    assert matched == APPROVED_TAG_MATCHED_EVENTS


def test_rivers_widen_downstream_and_the_yellow_river_is_yellow(content):
    """輿圖美術設計第四節：河流寫成物件，從上游寫到下游；只有黃河是土黃色。"""
    rivers = {river.name: river for river in content.map.rivers}
    assert list(rivers) == ["黃河", "潁水", "淯水", "拒馬河"]
    assert {name for name, river in rivers.items() if river.color == "yellow"} == {"黃河"}
    assert all(river.width[0] < river.width[1] for river in rivers.values())


def test_terrain_follows_eastern_han_geography(content):
    """輿圖美術設計第四節的初版擺法：七條有名字的山、兩段沒名字的（太行山南端的丘陵、嵩山南段）、四片林地，
    指北針在右側中段的空白，紙色底。"""
    m = content.map
    named = [t.name for t in m.terrain if t.name]
    assert named == ["燕山", "太行山", "呂梁山", "邙山", "嵩山", "伏牛山", "桐柏山"]
    assert [t.kind for t in m.terrain].count("forest") == 4
    assert len(m.terrain) == 13
    assert m.compass == (845, 680) and m.background == "#E9E2CC"
