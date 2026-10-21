# 古輿圖風格再往上一層（三種做法）：一甲 現在的設色山水底圖＋古輿圖記號；一乙 工筆手繪（山、樹、河、官道、印章框）；
# 一丙 絹本設色（一乙的畫法換青綠赭石、金印、卷軸邊、羅盤）。草圖、不是真畫面；字待 joy 潤。
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "mocks"
b = json.load(open(HERE / "map_base.json", encoding="utf-8"))
s = json.load(open(HERE / "map_state.json", encoding="utf-8"))
places, st, edges = b["places"], s["places"], b["edges"]
P = {p["id"]: p for p in places}
ME = "yingchuan"
VB = (150, 620, 500, 1003)
INS = {"feng": ("風", "#2B8A80"), "huo": ("火", "#CF4F27"), "shui": ("水", "#2C68B0"), "shan": ("山", "#8A5A33")}
RED = "#A8322A"

import sys  # noqa: E402

sys.path.insert(0, str(HERE))  # -I 不帶腳本目錄
from mock import frame  # noqa: E402  （mock.py 匯入時會重寫三張第一輪的草圖，無妨）


def holder(pid):
    return st[pid]["control"]


def prime(pid):
    return st[pid]["kind"] == "neutral"


def in_view(p, pad=60):
    x0, y0, w, h = VB
    return x0 - pad <= p["x"] <= x0 + w + pad and y0 - pad <= p["y"] <= y0 + h + pad


RIVERS = {
    "黃河": "M 60 696 C 250 706, 450 700, 740 714",
    "潁水": "M 300 790 C 380 880, 470 950, 500 1030 C 530 1110, 600 1200, 640 1345",
    "淯水": "M 50 950 C 95 1050, 70 1150, 110 1345",
    "汝水": "M 560 1130 C 600 1160, 660 1180, 720 1240",
}
RANGES = [(340, 850, 1.35, "嵩山"), (440, 822, 0.85, ""), (150, 735, 1.05, "北邙山"), (300, 1245, 1.25, "桐柏山"), (395, 1272, 0.8, ""),
          (55, 985, 1.1, "伏牛山"), (125, 1030, 0.75, ""), (560, 1098, 0.55, ""), (660, 1300, 0.9, "")]
TREES = [(515, 1005), (530, 1022), (548, 1010), (612, 1062), (628, 1078), (255, 905), (240, 922), (205, 1185), (222, 1200), (690, 1120), (706, 1138)]


def peak_poly(cx, cy, k):
    pts = [(-60, 16), (-44, -6), (-28, -22), (-14, -4), (0, -34), (14, -10), (26, -26), (42, -2), (60, 16)]
    return " ".join(f"{cx + x * k:.0f},{cy + y * k:.0f}" for x, y in pts)


def mountains(back, front, ink):
    out = []
    for cx, cy, k, name in RANGES:
        out.append(f'<polygon points="{peak_poly(cx + 26 * k, cy + 10 * k, k * 0.85)}" fill="{back}" stroke="{ink}" stroke-width=".8" opacity=".75"/>')
        out.append(f'<polygon points="{peak_poly(cx, cy, k)}" fill="{front}" stroke="{ink}" stroke-width="1.1" stroke-linejoin="round" opacity=".9"/>')
        for dx, dy in ((-28, -22), (0, -34), (26, -26)):  # 山脊一筆
            out.append(f'<path d="M {cx + dx * k:.0f} {cy + dy * k:.0f} l {8 * k:.0f} {18 * k:.0f}" stroke="{ink}" stroke-width=".9" opacity=".5" fill="none"/>')
        if name:
            out.append(f'<text x="{cx + 8}" y="{cy + 34 * k:.0f}" font-size="10.5" fill="{ink}" opacity=".75" style="font-family:serif;letter-spacing:2px">{name}</text>')
    return "".join(out)


def trees(fill, ink):
    out = []
    for x, y in TREES:
        out.append(f'<path d="M {x - 6} {y + 2} L {x} {y - 10} L {x + 6} {y + 2} Z M {x - 5} {y - 3} L {x} {y - 13} L {x + 5} {y - 3} Z" fill="{fill}" stroke="{ink}" stroke-width=".8"/><line x1="{x}" y1="{y + 2}" x2="{x}" y2="{y + 7}" stroke="{ink}" stroke-width="1.2"/>')
    return "".join(out)


def rivers(edge, water, waves=False):
    out = []
    for name, d in RIVERS.items():
        out.append(f'<path d="{d}" fill="none" stroke="{edge}" stroke-width="8" opacity=".35"/><path d="{d}" fill="none" stroke="{water}" stroke-width="5"/><path d="{d}" fill="none" stroke="{edge}" stroke-width="1" opacity=".8"/>')
        if waves:
            out.append(f'<path d="{d}" fill="none" stroke="{edge}" stroke-width=".8" stroke-dasharray="3 9" opacity=".7"/>')
    return "".join(out)


def roads(dark, paper):
    out = []
    for a, bb in edges:
        if a in P and bb in P:
            A, B = P[a], P[bb]
            out.append(f'<line x1="{A["x"]}" y1="{A["y"]}" x2="{B["x"]}" y2="{B["y"]}" stroke="{dark}" stroke-width="2.6" stroke-linecap="round" opacity=".8"/><line x1="{A["x"]}" y1="{A["y"]}" x2="{B["x"]}" y2="{B["y"]}" stroke="{paper}" stroke-width="1.1" stroke-linecap="round"/>')
    return "".join(out)


def icon(glyph, ink, paper):
    sw = f'stroke="{ink}" stroke-width="1.5" fill="{paper}" stroke-linejoin="round"'
    return {
        "城": f'<rect x="-10" y="-5" width="20" height="11" {sw}/><path d="M -10 -5 V -9 H -6 V -5 M -3 -5 V -9 H 3 V -5 M 6 -5 V -9 H 10 V -5" {sw}/><path d="M -3 6 V 1 A 3 3 0 0 1 3 1 V 6" fill="{ink}"/>',
        "營": f'<path d="M -10 8 L 0 -8 L 10 8 Z" {sw}/><path d="M -3 8 L 0 2 L 3 8" fill="{ink}"/><path d="M 0 -8 V -15 L 7 -13 L 0 -10" fill="{RED}" stroke="{RED}" stroke-width="1"/>',
        "寺": f'<path d="M -11 -1 L 0 -11 L 11 -1 Z" {sw}/><path d="M -7 -11 L 0 -17 L 7 -11 Z" {sw}/><rect x="-5" y="-1" width="10" height="8" {sw}/>',
        "渡": f'<path d="M -11 2 Q 0 11 11 2 Z" {sw}/><line x1="0" y1="2" x2="0" y2="-11" stroke="{ink}" stroke-width="1.4"/><path d="M 0 -11 L 9 -5 L 0 -1 Z" {sw}/>',
        "山": f'<path d="M -12 7 L -5 -5 L -1 1 L 4 -9 L 12 7 Z" {sw}/><path d="M 4 -9 l 3 7" stroke="{ink}" stroke-width=".9"/>',
        "野": f'<path d="M -9 6 L -9 -1 M -5 6 L -5 -5 M -1 6 L -1 0 M 3 6 L 3 -5 M 7 6 L 7 -1" stroke="{ink}" stroke-width="1.5" fill="none" stroke-linecap="round"/><circle cx="-7" cy="-3" r="1.2" fill="{ink}"/>',
    }[glyph]


def marks(ink, paper, seal_fill, seal_text, box_names=True, seal_word="寶"):
    """地點：圖、名字（大城用印章框）、高級資源領地的印、你的朱圈與旗、這裡悟得到的"""
    out = []
    for p in places:
        if not in_view(p):
            continue
        pid, me = p["id"], p["id"] == ME
        out.append(f'<g transform="translate({p["x"]},{p["y"]})">{icon(p["glyph"], ink, paper)}</g>')
        if me:
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="18" fill="none" stroke="{RED}" stroke-width="2.4"/><circle cx="{p["x"]}" cy="{p["y"]}" r="22" fill="none" stroke="{RED}" stroke-width="1" opacity=".6"/>'
                       f'<path d="M {p["x"] + 15} {p["y"] - 15} V {p["y"] - 42} L {p["x"] + 36} {p["y"] - 35} L {p["x"] + 15} {p["y"] - 27}" fill="{RED}" stroke="{RED}" stroke-width="1.5"/>')
        label = p["name"] + ("（你）" if me else "")
        size = 13.5 if p["big"] else 12
        nx = p["x"] + 16
        if p["big"] and box_names:
            wd = size * len(label) + 8
            out.append(f'<rect x="{nx - 4}" y="{p["y"] - 9}" width="{wd:.0f}" height="19" fill="{paper}" stroke="{RED}" stroke-width="1.2" opacity=".92"/>')
            out.append(f'<text x="{nx}" y="{p["y"] + 5}" font-size="{size}" font-weight="700" fill="{ink}" style="font-family:serif">{label}</text>')
            end = nx - 4 + wd + 4
        else:
            out.append(f'<text x="{nx}" y="{p["y"] + 5}" font-size="{size}" font-weight="{700 if p["big"] else 500}" fill="{ink}" stroke="{paper}" stroke-width="3.5" paint-order="stroke" style="font-family:serif">{label}</text>')
            end = nx + size * len(label) + 3
        if prime(pid):
            out.append(f'<rect x="{end:.0f}" y="{p["y"] - 7}" width="15" height="15" rx="2" fill="{seal_fill}"/><text x="{end + 7.5:.0f}" y="{p["y"] + 4.5}" font-size="11" text-anchor="middle" fill="{seal_text}" style="font-family:serif">{seal_word}</text>')
        ids = sorted(p["insights"], key=lambda i: i != p["strong"])[:3]
        for k, i in enumerate(ids):
            name, col = INS[i]
            out.append(f'<text x="{nx + k * 13:.0f}" y="{p["y"] + 20}" font-size="10.5" font-weight="700" fill="{col}" stroke="{paper}" stroke-width="3" paint-order="stroke" opacity=".9" style="font-family:serif">{name}</text>')
    return "".join(out)


def wash(colors, opacity=.5, r=78):
    out = []
    for p in places:
        c = holder(p["id"])
        if c and in_view(p, 160):
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="{r}" fill="{colors[c]}"/>')
    return f'<g filter="url(#wash)" opacity="{opacity}">{"".join(out)}</g>'


WASH_DEF = '<filter id="wash" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves="2" seed="3" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="24"/><feGaussianBlur stdDeviation="4"/></filter>'
GRAIN_DEF = '<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7"/><feColorMatrix values="0 0 0 0 0.35 0 0 0 0 0.28 0 0 0 0 0.18 0 0 0 0.09 0"/></filter>'


def region_names(ink):
    return "".join(f'<text x="{r["cx"]}" y="{r["cy"]}" font-size="30" fill="{ink}" opacity=".13" text-anchor="middle" style="font-family:serif;letter-spacing:8px">{r["name"]}</text>' for r in b["regions"])


def compass(x, y, ink, paper):
    pts = " ".join(f"{x + 18 * math.cos(math.radians(a)):.0f},{y + 18 * math.sin(math.radians(a)):.0f}" if a % 90 == 0 else f"{x + 6 * math.cos(math.radians(a)):.0f},{y + 6 * math.sin(math.radians(a)):.0f}" for a in range(0, 360, 45))
    return f'<circle cx="{x}" cy="{y}" r="24" fill="{paper}" stroke="{ink}" stroke-width="1" opacity=".9"/><polygon points="{pts}" fill="{ink}" opacity=".8"/><text x="{x}" y="{y - 27}" font-size="10" text-anchor="middle" fill="{RED}" style="font-family:serif">北</text>'


# ── 一甲：現在的設色山水底圖＋古輿圖記號 ──
def style_1a():
    inner = re.sub(r"^<svg\b[^>]*>", "", b["svg"]).replace("</svg>", "")
    INK, PAPER = "#2B241B", "#F2EAD6"
    return f"<defs>{WASH_DEF}</defs>{inner}" + wash({"guan": "#9DB4D3", "huang": "#E7C778"}, .5, 80) + marks(INK, PAPER, RED, "#fff", box_names=False)


# ── 一乙：工筆手繪 ──
def style_1b():
    x0, y0, w, h = VB
    INK, PAPER = "#3B2E1E", "#EBDFC4"
    out = [f'<defs>{WASH_DEF}{GRAIN_DEF}<radialGradient id="stain"><stop offset="0" stop-color="#B99A66" stop-opacity=".22"/><stop offset="1" stop-color="#B99A66" stop-opacity="0"/></radialGradient></defs>',
           f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="{PAPER}"/>',
           f'<circle cx="{x0 + 90}" cy="{y0 + 160}" r="170" fill="url(#stain)"/><circle cx="{x0 + w - 60}" cy="{y0 + 620}" r="220" fill="url(#stain)"/><circle cx="{x0 + 220}" cy="{y0 + 900}" r="150" fill="url(#stain)"/>',
           f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" filter="url(#grain)"/>']
    out.append(wash({"guan": "#8FAACB", "huang": "#D9B766"}, .5, 78))
    out.append(rivers("#5F7F96", "#C9DCE6"))
    out.append(mountains("#CFD3BC", "#A8B894", INK))
    out.append(trees("#9FB38B", INK))
    out.append(roads("#7A5A3A", PAPER))
    out.append(region_names(INK))
    out.append(marks(INK, PAPER, RED, "#fff"))
    out.append(compass(x0 + 48, y0 + 640, INK, PAPER))
    return "".join(out)


# ── 一丙：絹本設色（青綠赭石、金印、卷軸邊） ──
def style_1c():
    x0, y0, w, h = VB
    INK, PAPER, GOLD = "#2E2418", "#DECBA4", "#B8902F"
    out = [f'<defs>{WASH_DEF}{GRAIN_DEF}<radialGradient id="stain"><stop offset="0" stop-color="#8A6A3A" stop-opacity=".25"/><stop offset="1" stop-color="#8A6A3A" stop-opacity="0"/></radialGradient></defs>',
           f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="{PAPER}"/>',
           f'<circle cx="{x0 + 70}" cy="{y0 + 120}" r="190" fill="url(#stain)"/><circle cx="{x0 + w - 40}" cy="{y0 + 560}" r="240" fill="url(#stain)"/><circle cx="{x0 + 260}" cy="{y0 + 960}" r="170" fill="url(#stain)"/>',
           f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" filter="url(#grain)"/>']
    out.append(wash({"guan": "#5E86B5", "huang": "#C9922E"}, .42, 78))
    out.append(rivers("#3F6A80", "#9FC4CF", waves=True))
    out.append(mountains("#9FC1BA", "#5E9A86", INK))
    out.append(trees("#4F8A6A", INK))
    out.append(roads("#6B4A26", "#E8D9B4"))
    out.append(region_names(INK))
    out.append(marks(INK, "#EADBB8", GOLD, "#fff", seal_word="寶"))
    out.append(compass(x0 + 48, y0 + 640, INK, "#EADBB8"))
    # 卷軸邊：雙線框（隨畫面固定；草圖先畫在圖上）
    out.append(f'<rect x="{x0 + 6}" y="{y0 + 6}" width="{w - 12}" height="{h - 12}" fill="none" stroke="{GOLD}" stroke-width="2"/><rect x="{x0 + 11}" y="{y0 + 11}" width="{w - 22}" height="{h - 22}" fill="none" stroke="{INK}" stroke-width=".8" opacity=".6"/>')
    return "".join(out)


(OUT / "一甲-現在的山水加古輿圖記號.html").write_text(frame("一甲", style_1a(), "background:#E9E2CC"), encoding="utf-8")
(OUT / "一乙-工筆手繪.html").write_text(frame("一乙", style_1b(), "background:#EBDFC4"), encoding="utf-8")
(OUT / "一丙-絹本設色.html").write_text(frame("一丙", style_1c(), "background:#DECBA4"), encoding="utf-8")
print("寫了三張（一甲乙丙）")
