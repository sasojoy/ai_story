"""輿圖的畫法零件（純字串與幾何，不依賴介面框架，也不看視野）：設色山水的配色與座標寫法、路的二次曲線、
穿過每一點的平滑線（河、山脊）、大區邊的削角、河帶、地形（山頭、圓丘與樹，讓開地點、路與河；算一次就照內容
快取）、依標籤挑的地點圖示與所在地的紅旗、紙的雙線外框與指北針（輿圖美術設計）。
要畫什麼、畫成哪種狀態、各層怎麼疊由 mapview 決定。
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass

from .models import Content, Location, MapRiver, Terrain

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


# ── 地形（純裝飾：只跟內容有關，同一份內容只算一次）─────────────

MOUNTAIN_ROWS = (("#9CB9A1", "#7FA08A"), ("#7BA088", "#557D69"))  # 後排、前排：（山頭, 陰面）
RIDGE = "#F1EEE2"  # 山脊的亮線
HILL = ("#A9BE8F", "#8FA877")  # 圓丘、陰面
TREE = ("#7FA36A", "#5F8A50", "#6B5235")  # 樹冠、陰影、樹幹
TERRAIN_TEXT = "#4F6E5C"  # 山名
TERRAIN_NAME_SIZE = 12
TERRAIN_NAME_SPACING = 2  # 山名的字距
NODE_CLEAR = 14  # 山頭與樹讓開地點多遠：圓盤半徑 13，加上外圈
ROAD_CLEAR = 3  # 讓開路多遠
RIVER_CLEAR = 2  # 讓開河岸多遠（從河中線算要再加半個下游河寬）
ROAD_PIECES = 8  # 算讓開時，一條路的曲線切成幾段直線
TERRAIN_CACHE = 8  # 最多記住幾份內容的地形
Box = tuple[float, float, float, float]  # 左、上、右、下
Segment = tuple[Point, Point, float]  # 要讓開的一段直線，與要讓開多遠


@dataclass(frozen=True)
class Piece:
    """一個山頭、一座丘或一棵樹。"""

    base_y: float  # 山腳（樹根）的 y：照它由遠到近排，近的蓋住遠的
    box: Box  # 山體佔的範圍（山頭取中間七成寬）：讓開地點、路與河時拿它比
    extent: Box  # 整個畫出來的範圍：小地圖拿它挑視窗裡的
    svg: str


_terrain_cache: dict[str, tuple[Piece, ...]] = {}


def terrain(content: Content) -> tuple[Piece, ...]:
    """整張地圖的山頭、丘與樹，由遠到近排好。只跟內容（地形、地點、路、河）有關、跟誰在看無關，所以同一份內容
    只算一次；內容換了或改了（搬了地點、加了路或地形）算出來的鍵就不同，會重算，不會拿到舊的。"""
    key = _terrain_key(content)
    if key not in _terrain_cache:
        if len(_terrain_cache) >= TERRAIN_CACHE:
            _terrain_cache.pop(next(iter(_terrain_cache)))  # 丟掉最早算的那一份
        _terrain_cache[key] = _grow_terrain(content)
    return _terrain_cache[key]


def terrain_name_spot(piece: Terrain) -> Point:
    """地形的名字寫在哪（置中的 x、基線 y）：山腳線（林地是外框）的平均 x，最高那一點再往上一個山頭高；
    貼著地圖上緣的（燕山）往下挪到外框裡面，不壓到外框。"""
    points = piece.spine or piece.points
    y = min(p[1] for p in points) - piece.size - 4
    return sum(p[0] for p in points) / len(points), max(y, FRAME_INSIDE + TERRAIN_NAME_SIZE)


def _terrain_key(content: Content) -> str:
    m = content.map
    places = [(loc.id, loc.x, loc.y, sorted(map(str, loc.connections))) for loc in content.locations.values()]
    return repr(([t.model_dump() for t in m.terrain], [r.model_dump() for r in m.rivers], places))


def _grow_terrain(content: Content) -> tuple[Piece, ...]:
    places = [(float(loc.x), float(loc.y)) for loc in content.locations.values()]
    segments = _obstacles(content)
    pieces: list[Piece] = []
    for piece in content.map.terrain:
        key = piece.name + piece.kind  # 只看名字與種類：加一片新地形不會讓其他地形換個樣子
        if piece.kind == "forest":
            pieces += _forest(piece, key, places, segments)
        else:
            pieces += _ridge(piece, key, places, segments)
    return tuple(sorted(pieces, key=lambda p: p.base_y))


def _obstacles(content: Content) -> list[Segment]:
    """地形要讓開的線段：每條路（照畫出來的曲線切成 ROAD_PIECES 段）與每條河的中線（另加半個下游河寬）。"""
    segments: list[Segment] = []
    for a_id, a in content.locations.items():
        for b_id in a.connections:
            if a_id < b_id:
                b = content.locations[b_id]
                c = road_control(content, a_id, b_id)
                line = [bezier_point((a.x, a.y), c, (b.x, b.y), i / ROAD_PIECES) for i in range(ROAD_PIECES + 1)]
                segments += [(p, q, ROAD_CLEAR) for p, q in zip(line, line[1:])]
    for river in content.map.rivers:
        line = river_line(river)
        segments += [(p, q, river.width[1] / 2 + RIVER_CLEAR) for p, q in zip(line, line[1:])]
    return segments


def _clear(box: Box, places: list[Point], segments: list[Segment]) -> bool:
    """box 有沒有讓開每一個地點記號（圓盤）、每一條路與河。"""
    for x, y in places:
        if box[0] < x + NODE_CLEAR and x - NODE_CLEAR < box[2] and box[1] < y + NODE_CLEAR and y - NODE_CLEAR < box[3]:
            return False
    return not any(_crosses(a, b, (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)) for a, b, pad in segments)


def _crosses(a: Point, b: Point, box: Box) -> bool:
    """線段 a—b 有沒有碰到 box（Liang–Barsky 裁切：把線段裁到 box 裡，裁得出東西就是碰到）。"""
    low, high = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - box[0]), (dx, box[2] - a[0]), (-dy, a[1] - box[1]), (dy, box[3] - a[1])):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            low = max(low, t)
        else:
            high = min(high, t)
        if low > high:
            return False
    return True


def _inside(x: float, y: float, points: list[list[int]]) -> bool:
    """射線法：點是否在多邊形內。"""
    hit = False
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def _jitter(key: str, low: float, high: float) -> float:
    """看起來隨意、但同一份內容每次都一樣的數（不用亂數：地形只跟內容有關）。"""
    return low + zlib.crc32(key.encode()) % 1000 / 999 * (high - low)


def _forest(piece: Terrain, key: str, places: list[Point], segments: list[Segment]) -> list[Piece]:
    """林地：在多邊形裡每隔 13×11 擺一棵樹（位置稍微錯開），讓不開地點、路與河的就不種。"""
    xs, ys = [p[0] for p in piece.points], [p[1] for p in piece.points]
    crown, shade, trunk = TREE
    out: list[Piece] = []
    for gx in range(min(xs), max(xs), 13):
        for gy in range(min(ys), max(ys), 11):
            spot = f"{key}{gx}{gy}"
            x, y = gx + _jitter(spot + "x", -4, 4), gy + _jitter(spot + "y", -3, 3)
            box = (x - 6, y - 10, x + 6, y + 4)
            if not _inside(x, y, piece.points) or not _clear(box, places, segments):
                continue
            r = _jitter(spot + "r", 4, 5.6)
            svg = (
                f'<path d="M{fmt(x)},{fmt(y + 4)} v-4" stroke="{trunk}" stroke-width="1.4"/>'
                f'<circle cx="{fmt(x)}" cy="{fmt(y - r * 0.6)}" r="{fmt(r)}" fill="{crown}"/>'
                f'<circle cx="{fmt(x + r * 0.35)}" cy="{fmt(y - r * 0.4)}" r="{fmt(r * 0.55)}" fill="{shade}"/>'
            )
            out.append(Piece(y, box, (x - r, y - r * 1.6, x + r, y + 4), svg))
    return out


def _ridge(piece: Terrain, key: str, places: list[Point], segments: list[Segment]) -> list[Piece]:
    """山脈、丘陵：沿山腳線每隔一段排一個山頭（大小、位置稍微錯開）。山脈另外往山腳線的一側錯開一排小一點、
    淡一點的後排，看起來有前後兩排。讓不開地點、路與河的山頭就不畫，路穿過的地方自然留出山口。"""
    size = piece.size
    mountains = piece.kind == "mountains"
    line = catmull_rom(piece.spine, 20)
    step = size * (0.5 if mountains else 0.9)
    out: list[Piece] = []
    walked, count = 0.0, 0
    for i, (px, py) in enumerate(line):
        if i:
            walked += math.dist(line[i - 1], line[i])
        if count and walked < step:
            continue
        (ax, ay), (bx, by) = line[max(i - 1, 0)], line[min(i + 1, len(line) - 1)]
        length = math.hypot(bx - ax, by - ay) or 1
        nx, ny = -(by - ay) / length, (bx - ax) / length  # 山腳線的法線：後排往這邊錯開
        if ny > 0 or (abs(ny) < 0.35 and count % 2):  # 往上（遠處）錯開；山脈近乎南北向時左右輪流
            nx, ny = -nx, -ny
        walked = 0.0
        count += 1
        x = px + _jitter(f"{key}{count}x", -size * 0.2, size * 0.2)
        y = py + _jitter(f"{key}{count}y", -size * 0.25, size * 0.25)
        h = size * _jitter(f"{key}{count}h", 0.75, 1.2)
        w = h * (1.55 if mountains else 2.4)
        if not mountains:
            box = (x - w * 0.35, y - h * 0.8, x + w * 0.35, y)
            if _clear(box, places, segments):
                out.append(Piece(y, box, (x - w / 2, y - h * 0.8, x + w / 2, y), _hill(x, y, w, h)))
            continue
        if not _clear((x - w * 0.35, y - h, x + w * 0.35, y), places, segments):
            continue
        for row, (fill, dark) in enumerate(MOUNTAIN_ROWS):
            back = row == 0
            off = size * 0.5 if back else 0
            hx = x + nx * off + (_jitter(f"{key}{count}bx", -size * 0.2, size * 0.2) if back else 0)
            hy = y + ny * off - (size * 0.15 if back else 0)
            hh, hw = h * (0.8 if back else 1), w * (0.8 if back else 1)
            box = (hx - hw * 0.35, hy - hh, hx + hw * 0.35, hy)
            if back and not _clear(box, places, segments):
                continue
            svg = _peak(hx, hy, hw, hh, _jitter(f"{key}{count}{row}s", 0.6, 0.85), fill, dark)
            out.append(Piece(hy, box, (hx - hw / 2, hy - hh, hx + hw / 2, hy), svg))
    return out


def _peak(x: float, y: float, w: float, h: float, shoulder: float, fill: str, dark: str) -> str:
    """一個不規則的山頭：左肩、山尖、右肩，右半邊是陰面，左肩到山尖有一道亮線。"""
    left, top, right = (x - w * 0.22, y - h * shoulder), (x + w * 0.04, y - h), (x + w * 0.24, y - h * shoulder * 0.9)
    near = (x - w * 0.08, y - h * 0.9)
    outline = [(x - w / 2, y), left, near, top, right, (x + w / 2, y)]
    shade = [top, right, (x + w / 2, y), (x + w * 0.1, y)]
    return (
        f'<path d="{path_d(outline, closed=True)}" fill="{fill}"/>'
        f'<path d="{path_d(shade, closed=True)}" fill="{dark}"/>'
        f'<path d="{path_d([left, near, top])}" fill="none" stroke="{RIDGE}" stroke-width="1.1" stroke-linejoin="round"/>'
    )


def _hill(x: float, y: float, w: float, h: float) -> str:
    """一座圓丘，右邊有一塊陰面。"""
    fill, dark = HILL
    return (
        f'<path d="M{fmt(x - w / 2)},{fmt(y)} Q{fmt(x)},{fmt(y - h * 1.6)} {fmt(x + w / 2)},{fmt(y)} Z" fill="{fill}"/>'
        f'<path d="M{fmt(x)},{fmt(y - h * 0.8)} Q{fmt(x + w * 0.3)},{fmt(y - h * 0.6)} {fmt(x + w / 2)},{fmt(y)} '
        f'L{fmt(x + w * 0.1)},{fmt(y)} Z" fill="{dark}"/>'
    )


# ── 外框、指北針 ──────────────────────────────────────

FRAME = "#A08A5E"  # 外框與指北針
FRAME_OUTER, FRAME_INNER = 5, 10  # 雙線外框：外線、內線離紙邊多遠
FRAME_INSIDE = 14  # 外框裡面：擺出來的字從這裡開始，不壓到內線
BANNER = "#C0392B"  # 紅旗（所在地）與指北針的北端
COMPASS_RADIUS = 22  # 指北針的圓
COMPASS_NEEDLE = 30  # 指針從中心往上下各伸多長
NORTH_RISE = 36  # 「北」字的基線在中心上方多遠
NORTH_SIZE = 13


def frame(width: int, height: int) -> str:
    """紙的雙線外框。"""
    o, i = FRAME_OUTER, FRAME_INNER
    return (
        f'<rect x="{o}" y="{o}" width="{width - 2 * o}" height="{height - 2 * o}" rx="8" fill="none" stroke="{FRAME}" '
        'stroke-width="2"/>'
        f'<rect x="{i}" y="{i}" width="{width - 2 * i}" height="{height - 2 * i}" rx="6" fill="none" stroke="{FRAME}" '
        'stroke-width="0.8"/>'
    )


def compass(x: int, y: int) -> str:
    """指北針：一個圓、上下兩頭尖的指針（北端紅色），上面寫「北」。"""
    n = COMPASS_NEEDLE
    return (
        f'<circle cx="{x}" cy="{y}" r="{COMPASS_RADIUS}" fill="none" stroke="{FRAME}" stroke-width="1"/>'
        f'<path d="M{x},{y - n} L{x + 6},{y} L{x},{y + n} L{x - 6},{y} Z" fill="{FRAME}"/>'
        f'<path d="M{x},{y - n} L{x + 6},{y} L{x - 6},{y} Z" fill="{BANNER}"/>'
        f'<text x="{x}" y="{y - NORTH_RISE}" font-size="{NORTH_SIZE}" fill="#7A6640" text-anchor="middle">北</text>'
    )


# ── 地點圖示 ─────────────────────────────────────────

ICON_TAGS = (  # 地點圖示照標籤，由上往下判斷，先符合的算數；都不符合是小旗（flag）
    ("town", {"城鎮", "城池", "官署", "塢堡"}),
    ("camp", {"營寨"}),
    ("roof", {"寺院", "書院", "莊院", "結社", "門派"}),
    ("ferry", {"渡口", "河畔"}),
    ("peak", {"山林", "洞窟"}),
)
ICON_COLORS = {  # 主色、第二色
    "town": ("#B9604A", "#7E3B2C"),  # 城牆、城門
    "camp": ("#8C6A44", "#5E4529"),  # 營帳、帳門
    "roof": ("#5B6E8C", "#C9B994"),  # 屋頂、牆
    "ferry": ("#7A5A3A", "#F1E9D3"),  # 船身、帆
    "peak": ("#6E9580", "#4F7564"),  # 山頭、陰面
    "flag": ("#A0522D", "#5A3A2A"),  # 旗、旗桿
}
FADE = (0.58, 0.5)  # 去過／摸清：主色、第二色各往紙色淡幾成
SILHOUETTE = "#B6AE99"  # 未知（輪廓）的灰色剪影
DISC = "#F4EFDF"  # 摸清的地點底下的圓盤
DISC_FADED = "#EDE7D4"  # 去過／摸清的圓盤
RING_FADE = 0.45  # 去過／摸清：危險外圈往紙色淡幾成
DOT = "#C2BAA4"  # 淡點
BANNER_BOX = (9, -35, 26, -9)  # 所在地的紅旗佔的範圍（相對地點中心的左、上、右、下）


def icon_kind(loc: Location) -> str:
    """地點畫哪一種圖示（ICON_TAGS）：例如廣宗「城池、營寨」先符合城池，畫城牆。"""
    tags = set(loc.tags)
    return next((kind for kind, wanted in ICON_TAGS if tags & wanted), "flag")


def icon(kind: str, x: int, y: int, look: str) -> str:
    """地點圖示，中心在 x、y。look：full 全彩（所在地、看得見）、faded 淡色（去過／摸清）、ghost 灰色剪影（未知，
    門、陰面這些細節不畫）。"""
    main, second = ICON_COLORS[kind]
    if look == "faded":
        main, second = mix(main, PAPER, FADE[0]), mix(second, PAPER, FADE[1])
    elif look == "ghost":
        main = second = SILHOUETTE
    detail = look != "ghost"
    if kind == "town":
        gate = _fill(f"M{x - 2},{y + 7} v-4 a2,2 0 0 1 4,0 v4 Z", second) if detail else ""
        return _fill(f"M{x - 9},{y + 7} v-9 h3 v-3 h3 v3 h3 v-3 h3 v3 h3 v-3 h3 v3 v9 Z", main) + gate
    if kind == "camp":
        door = _fill(f"M{x - 3},{y + 7} L{x},{y + 1} L{x + 3},{y + 7} Z", second) if detail else ""
        return _fill(f"M{x - 10},{y + 7} L{x},{y - 8} L{x + 10},{y + 7} Z", main) + door
    if kind == "roof":
        roof = f"M{x - 11},{y - 1} Q{x - 6},{y - 2} {x - 4},{y - 8} L{x + 4},{y - 8} Q{x + 6},{y - 2} {x + 11},{y - 1} Z"
        return _fill(f"M{x - 7},{y - 1} h14 v8 h-14 Z", second) + _fill(roof, main)
    if kind == "ferry":
        hull = f"M{x - 11},{y + 2} L{x + 11},{y + 2} L{x + 7},{y + 8} L{x - 7},{y + 8} Z"
        return _fill(hull, main) + _fill(f"M{x - 1},{y + 1} L{x - 1},{y - 10} L{x + 8},{y + 1} Z", second)
    if kind == "peak":
        shade = _fill(f"M{x - 1},{y - 9} L{x + 10},{y + 7} L{x + 3},{y + 7} Z", second) if detail else ""
        return _fill(f"M{x - 10},{y + 7} L{x - 1},{y - 9} L{x + 10},{y + 7} Z", main) + shade
    pole = f'<path d="M{x - 4},{y + 8} V{y - 9}" stroke="{second}" stroke-width="1.8"/>'
    return pole + _fill(f"M{x - 4},{y - 9} L{x + 8},{y - 5} L{x - 4},{y - 1} Z", main)


ICON_BOX = (-12, -11, 24, 20)  # 單獨畫一個圖示的畫布（左、上、寬、高）：圖示中心在 (0, 0)；最寬的渡口與屋簷左右各 11，最高的渡口帆在上方 10，最低的船底在下方 8


def icon_svg(kind: str, look: str = "full") -> str:
    """單獨一個地點圖示（輿圖圖例用）：自成一張很小的 SVG，畫法就是地圖上的 icon()，不加圓盤與外圈；旁邊的字由網頁寫。"""
    left, top, width, height = ICON_BOX
    return (
        f'<svg class="tx-icon" viewBox="{left} {top} {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">{icon(kind, 0, 0, look)}</svg>'
    )


def banner(x: int, y: int) -> str:
    """所在地插的紅旗，插在記號右上（佔的範圍是 BANNER_BOX）。"""
    return (
        f'<path d="M{x + 11},{y - 9} V{y - 34}" stroke="#5A3A2A" stroke-width="1.8"/>'
        f'<path d="M{x + 11},{y - 34} L{x + 25},{y - 29} L{x + 11},{y - 24} Z" fill="{BANNER}"/>'
    )


def _fill(d: str, color: str) -> str:
    return f'<path d="{d}" fill="{color}"/>'
