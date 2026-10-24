"""盧植的淡彩水墨試作（1200×1600，透明底）：墨線勾形、乾筆、暖色淡彩、飛墨。進賢冠、長鬚、寬袖儒服、雙手捧簡。"""
import math, random, sys
R = random.Random("盧植・淡彩")
W, H = 1200, 1600
INK, OCHRE, SIENNA, BROWN, SLATE, VERM, SKIN = "#231f1a", "#c99a4a", "#a1683a", "#6f5236", "#5c6670", "#b4382a", "#d9b48c"

def f(v): return f"{v:.1f}".rstrip("0").rstrip(".")
def calli(pts, w0, w1, wmid=None, jitter=2.0):
    if wmid is None: wmid = max(w0, w1) * 1.15
    n = len(pts); left, right = [], []
    for i, (x, y) in enumerate(pts):
        t = i / max(1, n - 1); w = (1 - t) * ((1 - t) * w0 + t * wmid) + t * ((1 - t) * wmid + t * w1)
        if i == 0: dx, dy = pts[1][0] - x, pts[1][1] - y
        elif i == n - 1: dx, dy = x - pts[i - 1][0], y - pts[i - 1][1]
        else: dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        L = math.hypot(dx, dy) or 1; nx, ny = -dy / L, dx / L; j = R.uniform(-jitter, jitter)
        left.append((x + nx * (w / 2 + j), y + ny * (w / 2 + j))); right.append((x - nx * (w / 2 - j), y - ny * (w / 2 - j)))
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in left + right[::-1]) + " Z"
def ink(pts, w0, w1, op=0.92, wmid=None, filt="rough", color=INK, jitter=2.0):
    fl = f' filter="url(#{filt})"' if filt else ""
    return f'<path d="{calli(pts, w0, w1, wmid, jitter)}" fill="{color}" fill-opacity="{op}"{fl}/>'
def poly(pts, color, op, filt="wash"):
    d = "M" + " L".join(f"{f(x)} {f(y)}" for x, y in pts) + " Z"; fl = f' filter="url(#{filt})"' if filt else ""
    return f'<path d="{d}" fill="{color}" fill-opacity="{op}"{fl}/>'
def wobble(pts, a): return [(x + R.uniform(-a, a), y + R.uniform(-a, a)) for x, y in pts]
def curve(x0, y0, x1, y1, n=8, bend=0.0, amp=3):
    return [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t + math.sin(math.pi * t) * bend + R.uniform(-amp, amp)) for t in (i / n for i in range(n + 1))]
def splat(cx, cy, n, spread, rmax=3.0, op=0.8, color=INK):
    out = []
    for _ in range(n):
        a = R.uniform(0, math.tau); d = abs(R.gauss(0, spread)); x, y = cx + math.cos(a) * d, cy + math.sin(a) * d * 0.8
        r = R.uniform(0.5, rmax) * max(0.15, 1 - d / (spread * 3))
        out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{color}" fill-opacity="{op * R.uniform(0.35, 1):.2f}"/>')
    return "".join(out)
def outline(pts, w=5, op=0.9):
    """沿著一圈輪廓一段一段下筆，粗細有變化。"""
    out = []; n = len(pts)
    for i in range(n):
        a, c = pts[i], pts[(i + 1) % n]; m = ((a[0] + c[0]) / 2 + R.uniform(-3, 3), (a[1] + c[1]) / 2 + R.uniform(-3, 3))
        out.append(ink([a, m, c], w * R.uniform(0.3, 0.8), w * R.uniform(0.3, 1.0), op, w * R.uniform(0.9, 1.4), "rough", INK, 1.5))
    return "".join(out)

defs = '''<defs>
<filter id="rough" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="3" seed="3" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="8" xChannelSelector="R" yChannelSelector="G" result="d"/><feGaussianBlur in="d" stdDeviation="0.5"/></filter>
<filter id="dry" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency="0.08 0.9" numOctaves="2" seed="11" result="t"/><feColorMatrix in="t" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 2.4 -0.8" result="m"/><feComposite in="SourceGraphic" in2="m" operator="in" result="s"/><feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="5" result="n"/><feDisplacementMap in="s" in2="n" scale="6" xChannelSelector="R" yChannelSelector="G"/></filter>
<filter id="wash" x="-15%" y="-15%" width="130%" height="130%"><feGaussianBlur in="SourceGraphic" stdDeviation="5" result="b"/><feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="2" seed="9" result="t"/><feColorMatrix in="t" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.7 0.55" result="m"/><feComposite in="b" in2="m" operator="in" result="g"/><feTurbulence type="fractalNoise" baseFrequency="0.015" numOctaves="2" seed="4" result="n"/><feDisplacementMap in="g" in2="n" scale="16" xChannelSelector="R" yChannelSelector="G"/></filter>
<filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="18"/></filter>
</defs>'''
b = []
cx, hy = 600, 330   # 頭心
# 影子
b.append(f'<ellipse cx="{cx}" cy="1480" rx="240" ry="34" fill="{INK}" fill-opacity="0.16" filter="url(#soft)"/>')
# 袍：墨青淡彩的大塊，外加赭石的襯色；再用墨線勾
robe = [(540, 470), (470, 500), (400, 560), (330, 680), (280, 850), (250, 960), (300, 985), (380, 940), (370, 1140), (352, 1300), (336, 1460),
        (864, 1460), (848, 1300), (830, 1140), (820, 940), (900, 985), (950, 960), (920, 850), (870, 680), (800, 560), (730, 500), (660, 470)]
b.append(poly(wobble(robe, 5), SLATE, 0.5))
b.append(poly(wobble([(730, 500), (800, 560), (870, 680), (920, 850), (950, 960), (900, 985), (820, 940), (830, 1140), (848, 1300), (864, 1460), (700, 1460), (700, 520)], 6), INK, 0.16))  # 右側陰影
b.append(poly(wobble([(336, 1460), (864, 1460), (850, 1380), (350, 1380)], 6), INK, 0.12))
b.append(poly(wobble([(400, 560), (330, 680), (280, 850), (300, 985), (380, 940), (370, 1140), (352, 1300), (336, 1460), (600, 1460), (600, 520)], 5), SLATE, 0.18))
b.append(poly(wobble([(560, 480), (640, 480), (700, 1460), (500, 1460)], 4), OCHRE, 0.28))  # 襟與中幅的暖色
b.append(poly(wobble([(260, 900), (390, 920), (380, 980), (300, 990)], 4), SIENNA, 0.35))  # 袖口
b.append(poly(wobble([(810, 920), (940, 900), (900, 990), (820, 980)], 4), SIENNA, 0.35))
b.append(outline(robe, 7, 0.9))
# 衣褶：乾筆
for pts in ([(470, 560), (430, 760), (400, 930)], [(730, 560), (770, 760), (800, 930)], [(600, 500), (596, 700), (590, 1000)], [(470, 1000), (460, 1250), (450, 1440)], [(730, 1000), (742, 1250), (754, 1440)], [(540, 1050), (530, 1440)], [(660, 1050), (672, 1440)]):
    b.append(ink(curve(*pts[0], *pts[-1], 8, R.uniform(-14, 14), 3), 1.2, 4, 0.55, 6, "dry"))
# 下擺飛墨
b.append(splat(600, 1470, 60, 260, 3.6, 0.55))
# 簡：橫捧在胸前，赭石的竹片、墨線編繩
sx, sy = 460, 1000
b.append(poly(wobble([(sx, sy), (sx + 280, sy), (sx + 280, sy + 70), (sx, sy + 70)], 2), OCHRE, 0.75, "rough"))
for i in range(14):
    b.append(ink([(sx + 10 + i * 19.5, sy + 4), (sx + 10 + i * 19.5, sy + 66)], 1.5, 1.5, 0.7, 2, "rough", BROWN))
b.append(ink(curve(sx - 6, sy + 18, sx + 286, sy + 18, 12, 0, 1.5), 2, 2, 0.8, 3))
b.append(ink(curve(sx - 6, sy + 52, sx + 286, sy + 52, 12, 0, 1.5), 2, 2, 0.8, 3))
# 手：從袖口露出的兩隻手捧著簡
for hx in (430, 740):
    b.append(poly(wobble([(hx, sy + 10), (hx + 40, sy - 6), (hx + 46, sy + 60), (hx + 4, sy + 70)], 2), SKIN, 0.9, "rough"))
    b.append(outline([(hx, sy + 10), (hx + 40, sy - 6), (hx + 46, sy + 60), (hx + 4, sy + 70)], 3, 0.8))
# 頭與臉：膚色淡彩，墨線勾臉型，不細畫五官（眉、閉目一線、鼻、口各一筆）
b.append(f'<ellipse cx="{cx}" cy="{hy}" rx="92" ry="110" fill="{SKIN}" fill-opacity="0.9" filter="url(#wash)"/>')
b.append(outline([(cx - 88, hy - 40), (cx - 90, hy + 40), (cx - 50, hy + 100), (cx, hy + 112), (cx + 50, hy + 100), (cx + 90, hy + 40), (cx + 88, hy - 40)], 4, 0.85))
b.append(ink(curve(cx - 60, hy - 30, cx - 18, hy - 36, 4, -4, 1), 1, 5, 0.9, 6))   # 眉
b.append(ink(curve(cx + 18, hy - 36, cx + 60, hy - 30, 4, -4, 1), 5, 1, 0.9, 6))
b.append(ink(curve(cx - 52, hy - 6, cx - 20, hy - 4, 4, 3, 0.8), 1, 2.5, 0.85, 3))   # 目
b.append(ink(curve(cx + 20, hy - 4, cx + 52, hy - 6, 4, 3, 0.8), 2.5, 1, 0.85, 3))
b.append(ink(curve(cx - 6, hy + 10, cx + 8, hy + 44, 4, 0, 1), 1, 2, 0.6, 2.5))      # 鼻
b.append(ink(curve(cx - 22, hy + 66, cx + 22, hy + 66, 4, 2, 0.8), 1, 2, 0.7, 3))     # 口
# 鬚：長鬚一撮撮往下，墨色帶灰
for i in range(18):
    x0 = cx - 50 + i * 6 + R.uniform(-3, 3); y0 = hy + 80 + abs(i - 9) * 3
    b.append(ink(curve(x0, y0, x0 + R.uniform(-14, 14), y0 + R.uniform(180, 300) - abs(i - 9) * 12, 6, R.uniform(-10, 10), 2), 4, 0.5, R.uniform(0.5, 0.85), 5))
for i in range(6):   # 兩鬢
    for side in (-1, 1):
        x0 = cx + side * (70 + i * 3); y0 = hy + 20 + i * 8
        b.append(ink(curve(x0, y0, x0 + side * R.uniform(0, 16), y0 + R.uniform(60, 120), 5, side * 6, 2), 3, 0.5, 0.6, 4))
# 進賢冠：墨色的冠體、赭石的冠梁、兩條纓帶
cap = [(cx - 96, hy - 60), (cx + 96, hy - 60), (cx + 112, hy - 250), (cx + 40, hy - 300), (cx - 70, hy - 262)]
b.append(poly(wobble(cap, 4), INK, 0.92, "rough"))
b.append(poly(wobble([(cx - 50, hy - 100), (cx + 70, hy - 100), (cx + 80, hy - 230), (cx - 30, hy - 236)], 3), SIENNA, 0.5, "rough"))
for i in range(3):
    b.append(ink(curve(cx - 46 + i * 44, hy - 95, cx - 30 + i * 46, hy - 240, 6, 0, 2), 1.5, 3, 0.9, 4, "rough", OCHRE))
b.append(ink(curve(cx - 80, hy - 70, cx - 90, hy - 20, 5, -6, 2), 2, 4, 0.9, 5))
b.append(ink(curve(cx + 80, hy - 70, cx + 90, hy - 20, 5, 6, 2), 2, 4, 0.9, 5))
for side in (-1, 1):   # 纓帶
    b.append(ink(curve(cx + side * 86, hy - 30, cx + side * 150, hy + 420, 10, side * 30, 4), 3, 1.5, 0.85, 4, "rough", VERM))
# 飛墨
b.append(splat(cx - 330, 1000, 30, 90, 3, 0.5))
b.append(splat(cx + 340, 980, 24, 80, 3, 0.5))
b.append(splat(cx + 150, hy - 280, 14, 40, 2.2, 0.5))
svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{defs}{"".join(b)}</svg>'
open(sys.argv[1], "w", encoding="utf-8").write(svg); print("written", len(svg))
