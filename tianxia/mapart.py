"""輿圖的畫法零件（純字串與幾何，不依賴介面框架，也不看視野）：設色山水的配色與座標寫法、路的二次曲線、
穿過每一點的平滑線（河、山脊）、大區邊的削角（輿圖美術設計）。要畫什麼、畫成哪種狀態由 mapview 決定。
"""
from __future__ import annotations

import math
import zlib

from .models import Content, MapRiver

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


# ── 大區、河 ─────────────────────────────────────────

REGION_INK = "#6B5A3A"  # 大區描邊：原本的底色往這個顏色加深
REGION_EDGE = 0.35  # 加深幾成
RIVER_STEPS = 12  # 河的平滑線：每兩點之間切幾段
RIVER_COLORS = {"blue": ("#6FA0C2", "#A9C9DE"), "yellow": ("#C9A867", "#E2CB94")}  # 河身、中間的亮線


def path_d(points: list[Point], closed: bool = False) -> str:
    """一串點寫成 <path> 的 d（直線連起來；closed 時收口）。"""
    return "M" + " L".join(f"{fmt(x)},{fmt(y)}" for x, y in points) + (" Z" if closed else "")


def region_shape(points: list[list[int]], fill: str, base: str) -> str:
    """一塊大區：削角（chaikin）的底色塊，fill 是要塗的顏色（局勢層會往紅色靠），描邊用原本的底色 base 往墨色加深。"""
    edge = mix(base, REGION_INK, REGION_EDGE)
    return (
        f'<path d="{path_d(chaikin(points), closed=True)}" fill="{fill}" stroke="{edge}" stroke-width="1.4" '
        'stroke-linejoin="round"/>'
    )


def river_line(river: MapRiver) -> list[Point]:
    """河的平滑中線，從上游到下游。"""
    return catmull_rom(river.points, RIVER_STEPS)


def river_shape(river: MapRiver) -> str:
    """一條河：中線往兩側各推半個河寬圍成的色帶（從上游的 width[0] 漸寬到下游的 width[1]），中間一條淺色亮線。"""
    body, light = RIVER_COLORS[river.color]
    line = river_line(river)
    w0, w1 = river.width
    last = len(line) - 1
    left: list[Point] = []
    right: list[Point] = []
    for i, (x, y) in enumerate(line):
        (ax, ay), (bx, by) = line[max(i - 1, 0)], line[min(i + 1, last)]
        length = math.hypot(bx - ax, by - ay) or 1
        half = (w0 + (w1 - w0) * i / last) / 2
        nx, ny = -(by - ay) / length * half, (bx - ax) / length * half  # 中線的法線，長度是半個河寬
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))
    shine = " ".join(f"{fmt(x)},{fmt(y)}" for x, y in line)
    return (
        f'<path d="{path_d(left + right[::-1], closed=True)}" fill="{body}" stroke="{body}" stroke-width="1" '
        'stroke-linejoin="round"/>'
        f'<polyline points="{shine}" fill="none" stroke="{light}" stroke-width="{fmt(max(1.5, w0 * 0.3))}" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )


# ── 路 ───────────────────────────────────────────────

ROAD_STYLE = {  # 路的種類：顏色、粗細、虛線
    "官道": ("#8E6B45", 2.6, "8 4"),
    "路": ("#9C7E58", 1.8, "5 4"),
    "山路": ("#86704F", 1.9, "1.5 4"),
}
FAINT_ROAD = ("#C2B394", 1.4, "1.5 4")  # 兩頭都沒摸清的路
