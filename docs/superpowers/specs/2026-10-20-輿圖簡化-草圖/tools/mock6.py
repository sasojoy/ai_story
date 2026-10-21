# 方案一的天下圖改版：大區裡面要看得出前線在哪——每一區的地面照「離哪個地點最近」分給那個地點的佔領方（小六角格拼成），
# 官與巾相接的格邊畫成紅色的前線，有主與沒人佔相接的畫細線。其餘同 mock5（字待 joy 潤）。
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mock5 import GOLD, INK, ME, MINI, OUT, P, PAPER, RED, SIDES, b, clean_base, holder, page, places, prime, region_paths  # noqa: E402

R = 11  # 六角格半徑（地圖單位）
HW, VS = math.sqrt(3) * R, 1.5 * R


def polygon(d):
    return [(float(x), float(y)) for x, y in re.findall(r"(-?\d+\.?\d*),(-?\d+\.?\d*)", d)]


def inside(pt, poly):
    x, y = pt
    hit = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1:
            hit = not hit
    return hit


def hexpts(cx, cy):
    return [(cx + R * math.cos(math.radians(60 * i - 30)), cy + R * math.sin(math.radians(60 * i - 30))) for i in range(6)]


def tianxia_map2():
    base = clean_base()
    base = re.sub(r'<text class="tx-region-name"[^>]*>[^<]*</text>', "", base)
    out = [f'<g opacity=".5">{base}</g>']
    cells = {}  # (row, col) → (cx, cy, holder)
    for rid, d in region_paths().items():
        poly = polygon(d)
        mine = [p for p in places if p["region"] == rid]
        xs, ys = [x for x, _ in poly], [y for _, y in poly]
        r0, r1 = int((min(ys) - R) / VS), int((max(ys) + R) / VS) + 1
        for row in range(r0, r1 + 1):
            cy = row * VS
            c0, c1 = int((min(xs) - HW) / HW), int((max(xs) + HW) / HW) + 1
            for col in range(c0, c1 + 1):
                cx = col * HW + (HW / 2 if row % 2 else 0)
                if not inside((cx, cy), poly):
                    continue
                near = min(mine, key=lambda p: (p["x"] - cx) ** 2 + (p["y"] - cy) ** 2)
                cells[(row, col)] = (cx, cy, holder(near["id"]))
    fills = {"guan": "#8FAACB", "huang": "#E3C06A", None: "#D6D0C1"}
    for (row, col), (cx, cy, h) in cells.items():
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in hexpts(cx, cy))
        out.append(f'<polygon points="{pts}" fill="{fills[h]}" stroke="{fills[h]}" stroke-width=".6" opacity=".82"/>')
    # 前線：相鄰兩格一官一巾，共用的那一條邊畫紅；一邊有主一邊沒人佔畫細線
    front, border = [], []
    for (row, col), (cx, cy, h) in cells.items():
        pts = hexpts(cx, cy)
        odd = row % 2
        nbrs = [(row, col + 1), (row + 1, col + odd), (row + 1, col + odd - 1), (row, col - 1), (row - 1, col + odd - 1), (row - 1, col + odd)]
        for i, key in enumerate(nbrs):
            if key not in cells:
                continue
            h2 = cells[key][2]
            if h == h2:
                continue
            a, c = pts[i], pts[(i + 1) % 6]
            seg = f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{c[0]:.1f}" y2="{c[1]:.1f}"/>'
            (front if h and h2 else border).append(seg)
    out.append(f'<g stroke="{INK}" stroke-width="1.2" opacity=".45" stroke-linecap="round">{"".join(border)}</g>')
    out.append(f'<g stroke="{RED}" stroke-width="5" stroke-linecap="round">{"".join(front)}</g>')
    for rid, d in region_paths().items():
        out.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="2.4" stroke-linejoin="round"/>')
    for p in places:
        if prime(p["id"]):
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="7" fill="{GOLD if holder(p["id"]) else PAPER}" stroke="{GOLD}" stroke-width="2.5"/>')
    tally = {}
    for p in places:
        t = tally.setdefault(p["region"], {"guan": 0, "huang": 0, "prime": 0})
        if holder(p["id"]) in ("guan", "huang"):
            t[holder(p["id"])] += 1
        if prime(p["id"]):
            t["prime"] += 1
    for r in b["regions"]:
        t = tally.get(r["id"], {"guan": 0, "huang": 0, "prime": 0})
        cx, cy = r["cx"], r["cy"] - 10
        out.append(f'<text x="{cx}" y="{cy}" font-size="44" text-anchor="middle" fill="{INK}" stroke="{PAPER}" stroke-width="8" paint-order="stroke" font-weight="700" style="font-family:serif;letter-spacing:6px">{r["name"]}</text>')
        parts = [f'<tspan fill="{SIDES["guan"][1]}">官 {t["guan"]}</tspan>', f'<tspan fill="{SIDES["huang"][1]}">巾 {t["huang"]}</tspan>', f'<tspan fill="{GOLD}">寶 {t["prime"]}</tspan>']
        out.append(f'<text x="{cx}" y="{cy + 34}" font-size="24" text-anchor="middle" font-weight="700" stroke="{PAPER}" stroke-width="7" paint-order="stroke" style="font-family:serif">{"　".join(parts)}</text>')
    me = P[ME]
    out.append(f'<circle cx="{me["x"]}" cy="{me["y"]}" r="14" fill="{RED}" stroke="{PAPER}" stroke-width="4"/><path d="M {me["x"] + 10} {me["y"] - 12} V {me["y"] - 60} L {me["x"] + 48} {me["y"] - 48} L {me["x"] + 10} {me["y"] - 36}" fill="{RED}" stroke="{PAPER}" stroke-width="3"/>')
    return "".join(out)


(OUT / "方案一-天下圖.html").write_text(page("天下圖", "0 -130 900 1470", tianxia_map2(), '<span class="k">天下</span><span class="q">🔍 找地點、找人物</span><span>⏱ 版圖</span>', MINI, "xMidYMin meet"), encoding="utf-8")
print("天下圖改好")
