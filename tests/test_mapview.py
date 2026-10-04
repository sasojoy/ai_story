import html
import math
import re

import pytest

from tianxia.atlas import location_view, vision_range, visible_locations
from tianxia.mapart import bezier_point, bezier_tail, fmt, mix, road_control
from tianxia.mapview import (
    LEGEND_LAYERS, MINI_HEIGHT, NODE_FILL, ROUTE_STROKE, SELECT_STROKE, YOU_SIZE, node_shape, render_map,
    render_minimap, text_box, text_width,
)
from tianxia.models import Connection, Location
from tianxia.state import Journey, Rumor


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


def test_node_shapes_follow_tags(content):
    assert node_shape(content.locations["town"]) == "town"
    assert node_shape(content.locations["lake"]) == "wild"
    content.locations["lake"].tags.append("門派")
    assert node_shape(content.locations["lake"]) == "sect"


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
    assert "<rect" in svg  # 小鎮（城鎮）畫成方塊


def label_box(svg: str, loc_id: str):
    """大地圖上某個地點名字那一行大約佔的範圍。"""
    m = re.search(
        rf'<text x="([-\d.]+)" y="([-\d.]+)" font-size="(\d+)"[^>]*text-anchor="(\w+)"[^>]*data-loc="{loc_id}"[^>]*>([^<]*)</text>',
        svg,
    )
    return text_box(float(m[1]), float(m[2]), html.unescape(m[5]), int(m[3]), m[4])


def overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_labels_step_aside_for_other_places_and_labels(state, content):
    content.locations["lake"].x = 150  # 湖邊緊貼在小鎮右邊：小鎮的名字擺右邊會壓到湖邊的記號
    svg = render_map(state, content, "routes")
    town, lake = label_box(svg, "town"), label_box(svg, "lake")
    assert not overlap(town, lake) and not overlap(town, (140.5, 90.5, 159.5, 109.5))
    assert town[0] != 100 + 11 + 8 + 5  # 不是原本右邊的位置


def test_selected_label_sits_outside_the_selection_ring(state, content):
    svg = render_map(state, content, selected="lake")
    assert label_box(svg, "lake")[0] >= 200 + 8 + 10 + 1.5  # 選定的圓圈：半徑 18、線寬 3


def test_region_names_have_a_halo_so_they_read_on_any_tint(state, content):
    svg = render_map(state, content)
    assert re.search(r'<text [^>]*fill="#C9B98F"[^>]*stroke="#E9E2CC"[^>]*>測試北區</text>', svg)


def test_label_flips_left_near_right_edge(state, content):
    content.locations["lake"].x = 390
    assert 'text-anchor="end"' in render_map(state, content)


def test_legend_sits_at_the_bottom(state, content):
    svg = render_map(state, content)
    assert f'<rect x="8" y="{content.map.height - 50}"' in svg


def test_remembered_color_is_distinct_from_visible(state, content):
    from tianxia.mapview import NODE_FILL

    assert NODE_FILL["remembered"] == "#7F77DD"  # 紫色，和看得見的綠色明顯不同
    content.config.vision_base = 0
    state.player.visited.add("lake")
    assert 'fill="#7F77DD"' in render_map(state, content)


# ── 大地圖的圖層 ─────────────────────────────────────


def test_every_layer_has_its_own_legend(state, content):
    for layer, line in LEGEND_LAYERS.items():
        svg = render_map(state, content, layer, odds={"thug": "穩勝"}.get)
        assert line in svg and "外圈：綠安全／橙危險／紅兇險" in svg and "■ 城鎮" in svg
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
    assert f'r="8" fill="{NODE_FILL["visible"]}"' not in svg  # 湖邊改用危險度的顏色
    assert 'fill="#BA7517" stroke="#BA7517"' in svg
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
    assert f'r="18" fill="none" stroke="{SELECT_STROKE}" stroke-width="3"' in svg  # 湖邊 8 ＋ 10
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
    assert f'r="18" fill="none" stroke="{NODE_FILL["current"]}"' in svg  # 所在地的圓圈（同大地圖）
    assert f'rx="3" fill="{NODE_FILL["current"]}"' in svg  # 小鎮是城鎮：方塊
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
    assert "湖邊" not in svg and f'<circle cx="200" cy="100" r="4" fill="{NODE_FILL["dot"]}"/>' in svg  # 沒名字的淡點
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
