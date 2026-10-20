"""真實地圖（content/）的結構：九州（大區）、每區有環、跨區的路、路程目標、地點不擠。
見 docs/superpowers/specs/2026-10-03-地圖擴充與移動-design.md 第四、五節（路程目標：同州一站 2～4 分鐘）；
輿圖重製第 1 批（新天下，docs/superpowers/specs/2026-10-20-輿圖簡化-design.md 第三章）把五個大區換成三圈九州：
外圈出生州（洛陽、南陽、冀州〔含幽州〕、青州）、內圈中原四郡（潁川、東郡、陳留、汝南）、核心。跨州的路照新天下重排（外環路、輻路、
內環路），分鐘數是新天下量的、待 PM 對。"""
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
    # 外圈・出生州
    "luoyang": {"luoyang_road", "baima_temple", "luoyang_palace", "dajiangjun_fu", "beimang_hill", "mengjin_ford"},
    "nanyang": {"wan_city", "nanyang_road", "yu_river", "xinye", "nanyang_wilds", "lulin_zhai"},  # 綠林山寨：名聲 5.1
    "jizhou": {  # 幽州併進冀州最外側（設計 3.1）
        "zhuo_county", "market_town", "loushang_village", "zhuo_militia_hall", "juma_river", "yanshan_foot",
        "julu_altar", "guangzong", "xiaquyang", "haozu_fort",
    },
    "qingzhou": {"jishui", "linzi", "donglai_ford", "qingzhou_camp", "taishan_foot"},  # 新的五處（佔位，待 joy）
    # 內圈・中原
    "yingchuan": {
        "yingchuan", "yingshui", "yingchuan_wilds", "changshe", "yingchuan_academy", "songshan_foot", "hilltop_wilds",
        "huangjin_camp", "guan_camp",  # 官軍大營：FB-184 在四十處之外補的官軍操練點
    },
    "dongjun": {"baima_ford", "luzhi_camp", "puyang"},  # 盧植營搬進來當前哨舊址；濮陽是新的
    "chenliu": {"guandu", "chenliu_city", "jiwu"},  # 新的三處
    "runan": {"runan", "runan_academy", "runan_market", "runan_wilds", "qiao_county", "cao_manor", "nanyang_huangjin_camp"},
    # 核心
    "core": {"deep_mountain", "jade_cave", "lutai"},  # 鹿台是新的
}
REMAKE_LOCATIONS = {  # 輿圖重製第 1 批新加的十處（佔位，待 joy）
    "puyang", "guandu", "chenliu_city", "jiwu", "lutai", "qingzhou_camp", "linzi", "jishui", "donglai_ford", "taishan_foot",
}
NEW_LOCATIONS = {
    "loushang_village", "zhuo_militia_hall", "juma_river", "yanshan_foot",
    "julu_altar", "guangzong", "luzhi_camp", "xiaquyang", "haozu_fort", "baima_ford",
    "luoyang_palace", "dajiangjun_fu", "beimang_hill", "mengjin_ford",
    "nanyang_huangjin_camp", "yu_river", "xinye", "nanyang_wilds",
}
CROSS_ROADS = {  # 跨州的路 → （路的種類, 步行分鐘）：新天下量的（輿圖重製第 1 批，待 PM 對）
    # 外環路（出生州相連，企劃者「也要讓出生區直接相連」）
    frozenset({"haozu_fort", "mengjin_ford"}): ("路", 11),
    frozenset({"guangzong", "jishui"}): ("官道", 14),
    frozenset({"nanyang_road", "taishan_foot"}): ("官道", 14),
    frozenset({"luoyang_palace", "nanyang_wilds"}): ("山路", 16),
    # 輻路：出生州 → 內圈
    frozenset({"luoyang_road", "yingchuan"}): ("官道", 5),
    frozenset({"guan_camp", "luoyang_road"}): ("路", 3),
    frozenset({"baima_ford", "mengjin_ford"}): ("官道", 7),
    frozenset({"hilltop_wilds", "nanyang_road"}): ("官道", 6),
    frozenset({"nanyang_huangjin_camp", "nanyang_road"}): ("路", 5),
    frozenset({"nanyang_huangjin_camp", "wan_city"}): ("路", 10),
    frozenset({"baima_ford", "julu_altar"}): ("官道", 7),
    frozenset({"baima_ford", "guangzong"}): ("官道", 10),
    frozenset({"guangzong", "luzhi_camp"}): ("路", 11),
    frozenset({"guandu", "guangzong"}): ("官道", 9),
    frozenset({"jishui", "jiwu"}): ("路", 6),
    frozenset({"qiao_county", "taishan_foot"}): ("官道", 6),
    # 內環路（中原四郡相連）
    frozenset({"baima_ford", "changshe"}): ("官道", 6),
    frozenset({"guandu", "luzhi_camp"}): ("官道", 7),
    frozenset({"jiwu", "qiao_county"}): ("官道", 6),
    frozenset({"changshe", "runan_wilds"}): ("官道", 11),
    frozenset({"hilltop_wilds", "runan_wilds"}): ("路", 8),
    # 內圈 → 核心（每郡一條）
    frozenset({"deep_mountain", "songshan_foot"}): ("山路", 5),
    frozenset({"lutai", "puyang"}): ("山路", 13),
    frozenset({"chenliu_city", "lutai"}): ("山路", 7),
    frozenset({"lutai", "runan"}): ("山路", 13),
}


@pytest.fixture(scope="module")
def content():
    return load_content(CONTENT_DIR)


def _detail(content, state, loc_id: str) -> str:
    from tianxia.atlas import detail_text

    return detail_text(state, content, loc_id, lambda squad_id: "穩勝")


def test_the_map_detail_of_a_scouted_wild_place_lists_the_insight_exploring_teaches(content, monkeypatch):
    """W3，真實內容：潁川郊野寫的是風——摸清了詳情欄就寫「這裡能悟：風」，沒摸清的地點什麼也不露。"""
    from tianxia import insights

    monkeypatch.setattr(content.config, "open_map", False)  # 沒摸清是全圖開放之前的規則（同 closed_map；內容是整個模組共用的）
    state = new_game_state(content, "甲")
    state.player.location = "yingchuan"
    assert "yingchuan_wilds" not in state.player.visited
    far = _detail(content, state, "zhuo_county")  # 隔了好幾個大區、視野之外的涿郡
    assert far == "### ？\n\n尚未摸清" or "這裡能悟" not in far
    state.player.visited.add("yingchuan_wilds")
    near = _detail(content, state, "yingchuan_wilds")
    assert "**意境**　這裡能悟：風\n" in near
    for loc_id in ("changshe", "nanyang_wilds", "deep_mountain"):  # 兩個以上的，頓號隔開、順序照內容
        state.player.visited.add(loc_id)
        names = [content.insights[i].name for i in insights.explore_gives(content.locations[loc_id], content)]
        assert len(names) >= 2 and f"這裡能悟：{'、'.join(names)}" in _detail(content, state, loc_id)


def test_every_scouted_real_place_lists_exactly_what_exploring_there_can_teach(content):
    from tianxia import insights
    from tianxia.atlas import is_known

    state = new_game_state(content, "甲")
    listed = 0
    for loc in content.locations.values():
        if loc.prologue_only:
            continue
        state.player.visited.add(loc.id)
        text = _detail(content, state, loc.id)
        if not is_known(state, content, loc.id):  # 還沒開放的地點（南華觀等）：去過也不算摸清，什麼都不露
            assert "這裡能悟" not in text, loc.id
            continue
        names = [content.insights[i].name for i in insights.explore_gives(loc, content)]
        assert (f"這裡能悟：{'、'.join(names)}" in text) if names else ("這裡能悟" not in text), loc.id
        listed += bool(names)
    assert listed >= 30  # 正式內容的地點幾乎都有得悟：不是「全都沒寫」的空轉


def _region(loc_id: str) -> str:
    return next(r for r, members in REGIONS.items() if loc_id in members)


def _places(content):
    """大地圖上的地點：序章的草廬（Location.prologue_only）只有序章裡的人看得到，不算在四十處裡、也不在大區的規劃裡。"""
    return [loc for loc in content.locations.values() if not loc.prologue_only]


def _roads(content) -> dict[frozenset, str]:
    """每條路一次：{frozenset({a, b}): 路的種類}。connections 的每一項都是 Connection（str 的子類別，字串本身是目的地），路的種類讀 .road。"""
    roads = {}
    for loc in _places(content):
        for c in loc.connections:
            if content.locations[str(c)].prologue_only:
                continue
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


def test_the_map_has_its_locations_in_nine_regions(content):
    places = {loc.id for loc in _places(content)}
    assert places == set().union(*REGIONS.values())
    assert NEW_LOCATIONS <= places and REMAKE_LOCATIONS <= places
    assert {r.id for r in content.map.regions} == set(REGIONS)
    for loc_id in places:
        assert region_of(content, loc_id).id == _region(loc_id), loc_id


def test_the_mentors_hut_is_a_short_walk_from_yingchuan(content):
    """序章的草廬：只連潁川、步行兩三分鐘，落在潁川那一區；平常的地點清單裡沒有它。"""
    (hut,) = [loc for loc in content.locations.values() if loc.prologue_only]
    assert hut.id == content.tutorial.location == "mentor_hut"
    assert [str(c) for c in hut.connections] == ["yingchuan"] and "mentor_hut" in content.locations["yingchuan"].connections
    assert 2.0 <= leg_minutes(content, "mentor_hut", "yingchuan") <= 3.5
    assert region_of(content, "mentor_hut").id == "yingchuan"


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
        assert _connected({loc.id for loc in _places(content)}, rest), sorted(pair)


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
    assert 36 <= _shortest(content, "zhuo_county", "wan_city") <= 54  # 設計：約 45 分鐘，±20%（新天下約 40）


def test_locations_keep_room_for_their_labels(content):
    locs = list(content.locations.values())
    for i, a in enumerate(locs):
        for b in locs[i + 1:]:
            assert math.dist((a.x, a.y), (b.x, b.y)) >= 60, (a.id, b.id)


def test_new_locations_have_a_description_and_tags(content):
    for loc_id in NEW_LOCATIONS | REMAKE_LOCATIONS:
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


FIGURE_PLACES = {  # 設計 7.3、第一季設計 8.1；輿圖重製 1b（設計 3.1）：兩軍的人物開季站自家外圈，皇甫嵩、朱儁在洛陽官道、盧植在孟津渡、張曼成與趙弘在泰山腳；1c：波才在鉅鹿道壇
    "zhangjiao": "guangzong", "zhangbao": "xiaquyang", "zhangliang": "guangzong", "luzhi": "mengjin_ford",
    "dongzhuo": "mengjin_ford", "hejin": "dajiangjun_fu", "yuanshao": "dajiangjun_fu",
    "huangfusong": "luoyang_road", "zhujun": "luoyang_road", "caocao": "qiao_county", "sunjian": "wan_city",
    "liubei": "zhuo_county", "guanyu": "zhuo_county", "zhangfei": "zhuo_county", "taoqian": "runan_market",
    "bocai": "julu_altar", "zhangmancheng": "taishan_foot", "zhaohong": "taishan_foot",  # 人物誌 §6
}
JOIN_POINTS = {  # 設計 7.2、第一季設計 5.1；輿圖重製第 1 批：官軍、黃巾的投靠點只在外圈出生州，兩州各一處（企劃者）
    "guan": {"dajiangjun_fu", "wan_city"},
    "huang": {"julu_altar", "qingzhou_camp"},
    "haoqiang": {"zhuo_militia_hall", "cao_manor", "haozu_fort"},
}


def test_figures_stand_where_the_design_puts_them(content):
    assert {cid: content.characters[cid].talk_at for cid in FIGURE_PLACES} == FIGURE_PLACES


def test_each_faction_joins_where_the_design_puts_it(content):
    assert {f.id: set(f.join_at) for f in content.scenario.factions} == JOIN_POINTS


def test_meeting_yuanshao_happens_where_he_now_stands(content):
    assert content.events["meet_yuanshao"].locations == ["dajiangjun_fu"]


APPROVED_TAG_MATCHED_EVENTS = {  # 新地點靠 tags 撞上沒寫 locations 的舊事件，一律要先在這裡核准
    "beggar", "herb", "tavern_brawl", "teahouse", "train_insight", "train_onlooker", "waterfall", "wolves",
    "yingchuan_rule",
    # 遊歷打完接的通用戰後事件（content/events/train_aftermath.json）：寫的是過招前後的江湖見聞，哪裡都說得通
    "train_bettors", "train_campfire", "train_dropped_letter", "train_fallen_foe", "train_old_boxer",
    "train_runaway_cart", "train_sore_loser",
    # 散人的遊俠名號奇遇（content/events/ranger.json）：寇那一則寫的是野外林子裡的綠林拜帖，哪一處野外都說得通
    "ranger_kou_invitation",
    # 名聲 5.2 俠的交友事件（content/events/renown.json）：鄉民送糧、有人報信，寫的是城鎮裡的街坊，哪一座城鎮都說得通
    "xia_grain", "xia_tipoff",
}


def test_old_tag_matched_events_on_the_new_places_are_approved(content):
    """事件靠 tags 找地點（沒 tags 也沒 locations 就到處都有），地點只要 id 在 locations 裡也算數，兩者是「或」。
    地圖重排時新地點的 tags 可能撞上舊事件（例如 山林 的玉璽挖寶、水路／渡口 的封鎖），那些劇情是為特定地方寫的。
    能被任何行動（探索／遊歷／交友）抽到、而且不是靠 locations 點名到新地點的事件，集合必須剛好等於核准名單
    （只加 locations 沒拿掉 tags 的事件仍會靠 tags 撞進來，這裡一樣抓得到）。"""
    for places in (NEW_LOCATIONS, REMAKE_LOCATIONS):  # 輿圖重製第 1 批新加的十處也一樣（撞上的都在核准名單裡）
        matched = {
            e.id
            for e in content.events.values()
            if e.actions
            and any(
                loc_id not in e.locations and event_matches_location(e, content.locations[loc_id])
                for loc_id in places
            )
        }
        assert matched <= APPROVED_TAG_MATCHED_EVENTS, sorted(matched - APPROVED_TAG_MATCHED_EVENTS)
        assert places is REMAKE_LOCATIONS or matched == APPROVED_TAG_MATCHED_EVENTS


def test_rivers_widen_downstream_and_the_yellow_river_is_yellow(content):
    """輿圖美術設計第四節：河流寫成物件，從上游寫到下游；只有黃河是土黃色。"""
    rivers = {river.name: river for river in content.map.rivers}
    assert list(rivers) == ["黃河", "潁水", "淯水", "拒馬河", "濟水"]  # 濟水：輿圖重製第 1 批，青州那一條
    assert {name for name, river in rivers.items() if river.color == "yellow"} == {"黃河"}
    assert all(river.width[0] < river.width[1] for river in rivers.values())


def test_terrain_follows_eastern_han_geography(content):
    """輿圖美術設計第四節的擺法，輿圖重製第 1 批照新天下重擺（第 2 批重畫天下圖時再定）：六條有名字的山（燕山、太行山、呂梁山、
    伏牛山、桐柏山，加青州的泰山）、一段沒名字的（嵩山南段）、六片林地，指北針在左上角的空白，紙色底。"""
    m = content.map
    named = [t.name for t in m.terrain if t.name]
    assert named == ["燕山", "太行山", "呂梁山", "伏牛山", "桐柏山", "泰山"]
    assert [t.kind for t in m.terrain].count("forest") == 6
    assert len(m.terrain) == 13
    assert m.compass == (50, 50) and m.background == "#E9E2CC"
