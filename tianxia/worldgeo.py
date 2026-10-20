"""天下圖的幾何（輿圖重製第 2 批；輿圖簡化設計 4.1、第七章第 7 條「地面分法用離哪個地點最近」）。

- 地面格（cells）：每一州只拿自己州裡的地點分地面（沃羅諾伊）。每一格先在整張地圖的方框裡算成凸多邊形（半平面交），
  畫的時候再用那一州的輪廓裁（網頁的 clipPath）——州是不規則、凹的，凸的格子算起來最穩，邊也不會跑到州外面去。
- 相鄰的邊：同一州裡兩格共用的那一條（inner_edges，也要用那一州的輪廓裁）；兩州相接的那一段照兩邊各自的格子切開
  （cross_edges），每一小段記兩邊各是哪一格（那一州沒有地點就是 None＝沒人佔）。網頁照兩邊此刻歸誰決定畫紅線、細墨線或不畫。
- 州名擺哪（label_spot）、取景框（frame）、寫成 SVG 的 d（path）。

純幾何：不 import 內容與狀態、不看季、不看誰佔著。座標是地圖單位；Rect 一律 (x0, y0, x1, y1)。"""
from __future__ import annotations

import math

Point = tuple[float, float]
Rect = tuple[float, float, float, float]
Poly = list[tuple[Point, "int | None"]]  # 凸多邊形：每個頂點帶「從它出發的那條邊是跟第幾個種子共用」（方框的邊是 None）

EPS = 1e-9
COLLINEAR = 0.5  # 兩州的邊算同一條線：另一條的端點離這條線多近（地圖單位）
MIN_PIECE = 0.5  # 短於這個長度的一段不算（端點對不齊的零碎）
LABEL_COARSE, LABEL_FINE = 20.0, 5.0  # 找州名的位置：粗格、細格
LABEL_ASPECT = 2.0  # 州名是橫的：左右的空間打這個折再比（同樣的距離，上下比左右重要）


def fmt(v: float) -> str:
    """一位小數、去掉尾巴的 .0（-0 寫成 0）。"""
    out = f"{v:.1f}".rstrip("0").rstrip(".")
    return "0" if out in ("-0", "") else out


def path(points: list[Point], closed: bool = True) -> str:
    """SVG 的 d：M x y L x y …（closed 時收 Z）。"""
    if not points:
        return ""
    head, *rest = points
    return f"M{fmt(head[0])} {fmt(head[1])}" + "".join(f"L{fmt(x)} {fmt(y)}" for x, y in rest) + ("Z" if closed else "")


def inside(x: float, y: float, points: list[Point]) -> bool:
    """射線法：點在不在多邊形裡（同 atlas._inside；凹的、自己沿邊折返的也照算）。"""
    hit = False
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def _seg_dist(px: float, py: float, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / length))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def _dedupe(poly: Poly) -> Poly:
    """拿掉跟下一個頂點重合的頂點（留下一個：它的邊才是真的那一條）。"""
    out: Poly = []
    n = len(poly)
    for k in range(n):
        p = poly[k][0]
        q = poly[(k + 1) % n][0]
        if math.hypot(p[0] - q[0], p[1] - q[1]) > 1e-7:
            out.append(poly[k])
    return out if len(out) >= 3 else []


def _clip(poly: Poly, a: Point, b: Point, tag: int) -> Poly:
    """留下離 a 比離 b 近（或一樣近）的那一半；切出來的新邊標 tag（Sutherland–Hodgman，poly 是凸的）。"""
    nx, ny = b[0] - a[0], b[1] - a[1]
    if nx == 0 and ny == 0:
        return poly
    c = (nx * (a[0] + b[0]) + ny * (a[1] + b[1])) / 2

    def f(p: Point) -> float:
        return nx * p[0] + ny * p[1] - c

    def cross(p: Point, q: Point, fp: float, fq: float) -> Point:
        t = fp / (fp - fq)
        return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))

    out: Poly = []
    n = len(poly)
    for k in range(n):
        p, t = poly[k]
        q = poly[(k + 1) % n][0]
        fp, fq = f(p), f(q)
        if fp <= EPS:
            out.append((p, t))
            if fq > EPS:  # 出去：交點起是沿著切線的新邊
                out.append((cross(p, q, fp, fq), tag))
        elif fq <= EPS:  # 進來：交點起是原本那條邊剩下的一截
            out.append((cross(p, q, fp, fq), t))
    return _dedupe(out)


def cells(seeds: list[Point], box: Rect) -> list[Poly]:
    """每個種子在 box 裡、離它最近的那一塊（凸多邊形）；種子照傳進來的順序，邊的標記是另一個種子的索引。"""
    x0, y0, x1, y1 = box
    square: Poly = [((x0, y0), None), ((x1, y0), None), ((x1, y1), None), ((x0, y1), None)]
    out = []
    for i, a in enumerate(seeds):
        poly = square
        for j, b in enumerate(seeds):
            if j != i and poly:
                poly = _clip(poly, a, b, j)
        out.append(poly)
    return out


def inner_edges(polys: list[Poly]) -> list[tuple[int, int, Point, Point]]:
    """同一組種子兩兩共用的邊（i < j，一對一條）。"""
    out = []
    for i, poly in enumerate(polys):
        n = len(poly)
        for k in range(n):
            p, tag = poly[k]
            q = poly[(k + 1) % n][0]
            if tag is not None and tag > i and math.hypot(q[0] - p[0], q[1] - p[1]) > MIN_PIECE:
                out.append((i, tag, p, q))
    return out


def _edges(points: list[Point]):
    n = len(points)
    for k in range(n):
        yield points[k], points[(k + 1) % n]


def _on_map_edge(p: Point, q: Point, width: float, height: float) -> bool:
    return (p[0] == q[0] and p[0] in (0, width)) or (p[1] == q[1] and p[1] in (0, height))


def shared_borders(regions: list[tuple[str, list[Point]]], width: float, height: float) -> list[tuple[str, str, Point, Point]]:
    """兩州相接的那幾段：兩州各有一條邊在同一條線上、而且有重疊（照 regions 的先後寫成 (前, 後, 起, 迄)）；沿地圖外緣的不算。"""
    out = []
    for ia, (ida, pa) in enumerate(regions):
        for idb, pb in regions[ia + 1:]:
            for p1, q1 in _edges(pa):
                dx, dy = q1[0] - p1[0], q1[1] - p1[1]
                length = math.hypot(dx, dy)
                if length < MIN_PIECE or _on_map_edge(p1, q1, width, height):
                    continue
                for p2, q2 in _edges(pb):
                    if _on_map_edge(p2, q2, width, height):
                        continue
                    off = [abs(dx * (pt[1] - p1[1]) - dy * (pt[0] - p1[0])) / length for pt in (p2, q2)]
                    if max(off) > COLLINEAR:
                        continue
                    ta = ((p2[0] - p1[0]) * dx + (p2[1] - p1[1]) * dy) / (length * length)
                    tb = ((q2[0] - p1[0]) * dx + (q2[1] - p1[1]) * dy) / (length * length)
                    lo, hi = max(0.0, min(ta, tb)), min(1.0, max(ta, tb))
                    if (hi - lo) * length > MIN_PIECE:
                        out.append((ida, idb, (p1[0] + lo * dx, p1[1] + lo * dy), (p1[0] + hi * dx, p1[1] + hi * dy)))
    return out


def _span(p: Point, q: Point, poly: Poly) -> tuple[float, float] | None:
    """線段 p→q 落在凸多邊形 poly 裡的那一截（參數 t 的區間；Cyrus–Beck）；沒有交集是 None。"""
    if len(poly) < 3:
        return None
    pts = [v for v, _ in poly]
    cx, cy = sum(v[0] for v in pts) / len(pts), sum(v[1] for v in pts) / len(pts)
    lo, hi = 0.0, 1.0
    dx, dy = q[0] - p[0], q[1] - p[1]
    for a, b in _edges(pts):
        ex, ey = b[0] - a[0], b[1] - a[1]
        side = ex * (cy - a[1]) - ey * (cx - a[0])
        sign = 1.0 if side >= 0 else -1.0
        g0 = sign * (ex * (p[1] - a[1]) - ey * (p[0] - a[0]))
        g1 = sign * (ex * dy - ey * dx)
        if abs(g1) < EPS:
            if g0 < -1e-7:
                return None
            continue
        t = -g0 / g1
        if g1 > 0:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
        if lo > hi + 1e-12:
            return None
    return (lo, hi) if hi - lo > 1e-9 else None


def split(p: Point, q: Point, polys: list[Poly]) -> list[tuple[float, float, int]]:
    """線段 p→q 被一組凸格切成幾段：(t0, t1, 第幾格)，照 t 排。"""
    out = []
    for i, poly in enumerate(polys):
        span = _span(p, q, poly)
        if span is not None:
            out.append((span[0], span[1], i))
    return sorted(out)


def _owner(t: float, spans: list[tuple[float, float, int]]) -> int | None:
    for lo, hi, i in spans:
        if lo - 1e-9 <= t <= hi + 1e-9:
            return i
    return None


def cross_edges(
    regions: list[tuple[str, list[Point]]], seeds: dict[str, list[tuple[str, Point]]], box: Rect,
) -> list[tuple[str | None, str | None, Point, Point]]:
    """兩州相接的每一小段，兩邊各是哪一格：(前一州那一格的 id, 後一州那一格的 id, 起, 迄)；那一州沒有種子是 None。
    同一對的相鄰幾段接成一段。seeds：州 id → [(格子的 id, 座標)]；box 是整張地圖 (0, 0, 寬, 高)。"""
    polys = {rid: cells([pt for _, pt in seeds.get(rid, [])], box) for rid, _ in regions}
    out = []
    for ra, rb, p, q in shared_borders(regions, box[2], box[3]):
        sa, sb = split(p, q, polys[ra]), split(p, q, polys[rb])
        cuts = sorted({0.0, 1.0, *(t for lo, hi, _ in sa + sb for t in (lo, hi) if 0 < t < 1)})
        runs: list[list] = []  # [a, b, t0, t1]
        for t0, t1 in zip(cuts, cuts[1:]):
            if t1 - t0 < 1e-9:
                continue
            mid = (t0 + t1) / 2
            ia, ib = _owner(mid, sa), _owner(mid, sb)
            a = seeds[ra][ia][0] if ia is not None else None
            b = seeds[rb][ib][0] if ib is not None else None
            if runs and runs[-1][0] == a and runs[-1][1] == b:
                runs[-1][3] = t1
            else:
                runs.append([a, b, t0, t1])

        def at(t: float, p: Point = p, q: Point = q) -> Point:
            return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))

        out += [(a, b, at(t0), at(t1)) for a, b, t0, t1 in runs]
    return [e for e in out if math.hypot(e[3][0] - e[2][0], e[3][1] - e[2][1]) > MIN_PIECE]


def clip_rect(points: list[Point], rect: Rect) -> list[Point]:
    """多邊形裁進方框（Sutherland–Hodgman；凹的照裁，可能沿框邊多出一來一回的零面積段，判斷「在不在裡面」不受影響）。"""
    x0, y0, x1, y1 = rect
    planes = ((lambda p: p[0] - x0, 0), (lambda p: x1 - p[0], 0), (lambda p: p[1] - y0, 1), (lambda p: y1 - p[1], 1))
    poly = list(points)
    for f, _ in planes:
        if not poly:
            break
        out = []
        for k in range(len(poly)):
            p, q = poly[k], poly[(k + 1) % len(poly)]
            fp, fq = f(p), f(q)
            if fp >= 0:
                out.append(p)
                if fq < 0:
                    t = fp / (fp - fq)
                    out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
            elif fq >= 0:
                t = fp / (fp - fq)
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        poly = out
    return poly


def label_spot(polygon: list[Point], frame_rect: Rect, places: list[Point]) -> Point:
    """州名擺哪：（州 ∩ 取景框）裡離邊與地點都最遠的一點（左右的距離打 LABEL_ASPECT 折：字是橫的）。粗格找、細格修。
    整州都在框外（或小到放不下一格）時用頂點的平均。"""
    return label_spots(polygon, frame_rect, places, 1)[0]


LABEL_APART = 80.0  # 備選的州名位置彼此至少隔多遠（地圖單位）
LABEL_KEEP = 0.4  # 備選的分數至少要有最好那一個的幾成


def label_spots(polygon: list[Point], frame_rect: Rect, places: list[Point], n: int = 4) -> list[Point]:
    """州名可以擺的幾個位置，好的在前（第一個同 label_spot）：網頁照螢幕上的字級量州名框，前一個會壓到別州的州名就換下一個。
    彼此隔 LABEL_APART 以上、分數不到最好那一個 LABEL_KEEP 成的不列。"""
    poly = clip_rect(polygon, frame_rect) or list(polygon)
    squash = [(x / LABEL_ASPECT, y) for x, y in poly]
    marks = [(x / LABEL_ASPECT, y) for x, y in places]

    def score(x: float, y: float) -> float:
        sx = x / LABEL_ASPECT
        edge = min(_seg_dist(sx, y, a, b) for a, b in _edges(squash))
        near = min((math.hypot(sx - mx, y - my) for mx, my in marks), default=edge)
        return min(edge, near)

    xs, ys = [p[0] for p in poly], [p[1] for p in poly]

    def scan(xa: float, xb: float, ya: float, yb: float, step: float) -> list[tuple[float, float, float]]:
        found = []
        y = ya + step / 2
        while y < yb:
            x = xa + step / 2
            while x < xb:
                if inside(x, y, poly):
                    found.append((score(x, y), x, y))
                x += step
            y += step
        return found

    coarse = scan(min(xs), max(xs), min(ys), max(ys), LABEL_COARSE)
    if not coarse:
        return [(round(sum(xs) / len(xs), 1), round(sum(ys) / len(ys), 1))]
    coarse.sort(key=lambda t: (-t[0], t[2], t[1]))
    picks: list[tuple[float, float, float]] = []
    for s, x, y in coarse:  # 好的在前，彼此隔開；每一個再用細格修一次
        if len(picks) >= n or s < coarse[0][0] * LABEL_KEEP:
            break
        if all(math.hypot(x - px, y - py) >= LABEL_APART for _, px, py in picks):
            fine = scan(x - LABEL_COARSE, x + LABEL_COARSE, y - LABEL_COARSE, y + LABEL_COARSE, LABEL_FINE) or [(s, x, y)]
            picks.append(max(fine, key=lambda t: (t[0], -t[2], -t[1])))
    return [(round(x, 1), round(y, 1)) for _, x, y in picks]


def frame(points: list[Point], width: float, height: float, margin: float) -> Rect:
    """取景框：這些點的外框往外加 margin，夾在地圖裡。"""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (max(0, min(xs) - margin), max(0, min(ys) - margin), min(width, max(xs) + margin), min(height, max(ys) + margin))
