import hashlib
import json
import math
import re

import pytest

from conftest import real_content
from tianxia.mapart import (
    ICON_BOX, ICON_COLORS, MOUNTAIN_ROWS, PAPER, RIVER_STEPS, bezier_point, bezier_tail, catmull_rom, chaikin, fmt, icon, icon_svg, mix,
    river_shape, road_control, terrain, terrain_data, terrain_labels, terrain_name_spot, terrain_peaks, terrain_rivers, terrain_trees,
)
from tianxia.models import Terrain


def test_coordinates_are_written_short():
    assert (fmt(150.0), fmt(96.54), fmt(133.333), fmt(-0.04)) == ("150", "96.5", "133.3", "0")


def test_mix_moves_a_colour_towards_another():
    assert mix("#000000", "#FFFFFF", 0.5) == "#808080"
    assert mix("#B9604A", PAPER, 0) == "#B9604A" and mix("#B9604A", PAPER, 1) == PAPER


def test_bezier_runs_from_end_to_end_and_bends_towards_the_control():
    a, c, b = (0, 0), (50, 100), (100, 0)
    assert bezier_point(a, c, b, 0) == a and bezier_point(a, c, b, 1) == b
    assert bezier_point(a, c, b, 0.5) == (50, 50)


def test_bezier_tail_is_the_rest_of_the_same_curve():
    a, c, b = (0, 0), (50, 100), (100, 0)
    start, control = bezier_tail(a, c, b, 0.3)
    assert start == bezier_point(a, c, b, 0.3)
    for s in (0.25, 0.5, 0.75):  # 後半段第 s 點＝原曲線第 0.3 + 0.7 × s 點
        assert bezier_point(start, control, b, s) == pytest.approx(bezier_point(a, c, b, 0.3 + 0.7 * s))


def test_a_road_bends_seven_percent_the_same_way_from_both_ends(content):
    assert road_control(content, "town", "lake") == road_control(content, "lake", "town")
    x, y = road_control(content, "town", "lake")  # 小鎮 (100, 100)—湖邊 (200, 100)：路長 100
    assert x == 150 and abs(y - 100) == pytest.approx(7)


def test_catmull_rom_passes_through_every_point():
    points = [[0, 0], [40, 30], [80, 10], [120, 50]]
    line = catmull_rom(points, 6)
    assert len(line) == 3 * 6 + 1
    assert line[::6] == [tuple(map(float, p)) for p in points]
    assert all(y == 0 for _, y in catmull_rom([[0, 0], [50, 0], [100, 0]], 5))  # 直線還是直線


def test_chaikin_cuts_every_corner_and_stays_inside_a_convex_shape():
    square = [[0, 0], [100, 0], [100, 100], [0, 100]]
    smooth = chaikin(square)
    assert len(smooth) == 4 * 2 ** 3  # 切 3 輪，每輪點數加倍
    assert all(0 <= x <= 100 and 0 <= y <= 100 for x, y in smooth)
    assert min(math.dist(p, corner) for p in smooth for corner in square) > 5  # 四個角都削掉了
    assert chaikin(square, rounds=1)[:2] == [(12, 0), (88, 0)]  # 每輪從兩頭各切 12%


def _extent(markup: str) -> tuple[float, float, float, float]:
    """圖示畫出來的範圍（左、上、右、下）：只認圖示用到的路徑指令（M L Q V H v h a Z），每個頂點再加半個線寬（旗桿是描邊）。"""
    xs: list[float] = []
    ys: list[float] = []
    for d, width in re.findall(r'<path d="([^"]+)"(?: fill="[^"]*"| stroke="[^"]*" stroke-width="([\d.]+)")', markup):
        half = float(width) / 2 if width else 0.0
        x = y = 0.0
        for cmd, args in re.findall(r"([MLQVHZvhaz])([^MLQVHZvhaz]*)", d):
            nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", args)]
            if cmd == "Q":  # 控制點也算進來：曲線不會超出控制點圍起來的範圍
                xs += [nums[0] - half, nums[0] + half]
                ys += [nums[1] - half, nums[1] + half]
            if cmd in "MLQ":
                x, y = nums[-2], nums[-1]
            elif cmd == "V":
                y = nums[0]
            elif cmd == "H":
                x = nums[0]
            elif cmd == "v":
                y += nums[0]
            elif cmd == "h":
                x += nums[0]
            elif cmd == "a":  # 圓弧只看終點（相對座標）
                x, y = x + nums[-2], y + nums[-1]
            xs += [x - half, x + half]
            ys += [y - half, y + half]
    return min(xs), min(ys), max(xs), max(ys)


def test_every_legend_icon_fits_inside_its_own_small_svg():
    left, top, width, height = ICON_BOX
    assert set(ICON_COLORS) == {"town", "camp", "roof", "ferry", "peak", "flag"}
    for kind in ICON_COLORS:
        svg = icon_svg(kind)
        assert svg.startswith(f'<svg class="tx-icon" viewBox="{left} {top} {width} {height}" width="{width}" height="{height}"')
        assert svg.endswith("</svg>") and icon(kind, 0, 0, "full") in svg  # 就是地圖上畫的那個圖示，不另畫一份
        x0, y0, x1, y1 = _extent(icon(kind, 0, 0, "full"))
        assert left <= x0 and x1 <= left + width and top <= y0 and y1 <= top + height, kind
    assert 'aria-hidden="true"' in icon_svg("town") and "<text" not in icon_svg("town")  # 圖示旁邊的字由網頁寫
    assert icon("town", 0, 0, "faded") in icon_svg("town", "faded")


# ── 輿圖表現 S1：地形的位置單獨給成數字（base.terrain），跟 svg 畫的是同一份 ─────────────────────

HAND_MADE_PIECES = 99  # 下面那塊地形在測試內容（400×200、三個地點、y=150 一條河）上長出幾個山頭、丘與樹
HAND_MADE_SVG_SHA1 = "da2feccdddb68c76973ec4dffd3d974497efaea1"  # 它們的 svg 串起來的 sha1：輿圖表現 S1 動手之前量的


def _hand_made_terrain(content):
    """測試內容加一小塊地形：一條山脈（有前後兩排）、一排碰到河的丘陵、一片林地；兩處有名字。"""
    content.map.terrain = [
        Terrain(kind="mountains", name="測試山", spine=[[30, 30], [150, 55], [260, 35], [380, 50]], size=16),
        Terrain(kind="hills", name="測試丘", spine=[[20, 125], [150, 142], [380, 150]], size=12),
        Terrain(kind="forest", points=[[40, 60], [200, 60], [200, 90], [40, 90]]),
    ]
    return content


def _points(d: str) -> list[tuple[float, float]]:
    """<path d> 裡每一個「x,y」的點（M、L、Q 後面的）。"""
    return [tuple(float(v) for v in p.split(",")) for p in re.findall(r"-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?", d)]


def _first_path(svg: str) -> str:
    return re.match(r'<path d="([^"]+)"', svg).group(1)


def test_adding_the_data_did_not_change_what_the_terrain_draws(content):
    """位置另外給成數字，畫出來的 svg 一個位元組都不變（舊圖照舊畫 base.svg，W5 才拿掉）；改 mapart 的畫法、或這個測試內容的
    地點座標時，這兩個數字要跟著改。"""
    pieces = terrain(_hand_made_terrain(content))
    assert len(pieces) == HAND_MADE_PIECES
    assert hashlib.sha1("".join(p.svg for p in pieces).encode()).hexdigest() == HAND_MADE_SVG_SHA1


def test_the_data_splits_the_pieces_into_peaks_and_trees_from_far_to_near(content):
    c = _hand_made_terrain(content)
    pieces, data = terrain(c), terrain_data(c)
    assert set(data) == {"peaks", "trees", "rivers", "labels"}
    peaks, trees = data["peaks"], data["trees"]
    assert len(peaks) + len(trees) == len(pieces) and peaks and trees
    assert all(set(p) == {"x", "y", "size", "back"} and isinstance(p["back"], bool) for p in peaks)
    assert all(set(t) == {"x", "y", "r"} for t in trees)
    assert [p["y"] for p in peaks] == sorted(p["y"] for p in peaks)  # 由遠到近：近的蓋住遠的
    assert [t["y"] for t in trees] == sorted(t["y"] for t in trees)
    assert sum(p["back"] for p in peaks) == sum(1 for q in pieces if q.kind == "peak" and q.back) > 0  # 山脈有後排
    assert 0 < sum(1 for q in pieces if q.kind == "hill") and all(not q.back for q in pieces if q.kind == "hill")  # 丘當山送、沒有後排
    assert sum(not p["back"] for p in peaks) > sum(p["back"] for p in peaks)  # 前排比後排多（丘全在前排）
    assert all(4 <= t["r"] <= 5.6 for t in trees)
    assert all(0 <= t["x"] <= c.map.width and 0 <= t["y"] <= c.map.height for t in trees)


def test_the_data_is_a_fresh_plain_copy_each_time(content):
    c = _hand_made_terrain(content)
    first = terrain_data(c)
    assert json.loads(json.dumps(first)) == first  # 只有數字、字串、布林，直接可以送 JSON
    first["peaks"].clear()
    first["trees"][0]["x"] = -1
    assert terrain_data(c)["peaks"] and terrain_data(c)["trees"][0]["x"] != -1  # 改了這一份不會漏到快取的那一份


def test_the_hand_made_labels_are_the_river_name_then_the_named_terrain(content):
    labels = terrain_labels(_hand_made_terrain(content))
    assert [(l["text"], l["anchor"]) for l in labels] == [("測試區", "start"), ("測試山", "middle"), ("測試丘", "middle")]
    assert (labels[0]["x"], labels[0]["y"]) == (20, 20)  # 內容寫的河名位置（字開頭、基線）
    assert all(isinstance(l[k], (int, float)) for l in labels for k in ("x", "y"))


def test_every_peak_hill_and_tree_in_the_data_is_the_one_the_svg_draws():
    c = real_content()
    pieces, peaks, trees = terrain(c), iter(terrain_peaks(c)), iter(terrain_trees(c))
    seen = {"peak": 0, "hill": 0, "tree": 0}
    for piece in pieces:
        seen[piece.kind] += 1
        if piece.kind == "tree":
            got = next(trees)
            trunk = re.search(r'<path d="M([-\d.]+),([-\d.]+) v-4"', piece.svg)
            cx, cy, r = map(float, re.search(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="([-\d.]+)"', piece.svg).groups())
            assert got["x"] == cx == float(trunk.group(1)) and got["r"] == r
            assert float(trunk.group(2)) == pytest.approx(got["y"] + 4, abs=0.1)  # 樹幹的底
            assert cy == pytest.approx(got["y"] - 0.6 * got["r"], abs=0.15)  # 樹冠圓心
            continue
        got = next(peaks)
        points = _points(_first_path(piece.svg))
        if piece.kind == "hill":
            start, control, end = points  # M 左腳 Q 控制點 右腳
            assert got["back"] is False and got["y"] == start[1] == end[1]
            assert got["x"] == control[0] and got["size"] == pytest.approx((got["y"] - control[1]) / 2, abs=0.15)
            assert end[0] - start[0] == pytest.approx(3 * got["size"], abs=0.5)
            continue
        left_foot, top, right_foot = points[0], points[3], points[5]  # 輪廓：左腳、左肩、近肩、山尖、右肩、右腳
        assert got["y"] == left_foot[1] == right_foot[1]
        assert got["x"] == pytest.approx((left_foot[0] + right_foot[0]) / 2, abs=0.11)
        assert got["y"] - got["size"] == pytest.approx(top[1], abs=0.15)  # 山尖
        assert right_foot[0] - left_foot[0] == pytest.approx(1.55 * got["size"], abs=0.3)
        fill = re.match(r'<path d="[^"]+" fill="([^"]+)"', piece.svg).group(1)
        assert fill == MOUNTAIN_ROWS[0 if got["back"] else 1][0]  # 後排畫淡的那一色
    assert next(peaks, None) is None and next(trees, None) is None  # 一個不多、一個不少
    assert seen["peak"] and seen["hill"] and seen["tree"]


def test_every_river_in_the_data_is_the_line_the_svg_draws():
    c = real_content()
    rivers = terrain_rivers(c)
    assert len(rivers) == len(c.map.rivers) > 0
    for river, got in zip(c.map.rivers, rivers):
        assert set(got) == {"points", "width", "color"}
        assert got["color"] == river.color and got["width"] == [river.width[0], river.width[1]]
        shine = re.search(r'<polyline points="([^"]+)"', river_shape(river)).group(1)  # 色帶正中間那條亮線＝中線
        assert got["points"] == [[float(v) for v in p.split(",")] for p in shine.split()]
        assert got["points"][::RIVER_STEPS] == [[float(x), float(y)] for x, y in river.points]  # 平滑線穿過內容寫的每一個點


def test_the_labels_in_the_data_are_the_river_names_then_the_named_terrain():
    c = real_content()
    labels = terrain_labels(c)
    named = [t for t in c.map.terrain if t.name]
    assert [l["text"] for l in labels] == [l.text for l in c.map.labels] + [t.name for t in named]
    for label, source in zip(labels, c.map.labels):
        assert (label["x"], label["y"], label["anchor"]) == (source.x, source.y, "start")
    for label, piece in zip(labels[len(c.map.labels):], named):
        x, y = terrain_name_spot(piece)
        assert (label["x"], label["y"]) == (pytest.approx(x, abs=0.06), pytest.approx(y, abs=0.06)) and label["anchor"] == "middle"
