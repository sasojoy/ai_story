# 地理打掉重來的兩個提案（天下圖那一層的示意）：甲「同心圓天下」（外圈四個出生州、內圈中原四郡、核心鹿台）；
# 乙「南北對壘」（直的：上黃巾、中中原、下官軍，手機直屏順）。地名用現有的加幾個新的（標「新」），都待 joy 潤。
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mock5 import INK, OUT, PAPER, RED, page  # noqa: E402

GUAN, HUANG, NEUTRAL, CORE, GOLD = "#8FAACB", "#E3C06A", "#D6D0C1", "#E8C86A", "#C9962B"
MINI2 = '<div class="drawer"><div class="grab"></div><div class="mini"><span>你在 <b>（出生點之後再定）</b></span><i>進入此區 ›</i></div></div>'


def t(x, y, s, size=13, w=400, fill=INK, anchor="middle", halo=PAPER):
    return f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" text-anchor="{anchor}" font-weight="{w}" fill="{fill}" stroke="{halo}" stroke-width="{size / 3:.1f}" paint-order="stroke" style="font-family:serif">{s}</text>'


def dot(x, y, kind, name, label=True, dy=18):
    col = {"guan": "#3D5F8F", "huang": "#B9821A", "neutral": "#8F8B82", "core": RED}[kind]
    fill = {"guan": "#DCE5F0", "huang": "#F4E7C2", "neutral": PAPER, "core": RED}[kind]
    out = [f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{9 if kind == "core" else 7}" fill="{fill}" stroke="{col}" stroke-width="2.2"/>']
    if kind in ("neutral", "core"):
        out.append(f'<circle cx="{x + 9:.0f}" cy="{y - 9:.0f}" r="4.5" fill="{GOLD}" stroke="{PAPER}" stroke-width="1.2"/>')  # 高級資源：金點
    if label:
        out.append(t(x, y + dy, name, 12.5, 500))
    return "".join(out)


def sector(cx, cy, r0, r1, a0, a1, fill):
    def pt(r, a):
        return f"{cx + r * math.cos(math.radians(a)):.1f} {cy + r * math.sin(math.radians(a)):.1f}"
    large = 1 if a1 - a0 > 180 else 0
    return f'<path d="M {pt(r0, a0)} A {r0} {r0} 0 {large} 1 {pt(r1 - r1 + r0, a1)} L {pt(r1, a1)} A {r1} {r1} 0 {large} 0 {pt(r1, a0)} Z" fill="{fill}" stroke="{INK}" stroke-width="2.2" stroke-linejoin="round" opacity=".92"/>'


# ══ 甲：同心圓天下 ══
def ring_world():
    W, H = 900, 1000
    cx, cy = 450, 500
    out = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="#E9E2CC"/>']
    OUTER = [("洛陽", -180, -90, GUAN, "guan", ["洛陽宮城", "孟津渡", "白馬寺", "北邙山", "洛陽官道"]),
             ("冀州", -90, 0, HUANG, "huang", ["廣宗", "鉅鹿道壇", "下曲陽", "涿郡", "白馬津"]),
             ("青州（新）", 0, 90, HUANG, "huang", ["臨淄（新）", "泰山腳（新）", "濟南（新）", "東萊渡（新）", "青州黃巾營（新）"]),
             ("南陽", 90, 180, GUAN, "guan", ["宛城", "新野", "淯水河畔", "綠林山寨", "南陽官道"])]
    INNER = [("東郡（新）", -135, -45, ["濮陽（新）", "東阿（新）", "黃河渡（新）"]),
             ("陳留（新）", -45, 45, ["陳留（新）", "官渡（新）", "己吾（新）"]),
             ("汝南", 45, 135, ["汝南", "汝南集市", "譙縣"]),
             ("潁川", 135, 225, ["潁川郡", "長社", "潁川書院"])]
    for name, a0, a1, fill, kind, ps in OUTER:
        out.append(sector(cx, cy, 300, 470, a0, a1, fill))
    for name, a0, a1, ps in INNER:
        out.append(sector(cx, cy, 110, 300, a0, a1, NEUTRAL))
    out.append(f'<circle cx="{cx}" cy="{cy}" r="110" fill="{CORE}" stroke="{RED}" stroke-width="3"/>')
    # 路：環路（同一圈相鄰的）與輻路（外圈到內圈到核心）
    roads = []
    for a in range(-157, 203, 45):  # 輻路
        roads.append((cx + 470 * math.cos(math.radians(a)), cy + 470 * math.sin(math.radians(a)), cx + 60 * math.cos(math.radians(a)), cy + 60 * math.sin(math.radians(a))))
    for x1, y1, x2, y2 in roads:
        out.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="#A89877" stroke-width="2" stroke-dasharray="6 5"/>')
    for r in (385, 205):
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#A89877" stroke-width="2" stroke-dasharray="6 5"/>')
    for name, a0, a1, fill, kind, ps in OUTER:
        mid = (a0 + a1) / 2
        out.append(t(cx + 385 * math.cos(math.radians(mid)), cy + 385 * math.sin(math.radians(mid)) - 26, name, 30, 700))
        out.append(t(cx + 385 * math.cos(math.radians(mid)), cy + 385 * math.sin(math.radians(mid)) - 2, "出生州・基礎資源", 13, 500, "#4A4234"))
        for i, p in enumerate(ps):
            a = a0 + (i + 1) * (a1 - a0) / (len(ps) + 1)
            r = 345 if i % 2 else 425
            out.append(dot(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)), kind, p))
    for name, a0, a1, ps in INNER:
        mid = (a0 + a1) / 2
        out.append(t(cx + 250 * math.cos(math.radians(mid)), cy + 250 * math.sin(math.radians(mid)) - 22, name, 24, 700))
        out.append(t(cx + 250 * math.cos(math.radians(mid)), cy + 250 * math.sin(math.radians(mid)) - 1, "高級資源・中立", 12, 500, "#4A4234"))
        for i, p in enumerate(ps):
            a = a0 + (i + 1) * (a1 - a0) / (len(ps) + 1)
            out.append(dot(cx + 175 * math.cos(math.radians(a)), cy + 175 * math.sin(math.radians(a)), "neutral", p))
    out.append(t(cx, cy - 30, "核心", 24, 700, RED))
    out.append(dot(cx, cy, "core", "鹿台（新）・玉璽", dy=26))
    out.append(dot(cx - 60, cy + 40, "core", "嵩山深處", dy=22))
    out.append(dot(cx + 60, cy + 40, "core", "南華觀", dy=22))
    return f"0 -40 {W} {H + 40}", "".join(out)


# ══ 乙：南北對壘（直的） ══
def belt_world():
    W, H = 900, 1300
    out = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="#E9E2CC"/>']

    def blob(x, y, w, h, fill):
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="60" fill="{fill}" stroke="{INK}" stroke-width="2.2" opacity=".92"/>'

    out.append(blob(80, 40, 740, 150, HUANG))     # 幽州（最外、桃園起點）
    out.append(blob(40, 200, 400, 240, HUANG))    # 冀州
    out.append(blob(460, 200, 400, 240, HUANG))   # 青州
    out.append(blob(40, 470, 400, 180, NEUTRAL))  # 東郡
    out.append(blob(460, 470, 400, 180, NEUTRAL))  # 陳留
    out.append(blob(40, 680, 400, 180, NEUTRAL))  # 潁川
    out.append(blob(460, 680, 400, 180, NEUTRAL))  # 汝南
    out.append(f'<circle cx="450" cy="665" r="90" fill="{CORE}" stroke="{RED}" stroke-width="3"/>')
    out.append(blob(40, 900, 400, 240, GUAN))     # 洛陽
    out.append(blob(460, 900, 400, 240, GUAN))    # 南陽
    out.append(blob(80, 1150, 740, 110, GUAN))    # 荊北／長安道（最外）
    for x in (240, 660):  # 直的輻路
        out.append(f'<line x1="{x}" y1="100" x2="{x}" y2="1210" stroke="#A89877" stroke-width="2" stroke-dasharray="6 5"/>')
    for y in (320, 560, 770, 1020):  # 橫的
        out.append(f'<line x1="120" y1="{y}" x2="780" y2="{y}" stroke="#A89877" stroke-width="2" stroke-dasharray="6 5"/>')
    labels = [("幽州", 450, 100, "huang", "出生州（最外）", ["涿郡", "樓桑里", "鄉里結社"]),
              ("冀州", 240, 260, "huang", "黃巾出生州・基礎資源", ["廣宗", "鉅鹿道壇", "下曲陽", "白馬津"]),
              ("青州（新）", 660, 260, "huang", "黃巾出生州・基礎資源", ["臨淄（新）", "泰山腳（新）", "濟南（新）", "東萊渡（新）"]),
              ("東郡（新）", 240, 520, "neutral", "高級資源・中立", ["濮陽（新）", "東阿（新）", "黃河渡（新）"]),
              ("陳留（新）", 660, 520, "neutral", "高級資源・中立", ["陳留（新）", "官渡（新）", "己吾（新）"]),
              ("潁川", 240, 730, "neutral", "高級資源・中立", ["潁川郡", "長社", "潁川書院"]),
              ("汝南", 660, 730, "neutral", "高級資源・中立", ["汝南", "汝南集市", "譙縣"]),
              ("洛陽", 240, 960, "guan", "官軍出生州・基礎資源", ["洛陽宮城", "孟津渡", "白馬寺", "洛陽官道"]),
              ("南陽", 660, 960, "guan", "官軍出生州・基礎資源", ["宛城", "新野", "淯水河畔", "綠林山寨"]),
              ("荊北（新）", 450, 1195, "guan", "出生州（最外）", ["襄陽（新）", "樊城（新）", "漢水渡（新）"])]
    for name, x, y, kind, sub, ps in labels:
        out.append(t(x, y, name, 28 if len(ps) > 3 else 24, 700))
        out.append(t(x, y + 22, sub, 12.5, 500, "#4A4234"))
        n = len(ps)
        for i, p in enumerate(ps):
            px = x - (n - 1) * 46 + i * 92
            out.append(dot(px, y + 70 + (18 if i % 2 else 0), kind, p, dy=20))
    out.append(t(450, 640, "核心", 22, 700, RED))
    out.append(dot(450, 672, "core", "鹿台（新）・玉璽", dy=26))
    return f"0 -40 {W} {H + 40}", "".join(out)


OUT.mkdir(exist_ok=True)
vb, body = ring_world()
(OUT / "新地理甲-同心圓天下.html").write_text(page("同心圓天下", vb, body, '<span class="k">天下</span><span class="q">甲・同心圓天下（示意）</span>', MINI2, "xMidYMin meet"), encoding="utf-8")
vb, body = belt_world()
(OUT / "新地理乙-南北對壘.html").write_text(page("南北對壘", vb, body, '<span class="k">天下</span><span class="q">乙・南北對壘（示意）</span>', MINI2, "xMidYMin meet"), encoding="utf-8")
print("寫了新地理甲、乙")
