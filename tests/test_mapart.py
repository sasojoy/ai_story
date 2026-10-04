import math

import pytest

from tianxia.mapart import PAPER, bezier_point, bezier_tail, catmull_rom, chaikin, fmt, mix, road_control


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
