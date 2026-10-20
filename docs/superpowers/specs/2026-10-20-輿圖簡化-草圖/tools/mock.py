# 輿圖風格草圖（三種，同一塊潁川、同一份領地資料、同一張抽屜卡）：讀 map_base.json／map_state.json，吐 mocks/*.html。
# 不是真畫面：只畫四樣東西——誰的領地、高級資源領地、你在哪、這裡悟什麼。字待 joy 潤。
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "mocks"
OUT.mkdir(exist_ok=True)
b = json.load(open(HERE / "map_base.json", encoding="utf-8"))
s = json.load(open(HERE / "map_state.json", encoding="utf-8"))
places, st, edges = b["places"], s["places"], b["edges"]
P = {p["id"]: p for p in places}
ME = "yingchuan"
VB = (150, 620, 500, 1003)  # 看的那一塊（地圖單位）：x, y, w, h（洛陽到汝南，潁川在中間）
SIDES = {"guan": ("官軍", "#3D5F8F", "#9DB4D3"), "huang": ("黃巾", "#B9821A", "#E7C778")}
INS = {"feng": ("風", "#2B8A80"), "huo": ("火", "#CF4F27"), "shui": ("水", "#2C68B0"), "shan": ("山", "#8A5A33")}
GOLD, RED, INK, PAPER = "#C9962B", "#A8322A", "#2B241B", "#F7F1E3"


def holder(pid):
    return st[pid]["control"]


def prime(pid):
    return st[pid]["kind"] == "neutral"


def in_view(p, pad=60):
    x0, y0, w, h = VB
    return x0 - pad <= p["x"] <= x0 + w + pad and y0 - pad <= p["y"] <= y0 + h + pad


# ── 手畫的地形（地圖單位；只給草圖用） ──
RIVERS = {
    "黃河": "M 60 696 C 250 706, 450 700, 740 714",
    "潁水": "M 300 790 C 380 880, 470 950, 500 1030 C 530 1110, 600 1200, 640 1345",
    "淯水": "M 50 950 C 95 1050, 70 1150, 110 1345",
}
MOUNTAINS = [(335, 862, "嵩山"), (112, 738, "北邙山"), (300, 1240, "桐柏山"), (40, 1000, "伏牛山"), (520, 850, "")]


def peaks(cx, cy, scale=1.0):
    pts = [(-44, 12), (-24, -18), (-8, 2), (8, -28), (24, -4), (40, -18), (56, 12)]
    return "M " + " L ".join(f"{cx + x * scale:.0f} {cy + y * scale:.0f}" for x, y in pts)


def road_lines(stroke, width, dash=""):
    out = []
    for a, bb in edges:
        if a in P and bb in P:
            A, B = P[a], P[bb]
            out.append(f'<line x1="{A["x"]}" y1="{A["y"]}" x2="{B["x"]}" y2="{B["y"]}" stroke="{stroke}" stroke-width="{width}" stroke-linecap="round"{f" stroke-dasharray=\"{dash}\"" if dash else ""}/>')
    return "".join(out)


def ins_text(p, x, y, size=10.5, muted=False):
    """名字底下：這裡悟得到的（最濃在前），照意境的顏色寫字"""
    ids = sorted(p["insights"], key=lambda i: i != p["strong"])[:3]
    out, dx = [], 0
    for i in ids:
        name, col = INS[i]
        out.append(f'<text x="{x + dx:.0f}" y="{y:.0f}" font-size="{size}" font-weight="700" fill="{col}" stroke="{PAPER}" stroke-width="3" paint-order="stroke" opacity="{0.85 if muted else 1}" style="font-family:serif">{name}</text>')
        dx += size * 1.25
    return "".join(out)


def frame(title, body_svg, bg_css, extra_css=""):
    x0, y0, w, h = VB
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
*{{box-sizing:border-box}} html,body{{margin:0;height:100%;background:#F4EEE2;font-family:"Microsoft JhengHei","PingFang TC",sans-serif;color:#2B241B}}
.top{{height:60px;padding:8px 14px;background:#F4EEE2;border-bottom:1px solid #E2D9C6}}
.top b{{font-size:17px;font-family:serif}} .top small{{color:#6B6150;font-size:12px;margin-left:6px}} .top .loc{{font-size:12.5px;color:#4A4234;margin-top:3px}}
.map{{position:absolute;top:60px;left:0;right:0;bottom:0;overflow:hidden;{bg_css}}}
.map svg{{position:absolute;left:0;top:0;width:100%;height:100%}}
.search{{position:absolute;left:10px;top:10px;right:64px;height:40px;border-radius:20px;background:rgba(255,252,245,.92);box-shadow:0 1px 4px rgba(0,0,0,.12);display:flex;align-items:center;padding:0 14px;font-size:14px;color:#6B6150}}
.ctl{{position:absolute;right:10px;top:10px;display:flex;flex-direction:column;gap:8px}} .ctl span{{width:44px;height:44px;border-radius:12px;background:rgba(255,252,245,.95);box-shadow:0 1px 4px rgba(0,0,0,.12);display:flex;align-items:center;justify-content:center;font-size:20px;color:#2B241B}} .ctl span.me{{color:#A8322A}}
.drawer{{position:absolute;left:0;right:0;bottom:56px;height:234px;background:#FBF6EA;border-radius:18px 18px 0 0;box-shadow:0 -2px 10px rgba(0,0,0,.12);padding:10px 14px 0}}
.grab{{width:40px;height:4px;border-radius:2px;background:#D8CEB8;margin:0 auto 10px}}
.h1{{display:flex;align-items:center;gap:8px;font-size:19px;font-weight:700;font-family:serif}} .seal{{width:24px;height:24px;border-radius:5px;background:#3D5F8F;color:#fff;font-size:14px;display:flex;align-items:center;justify-content:center;font-weight:700}}
.kind{{color:#3D5F8F;font-weight:700;font-size:13.5px;margin:2px 0 8px}}
.ins{{display:flex;align-items:center;gap:8px;font-size:13px;color:#6B6150;margin-bottom:8px}} .ins b{{display:inline-flex;align-items:center;gap:4px;height:26px;padding:0 9px;border-radius:13px;background:#CF4F27;color:#fff;font-family:serif;font-size:15px}} .ins b em{{font-style:normal;font-size:11.5px;font-weight:500}}
.foes{{font-size:13px;color:#6B6150}} .foes b{{display:block;color:#2B241B;font-size:14px;margin:2px 0 8px}}
.acts{{display:flex;gap:8px}} .acts span{{flex:1;height:50px;border-radius:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-weight:700;font-size:15px;border:1px solid #D8CEB8;background:#F3EBDA}} .acts span small{{font-weight:400;font-size:11.5px}} .acts span.main{{background:#A8322A;color:#fff;border-color:#A8322A}}
.tabs{{position:absolute;left:0;right:0;bottom:0;height:56px;background:#F4EEE2;border-top:1px solid #E2D9C6;display:flex}} .tabs span{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:11px;color:#6B6150}} .tabs span b{{font-family:serif;font-size:20px;font-weight:400;color:#2B241B}} .tabs span.on b,.tabs span.on{{color:#A8322A}}
{extra_css}
</style></head><body>
<div class="top"><b>映雪</b><small>官軍・鄉勇・第1級</small><div class="loc">📍 潁川郡（陽翟）　第 1 週・週二 16:13</div></div>
<div class="map"><svg viewBox="{x0} {y0} {w} {h}" preserveAspectRatio="xMidYMin slice" xmlns="http://www.w3.org/2000/svg">{body_svg}</svg>
<div class="search">🔍 找地點、找人物</div><div class="ctl"><span class="me">◎</span><span>＋</span><span>－</span></div>
<div class="drawer"><div class="grab"></div><div class="h1"><span class="seal">官</span>潁川郡（陽翟）（你）</div><div class="kind">官軍的基礎資源領地</div>
<div class="ins">此地能悟 <b>火<em>最濃</em></b></div><div class="foes">此地的對手<b>沒有對手</b></div>
<div class="acts"><span class="main">出陣・守<small>今日還能 5 次</small></span><span>探索<small>回江湖頁挑一種</small></span></div></div></div>
<div class="tabs"><span><b>江</b>江湖</span><span><b>修</b>修練</span><span><b>煉</b>煉製</span><span class="on"><b>圖</b>輿圖</span><span><b>聞</b>見聞</span></div>
</body></html>"""


# ══ 風格一：古輿圖（紙本手繪、淡彩渲染領地、朱印） ══
def icon_ink(glyph):
    sw = 'stroke="%s" stroke-width="1.7" fill="%s" stroke-linejoin="round"' % (INK, PAPER)
    return {
        "城": f'<rect x="-8" y="-5" width="16" height="12" {sw}/><rect x="-4" y="-9" width="8" height="4" {sw}/>',
        "營": f'<path d="M -9 7 L 0 -8 L 9 7 Z" {sw}/><line x1="0" y1="-8" x2="0" y2="7" stroke="{INK}" stroke-width="1.2"/>',
        "寺": f'<path d="M -10 -2 L 0 -11 L 10 -2 Z" {sw}/><rect x="-5" y="-2" width="10" height="9" {sw}/>',
        "渡": f'<path d="M -10 1 Q 0 10 10 1 Z" {sw}/><line x1="0" y1="1" x2="0" y2="-9" stroke="{INK}" stroke-width="1.4"/><path d="M 0 -9 L 7 -5 L 0 -2" fill="{INK}"/>',
        "山": f'<path d="M -11 7 L -4 -4 L 0 2 L 5 -8 L 11 7 Z" {sw}/>',
        "野": f'<path d="M -8 6 L -8 -1 M -4 6 L -4 -4 M 0 6 L 0 0 M 4 6 L 4 -4 M 8 6 L 8 -1" stroke="{INK}" stroke-width="1.5" fill="none" stroke-linecap="round"/>',
    }[glyph]


def style_old():
    out = [
        '<defs><filter id="wash" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves="2" seed="3" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="24"/><feGaussianBlur stdDeviation="4"/></filter>'
        '<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7"/><feColorMatrix values="0 0 0 0 0.35 0 0 0 0 0.28 0 0 0 0 0.18 0 0 0 0.09 0"/></filter></defs>',
        f'<rect x="{VB[0]}" y="{VB[1]}" width="{VB[2]}" height="{VB[3]}" fill="#EBDFC4"/>',
        f'<rect x="{VB[0]}" y="{VB[1]}" width="{VB[2]}" height="{VB[3]}" filter="url(#grain)"/>',
    ]
    # 領地：淡彩渲染（相鄰同一方的連成一片）
    wash = []
    for p in places:
        c = holder(p["id"])
        if c and in_view(p, 160):
            wash.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="78" fill="{SIDES[c][2]}"/>')
    out.append(f'<g filter="url(#wash)" opacity=".5">{"".join(wash)}</g>')
    # 河、山（墨線）
    for name, d in RIVERS.items():
        out.append(f'<path d="{d}" fill="none" stroke="#8FB3C9" stroke-width="7" opacity=".45"/><path d="{d}" fill="none" stroke="{INK}" stroke-width="1" opacity=".6"/>')
    for cx, cy, name in MOUNTAINS:
        out.append(f'<path d="{peaks(cx, cy, 1.1)}" fill="none" stroke="{INK}" stroke-width="1.4" opacity=".7" stroke-linejoin="round"/><path d="{peaks(cx + 30, cy + 22, 0.7)}" fill="none" stroke="{INK}" stroke-width="1.1" opacity=".45"/>')
        if name:
            out.append(f'<text x="{cx + 10}" y="{cy + 40}" font-size="11" fill="{INK}" opacity=".7" style="font-family:serif;letter-spacing:2px">{name}</text>')
    out.append(road_lines(INK, 1.2, "3 4"))
    for r in b["regions"]:
        out.append(f'<text x="{r["cx"]}" y="{r["cy"]}" font-size="30" fill="{INK}" opacity=".12" text-anchor="middle" style="font-family:serif;letter-spacing:8px">{r["name"]}</text>')
    # 地點：墨筆小圖、地名、朱印
    for p in places:
        if not in_view(p):
            continue
        pid, me = p["id"], p["id"] == ME
        out.append(f'<g transform="translate({p["x"]},{p["y"]})">{icon_ink(p["glyph"])}</g>')
        if me:
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="17" fill="none" stroke="{RED}" stroke-width="2.4"/><circle cx="{p["x"]}" cy="{p["y"]}" r="21" fill="none" stroke="{RED}" stroke-width="1" opacity=".6"/>'
                       f'<path d="M {p["x"] + 14} {p["y"] - 14} V {p["y"] - 40} L {p["x"] + 34} {p["y"] - 33} L {p["x"] + 14} {p["y"] - 26}" fill="{RED}" stroke="{RED}" stroke-width="1.5"/>')
        size = 14 if p["big"] else 12.5
        nx = p["x"] + 15
        out.append(f'<text x="{nx}" y="{p["y"] + 5}" font-size="{size}" font-weight="{700 if p["big"] else 500}" fill="{INK}" stroke="#EBDFC4" stroke-width="3.5" paint-order="stroke" style="font-family:serif">{p["name"]}{"（你）" if me else ""}</text>')
        if prime(pid):
            px = nx + size * (len(p["name"]) + (2 if me else 0)) + 4
            out.append(f'<rect x="{px:.0f}" y="{p["y"] - 7}" width="14" height="14" rx="2" fill="{RED}"/><text x="{px + 7:.0f}" y="{p["y"] + 4}" font-size="10.5" text-anchor="middle" fill="#fff" style="font-family:serif">寶</text>')
        out.append(ins_text(p, nx, p["y"] + 19, 10.5, muted=True))
    return "".join(out)


# ══ 風格二：戰棋版圖（六角格、整塊上色） ══
def style_hex():
    R = 24
    W, H = math.sqrt(3) * R, 1.5 * R
    x0, y0, w, h = VB
    cols = int(w / W) + 3
    rows = int(h / H) + 3
    near = [p for p in places if in_view(p, 200)]
    cells, own = [], {}

    def hexpts(cx, cy):
        return " ".join(f"{cx + R * math.cos(math.radians(60 * i - 30)):.1f},{cy + R * math.sin(math.radians(60 * i - 30)):.1f}" for i in range(6))

    for r in range(rows):
        for c in range(cols):
            cx = x0 - W + c * W + (W / 2 if r % 2 else 0)
            cy = y0 - H + r * H
            best, bd = None, 1e9
            for p in near:
                d = math.hypot(p["x"] - cx, p["y"] - cy)
                if d < bd:
                    best, bd = p, d
            if best is None or bd > 118:
                continue
            side = holder(best["id"])
            fill = SIDES[side][2] if side else "#DED8C9"
            cells.append(f'<polygon points="{hexpts(cx, cy)}" fill="{fill}" stroke="#FFFFFF" stroke-width="1.6" opacity=".92"/>')
            if best["id"] not in own or bd < own[best["id"]][0]:
                own[best["id"]] = (bd, cx, cy)
    out = [f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#F1EAD9"/>']
    for name, d in RIVERS.items():
        out.append(f'<path d="{d}" fill="none" stroke="#BFD6E3" stroke-width="12" opacity=".6"/>')
    out.append("".join(cells))
    out.append(road_lines("#8C7B62", 2, "6 5"))
    for r in b["regions"]:
        out.append(f'<text x="{r["cx"]}" y="{r["cy"]}" font-size="30" fill="{INK}" opacity=".14" text-anchor="middle" style="font-family:serif;letter-spacing:8px">{r["name"]}</text>')
    for p in places:
        if not in_view(p) or p["id"] not in own:
            continue
        pid, me = p["id"], p["id"] == ME
        _, cx, cy = own[pid]
        side = holder(pid)
        col = SIDES[side][1] if side else "#8F8B82"
        if prime(pid):
            out.append(f'<polygon points="{hexpts(cx, cy)}" fill="none" stroke="{GOLD}" stroke-width="3.2"/>')
        if me:
            out.append(f'<polygon points="{hexpts(cx, cy)}" fill="none" stroke="{RED}" stroke-width="3.4"/>')
        out.append(f'<rect x="{cx - 10:.0f}" y="{cy - 10:.0f}" width="20" height="20" rx="4" fill="{col}" stroke="#fff" stroke-width="1.5"/><text x="{cx:.0f}" y="{cy + 5:.0f}" font-size="12.5" text-anchor="middle" fill="#fff" font-weight="700" style="font-family:serif">{p["glyph"]}</text>')
        if prime(pid):
            out.append(f'<text x="{cx + 11:.0f}" y="{cy - 9:.0f}" font-size="13" text-anchor="middle" fill="{GOLD}" stroke="#fff" stroke-width="2.5" paint-order="stroke">★</text>')
        if me:
            out.append(f'<path d="M {cx + 11:.0f} {cy - 12:.0f} V {cy - 36:.0f} L {cx + 30:.0f} {cy - 30:.0f} L {cx + 11:.0f} {cy - 24:.0f}" fill="{RED}" stroke="{RED}" stroke-width="1.5"/>')
        size = 13 if p["big"] else 12
        out.append(f'<text x="{cx + 14:.0f}" y="{cy + 5:.0f}" font-size="{size}" font-weight="700" fill="{INK}" stroke="#fff" stroke-width="3.5" paint-order="stroke">{p["name"]}{"（你）" if me else ""}</text>')
        ids = sorted(p["insights"], key=lambda i: i != p["strong"])[:3]
        for k, i in enumerate(ids):
            out.append(f'<rect x="{cx - 10 + k * 8:.0f}" y="{cy + 13:.0f}" width="6" height="6" rx="1" fill="{INS[i][1]}" stroke="#fff" stroke-width="1"/>')
    return "".join(out)


# ══ 風格三：極簡節點圖（平的底、圓點、顏色＝領地） ══
def style_min():
    x0, y0, w, h = VB
    out = [f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#F6F1E6"/>']
    for name, d in RIVERS.items():
        out.append(f'<path d="{d}" fill="none" stroke="#D5E4EC" stroke-width="14" stroke-linecap="round"/>')
    for r in b["regions"]:
        out.append(f'<text x="{r["cx"]}" y="{r["cy"]}" font-size="34" fill="{INK}" opacity=".08" text-anchor="middle" font-weight="700" style="letter-spacing:10px">{r["name"]}</text>')
    # 領地：同一方的相鄰地點之間的路畫成那一方的粗淡線，整片看起來連在一起
    for a, bb in edges:
        if a in P and bb in P and holder(a) and holder(a) == holder(bb):
            A, B = P[a], P[bb]
            out.append(f'<line x1="{A["x"]}" y1="{A["y"]}" x2="{B["x"]}" y2="{B["y"]}" stroke="{SIDES[holder(a)][2]}" stroke-width="26" stroke-linecap="round" opacity=".45"/>')
    out.append(road_lines("#CBBFA6", 2.5))
    for p in places:
        if not in_view(p):
            continue
        pid, me = p["id"], p["id"] == ME
        side = holder(pid)
        col = SIDES[side][1] if side else "#B2AB9D"
        r = 14 if p["big"] else 11
        if prime(pid):
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="{r + 5}" fill="none" stroke="{GOLD}" stroke-width="3"/>')
        if me:
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="{r + 10}" fill="none" stroke="{RED}" stroke-width="2" opacity=".5"/><circle cx="{p["x"]}" cy="{p["y"]}" r="{r + 5}" fill="none" stroke="{RED}" stroke-width="3"/>')
        out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="{r}" fill="{col}" stroke="#fff" stroke-width="2"/><text x="{p["x"]}" y="{p["y"] + r * 0.38}" font-size="{r * 1.05}" text-anchor="middle" fill="#fff" font-weight="700" style="font-family:serif">{p["glyph"]}</text>')
        if prime(pid):
            out.append(f'<text x="{p["x"] + r + 2}" y="{p["y"] - r - 2}" font-size="14" text-anchor="middle" fill="{GOLD}" stroke="#fff" stroke-width="2.5" paint-order="stroke">★</text>')
        if me:
            out.append(f'<path d="M {p["x"] + r + 4} {p["y"] - r - 6} V {p["y"] - r - 32} L {p["x"] + r + 24} {p["y"] - r - 26} L {p["x"] + r + 4} {p["y"] - r - 19}" fill="{RED}" stroke="{RED}" stroke-width="1.5"/>')
        size = 13 if p["big"] else 12
        out.append(f'<text x="{p["x"] + r + 6}" y="{p["y"] + 4.5}" font-size="{size}" font-weight="{700 if p["big"] else 500}" fill="{INK}" stroke="#F6F1E6" stroke-width="3.5" paint-order="stroke">{p["name"]}{"（你）" if me else ""}</text>')
        ids = sorted(p["insights"], key=lambda i: i != p["strong"])[:3]
        for k, i in enumerate(ids):
            out.append(f'<circle cx="{p["x"] + r + 10 + k * 10}" cy="{p["y"] + 14}" r="3.6" fill="{INS[i][1]}" stroke="#fff" stroke-width="1"/>')
    return "".join(out)


(OUT / "風格一-古輿圖.html").write_text(frame("古輿圖", style_old(), "background:#EBDFC4"), encoding="utf-8")
(OUT / "風格二-戰棋版圖.html").write_text(frame("戰棋版圖", style_hex(), "background:#F1EAD9"), encoding="utf-8")
(OUT / "風格三-極簡節點.html").write_text(frame("極簡節點", style_min(), "background:#F6F1E6"), encoding="utf-8")
print("寫了三張：", OUT)
