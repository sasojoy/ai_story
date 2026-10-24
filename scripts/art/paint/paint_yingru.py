"""潁川汝南場景的淡彩水墨試作（1500×900）：毛筆形的墨塊、濾鏡暈染與飛白、暖色淡彩、宣紙紋。"""
import math, random, sys
R = random.Random("潁川汝南・淡彩")
W, H = 1500, 900
PAPER, INK = "#f1e8d6", "#231f1a"
OCHRE, SIENNA, BROWN, FIELD, WATER, VERM, MIST = "#c99a4a", "#a1683a", "#6f5236", "#8c8a5c", "#8a9ca3", "#b4382a", "#f6efe2"

def f(v): return f"{v:.1f}".rstrip("0").rstrip(".")

def calli(pts, w0, w1, wmid=None, jitter=2.0):
    """毛筆一筆：沿折線兩側算出寬度（起筆 w0、中段 wmid、收筆 w1），填成一塊。"""
    if wmid is None: wmid = max(w0, w1) * 1.15
    n = len(pts); left, right = [], []
    for i, (x, y) in enumerate(pts):
        t = i / max(1, n - 1)
        w = (1 - t) * ((1 - t) * w0 + t * wmid) + t * ((1 - t) * wmid + t * w1)
        if i == 0: dx, dy = pts[1][0] - x, pts[1][1] - y
        elif i == n - 1: dx, dy = x - pts[i - 1][0], y - pts[i - 1][1]
        else: dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        L = math.hypot(dx, dy) or 1; nx, ny = -dy / L, dx / L
        j = R.uniform(-jitter, jitter)
        left.append((x + nx * (w / 2 + j), y + ny * (w / 2 + j)))
        right.append((x - nx * (w / 2 - j), y - ny * (w / 2 - j)))
    poly = left + right[::-1]
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in poly) + " Z"

def ink(pts, w0, w1, op=0.92, wmid=None, filt="rough", color=INK, jitter=2.0):
    fl = f' filter="url(#{filt})"' if filt else ""
    return f'<path d="{calli(pts, w0, w1, wmid, jitter)}" fill="{color}" fill-opacity="{op}"{fl}/>'

def poly(pts, color, op, filt="wash", blur=None):
    d = "M" + " L".join(f"{f(x)} {f(y)}" for x, y in pts) + " Z"
    fl = f' filter="url(#{filt})"' if filt else ""
    return f'<path d="{d}" fill="{color}" fill-opacity="{op}"{fl}/>'

def wobble(pts, a): return [(x + R.uniform(-a, a), y + R.uniform(-a, a)) for x, y in pts]

def curve(x0, y0, x1, y1, n=8, bend=0.0, amp=4):
    out = []
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t; y = y0 + (y1 - y0) * t + math.sin(math.pi * t) * bend + R.uniform(-amp, amp)
        out.append((x, y))
    return out

def splat(cx, cy, n, spread, rmax=3.0, op=0.8, color=INK):
    out = []
    for _ in range(n):
        a = R.uniform(0, math.tau); d = abs(R.gauss(0, spread))
        x, y = cx + math.cos(a) * d, cy + math.sin(a) * d * 0.7
        r = R.uniform(0.5, rmax) * max(0.15, 1 - d / (spread * 3))
        out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{color}" fill-opacity="{op * R.uniform(0.35, 1):.2f}"/>')
    return "".join(out)

def mountain(x0, x1, base, peak, humps, color, op, filt="wash"):
    pts = [(x0, base)]; w = x1 - x0
    for i in range(humps):
        px = x0 + w * (i + 0.5) / humps + R.uniform(-w * 0.06, w * 0.06); py = peak + R.uniform(-30, 30)
        pts += [(px - w / humps * 0.32, (base + py) / 2 + R.uniform(-15, 15)), (px, py), (px + w / humps * 0.2, py + R.uniform(10, 40))]
    pts.append((x1, base))
    return poly(wobble(pts, 4), color, op, filt)

b = []
defs = f'''<defs>
<filter id="rough" x="-10%" y="-10%" width="120%" height="120%">
  <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="3" seed="3" result="n"/>
  <feDisplacementMap in="SourceGraphic" in2="n" scale="9" xChannelSelector="R" yChannelSelector="G" result="d"/>
  <feGaussianBlur in="d" stdDeviation="0.6"/>
</filter>
<filter id="dry" x="-10%" y="-10%" width="120%" height="120%">
  <feTurbulence type="fractalNoise" baseFrequency="0.9 0.08" numOctaves="2" seed="11" result="t"/>
  <feColorMatrix in="t" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 2.6 -0.9" result="m"/>
  <feComposite in="SourceGraphic" in2="m" operator="in" result="s"/>
  <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="5" result="n"/>
  <feDisplacementMap in="s" in2="n" scale="7" xChannelSelector="R" yChannelSelector="G"/>
</filter>
<filter id="wash" x="-15%" y="-15%" width="130%" height="130%">
  <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="b"/>
  <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="3" seed="9" result="t"/>
  <feColorMatrix in="t" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1.6 -0.15" result="m"/>
  <feComposite in="b" in2="m" operator="in" result="g"/>
  <feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves="2" seed="4" result="n"/>
  <feDisplacementMap in="g" in2="n" scale="14" xChannelSelector="R" yChannelSelector="G"/>
</filter>
<filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="14"/></filter>
<filter id="paper"><feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" seed="2"/>
  <feColorMatrix type="matrix" values="0 0 0 0 0.35  0 0 0 0 0.28  0 0 0 0 0.18  0 0 0 0.09 0"/></filter>
<filter id="stain"><feTurbulence type="fractalNoise" baseFrequency="0.006" numOctaves="2" seed="8"/>
  <feColorMatrix type="matrix" values="0 0 0 0 0.75  0 0 0 0 0.6  0 0 0 0 0.35  0 0 0 0.16 0"/></filter>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e9dfc9"/><stop offset="1" stop-color="{PAPER}" stop-opacity="0"/></linearGradient>
<linearGradient id="fog" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{MIST}" stop-opacity="0"/><stop offset="0.55" stop-color="{MIST}" stop-opacity="0.95"/><stop offset="1" stop-color="{MIST}" stop-opacity="0"/></linearGradient>
</defs>'''
b.append(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
b.append(f'<rect width="{W}" height="{H}" filter="url(#stain)"/>')
b.append(f'<rect width="{W}" height="{H * 0.45}" fill="url(#sky)"/>')

# 遠山：藍灰淡彩兩層，再一層淡墨勾稜
b.append(mountain(-100, 1000, 420, 230, 4, WATER, 0.22))
b.append(mountain(600, 1650, 430, 270, 3, WATER, 0.3))
b.append(mountain(-60, 700, 425, 300, 3, BROWN, 0.12))
for i in range(5):
    x0 = R.uniform(50, 1300); b.append(ink(curve(x0, R.uniform(250, 330), x0 + R.uniform(90, 200), R.uniform(300, 400), 6, -18, 6), 1, 4, 0.22, 5))
b.append(f'<rect x="0" y="330" width="{W}" height="200" fill="url(#fog)"/>')

# 長社城：土黃的牆、墨線、門樓
b.append(poly(wobble([(930, 520), (1500, 512), (1500, 575), (930, 580)], 3), OCHRE, 0.5))
b.append(poly(wobble([(930, 520), (1500, 512), (1500, 575), (930, 580)], 3), SIENNA, 0.22))
b.append(ink(curve(925, 522, 1500, 512, 12, 0, 2), 2, 3, 0.8, 5))
b.append(ink(curve(925, 580, 1500, 574, 12, 0, 2), 2, 2, 0.55, 3))
for i in range(13):
    x = 940 + i * 44
    b.append(poly(wobble([(x, 522), (x + 24, 521), (x + 24, 506), (x, 507)], 1.5), INK, 0.78, "rough"))
    if i % 3 == 0: b.append(ink([(x + 2, 580), (x + 3, 530)], 1, 1.5, 0.3))
# 門樓：兩層，墨色的屋頂、赭石的樓身
for (x, y, w, h) in ((1095, 506, 150, 54), (1115, 452, 110, 50)):
    b.append(poly(wobble([(x + 12, y), (x + w - 12, y), (x + w - 16, y - h + 18), (x + 16, y - h + 18)], 2), SIENNA, 0.55))
    b.append(poly(wobble([(x + 12, y), (x + w - 12, y), (x + w - 16, y - h + 18), (x + 16, y - h + 18)], 2), OCHRE, 0.3))
    rx0, rx1, ry = x - 14, x + w + 14, y - h + 20
    b.append(poly(wobble([(rx0 - 6, ry + 4), (rx0 + 20, ry - 2), (x + w / 2, ry - 24), (rx1 - 20, ry - 2), (rx1 + 6, ry + 4), (rx1 - 2, ry - 10), (x + w / 2, ry - 36), (rx0 + 2, ry - 10)], 2), INK, 0.9, "rough"))
    b.append(ink([(rx0 - 10, ry + 2), (x + w / 2, ry + 6), (rx1 + 10, ry + 2)], 2, 2, 0.95, 5))
    for k in range(4):
        b.append(ink([(x + 30 + k * 28, y - 6), (x + 30 + k * 28, y - h + 26)], 1, 1.5, 0.35))
b.append(ink([(1232, 404), (1234, 350)], 2, 1.2, 0.9))
b.append(poly(wobble([(1234, 350), (1278, 356), (1272, 372), (1282, 386), (1235, 384)], 3), VERM, 0.85, "rough"))

# 田：淡彩色塊加乾筆的壟
for i, (x0, y0, w, h, c, op) in enumerate(((40, 560, 560, 70, FIELD, 0.28), (90, 600, 640, 90, OCHRE, 0.26), (0, 650, 520, 110, FIELD, 0.22), (640, 600, 360, 60, OCHRE, 0.2))):
    b.append(poly(wobble([(x0, y0), (x0 + w, y0 - 8), (x0 + w - 40, y0 + h), (x0 - 20, y0 + h + 6)], 6), c, op))
for i in range(12):
    y = 570 + i * 17; x1 = 700 - i * 12
    b.append(ink(curve(30 + i * 10, y, x1, y + R.uniform(-6, 6), 10, 0, 3), 0.8, 2.2, 0.35 + i * 0.03, 3.5, "dry"))

# 潁水：藍灰的淡彩帶、兩岸墨線、水紋留白
river = [(0, 560), (180, 575), (380, 620), (560, 690), (760, 760), (1000, 820), (1300, 870), (1500, 890)]
band = [(x, y - 26) for x, y in river] + [(x, y + 60) for x, y in reversed(river)]
b.append(poly(wobble(band, 6), WATER, 0.42))
b.append(poly(wobble([(x, y - 10) for x, y in river] + [(x, y + 30) for x, y in reversed(river)], 6), WATER, 0.25))
b.append(ink([(x, y - 28) for x, y in river], 1.5, 3, 0.55, 4))
b.append(ink([(x, y + 64) for x, y in river], 1, 2.5, 0.45, 3.5))
for i in range(16):
    t = R.uniform(0.05, 0.95); k = int(t * (len(river) - 1)); x0, y0 = river[k]; x1, y1 = river[k + 1]
    cx = x0 + (x1 - x0) * 0.5 + R.uniform(-60, 60); cy = y0 + (y1 - y0) * 0.5 + R.uniform(0, 30)
    b.append(ink(curve(cx - R.uniform(30, 90), cy, cx + R.uniform(30, 90), cy + R.uniform(-3, 3), 5, 0, 1.5), 0.6, 1.8, 0.55, 2.5, "rough", "#fbf6ea", 0.8))
    b.append(ink(curve(cx - R.uniform(20, 70), cy + 8, cx + R.uniform(20, 70), cy + 10, 5, 0, 1.5), 0.5, 1.4, 0.4, 2, "rough", INK, 0.8))

# 楊柳三株：墨幹、長條垂枝、上一點淡綠
for (x, y, h) in ((300, 590, 170), (400, 575, 130), (1330, 640, 150)):
    b.append(ink(curve(x, y, x + 10, y - h * 0.55, 6, 14, 3) + curve(x + 10, y - h * 0.55, x + 2, y - h, 5, -10, 3)[1:], 14, 5, 0.9, 16))
    b.append(ink(curve(x + 8, y - h * 0.5, x - 40, y - h * 0.72, 5, 8, 3), 6, 2, 0.85, 7))
    b.append(poly(wobble([(x - 70, y - h * 0.95), (x + 80, y - h * 1.02), (x + 60, y - h * 0.6), (x - 50, y - h * 0.62)], 8), FIELD, 0.22))
    for i in range(22):
        sx = x + R.uniform(-55, 65); sy = y - h * R.uniform(0.6, 1.0)
        b.append(ink(curve(sx, sy, sx + R.uniform(-30, 30), sy + h * R.uniform(0.3, 0.55), 6, R.uniform(-10, 10), 2), 1.6, 0.4, 0.75, 1.8))

# 官道與行人：赭石淡彩的路、墨色人影、土黃斗笠、藍灰包袱
b.append(poly(wobble([(560, 900), (700, 800), (900, 760), (1100, 740), (1500, 745), (1500, 790), (1130, 790), (960, 810), (780, 860), (700, 900)], 8), SIENNA, 0.22))
b.append(ink(curve(560, 896, 1500, 748, 14, -20, 6), 1.5, 3, 0.3, 4, "dry"))
px, py, ph = 1040, 792, 150
b.append(f'<ellipse cx="{px}" cy="{py + 6}" rx="42" ry="9" fill="{INK}" fill-opacity="0.18" filter="url(#soft)"/>')
body = wobble([(px - 22, py - ph * 0.72), (px + 22, py - ph * 0.72), (px + 30, py - ph * 0.3), (px + 20, py), (px + 5, py), (px, py - ph * 0.22), (px - 6, py), (px - 20, py), (px - 32, py - ph * 0.3)], 3)
b.append(poly(body, INK, 0.93, "rough"))
b.append(poly(wobble([(px - 6, py - ph * 0.6), (px + 10, py - ph * 0.62), (px + 8, py - ph * 0.3), (px - 10, py - ph * 0.32)], 2), SIENNA, 0.45, "rough"))
b.append(poly(wobble([(px + 16, py - ph * 0.7), (px + 44, py - ph * 0.66), (px + 42, py - ph * 0.46), (px + 18, py - ph * 0.5)], 3), WATER, 0.7, "rough"))
b.append(f'<circle cx="{px}" cy="{py - ph * 0.84}" r="{ph * 0.075}" fill="{INK}" fill-opacity="0.95" filter="url(#rough)"/>')
b.append(poly(wobble([(px - 36, py - ph * 0.86), (px, py - ph * 1.02), (px + 36, py - ph * 0.86)], 2), OCHRE, 0.9, "rough"))
b.append(ink([(px - 38, py - ph * 0.85), (px + 38, py - ph * 0.85)], 1.5, 1.5, 0.9, 3))
b.append(ink([(px + 28, py - ph * 0.95), (px + 34, py + 4)], 3, 2, 0.9, 3.5))
b.append(splat(px - 10, py - 20, 26, 40, 2.6, 0.6))

# 路過河的地方是淺灘：幾塊踏石
for k, (sx, sy) in enumerate(((760, 822), (800, 816), (842, 808), (884, 800), (926, 792))):
    b.append(poly(wobble([(sx - 16, sy), (sx + 16, sy - 2), (sx + 12, sy + 10), (sx - 14, sy + 10)], 2), BROWN, 0.75, "rough"))
    b.append(ink([(sx - 16, sy + 10), (sx + 14, sy + 10)], 1.2, 2, 0.6, 2.5))
# 近景草與墨點、遠處的雁
for i in range(26):
    gx, gy = R.uniform(20, 560), R.uniform(760, 890)
    for k in range(4):
        b.append(ink(curve(gx + k * 5, gy, gx + k * 5 + R.uniform(-8, 8), gy - R.uniform(18, 40), 3, R.uniform(-4, 4), 1), 1.8, 0.3, 0.7, 2))
b.append(splat(260, 860, 50, 90, 3.2, 0.55))
b.append(splat(1400, 640, 30, 60, 2.4, 0.4, SIENNA))
for i in range(6):
    bx, by = 520 + i * 34, 215 + math.sin(i * 0.9) * 12; s = R.uniform(8, 13)
    b.append(ink([(bx - s, by), (bx, by + s * 0.45), (bx + s, by)], 0.8, 0.8, 0.6, 1.8))
b.append(f'<rect width="{W}" height="{H}" filter="url(#paper)"/>')

svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{defs}{"".join(b)}</svg>'
open(sys.argv[1], "w", encoding="utf-8").write(svg)
print("written", len(svg))
