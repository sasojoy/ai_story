"""輿圖的畫法零件（純字串與幾何，不依賴介面框架，也不看視野）：設色山水的配色與座標寫法、路的二次曲線、
穿過每一點的平滑線（河、山脊）、大區邊的削角（輿圖美術設計）。要畫什麼、畫成哪種狀態由 mapview 決定。
"""
from __future__ import annotations

import zlib

from .models import Content

Point = tuple[float, float]

PAPER = "#E9E2CC"  # 紙色：淡色（去過／摸清）的圖示往這裡淡
ROAD_BEND = 0.07  # 路的彎度：控制點離中點多遠（路長的幾成）
REGION_ROUNDS = 3  # 大區邊削角：切幾輪
REGION_CUT = 0.12  # 每一輪每條邊從兩頭各切掉幾成


def fmt(value: float) -> str:
    """座標的寫法：取到小數一位、整數不寫小數點，SVG 才不會太大（加 0 是為了把 -0.0 寫成 0）。"""
    return f"{round(value, 1) + 0:g}"


def mix(color: str, other: str, ratio: float) -> str:
    """把 color 往 other 靠 ratio（0～1）：淡色圖示往紙色淡、大區描邊往墨色加深、大勢往紅色靠都用它。"""
    a = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    b = (int(other[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x * (1 - ratio) + y * ratio):02X}" for x, y in zip(a, b))


def bezier_point(a: Point, c: Point, b: Point, t: float) -> Point:
    """二次曲線 a→b（控制點 c）上第 t（0～1）的那一點。"""
    s = 1 - t
    return s * s * a[0] + 2 * s * t * c[0] + t * t * b[0], s * s * a[1] + 2 * s * t * c[1] + t * t * b[1]


def bezier_tail(a: Point, c: Point, b: Point, t: float) -> tuple[Point, Point]:
    """二次曲線 a→b 從第 t 點走到 b 的那一段（本身也是二次曲線）：回傳它的（起點, 控制點），終點就是 b。"""
    return bezier_point(a, c, b, t), (c[0] + (b[0] - c[0]) * t, c[1] + (b[1] - c[1]) * t)


def road_control(content: Content, a_id: str, b_id: str) -> Point:
    """a—b 這條路畫成二次曲線的控制點：中點往垂直方向偏路長的 ROAD_BEND。偏哪一邊看兩站 id（排序後）的雜湊，
    所以兩個方向算出來是同一條。"""
    lo, hi = sorted((a_id, b_id))
    a, b = content.locations[lo], content.locations[hi]
    k = ROAD_BEND if zlib.crc32(f"{lo}|{hi}".encode()) % 2 else -ROAD_BEND
    return (a.x + b.x) / 2 - (b.y - a.y) * k, (a.y + b.y) / 2 + (b.x - a.x) * k


def catmull_rom(points: list[list[int]], steps: int) -> list[Point]:
    """穿過每一個點的平滑線（Catmull-Rom）：每兩點之間切成 steps 段，頭尾照原樣。"""
    pts = [(float(p[0]), float(p[1])) for p in points]
    out: list[Point] = []
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, len(pts) - 1)]
        for step in range(steps):
            t = step / steps
            x, y = (
                0.5 * (
                    2 * p1[k] + (p2[k] - p0[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
                    + (3 * p1[k] - p0[k] - 3 * p2[k] + p3[k]) * t * t * t
                )
                for k in (0, 1)
            )
            out.append((x, y))
    out.append(pts[-1])
    return out


def chaikin(points: list[list[int]], rounds: int = REGION_ROUNDS, cut: float = REGION_CUT) -> list[Point]:
    """削角（Chaikin）：每一輪把每條邊換成兩點（離兩頭各 cut 成），角就被削掉一小段。凸的角削完還在原本的
    多邊形裡面；凹的角會往外鼓一點點——只是外觀，大區歸屬照舊用原始多邊形（atlas.region_of）。"""
    pts = [(float(p[0]), float(p[1])) for p in points]
    for _ in range(rounds):
        out: list[Point] = []
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            out += [(x1 + (x2 - x1) * cut, y1 + (y2 - y1) * cut), (x2 + (x1 - x2) * cut, y2 + (y1 - y2) * cut)]
        pts = out
    return pts
