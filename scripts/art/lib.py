"""第一批圖的向量水墨工具（圖像版第八章；PM 2026-10-24 畫的第一版）。

全部是黑墨在宣紙色上：淡墨當遠山與水氣（高斯模糊的色塊）、濃墨當近景與人影（實心）、
筆觸是帶抖動的折線、墨點是隨機的小圓；每一張用自己名字當亂數種子，重跑一樣。
產出的 SVG 不含任何字（文字由畫面蓋上去）。只有 scripts/art/ 的幾支讀它。
"""
from __future__ import annotations

import math
import random

PAPER = "#f4ede0"
INK = "#1d1912"


def rng_for(name: str) -> random.Random:
    return random.Random(f"天下大勢｜第一批圖｜{name}")


def fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def path_d(points, close=False) -> str:
    d = "M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in points)
    return d + (" Z" if close else "")


def jitter(points, rng: random.Random, amount: float):
    return [(x + rng.uniform(-amount, amount), y + rng.uniform(-amount, amount)) for x, y in points]


def stroke(points, width: float, rng: random.Random, opacity: float = 0.9, amount: float = 1.2, cap="round") -> str:
    """一筆：帶抖動的折線，粗細與濃淡給定。"""
    pts = jitter(points, rng, amount)
    return (f'<path d="{path_d(pts)}" fill="none" stroke="{INK}" stroke-width="{fmt(width)}" '
            f'stroke-opacity="{opacity}" stroke-linecap="{cap}" stroke-linejoin="round"/>')


def brush(points, width: float, rng: random.Random, opacity: float = 0.9, amount: float = 1.0) -> str:
    """一筆有粗有細的毛筆：同一條線疊三道，中段最粗、兩頭收尖。"""
    out = []
    n = len(points)
    for i in range(1, n):
        t = i / n
        w = width * (0.35 + 0.65 * math.sin(math.pi * t))
        seg = jitter([points[i - 1], points[i]], rng, amount)
        out.append(f'<path d="{path_d(seg)}" fill="none" stroke="{INK}" stroke-width="{fmt(max(0.6, w))}" '
                   f'stroke-opacity="{opacity}" stroke-linecap="round"/>')
    return "".join(out)


def wash(points, opacity: float, blur: float = 0.0, rng: random.Random | None = None, amount: float = 0.0) -> str:
    """淡墨色塊：遠山、水氣、地面。blur 給了就套高斯模糊。"""
    pts = jitter(points, rng, amount) if rng and amount else points
    f = f' filter="url(#blur{int(blur)})"' if blur else ""
    return f'<path d="{path_d(pts, close=True)}" fill="{INK}" fill-opacity="{opacity}"{f}/>'


def splatter(rng: random.Random, cx: float, cy: float, n: int, spread: float, rmax: float = 2.2, opacity: float = 0.7) -> str:
    out = []
    for _ in range(n):
        a = rng.uniform(0, math.tau)
        d = abs(rng.gauss(0, spread))
        x, y = cx + math.cos(a) * d, cy + math.sin(a) * d * 0.6
        r = rng.uniform(0.4, rmax) * max(0.2, 1 - d / (spread * 3))
        out.append(f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(r)}" fill="{INK}" fill-opacity="{opacity * rng.uniform(0.4, 1)}"/>')
    return "".join(out)


def mountain(rng: random.Random, x0: float, x1: float, base: float, peak: float, opacity: float, blur: float = 0, humps: int = 3) -> str:
    """一排遠山：幾座山峰連起來的淡墨。"""
    pts = [(x0, base)]
    w = x1 - x0
    for i in range(humps):
        px = x0 + w * (i + 0.5) / humps + rng.uniform(-w * 0.08, w * 0.08)
        py = peak + rng.uniform(-18, 18)
        pts.append((px - w / humps * 0.3, (base + py) / 2 + rng.uniform(-10, 10)))
        pts.append((px, py))
    pts.append((x1, base))
    return wash(pts, opacity, blur, rng, 2)


def ground(rng: random.Random, y: float, width: float, opacity: float = 0.12, blur: float = 6) -> str:
    return wash([(0, y), (width, y - 6), (width, y + 60), (0, y + 60)], opacity, blur, rng, 3)


def mist(x: float, y: float, w: float, h: float, opacity: float = 0.5) -> str:
    return f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" fill="url(#mist)" fill-opacity="{opacity}"/>'


def water(rng: random.Random, x0: float, x1: float, y: float, lines: int = 6, opacity: float = 0.35) -> str:
    out = []
    for i in range(lines):
        yy = y + i * rng.uniform(6, 11)
        a = rng.uniform(x0, x0 + (x1 - x0) * 0.4)
        b = rng.uniform(a + 40, x1)
        out.append(stroke([(a, yy), ((a + b) / 2, yy + rng.uniform(-2, 2)), (b, yy)], rng.uniform(0.8, 1.6), rng, opacity * rng.uniform(0.5, 1), 0.8))
    return "".join(out)


def pine(rng: random.Random, x: float, y: float, h: float, opacity: float = 0.9) -> str:
    """松：一根彎幹，幾層橫出去的針葉。"""
    out = [brush([(x, y), (x + rng.uniform(-4, 4), y - h * 0.5), (x + rng.uniform(-8, 8), y - h)], h * 0.08, rng, opacity)]
    for i in range(4):
        t = 0.35 + i * 0.18
        yy = y - h * t
        span = h * (0.42 - i * 0.07)
        side = 1 if i % 2 == 0 else -1
        out.append(brush([(x, yy), (x + side * span * 0.5, yy - 3), (x + side * span, yy + 2)], h * 0.05, rng, opacity * 0.9))
        out.append(wash([(x + side * span * 0.15, yy - 2), (x + side * span, yy + 1), (x + side * span * 0.5, yy - h * 0.08)], opacity * 0.8, 0, rng, 1))
    return "".join(out)


def willow(rng: random.Random, x: float, y: float, h: float, opacity: float = 0.8) -> str:
    out = [brush([(x, y), (x + 6, y - h * 0.6), (x + 2, y - h)], h * 0.07, rng, opacity)]
    for i in range(7):
        sx = x + rng.uniform(-6, 10)
        sy = y - h * rng.uniform(0.6, 1.0)
        out.append(stroke([(sx, sy), (sx + rng.uniform(-14, 18), sy + h * 0.25), (sx + rng.uniform(-10, 22), sy + h * 0.55)], 1.2, rng, opacity * 0.7, 1.5))
    return "".join(out)


def bare_tree(rng: random.Random, x: float, y: float, h: float, opacity: float = 0.9) -> str:
    out = [brush([(x, y), (x + 3, y - h * 0.55), (x - 2, y - h * 0.8)], h * 0.07, rng, opacity)]
    for i in range(5):
        t = rng.uniform(0.45, 0.85)
        bx, by = x + 1, y - h * t
        side = rng.choice((-1, 1))
        out.append(brush([(bx, by), (bx + side * h * 0.18, by - h * 0.12), (bx + side * h * 0.3, by - h * 0.28)], h * 0.03, rng, opacity * 0.85))
    return "".join(out)


def grass(rng: random.Random, x: float, y: float, n: int = 5, h: float = 10, opacity: float = 0.8) -> str:
    out = []
    for i in range(n):
        gx = x + rng.uniform(-8, 8)
        out.append(stroke([(gx, y), (gx + rng.uniform(-4, 4), y - h * rng.uniform(0.6, 1))], 1.0, rng, opacity, 0.5))
    return "".join(out)


def figure(rng: random.Random, x: float, y: float, h: float, hat: bool = True, pole: bool = False, opacity: float = 0.95, lean: float = 0) -> str:
    """一個人影：斗笠或髮髻、斜肩的袍、兩腿；y 是腳底。lean 正數往右傾。"""
    head_r = h * 0.075
    hy = y - h * 0.86
    out = []
    body = [(x - h * 0.13 + lean, y - h * 0.72), (x + h * 0.13 + lean, y - h * 0.72), (x + h * 0.17, y - h * 0.3), (x + h * 0.11, y), (x + h * 0.02, y), (x, y - h * 0.22), (x - h * 0.04, y), (x - h * 0.13, y), (x - h * 0.19, y - h * 0.3)]
    out.append(wash(body, opacity, 0, rng, h * 0.012))
    out.append(f'<circle cx="{fmt(x + lean)}" cy="{fmt(hy)}" r="{fmt(head_r)}" fill="{INK}" fill-opacity="{opacity}"/>')
    if hat:
        out.append(wash([(x - h * 0.2 + lean, hy - head_r * 0.2), (x + lean, hy - head_r * 1.9), (x + h * 0.2 + lean, hy - head_r * 0.2)], opacity, 0, rng, 1))
    if pole:
        out.append(stroke([(x + h * 0.16, y - h * 0.95), (x + h * 0.2, y + 2)], h * 0.025, rng, opacity, 0.5))
    out.append(splatter(rng, x, y - h * 0.3, 6, h * 0.12, 1.4, 0.5))
    return "".join(out)


def roof(rng: random.Random, x: float, y: float, w: float, h: float, opacity: float = 0.9) -> str:
    """一片翹起的屋頂（正面看）：中間平、兩端往上翹。y 是簷口。"""
    pts = [(x - w * 0.08, y - h * 0.35), (x + w * 0.1, y), (x + w * 0.9, y), (x + w * 1.08, y - h * 0.35), (x + w * 0.85, y - h * 0.5), (x + w * 0.5, y - h), (x + w * 0.15, y - h * 0.5)]
    return wash(pts, opacity, 0, rng, 1.2) + brush([(x - w * 0.1, y - h * 0.38), (x + w * 0.5, y + 2), (x + w * 1.1, y - h * 0.38)], 2.2, rng, opacity)


def building(rng: random.Random, x: float, y: float, w: float, h: float, storeys: int = 1, opacity: float = 0.85) -> str:
    """樓：幾層屋頂疊上去，牆是淡墨。y 是地面。"""
    out = []
    for i in range(storeys):
        sw = w * (1 - i * 0.18)
        sx = x + (w - sw) / 2
        top = y - h * (i + 1) / storeys
        out.append(wash([(sx + sw * 0.1, y - h * i / storeys), (sx + sw * 0.9, y - h * i / storeys), (sx + sw * 0.85, top + 8), (sx + sw * 0.15, top + 8)], opacity * 0.35, 0, rng, 0.8))
        out.append(roof(rng, sx, top + 8, sw, h / storeys * 0.45, opacity))
    return "".join(out)


def wall(rng: random.Random, x0: float, x1: float, y: float, h: float, opacity: float = 0.75, crenel: int = 12) -> str:
    out = [wash([(x0, y), (x1, y), (x1, y - h), (x0, y - h)], opacity * 0.6, 0, rng, 1)]
    step = (x1 - x0) / crenel
    for i in range(crenel):
        if i % 2 == 0:
            cx = x0 + i * step
            out.append(wash([(cx, y - h), (cx + step, y - h), (cx + step, y - h - h * 0.18), (cx, y - h - h * 0.18)], opacity, 0, rng, 0.6))
    out.append(brush([(x0, y - h), (x1, y - h)], 2, rng, opacity))
    return "".join(out)


def flag(rng: random.Random, x: float, y: float, h: float, opacity: float = 0.9, side: int = 1) -> str:
    out = [stroke([(x, y), (x, y - h)], 1.6, rng, opacity, 0.4)]
    out.append(wash([(x, y - h), (x + side * h * 0.45, y - h + h * 0.12), (x + side * h * 0.4, y - h + h * 0.3), (x, y - h + h * 0.36)], opacity * 0.9, 0, rng, 1.5))
    return "".join(out)


def tent(rng: random.Random, x: float, y: float, w: float, h: float, opacity: float = 0.8) -> str:
    return wash([(x, y), (x + w, y), (x + w * 0.55, y - h), (x + w * 0.45, y - h)], opacity, 0, rng, 1) + brush([(x + w * 0.5, y - h - 6), (x + w * 0.5, y - h * 0.3)], 1.5, rng, opacity)


def boat(rng: random.Random, x: float, y: float, w: float, opacity: float = 0.9, boatman: bool = True) -> str:
    out = [wash([(x, y - 6), (x + w, y - 8), (x + w * 0.9, y + 4), (x + w * 0.1, y + 4)], opacity, 0, rng, 1)]
    out.append(brush([(x - 6, y - 10), (x + w * 0.5, y + 2), (x + w + 8, y - 12)], 2.2, rng, opacity))
    if boatman:
        out.append(figure(rng, x + w * 0.75, y - 6, w * 0.55, hat=True, pole=True, opacity=opacity))
    return "".join(out)


def horse(rng: random.Random, x: float, y: float, h: float, opacity: float = 0.95, running: bool = True) -> str:
    """馬的側影：身、頸、頭、四腿，y 是蹄。"""
    body = [(x, y - h * 0.5), (x + h * 0.9, y - h * 0.55), (x + h * 1.0, y - h * 0.38), (x + h * 0.85, y - h * 0.28), (x + h * 0.15, y - h * 0.26), (x - h * 0.05, y - h * 0.38)]
    out = [wash(body, opacity, 0, rng, h * 0.02)]
    out.append(wash([(x + h * 0.85, y - h * 0.55), (x + h * 1.05, y - h * 0.95), (x + h * 1.25, y - h * 0.92), (x + h * 1.3, y - h * 0.78), (x + h * 1.12, y - h * 0.72), (x + h * 1.0, y - h * 0.45)], opacity, 0, rng, h * 0.02))
    legs = [((x + h * 0.1, y - h * 0.3), (x - h * 0.15 if running else x + h * 0.08, y)), ((x + h * 0.25, y - h * 0.3), (x + h * 0.3, y)), ((x + h * 0.75, y - h * 0.3), (x + h * 0.95 if running else x + h * 0.72, y)), ((x + h * 0.88, y - h * 0.3), (x + h * 0.8, y))]
    for a, b in legs:
        out.append(brush([a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), b], h * 0.07, rng, opacity))
    out.append(brush([(x, y - h * 0.5), (x - h * 0.25, y - h * 0.6), (x - h * 0.4, y - h * 0.45)], h * 0.05, rng, opacity * 0.8))
    for i in range(4):
        out.append(stroke([(x + h * 0.95 + i * 3, y - h * 0.95 - i * 2), (x + h * 0.8 + i * 3, y - h * 0.7)], 1.5, rng, opacity * 0.7, 1))
    return "".join(out)


def birds(rng: random.Random, x: float, y: float, n: int = 5, opacity: float = 0.7) -> str:
    out = []
    for i in range(n):
        bx, by = x + i * rng.uniform(12, 22), y + rng.uniform(-10, 10)
        s = rng.uniform(4, 8)
        out.append(stroke([(bx - s, by), (bx, by + s * 0.5), (bx + s, by)], 1.2, rng, opacity, 0.5))
    return "".join(out)


def moon(x: float, y: float, r: float) -> str:
    return (f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(r)}" fill="{INK}" fill-opacity="0.12" filter="url(#blur6)"/>'
            f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(r * 0.8)}" fill="#fbf7ee" stroke="{INK}" stroke-opacity="0.5" stroke-width="1.2"/>')


def smoke(rng: random.Random, x: float, y: float, h: float, opacity: float = 0.35) -> str:
    pts = [(x, y)]
    for i in range(1, 6):
        pts.append((x + rng.uniform(-10, 10) * i * 0.4, y - h * i / 5))
    return stroke(pts, 2.5, rng, opacity, 2) + stroke(pts, 7, rng, opacity * 0.3, 3)


def svg(width: int, height: int, body: str, paper: bool = True, grain: bool = True) -> str:
    defs = (
        '<defs>'
        '<filter id="blur2" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="2"/></filter>'
        '<filter id="blur4" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="4"/></filter>'
        '<filter id="blur6" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="6"/></filter>'
        '<filter id="blur10" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="10"/></filter>'
        '<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7"/>'
        '<feColorMatrix type="matrix" values="0 0 0 0 0.12 0 0 0 0 0.1 0 0 0 0 0.07 0 0 0 0.07 0"/></filter>'
        '<linearGradient id="mist" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f4ede0" stop-opacity="0"/><stop offset="1" stop-color="#f4ede0" stop-opacity="1"/></linearGradient>'
        '</defs>'
    )
    bg = f'<rect width="{width}" height="{height}" fill="{PAPER}"/>' if paper else ""
    gr = f'<rect width="{width}" height="{height}" filter="url(#grain)"/>' if (paper and grain) else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
            f'{defs}{bg}{gr}{body}</svg>')
