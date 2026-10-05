import html
import math
import re
from pathlib import Path

import pytest

from tianxia.atlas import location_view, vision_range, visible_locations
from tianxia.content import load_content
from tianxia.mapart import bezier_point, bezier_tail, fmt, icon_kind, icon_svg, mix, road_control, terrain
from tianxia.mapview import (
    LEGEND_ICONS, LEGEND_LAYERS, LEGEND_RING, LEGEND_STATES, LEGEND_STRIKE, MINI_HEIGHT, ROUTE_STROKE, SELECT_STROKE, YOU_SIZE,
    legend_data, render_map, render_minimap, text_box, text_width,
)
from tianxia.models import Connection, Location, MapRiver, Terrain
from tianxia.state import Journey, Rumor, new_game_state


def no_odds(squad_id: str) -> str:
    raise AssertionError(f"不該算勝算：{squad_id}")


def test_vision_range_grows_with_fame(state, content):
    assert vision_range(state, content) == 2
    state.player.stats["fame"] = 10
    assert vision_range(state, content) == 3


def test_visible_locations_skip_locked(state, content):
    assert visible_locations(state, content) == {"town", "lake"}
    state.world.flags.add("cave_open")
    assert visible_locations(state, content) == {"town", "lake", "cave"}


def test_location_views(state, content):
    content.config.vision_base = 0
    visible = visible_locations(state, content)
    assert location_view("town", state, content, visible) == "current"
    assert location_view("lake", state, content, visible) == "dot"
    assert location_view("cave", state, content, visible) == "hidden"
    content.locations["lake"].important = True
    assert location_view("lake", state, content, visible) == "outline"
    state.player.visited.add("lake")
    assert location_view("lake", state, content, visible) == "remembered"
    content.config.vision_base = 1
    assert location_view("lake", state, content, visible_locations(state, content)) == "visible"


def test_render_map(state, content):
    html_out = render_map(state, content)
    # max-width:100% 是手機上那個「地圖超出邊界、卡住看不了」的修法：少了它，這個 div 會被
    # 裡面整張地圖寬的 SVG 撐開、整塊溢出版面，overflow:auto 永遠不會啟動。
    assert html_out.startswith('<div class="tx-world-map" style="overflow:auto;max-width:100%;max-height:75vh">')
    assert html_out.endswith("</svg></div>")
    m = content.map
    assert f'style="width:{m.width}px;height:{m.height}px;max-width:none;font-family:sans-serif"' in html_out
    svg = html_out
    assert "小鎮" in svg and "湖邊" in svg and "測試區" in svg
    assert "寶洞" not in svg  # 尚未解鎖
    content.config.vision_base = 0
    content.locations["lake"].important = True
    assert "湖邊？" in render_map(state, content)


def test_icons_follow_tags_and_the_first_match_wins(content):
    lake = content.locations["lake"]
    for tags, kind in [
        (["城鎮"], "town"), (["官署"], "town"), (["城池", "營寨"], "town"),  # 廣宗：先符合城池，畫城牆
        (["營寨"], "camp"), (["祭壇", "營寨"], "camp"),
        (["寺院"], "roof"), (["書院"], "roof"), (["門派"], "roof"),
        (["渡口"], "ferry"), (["河畔"], "ferry"),
        (["山林"], "peak"), (["洞窟"], "peak"),
        (["野外"], "flag"), (["湖畔"], "flag"), ([], "flag"),
    ]:
        lake.tags = tags
        assert icon_kind(lake) == kind, tags


def test_text_width():
    assert text_width("湖邊", 10) == 20
    assert text_width("ab", 10) == 12
    assert text_width("⚑★✦⚔↘←", 10) == 60  # 地圖記號與箭頭在中文字型裡約一個字寬


def test_render_map_new_look(state, content):
    svg = render_map(state, content, "routes")  # 路線層的大區保持原色
    assert 'fill="#E9E2CC"' in svg  # 紙色底（輿圖美術設計 2.1）
    assert "測試北區" in svg and 'fill="#EFE5CB"' in svg  # 區域
    assert 'stroke="#BA7517"' in svg  # 湖邊危險 2 → 橙色外圈
    assert "湖邊 ⚔" in svg and "★" not in svg
    assert "paint-order:stroke" in svg
    assert 'fill="#B9604A"' in place(svg, "town") and 'fill="#A0522D"' in place(svg, "lake")  # 城鎮畫城牆，湖畔畫小旗


def label_box(svg: str, loc_id: str):
    """大地圖上某個地點名字那一行大約佔的範圍。"""
    m = re.search(
        rf'<text x="([-\d.]+)" y="([-\d.]+)" font-size="(\d+)"[^>]*text-anchor="(\w+)"[^>]*data-loc="{loc_id}"[^>]*>([^<]*)</text>',
        svg,
    )
    return text_box(float(m[1]), float(m[2]), html.unescape(m[5]), int(m[3]), m[4])


def overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def place(svg: str, loc_id: str) -> str:
    """大地圖上一個地點的記號（<g data-loc> 那一組；圖例裡也有全彩的圖示，所以要只看這一組）。"""
    return re.search(rf'<g data-loc="{loc_id}"[^>]*>(.*?)</g>', svg)[1]


def test_labels_step_aside_for_other_places_and_labels(state, content):
    content.locations["lake"].x = 150  # 湖邊緊貼在小鎮右邊：小鎮的名字擺右邊會壓到湖邊的記號
    svg = render_map(state, content, "routes")
    town, lake = label_box(svg, "town"), label_box(svg, "lake")
    assert not overlap(town, lake) and not overlap(town, (136, 86, 164, 114))  # 湖邊的圓盤：半徑 13，外圈 2
    assert town[0] != 100 + 18 + 5  # 不是原本右邊的位置（所在地的紅圈半徑 17，外加線寬）


def test_selected_label_sits_outside_the_selection_ring(state, content):
    svg = render_map(state, content, selected="lake")
    assert label_box(svg, "lake")[0] >= 200 + 13 + 10 + 1.5  # 選定的圓圈：半徑 23、線寬 3


def test_region_names_have_a_halo_so_they_read_on_any_tint(state, content):
    svg = render_map(state, content)
    assert re.search(r'<text [^>]*fill="#C9B98F"[^>]*stroke="#E9E2CC"[^>]*>測試北區</text>', svg)


def test_label_flips_left_near_right_edge(state, content):
    content.locations["lake"].x = 390
    assert 'text-anchor="end"' in render_map(state, content)


def test_legend_sits_at_the_bottom_inside_the_frame(state, content):
    """圖例在左下角、外框裡面那條線之內，不蓋住外框（外框的內線在 10，圖例從 14 開始）。"""
    svg = render_map(state, content)
    assert f'<rect x="14" y="{content.map.height - 14 - 46}"' in svg


def test_view_states_are_full_faded_ghost_and_dot(state, content):
    lake = place(render_map(state, content), "lake")  # 看得見：全彩的小旗，圓盤外圈是危險色
    assert 'fill="#A0522D"' in lake and 'r="13" fill="#F4EFDF" stroke="#BA7517"' in lake
    content.config.vision_base = 0
    state.player.visited.add("lake")  # 去過但看不見：同一個圖示淡一點，圓盤與外圈也淡
    lake = place(render_map(state, content), "lake")
    flag, ring = mix("#A0522D", "#E9E2CC", 0.58), mix("#BA7517", "#E9E2CC", 0.45)
    assert f'fill="{flag}"' in lake and f'r="13" fill="#EDE7D4" stroke="{ring}"' in lake and 'fill="#A0522D"' not in lake
    state.player.visited.discard("lake")
    content.locations["lake"].important = True  # 未知、畫出輪廓：灰色剪影，沒有圓盤
    svg = render_map(state, content)
    assert 'fill="#B6AE99"' in place(svg, "lake") and 'r="13"' not in place(svg, "lake") and "湖邊？" in svg
    content.locations["lake"].important = False  # 淡點：小灰點
    assert '<circle cx="200" cy="100" r="4" fill="#C2BAA4"/>' in render_map(state, content)


def test_current_place_has_a_red_ring_and_a_red_flag_that_names_avoid(state, content):
    svg = render_map(state, content)
    assert '<circle cx="100" cy="100" r="17" fill="none" stroke="#C0392B" stroke-width="2"/>' in svg
    assert '<path d="M111,66 L125,71 L111,76 Z" fill="#C0392B"/>' in svg  # 紅旗插在小鎮右上
    lake = content.locations["lake"]
    lake.x, lake.y = 60, 75  # 湖邊的名字本來擺右邊，正好壓到紅旗
    assert not overlap(label_box(render_map(state, content), "lake"), (109, 65, 126, 91))


def test_legend_shows_the_six_icons_and_how_views_are_drawn(state, content):
    content.map.width = 900  # 夾具的地圖太窄，擺不下整行圖例
    svg = render_map(state, content)
    assert svg.count("scale(0.7)") == 6
    assert all(f">{text}<" in svg for text in ("城鎮", "寺院書院", "營寨", "渡口", "山林", "野外"))
    states = re.search(rf'<text x="(\d+)" y="\d+" font-size="12" fill="#5F5E5A">{LEGEND_STATES}</text>', svg)
    box = re.search(r'<rect x="14" y="\d+" width="([\d.]+)"', svg)
    assert int(states[1]) + text_width(LEGEND_STATES, 12) <= 14 + float(box[1])  # 圖例框裝得下第一行


def test_places_keep_their_tap_circle_first_for_phones(state, content):
    svg = render_map(state, content)  # web/style.css 靠「[data-loc] 底下第一層、fill-opacity="0" 的圓」放大點擊範圍
    assert '<g data-loc="lake" style="cursor:pointer"><circle cx="200" cy="100" r="16" fill="#000000" fill-opacity="0"/>' in svg
    assert svg.count('fill-opacity="0"') == 2  # 只有小鎮、湖邊的點擊圓是透明的：圓盤、紅圈、選定的圓圈都不是


def test_selected_current_place_keeps_its_name_off_the_rings_and_the_flag(state, content):
    svg = render_map(state, content, selected="town")
    assert 'r="23" fill="none" stroke="#2C2C2A"' in svg and 'r="17" fill="none" stroke="#C0392B"' in svg
    town = label_box(svg, "town")
    assert not overlap(town, (75.5, 75.5, 124.5, 124.5)) and not overlap(town, (109, 65, 126, 91))


def test_enemies_layer_tints_remembered_places_too(state, content):
    content.config.vision_base = 0
    state.player.visited.add("lake")  # 去過但看不見
    lake = place(render_map(state, content, "enemies", odds={"thug": "穩勝"}.get), "lake")
    disc, ring = mix("#BA7517", "#F4EFDF", 0.5), mix("#BA7517", "#E9E2CC", 0.45)
    assert f'r="13" fill="{disc}" stroke="{ring}"' in lake  # 圓盤照樣是危險色（這一層要看的就是危險），外圈照去過的淡色


# ── 大地圖的圖層 ─────────────────────────────────────


def test_every_layer_has_its_own_legend(state, content):
    for layer, line in LEGEND_LAYERS.items():
        svg = render_map(state, content, layer, odds={"thug": "穩勝"}.get)
        assert line in svg and "外圈：綠安全／橙危險／紅兇險" in svg and LEGEND_STATES in svg
        assert all(other not in svg for other in LEGEND_LAYERS.values() if other != line)


def test_situation_legend_says_what_a_flagged_leader_is():
    assert "⚑ 龍頭人物（會自己行動的江湖人物）常出沒" in LEGEND_LAYERS["situation"]


def test_situation_layer_tints_regions_and_flags_haunts(state, content):
    svg = render_map(state, content)
    assert 'fill="#E7C6AE"' in svg and 'fill="#EFE5CB"' not in svg  # 北區依寇亂 30 往紅色靠
    assert 'fill="#E2EAF1"' in svg  # 南區的寶藏線還沒浮現：原色
    assert ">寇亂 30<" in svg and "寶藏" not in svg
    assert "⚑ 翻江龍 常出沒" in svg
    state.world.trends["kou"] = 90
    assert 'fill="#D68875"' in render_map(state, content)  # 越凶越紅


def test_enemies_layer_colours_by_danger_and_names_the_worst_foe(state, content):
    svg = render_map(state, content, "enemies", odds={"thug": "穩勝"}.get)
    assert "最險：水寇小隊 穩勝" in svg
    disc = mix("#BA7517", "#F4EFDF", 0.5)  # 湖邊危險 2：圓盤是橙色往圓盤原色淡一半
    assert f'r="13" fill="{disc}" stroke="#BA7517"' in svg and 'r="13" fill="#F4EFDF" stroke="#BA7517"' not in svg
    bare = render_map(state, content, "enemies").replace(LEGEND_LAYERS["enemies"], "")
    assert "最險" not in bare  # 沒給 odds：不寫、也不算


def test_story_layer_marks_goals_and_recent_news(state, content):
    svg = render_map(state, content, "story")
    assert "★ 湖邊 ⚔" in svg and "✦" not in svg.replace(LEGEND_LAYERS["story"], "")
    state.world.rumors.append(Rumor(time=0, text="小鎮出事了。", location="town"))
    assert "✦ 小鎮（你）" in render_map(state, content, "story")


def test_routes_layer_shows_costs_and_the_selected_path(state, content):
    state.world.flags.add("cave_open")
    svg = render_map(state, content, "routes", selected="cave")
    # 路線層標步行分鐘：湖邊 3 分鐘、寶洞 3＋4.5＝7.5 分鐘（四捨五入 8）
    assert ">所在地<" in svg and ">3 分鐘<" in svg and ">8 分鐘<" in svg
    (ax, ay), (bx, by) = road_control(content, "town", "lake"), road_control(content, "lake", "cave")
    path = f"M100,100 Q{fmt(ax)},{fmt(ay)} 200,100 Q{fmt(bx)},{fmt(by)} 300,100"  # 每一段都沿著那條路的曲線
    assert f'<path d="{path}" fill="none" stroke="{ROUTE_STROKE}" stroke-width="5"' in svg
    assert ROUTE_STROKE + '" stroke-width="5"' not in render_map(state, content, "routes", selected="town")


def test_selected_place_is_outlined_and_places_are_clickable(state, content):
    svg = render_map(state, content, selected="lake")
    assert f'r="23" fill="none" stroke="{SELECT_STROKE}" stroke-width="3"' in svg  # 湖邊 13 ＋ 10
    assert svg.count('<g data-loc="town"') == 1 and svg.count('<g data-loc="lake"') == 1
    assert 'data-loc="cave"' not in svg  # 未開放：不畫
    content.config.vision_base = 0
    assert 'data-loc="lake"' not in render_map(state, content)  # 沒名字的淡點點不到
    content.locations["lake"].important = True
    assert '<g data-loc="lake"' in render_map(state, content)  # 畫出「湖邊？」的輪廓可以點


def test_unknown_places_show_only_outline_and_question_mark(state, content):
    content.config.vision_base = 0
    content.locations["lake"].important = True
    state.world.rumors.append(Rumor(time=0, text="湖邊出事了。", location="lake"))
    for layer in LEGEND_LAYERS:
        svg = render_map(state, content, layer, odds=no_odds).replace(LEGEND_LAYERS[layer], "")
        assert "湖邊？" in svg
        assert all(mark not in svg for mark in ("★", "✦", "⚑", "最險", "5 體力", "湖邊 ⚔"))


# ── 場景小地圖 ─────────────────────────────────────

TEXT_RE = re.compile(r'<text x="([-\d.]+)" y="([-\d.]+)" font-size="(\d+)"([^>]*)>([^<]*)</text>')
ARROW_RE = re.compile(r">([→↘↓↙←↖↑↗]) ([^<]+)</text>")


def window(svg: str):
    """小地圖截到的範圍（viewBox）：左、上、右、下。"""
    left, top, width, height = map(float, re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"', svg).groups())
    return left, top, left + width, top + height


def texts(svg: str):
    """小地圖上每段文字與它大約佔的範圍。"""
    out = []
    for m in TEXT_RE.finditer(svg):
        anchor = re.search(r'text-anchor="(\w+)"', m[4])
        text = html.unescape(m[5])
        out.append((text, text_box(float(m[1]), float(m[2]), text, int(m[3]), anchor[1] if anchor else "start")))
    return out


def add_place(content, loc_id: str, name: str, x: int, y: int, via: str) -> None:
    content.locations[loc_id] = Location(id=loc_id, name=name, description="某處。", connections=[via], x=x, y=y)
    content.locations[via].connections.append(loc_id)


def test_minimap_is_a_window_centred_on_the_player(state, content):
    svg = render_minimap(state, content)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    left, top, right, bottom = window(svg)
    assert (right - left, bottom - top) == tuple(content.map.mini_window)
    assert ((left + right) / 2, (top + bottom) / 2) == (100, 100)  # 小鎮在正中間
    assert f"height:{MINI_HEIGHT}px" in svg and "height:auto" not in svg  # 畫面上固定高度
    size = f'width="{right - left:g}" height="{bottom - top:g}"'
    assert f'<rect x="{left:g}" y="{top:g}" {size} fill="#E9E2CC"/>' in svg  # 地圖外面用底色
    assert 'clip-path="url(#' in svg  # 視窗外的東西不露出來
    state.player.location = "lake"
    left, top, right, bottom = window(render_minimap(state, content))
    assert ((left + right) / 2, (top + bottom) / 2) == (200, 100)


def test_minimap_window_follows_the_map(state, content):
    content.map.mini_window = (300, 200)
    left, top, right, bottom = window(render_minimap(state, content))
    assert (right - left, bottom - top) == (300, 200)


def test_minimap_draws_the_big_map_around_the_player(state, content):
    svg = render_minimap(state, content)
    assert 'fill="#EFE5CB"' in svg and 'fill="#E2EAF1"' in svg  # 兩個大區都在視窗裡
    assert 'fill="#E7C6AE"' not in svg  # 大區照原色，不依大勢變紅
    assert 'fill="#6FA0C2"' in svg  # 河
    assert '<path d="M200,100 Q' in svg  # 湖邊—小鎮的路
    assert re.search(r'font-weight="bold"[^>]*>小鎮（你）<', svg)  # 所在地最醒目
    assert 'r="17" fill="none" stroke="#C0392B"' in svg and 'fill="#C0392B"/>' in svg  # 所在地的紅圈與紅旗（同大地圖）
    assert 'fill="#B9604A"' in svg  # 小鎮是城鎮：城牆
    assert ">湖邊<" in svg and 'stroke="#BA7517"' in svg  # 看得見的地點寫名字、畫危險外圈


def test_minimap_names_regions_and_rivers_only_when_they_fit(state, content):
    svg = render_minimap(state, content)
    assert "測試北區" not in svg and "測試區" not in svg  # 落在視窗外或壓到邊
    north = content.map.regions[0]
    north.label_x, north.label_y = 120, 60
    content.map.labels[0].x, content.map.labels[0].y = 20, 140
    svg = render_minimap(state, content)
    assert ">測試北區<" in svg and ">測試區<" in svg


def test_minimap_fog_matches_the_big_map(state, content):
    content.config.vision_base = 0
    svg = render_minimap(state, content)
    assert "湖邊" not in svg and '<circle cx="200" cy="100" r="4" fill="#C2BAA4"/>' in svg  # 沒名字的淡點
    content.locations["lake"].important = True
    assert ">湖邊？<" in render_minimap(state, content)  # 畫出輪廓的未知地點
    cave = content.locations["cave"]
    cave.x, cave.y = 150, 60  # 挪進視窗，但還沒開放
    svg = render_minimap(state, content)
    assert "寶洞" not in svg and 'cx="150"' not in svg and "150,60" not in svg  # 記號與通往它的路都不畫
    state.world.flags.add("cave_open")
    content.config.vision_base = 2
    assert ">寶洞<" in render_minimap(state, content)


def test_minimap_leaves_out_layer_marks_odds_costs_news_and_legend(state, content):
    state.world.rumors.append(Rumor(time=0, text="湖邊出事了。", location="lake"))
    svg = render_minimap(state, content)
    assert all(mark not in svg for mark in ("★", "✦", "⚑", "⚔", "最險", "體力", "寇亂", "外圈", "所在地", "翻江龍"))
    assert [text for text, _ in texts(svg)] == ["小鎮（你）", "湖邊"]


def test_minimap_names_stay_inside_the_window(state, content):
    content.locations["lake"].x = 222  # 湖邊貼著視窗右緣：名字不能往右擺
    svg = render_minimap(state, content)
    left, top, right, bottom = window(svg)
    ((_, box),) = [(text, box) for text, box in texts(svg) if text == "湖邊"]
    assert left <= box[0] and box[2] <= right


def test_minimap_points_to_known_places_beyond_the_window(state, content):
    state.world.flags.add("cave_open")  # 寶洞：兩站外，在視窗右邊外面
    svg = render_minimap(state, content)
    assert ARROW_RE.findall(svg) == [("→", "寶洞")]
    ((_, box),) = [(text, box) for text, box in texts(svg) if text == "→ 寶洞"]
    left, top, right, bottom = window(svg)
    assert right - 20 < box[2] <= right and top < box[1] and box[3] < bottom  # 貼著右邊
    content.config.vision_base = 1  # 看不見寶洞：沒摸清就不標
    assert ARROW_RE.findall(render_minimap(state, content)) == []
    content.locations["cave"].important = True
    assert "寶洞" not in render_minimap(state, content)
    state.player.visited.add("cave")  # 去過：記得在哪
    assert ARROW_RE.findall(render_minimap(state, content)) == [("→", "寶洞")]


def test_minimap_places_just_beyond_the_edge_get_an_arrow_not_a_clipped_mark(state, content):
    state.world.flags.add("cave_open")
    content.locations["cave"].x = 240  # 中心在視窗右緣外 5：記號會露出一半
    svg = render_minimap(state, content)
    assert 'cx="240"' not in svg and ARROW_RE.findall(svg) == [("→", "寶洞")]
    assert '<path d="M240,100 Q' in svg  # 路照樣通到邊緣外


def test_minimap_points_to_at_most_four_places_nearest_first(state, content):
    state.world.flags.add("cave_open")
    add_place(content, "ridge", "北嶺", 250, 20, "town")  # 一站，170 遠
    add_place(content, "wood", "東林", 260, 180, "town")  # 一站，約 179 遠
    add_place(content, "slope", "南坡", 320, 115, "lake")  # 兩站，約 221 遠，和寶洞幾乎同一個方向
    add_place(content, "isle", "東島", 380, 100, "lake")  # 兩站，280 遠：第五個，不標
    add_place(content, "peak", "遠山", 350, 40, "cave")  # 三站：太遠，不標
    state.player.visited |= set(content.locations)
    svg = render_minimap(state, content)
    assert ARROW_RE.findall(svg) == [("↗", "北嶺"), ("↘", "東林"), ("→", "寶洞"), ("→", "南坡")]
    boxes = texts(svg)
    assert not [(a, b) for i, (a, box_a) in enumerate(boxes) for b, box_b in boxes[i + 1:] if overlap(box_a, box_b)]
    left, top, right, bottom = window(svg)
    assert all(left <= box[0] and top <= box[1] and box[2] <= right and box[3] <= bottom for _, box in boxes)


def test_minimap_keeps_showing_the_player_during_an_event(state, content):
    state.pending_event = "drunk"
    assert ">小鎮（你）<" in render_minimap(state, content)


def test_minimap_without_regions_still_shows_the_player(state, content):
    content.map.regions = []
    svg = render_minimap(state, content)
    assert 'fill="#EFE5CB"' not in svg and 'fill="#E2EAF1"' not in svg and ">小鎮（你）<" in svg


# ── 路上的「你」（路上設計 3.4）──────────────────────────────


def _walking(state, at=90.0):
    """從小鎮步行往湖邊（夾具 3 分鐘＝180 秒），現在是第 at 秒（預設走了一半）。"""
    state.player.journey = Journey(mode="walk", path=["lake"], arrive_at=[180.0])
    state.world.time = at


def test_on_the_road_the_map_draws_you_between_the_two_stops(state, content):
    _walking(state)
    svg = render_map(state, content)
    town, lake, bend = (100, 100), (200, 100), road_control(content, "town", "lake")
    (x, y), (cx, cy) = bezier_tail(town, bend, lake, 0.5)  # 走了一半：那條路（曲線）的正中間
    assert f'<circle class="tx-you" cx="{fmt(x)}" cy="{fmt(y)}" r="{YOU_SIZE}"' in svg
    ahead = f'<path d="M{fmt(x)},{fmt(y)} Q{fmt(cx)},{fmt(cy)} 200,100" fill="none" stroke="{ROUTE_STROKE}"'
    assert ahead in svg  # 還沒走的那一截，沿著同一條曲線，看得出走向
    assert ">你→<" in svg
    # 圓點與虛線畫在地點上面，不能擋住點前後那兩站（網頁照 [data-loc] 認點擊）
    circle = re.search(r'<circle class="tx-you"[^>]*>', svg).group(0)
    line = re.search(re.escape(ahead) + r"[^>]*>", svg).group(0)
    assert 'pointer-events="none"' in circle and 'pointer-events="none"' in line
    assert "小鎮（你）" not in svg  # 在路上：小鎮只是身後那一站
    state.player.journey = Journey(mode="walk", path=["town"], arrive_at=[180.0], origin="lake", share=0.5)
    svg = render_map(state, content)  # 在正中間掉頭回小鎮：箭頭朝西，虛線沿同一條曲線倒回小鎮
    (x, y), (cx, cy) = bezier_tail(lake, bend, town, 0.5)
    assert ">你←<" in svg and f'<path d="M{fmt(x)},{fmt(y)} Q{fmt(cx)},{fmt(cy)} 100,100" fill="none" stroke="{ROUTE_STROKE}"' in svg


def test_on_the_road_the_routes_layer_counts_from_where_you_are(state, content):
    _walking(state, at=60.0)  # 走了三分之一：回小鎮 1 分鐘、到湖邊 2 分鐘
    svg = render_map(state, content, "routes", selected="lake")
    assert ">1 分鐘<" in svg and ">2 分鐘<" in svg  # 小鎮、湖邊各自從路上算
    town, lake, bend = (100, 100), (200, 100), road_control(content, "town", "lake")
    (x, y), (cx, cy) = bezier_tail(town, bend, lake, 1 / 3)  # 粗線從路上的「你」沿著曲線走完剩下那一截
    assert f'<path d="M{fmt(x)},{fmt(y)} Q{fmt(cx)},{fmt(cy)} 200,100" fill="none" stroke="{ROUTE_STROKE}" stroke-width="5"' in svg
    svg = render_map(state, content, "routes", selected="town")  # 掉頭：同一條曲線倒回小鎮
    (x, y), (cx, cy) = bezier_tail(lake, bend, town, 2 / 3)
    assert f'<path d="M{fmt(x)},{fmt(y)} Q{fmt(cx)},{fmt(cy)} 100,100" fill="none" stroke="{ROUTE_STROKE}" stroke-width="5"' in svg


def test_on_the_road_the_minimap_is_centred_on_you(state, content):
    _walking(state)
    svg = render_minimap(state, content)
    left, top, right, bottom = window(svg)
    x, y = bezier_point((100, 100), road_control(content, "town", "lake"), (200, 100), 0.5)
    assert ((left + right) / 2, (top + bottom) / 2) == pytest.approx((x, y))
    assert f'<circle class="tx-you" cx="{fmt(x)}" cy="{fmt(y)}"' in svg
    assert [text for text, _ in texts(svg)] == ["小鎮", "湖邊", "你→"]


# ── 大區、河、路（輿圖美術設計 2.2～2.4）──────────────────────


def test_regions_have_cut_corners_and_a_darker_edge(state, content):
    svg = render_map(state, content)  # 局勢層：北區依寇亂 30 往紅色靠，描邊照原本的底色加深
    edge = mix("#EFE5CB", "#6B5A3A", 0.35)
    north = re.search(rf'<path d="(M[^"]+ Z)" fill="#E7C6AE" stroke="{edge}" stroke-width="1.4"', svg)
    assert north and north[1].count(" L") == 4 * 2 ** 3 - 1  # 四個角各切 3 輪
    assert not north[1].startswith("M0,0 ")  # 角削掉了：不從原本的角 (0, 0) 起筆


def test_rivers_are_ribbons_that_widen_downstream(state, content):
    svg = render_map(state, content)  # 夾具的河是舊格式：藍色、寬 4→8
    body = re.search(r'<path d="M([^"]+) Z" fill="#6FA0C2" stroke="#6FA0C2"', svg)[1]
    points = [tuple(map(float, p.split(","))) for p in body.split(" L")]
    half = len(points) // 2  # 前一半是一側的岸，後一半倒過來是另一側
    assert math.dist(points[0], points[-1]) == pytest.approx(4, abs=0.15)  # 上游寬 4
    assert math.dist(points[half - 1], points[half]) == pytest.approx(8, abs=0.15)  # 下游寬 8
    assert 'stroke="#A9C9DE" stroke-width="1.5"' in svg  # 中間的亮線
    content.map.rivers[0].color = "yellow"
    svg = render_map(state, content)
    assert 'fill="#C9A867"' in svg and 'stroke="#E2CB94"' in svg and 'fill="#6FA0C2"' not in svg


def test_roads_bend_and_are_drawn_by_their_kind(state, content):
    state.world.flags.add("cave_open")
    svg = render_map(state, content)  # 小鎮—湖邊是一般的路，湖邊—寶洞是山路
    (ax, ay), (bx, by) = road_control(content, "town", "lake"), road_control(content, "lake", "cave")
    road = f'<path d="M200,100 Q{fmt(ax)},{fmt(ay)} 100,100" fill="none" stroke="#9C7E58" stroke-width="1.8" stroke-dasharray="5 4"'
    trail = f'<path d="M300,100 Q{fmt(bx)},{fmt(by)} 200,100" fill="none" stroke="#86704F" stroke-width="1.9" stroke-dasharray="1.5 4"'
    assert road in svg and trail in svg
    assert svg.count(f"Q{fmt(ax)},{fmt(ay)} ") == 1  # 一條路只畫一次
    content.locations["town"].connections = [Connection("lake", "官道")]
    content.locations["lake"].connections = [Connection("town", "官道"), Connection("cave", "山路")]
    assert 'stroke="#8E6B45" stroke-width="2.6" stroke-dasharray="8 4"' in render_map(state, content)
    content.config.vision_base = 0  # 湖邊、寶洞都成了淡點：兩頭都沒摸清的路畫成淡色點線
    faint = f'<path d="M300,100 Q{fmt(bx)},{fmt(by)} 200,100" fill="none" stroke="#C2B394" stroke-width="1.4" stroke-dasharray="1.5 4"'
    assert faint in render_map(state, content)


# ── 地形、外框、指北針（輿圖美術設計 2.1、2.5）──────────────────────

RIDGE_ACROSS = Terrain(kind="mountains", name="測試嶺", spine=[[20, 100], [380, 100]], size=20)  # 正好壓過小鎮、湖邊與路
WOODS = Terrain(kind="forest", points=[[10, 40], [390, 40], [390, 190], [10, 190]])  # 整張地圖都是林地


@pytest.fixture(scope="module")
def real():
    return load_content(Path(__file__).parent.parent / "content")


def trampled(pieces, content) -> list[str]:
    """壓到地點記號或路的山頭與樹。地點記號是半徑 13 的圓盤加外圈（14）；路照畫出來的曲線細細取點。"""
    discs = [(loc.id, (loc.x - 14, loc.y - 14, loc.x + 14, loc.y + 14)) for loc in content.locations.values()]
    dots = []
    for a in content.locations.values():
        for b_id in a.connections:
            b, c = content.locations[b_id], road_control(content, a.id, b_id)
            dots += [(f"{a.id}—{b_id}", bezier_point((a.x, a.y), c, (b.x, b.y), i / 64)) for i in range(65)]
    found = []
    for piece in pieces:
        left, top, right, bottom = piece.box
        found += [f"{piece.box}×{name}" for name, d in discs if left < d[2] and d[0] < right and top < d[3] and d[1] < bottom]
        found += [f"{piece.box}×{name}" for name, (x, y) in dots if left < x < right and top < y < bottom]
    return found


def test_terrain_steps_aside_for_places_and_roads(content):
    content.map.terrain = [RIDGE_ACROSS, WOODS]
    pieces = terrain(content)
    assert any('fill="#7BA088"' in p.svg for p in pieces) and any('fill="#9CB9A1"' in p.svg for p in pieces)  # 前後兩排
    assert any('fill="#7FA36A"' in p.svg for p in pieces)  # 樹
    assert trampled(pieces, content) == []
    assert [p.base_y for p in pieces] == sorted(p.base_y for p in pieces)  # 由遠到近：近的蓋住遠的


def test_real_terrain_steps_aside_for_every_place_and_road(real):
    pieces = terrain(real)
    assert len(pieces) > 300 and trampled(pieces, real) == []


def test_terrain_steps_aside_for_rivers(content):
    content.map.terrain = [WOODS]
    content.map.rivers = []
    dry = terrain(content)
    content.map.rivers = [MapRiver(points=[[20, 150], [380, 150]], width=(6, 10))]  # 橫過林地、離地點與路都很遠
    pieces = terrain(content)
    bank = 10 / 2 + 2  # 河岸：從河中線算，下游河寬的一半再加 2

    def wet(found):
        return [p.box for p in found if p.box[1] < 150 + bank and p.box[3] > 150 - bank]

    assert wet(dry)  # 沒有河時這一帶種著樹：下面的斷言才真的咬得到
    assert wet(pieces) == [] and 0 < len(pieces) < len(dry)  # 有河時，河岸讓出來，兩岸照樣有樹


def test_terrain_is_worked_out_once_per_content_but_never_stale(content):
    content.map.terrain = [WOODS]
    first = terrain(content)
    assert terrain(content) is first  # 同一份內容只算一次
    content.locations["lake"].x = 330  # 搬了地點：樹要讓開新的位置
    moved = terrain(content)
    assert moved is not first and trampled(moved, content) == []
    assert trampled(first, content) != []  # 舊的那一份會壓到搬過去的湖邊


def test_terrain_is_drawn_under_the_roads(state, content):
    content.map.terrain = [WOODS]
    svg = render_map(state, content)
    assert svg.index('fill="#7FA36A"') < svg.index('<path d="M200,100 Q') < svg.index('data-loc="town"')


def test_terrain_names_are_drawn_and_place_names_step_aside(state, content):
    content.map.terrain = [Terrain(kind="mountains", name="測試嶺", spine=[[150, 130], [170, 130]], size=20)]
    svg = render_map(state, content)
    name = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)" font-size="12" fill="#4F6E5C"[^>]*pointer-events="none">測試嶺</text>', svg)
    assert name and (float(name[1]), float(name[2])) == (160, 106)  # 山腳線中間、往上一個山頭高
    box = text_box(float(name[1]), float(name[2]), "測試嶺", 12, "middle")
    assert not overlap(label_box(svg, "town"), box)  # 小鎮的名字本來擺右邊，正好壓到山名：讓開


def test_the_map_has_a_double_frame_and_a_compass_where_the_map_says(state, content):
    svg = render_map(state, content)
    assert '<rect x="5" y="5" width="390" height="190" rx="8" fill="none" stroke="#A08A5E" stroke-width="2"/>' in svg
    assert '<rect x="10" y="10" width="380" height="180" rx="6" fill="none" stroke="#A08A5E" stroke-width="0.8"/>' in svg
    assert ">北<" not in svg  # 夾具沒寫 compass：不畫
    content.map.compass = (250, 100)  # 正好在湖邊右邊，湖邊的名字本來擺這裡
    svg = render_map(state, content)
    assert '<circle cx="250" cy="100" r="22"' in svg and ">北<" in svg
    assert not overlap(label_box(svg, "lake"), (228, 70, 272, 130))  # 湖邊的名字讓開指北針


def test_the_frame_is_drawn_above_the_terrain_and_under_every_name_and_trend(state, content):
    content.map.terrain = [WOODS]
    svg = render_map(state, content)
    frame = svg.index('<rect x="5" y="5" width="390"')
    assert svg.rindex(terrain(content)[-1].svg) < frame  # 山頭與樹在框下面：靠邊的山不會探出框外
    assert frame < svg.index(">測試北區<") < svg.index('<path d="M200,100 Q')  # 大區名稱在框上面：名字的底色蓋得住框線
    assert frame < svg.index(">寇亂 30<")  # 大勢那一行也在框上面


def test_real_map_frame_is_under_the_region_names_and_trends(real):
    state = new_game_state(real, "測試")
    svg = render_map(state, real)
    frame = svg.index('<rect x="5" y="5" ')
    assert svg.rindex(terrain(real)[-1].svg) < frame  # 靠邊的山（如伏牛山）不探出框外
    names = [svg.index(f">{region.name}<") for region in real.map.regions]
    trends = [m.start() for m in re.finditer(r'<text [^>]*fill="#A32D2D"[^>]*>', svg)]
    assert trends and all(frame < at for at in names + trends)


def test_minimap_draws_the_region_names_over_the_rivers_and_terrain(state, content):
    content.map.terrain = [WOODS]
    content.map.regions[0].label_x, content.map.regions[0].label_y = 120, 60  # 名字落進視窗
    svg = render_minimap(state, content)
    left, top, right, bottom = window(svg)
    inside = [p for p in terrain(content) if p.extent[0] < right and left < p.extent[2] and p.extent[1] < bottom and top < p.extent[3]]
    name = svg.index(">測試北區<")
    assert inside and svg.index('fill="#6FA0C2" stroke="#6FA0C2"') < name  # 河在名字下面
    assert svg.rindex(inside[-1].svg) < name < svg.index('<path d="M200,100 Q')  # 山頭與樹在名字下面，路在名字上面


def test_terrain_is_the_same_before_and_after_a_place_unlocks(state, content):
    content.map.terrain = [WOODS]
    tree = re.compile(r'<circle [^>]*fill="#7FA36A"/>')
    before = render_map(state, content)  # 寶洞還沒開放：記號、名字、路都不畫
    state.world.flags.add("cave_open")
    after = render_map(state, content)
    assert "寶洞" not in before and "寶洞" in after
    assert tree.findall(before) and tree.findall(before) == tree.findall(after)  # 地形只跟內容有關，開放前後一樣


# ── 小地圖的地形、手機上的大小（輿圖美術設計第三節）──────────────────


def test_minimap_draws_only_the_terrain_touching_its_window(state, content):
    content.map.terrain = [WOODS]
    svg = render_minimap(state, content)
    left, top, right, bottom = window(svg)
    pieces = terrain(content)
    inside = [p for p in pieces if p.extent[0] < right and left < p.extent[2] and p.extent[1] < bottom and top < p.extent[3]]
    assert 0 < len(inside) < len(pieces)  # 林地蓋滿整張地圖，視窗只截到一部分
    assert svg.count('fill="#7FA36A"') == len(inside)


def test_minimap_names_terrain_only_when_it_fits(state, content):
    content.map.terrain = [Terrain(kind="mountains", name="測試嶺", spine=[[20, 160], [60, 160]], size=20)]
    assert ">測試嶺<" in render_minimap(state, content)  # 名字在 (40, 136)，整個落在視窗裡
    content.map.terrain[0].spine = [[300, 160], [340, 160]]  # 名字在 (320, 136)，視窗外
    assert ">測試嶺<" not in render_minimap(state, content)


def test_real_maps_stay_small_enough_for_phones(real):
    state = new_game_state(real, "測試")
    state.player.visited |= set(real.locations)  # 全部摸清：圓盤、名字最多的時候
    for layer in LEGEND_LAYERS:
        svg = render_map(state, real, layer, "wan_city", (lambda squad_id: "穩勝") if layer == "enemies" else None)
        assert len(svg.encode()) <= 200_000, layer  # 大地圖上限 200 KB
    for loc_id in real.locations:  # 小地圖每 10 秒跟著畫面更新一次：只放視窗裡的山頭
        state.player.location = loc_id
        assert len(render_minimap(state, real).encode()) <= 50_000, loc_id


# ── 圖例的資料（給網頁疊在地圖框角落；不畫進 SVG）──────────────────


def test_legend_data_has_six_icons_how_views_are_drawn_the_ring_and_this_layers_line(state, content):
    legend = legend_data(state, content, "routes")
    assert [(item["kind"], item["label"]) for item in legend["icons"]] == LEGEND_ICONS
    assert all(item["svg"] == icon_svg(item["kind"]) for item in legend["icons"])  # 圖示就是地圖上畫的那六個
    assert legend["states"] == LEGEND_STATES and legend["ring"] == LEGEND_RING
    assert legend["layer"] == LEGEND_LAYERS["routes"] and legend["strike"] == ""
    assert all(isinstance(value, str) for key, value in legend.items() if key != "icons")  # 全是字串：原樣就是 JSON


def test_every_layer_has_its_own_legend_line(state, content):
    for layer, line in LEGEND_LAYERS.items():
        assert legend_data(state, content, layer)["layer"] == line
    assert legend_data(state, content, "沒這層")["layer"] == ""  # 認不得的圖層不丟例外，網頁就不畫那一行
