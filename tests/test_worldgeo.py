"""天下圖的純幾何（輿圖重製第 2 批，tianxia/worldgeo.py）：每一州自己的地面格（離哪個地點最近）、相鄰兩格的邊、跨州的邊、
州名擺哪、取景框。不載內容。"""
from __future__ import annotations

import math

from tianxia import worldgeo

BOX = (0.0, 0.0, 100.0, 100.0)


def _area(poly):
    pts = [p for p, _ in poly] if poly and isinstance(poly[0][0], tuple) else poly
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2


def test_two_seeds_split_a_square_down_the_middle():
    polys = worldgeo.cells([(25, 50), (75, 50)], BOX)
    assert len(polys) == 2
    assert abs(_area(polys[0]) - 5000) < 1e-6 and abs(_area(polys[1]) - 5000) < 1e-6
    edges = worldgeo.inner_edges(polys)
    assert len(edges) == 1
    i, j, p, q = edges[0]
    assert (i, j) == (0, 1) and abs(p[0] - 50) < 1e-6 and abs(q[0] - 50) < 1e-6
    assert {round(p[1]), round(q[1])} == {0, 100}


def test_three_seeds_meet_at_one_point():
    polys = worldgeo.cells([(20, 20), (80, 20), (50, 80)], BOX)
    edges = worldgeo.inner_edges(polys)
    assert sorted((i, j) for i, j, _, _ in edges) == [(0, 1), (0, 2), (1, 2)]
    ends = [p for _, _, p, q in edges] + [q for _, _, p, q in edges]
    centre = min(ends, key=lambda pt: math.hypot(pt[0] - 50, pt[1] - 42))
    assert sum(1 for pt in ends if math.hypot(pt[0] - centre[0], pt[1] - centre[1]) < 1e-6) == 3  # 三條邊交在同一點


def test_one_seed_takes_the_whole_box():
    polys = worldgeo.cells([(10, 10)], BOX)
    assert abs(_area(polys[0]) - 10000) < 1e-6 and worldgeo.inner_edges(polys) == []


def test_shared_borders_between_two_squares_and_not_along_the_map_edge():
    left = ("a", [(0, 0), (50, 0), (50, 100), (0, 100)])
    right = ("b", [(50, 0), (100, 0), (100, 100), (50, 100)])
    borders = worldgeo.shared_borders([left, right], 100, 100)
    assert len(borders) == 1
    a, b, p, q = borders[0]
    assert {a, b} == {"a", "b"} and p[0] == q[0] == 50 and {p[1], q[1]} == {0, 100}
    # 沿地圖上緣的零面積折返（第 1 批的 map.json 有幾段）不算兩州相接
    spike_a = ("a", [(0, 0), (60, 0), (40, 0), (50, 0), (50, 100), (0, 100)])
    spike_b = ("b", [(50, 0), (40, 0), (60, 0), (100, 0), (100, 100), (50, 100)])
    assert all(p[1] != 0 or q[1] != 0 for _, _, p, q in worldgeo.shared_borders([spike_a, spike_b], 100, 100))


def test_a_border_is_split_where_each_side_changes_cell():
    left = ("a", [(0, 0), (50, 0), (50, 100), (0, 100)])
    right = ("b", [(50, 0), (100, 0), (100, 100), (50, 100)])
    seeds = {"a": [("a1", (25, 25)), ("a2", (25, 75))], "b": [("b1", (75, 40))]}
    edges = worldgeo.cross_edges([left, right], seeds, (0, 0, 100, 100))
    pairs = sorted((e[0], e[1]) for e in edges)
    assert pairs == [("a1", "b1"), ("a2", "b1")]
    cut = next(e for e in edges if e[0] == "a1")
    assert abs(max(cut[2][1], cut[3][1]) - 50) < 1e-6  # 左州兩格的分界在 y=50


def test_a_region_without_seeds_is_all_unheld():
    left = ("a", [(0, 0), (50, 0), (50, 100), (0, 100)])
    right = ("b", [(50, 0), (100, 0), (100, 100), (50, 100)])
    edges = worldgeo.cross_edges([left, right], {"a": [("a1", (25, 50))], "b": []}, (0, 0, 100, 100))
    assert [(e[0], e[1]) for e in edges] == [("a1", None)]


def test_label_spot_sits_inside_a_crescent_away_from_places():
    crescent = [(0, 0), (100, 0), (100, 30), (30, 30), (30, 70), (100, 70), (100, 100), (0, 100)]  # 「匚」形
    x, y = worldgeo.label_spot(crescent, (0, 0, 100, 100), [(15, 50)])
    assert worldgeo.inside(x, y, crescent)
    assert math.hypot(x - 15, y - 50) > 20  # 讓開地點


def test_frame_wraps_the_places_with_a_margin_inside_the_map():
    assert worldgeo.frame([(100, 200), (300, 500)], 900, 1340, 60) == (40, 140, 360, 560)  # (x0, y0, x1, y1)
    assert worldgeo.frame([(10, 10), (890, 1330)], 900, 1340, 60) == (0, 0, 900, 1340)


def test_path_is_a_closed_svg_path_with_one_decimal():
    assert worldgeo.path([(0, 0), (10.04, 0), (10, 5.26)]) == "M0 0L10 0L10 5.3Z"
    assert worldgeo.path([(0, 0), (10, 0)], closed=False) == "M0 0L10 0"
