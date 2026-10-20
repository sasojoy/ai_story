# 輿圖大改的兩個方案（草圖）：方案一「兩層輿圖」（天下圖、區圖，不自由縮放）；方案二「行軍卷」（三條戰線各一卷）。
# 讀 map_base.json／map_state.json（真資料：地點、路、大區、誰佔著、開季中立）；字待 joy 潤。
import json
import re
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "mocks"
sys.path.insert(0, str(HERE))
b = json.load(open(HERE / "map_base.json", encoding="utf-8"))
s = json.load(open(HERE / "map_state.json", encoding="utf-8"))
places, st, edges = b["places"], s["places"], b["edges"]
P = {p["id"]: p for p in places}
ME = "yingchuan"
INS = {"feng": ("風", "#2B8A80"), "huo": ("火", "#CF4F27"), "shui": ("水", "#2C68B0"), "shan": ("山", "#8A5A33")}
RED, GOLD, INK, PAPER = "#A8322A", "#C9962B", "#2B241B", "#F2EAD6"
SIDES = {"guan": ("官軍", "#3D5F8F", "#9DB4D3", "#DCE5F0"), "huang": ("黃巾", "#B9821A", "#E7C778", "#F4E7C2")}
SIDE_INK = {"guan": ("#3D5F8F", "#DCE5F0"), "huang": ("#B9821A", "#F4E7C2"), None: ("#8F8B82", "#EFEBE2")}
REGION_NAME = {r["id"]: r["name"] for r in b["regions"]}
holder = lambda pid: st[pid]["control"]  # noqa: E731
prime = lambda pid: st[pid]["kind"] == "neutral"  # noqa: E731
neighbors = {}
for a, c in edges:
    neighbors.setdefault(a, []).append(c)
    neighbors.setdefault(c, []).append(a)

CSS = """
*{box-sizing:border-box} html,body{margin:0;height:100%;background:#F4EEE2;font-family:"Microsoft JhengHei","PingFang TC",sans-serif;color:#2B241B}
.top{height:60px;padding:8px 14px;background:#F4EEE2;border-bottom:1px solid #E2D9C6}
.top b{font-size:17px;font-family:serif} .top small{color:#6B6150;font-size:12px;margin-left:6px} .top .loc{font-size:12.5px;color:#4A4234;margin-top:3px}
.map{position:absolute;top:60px;left:0;right:0;bottom:56px;overflow:hidden;background:#E9E2CC}
.map svg{position:absolute;left:0;top:0;width:100%;height:100%}
.strip{position:absolute;left:10px;right:10px;top:10px;display:flex;gap:8px;align-items:center}
.strip span{height:38px;border-radius:19px;background:rgba(255,252,245,.94);box-shadow:0 1px 4px rgba(0,0,0,.12);display:flex;align-items:center;padding:0 14px;font-size:14px;font-weight:700}
.strip span.q{flex:1;font-weight:400;color:#6B6150} .strip span.k{color:#A8322A}
.drawer{position:absolute;left:0;right:0;bottom:56px;background:#FBF6EA;border-radius:18px 18px 0 0;box-shadow:0 -2px 10px rgba(0,0,0,.12);padding:10px 14px 12px}
.grab{width:40px;height:4px;border-radius:2px;background:#D8CEB8;margin:0 auto 10px}
.h1{display:flex;align-items:center;gap:8px;font-size:19px;font-weight:700;font-family:serif} .seal{width:24px;height:24px;border-radius:5px;background:#3D5F8F;color:#fff;font-size:14px;display:flex;align-items:center;justify-content:center;font-weight:700}
.kind{color:#3D5F8F;font-weight:700;font-size:13.5px;margin:2px 0 8px}
.ins{display:flex;align-items:center;gap:8px;font-size:13px;color:#6B6150;margin-bottom:8px} .ins b{display:inline-flex;align-items:center;gap:4px;height:26px;padding:0 9px;border-radius:13px;background:#CF4F27;color:#fff;font-family:serif;font-size:15px} .ins b em{font-style:normal;font-size:11.5px;font-weight:500}
.foes{font-size:13px;color:#6B6150} .foes b{display:block;color:#2B241B;font-size:14px;margin:2px 0 8px}
.acts{display:flex;gap:8px} .acts span{flex:1;height:50px;border-radius:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-weight:700;font-size:15px;border:1px solid #D8CEB8;background:#F3EBDA} .acts span small{font-weight:400;font-size:11.5px} .acts span.main{background:#A8322A;color:#fff;border-color:#A8322A}
.mini{display:flex;align-items:center;justify-content:space-between;font-size:14.5px} .mini b{font-family:serif} .mini i{font-style:normal;color:#A8322A;font-weight:700}
.tabs{position:absolute;left:0;right:0;bottom:0;height:56px;background:#F4EEE2;border-top:1px solid #E2D9C6;display:flex} .tabs span{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:11px;color:#6B6150} .tabs span b{font-family:serif;font-size:20px;font-weight:400;color:#2B241B} .tabs span.on b,.tabs span.on{color:#A8322A}
"""
CARD = """<div class="drawer"><div class="grab"></div><div class="h1"><span class="seal">官</span>潁川郡（陽翟）（你）</div><div class="kind">官軍的基礎資源領地</div>
<div class="ins">此地能悟 <b>火<em>最濃</em></b></div><div class="foes">此地的對手<b>沒有對手</b></div>
<div class="acts"><span class="main">出陣・守<small>今日還能 5 次</small></span><span>探索<small>回江湖頁挑一種</small></span></div></div>"""
MINI = """<div class="drawer"><div class="grab"></div><div class="mini"><span>你在 <b>潁川汝南・潁川郡</b></span><i>進入此區 ›</i></div></div>"""
TABS = '<div class="tabs"><span><b>江</b>江湖</span><span><b>修</b>修練</span><span><b>煉</b>煉製</span><span class="on"><b>圖</b>輿圖</span><span><b>聞</b>見聞</span></div>'


def page(title, viewbox, body, strip, drawer, ratio="xMidYMid meet"):
    return f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{CSS}</style></head><body>' \
           f'<div class="top"><b>映雪</b><small>官軍・鄉勇・第1級</small><div class="loc">📍 潁川郡（陽翟）　第 1 週・週二 16:13</div></div>' \
           f'<div class="map"><svg viewBox="{viewbox}" preserveAspectRatio="{ratio}" xmlns="http://www.w3.org/2000/svg">{body}</svg><div class="strip">{strip}</div>{drawer}</div>{TABS}</body></html>'


def icon(glyph, ink, paper, k=1.0):
    sw = f'stroke="{ink}" stroke-width="{1.5 / k:.2f}" fill="{paper}" stroke-linejoin="round"'
    body = {
        "城": f'<rect x="-10" y="-5" width="20" height="11" {sw}/><path d="M -10 -5 V -9 H -6 V -5 M -3 -5 V -9 H 3 V -5 M 6 -5 V -9 H 10 V -5" {sw}/><path d="M -3 6 V 1 A 3 3 0 0 1 3 1 V 6" fill="{ink}"/>',
        "營": f'<path d="M -10 8 L 0 -8 L 10 8 Z" {sw}/><path d="M -3 8 L 0 2 L 3 8" fill="{ink}"/><path d="M 0 -8 V -15 L 7 -13 L 0 -10" fill="{RED}" stroke="{RED}" stroke-width="1"/>',
        "寺": f'<path d="M -11 -1 L 0 -11 L 11 -1 Z" {sw}/><path d="M -7 -11 L 0 -17 L 7 -11 Z" {sw}/><rect x="-5" y="-1" width="10" height="8" {sw}/>',
        "渡": f'<path d="M -11 2 Q 0 11 11 2 Z" {sw}/><line x1="0" y1="2" x2="0" y2="-11" stroke="{ink}" stroke-width="1.4"/><path d="M 0 -11 L 9 -5 L 0 -1 Z" {sw}/>',
        "山": f'<path d="M -12 7 L -5 -5 L -1 1 L 4 -9 L 12 7 Z" {sw}/><path d="M 4 -9 l 3 7" stroke="{ink}" stroke-width=".9"/>',
        "野": f'<path d="M -9 6 L -9 -1 M -5 6 L -5 -5 M -1 6 L -1 0 M 3 6 L 3 -5 M 7 6 L 7 -1" stroke="{ink}" stroke-width="1.5" fill="none" stroke-linecap="round"/><circle cx="-7" cy="-3" r="1.2" fill="{ink}"/>',
    }[glyph]
    return f'<g transform="scale({k})">{body}</g>'


def clean_base():
    svg = re.sub(r"^<svg\b[^>]*>", "", b["svg"]).replace("</svg>", "")
    svg = svg.replace('stroke="#A88F62"', 'stroke="none"')
    svg = svg.replace(' stroke-dasharray="5 4"', "").replace('stroke="#9C7E58"', 'stroke="#BFAE8E"').replace('stroke-width="1.8"', 'stroke-width="1.4"')
    svg = svg.replace('stroke="#8E6B45"', 'stroke="#C6B698"').replace('stroke-width="5.2"', 'stroke-width="3.2"').replace('stroke="#F1E7CF"', 'stroke="#F4EDDC"')
    svg = svg.replace(' stroke-dasharray="1.5 4"', "").replace('stroke="#86704F"', 'stroke="#CDBFA3"')
    return svg


def region_paths():
    return dict(re.findall(r'<path data-region="([^"]+)" d="([^"]+)"', b["svg"]))


# ══ 方案一・天下圖 ══
def tianxia_map():
    base = clean_base()
    base = re.sub(r'<text class="tx-region-name"[^>]*>[^<]*</text>', "", base)  # 大區名自己寫
    out = [f'<g opacity=".55">{base}</g>']
    tally = {}
    for p in places:
        t = tally.setdefault(p["region"], {"guan": 0, "huang": 0, "prime": 0, "n": 0})
        t["n"] += 1
        if holder(p["id"]) in ("guan", "huang"):
            t[holder(p["id"])] += 1
        if prime(p["id"]):
            t["prime"] += 1
    for rid, d in region_paths().items():
        t = tally.get(rid, {"guan": 0, "huang": 0, "prime": 0, "n": 1})
        side = "guan" if t["guan"] > t["huang"] else "huang" if t["huang"] > t["guan"] else None
        share = abs(t["guan"] - t["huang"]) / max(1, t["n"])
        fill = SIDES[side][2] if side else "#D9D3C4"
        out.append(f'<path d="{d}" fill="{fill}" fill-opacity="{0.35 + 0.45 * share:.2f}" stroke="{INK}" stroke-width="2.2" stroke-linejoin="round" opacity=".95"/>')
    # 前線：兩頭歸不同一方的路，畫一道短短的紅線
    for a, c in edges:
        if holder(a) and holder(c) and holder(a) != holder(c):
            A, B = P[a], P[c]
            out.append(f'<line x1="{A["x"]}" y1="{A["y"]}" x2="{B["x"]}" y2="{B["y"]}" stroke="{RED}" stroke-width="6" stroke-linecap="round" opacity=".75"/>')
    for p in places:  # 高級資源領地：金點（有主的畫實心、沒人佔空心）
        if prime(p["id"]):
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="7" fill="{GOLD if holder(p["id"]) else PAPER}" stroke="{GOLD}" stroke-width="2.5"/>')
    for r in b["regions"]:
        t = tally.get(r["id"], {"guan": 0, "huang": 0, "prime": 0})
        cx, cy = r["cx"], r["cy"] - 10
        out.append(f'<text x="{cx}" y="{cy}" font-size="44" text-anchor="middle" fill="{INK}" stroke="{PAPER}" stroke-width="8" paint-order="stroke" font-weight="700" style="font-family:serif;letter-spacing:6px">{r["name"]}</text>')
        parts = [f'<tspan fill="{SIDES["guan"][1]}">官 {t["guan"]}</tspan>', f'<tspan fill="{SIDES["huang"][1]}">巾 {t["huang"]}</tspan>', f'<tspan fill="{GOLD}">寶 {t["prime"]}</tspan>']
        out.append(f'<text x="{cx}" y="{cy + 34}" font-size="24" text-anchor="middle" font-weight="700" stroke="{PAPER}" stroke-width="7" paint-order="stroke" style="font-family:serif">{"　".join(parts)}</text>')
    me = P[ME]
    out.append(f'<circle cx="{me["x"]}" cy="{me["y"]}" r="14" fill="{RED}" stroke="{PAPER}" stroke-width="4"/><path d="M {me["x"] + 10} {me["y"] - 12} V {me["y"] - 60} L {me["x"] + 48} {me["y"] - 48} L {me["x"] + 10} {me["y"] - 36}" fill="{RED}" stroke="{PAPER}" stroke-width="3"/>')
    return "".join(out)


# ══ 方案一・區圖（潁川汝南） ══
def region_map(rid="yingru"):
    mine = [p for p in places if p["region"] == rid]
    xs, ys = [p["x"] for p in mine], [p["y"] for p in mine]
    x0, y0, x1, y1 = min(xs) - 60, min(ys) - 120, max(xs) + 130, max(ys) + 60
    w, h = x1 - x0, y1 - y0
    base = clean_base()
    out = [f'<clipPath id="clip"><rect x="{x0}" y="{y0}" width="{w}" height="{h}"/></clipPath>', f'<g clip-path="url(#clip)">{base}</g>',
           f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#FFFFFF" opacity=".18"/>']
    ids = {p["id"] for p in mine}
    for a, c in edges:  # 通到區外的路：畫到邊上、寫往哪一區
        if (a in ids) != (c in ids):
            inside, outside = (P[a], P[c]) if a in ids else (P[c], P[a])
            dx, dy = outside["x"] - inside["x"], outside["y"] - inside["y"]
            n = (dx * dx + dy * dy) ** 0.5 or 1
            ex, ey = inside["x"] + dx / n * 48, inside["y"] + dy / n * 48
            out.append(f'<line x1="{inside["x"]}" y1="{inside["y"]}" x2="{ex:.0f}" y2="{ey:.0f}" stroke="#BFAE8E" stroke-width="1.8" stroke-dasharray="4 4"/>')
            out.append(f'<text x="{ex + dx / n * 10:.0f}" y="{ey + dy / n * 10 + 4:.0f}" font-size="11" text-anchor="middle" fill="#6B5A44" stroke="{PAPER}" stroke-width="3" paint-order="stroke" style="font-family:serif">→ {REGION_NAME[outside["region"]]}</text>')
    for p in mine:
        pid, me = p["id"], p["id"] == ME
        side = holder(pid)
        fg, bg = SIDE_INK[side]
        out.append(f'<g transform="translate({p["x"]},{p["y"]})">{icon(p["glyph"], fg, PAPER, 1.5)}</g>')
        if me:
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="24" fill="none" stroke="{RED}" stroke-width="2.6"/><path d="M {p["x"] + 16} {p["y"] - 16} V {p["y"] - 44} L {p["x"] + 38} {p["y"] - 37} L {p["x"] + 16} {p["y"] - 29}" fill="{RED}" stroke="{RED}" stroke-width="1.5"/>')
        label = p["name"] + ("（你）" if me else "")
        size = 17 if p["big"] else 15
        nx = p["x"] + 22
        wd = size * len(label) + 10
        out.append(f'<rect x="{nx - 5}" y="{p["y"] - 12}" width="{wd:.0f}" height="24" fill="{bg}" stroke="{fg}" stroke-width="{1.4 if p["big"] else 1}" opacity=".95"/><text x="{nx}" y="{p["y"] + 6}" font-size="{size}" font-weight="{700 if p["big"] else 500}" fill="{INK}" style="font-family:serif">{label}</text>')
        end = nx - 5 + wd + 5
        if prime(pid):
            out.append(f'<rect x="{end:.0f}" y="{p["y"] - 10}" width="20" height="20" rx="3" fill="{RED}"/><text x="{end + 10:.0f}" y="{p["y"] + 5.5}" font-size="14" text-anchor="middle" fill="#fff" style="font-family:serif">寶</text>')
        for k, i in enumerate(sorted(p["insights"], key=lambda i: i != p["strong"])[:2]):
            name, col = INS[i]
            out.append(f'<text x="{nx + k * 16:.0f}" y="{p["y"] + 27}" font-size="13" font-weight="700" fill="{col}" stroke="{PAPER}" stroke-width="3" paint-order="stroke" style="font-family:serif">{name}</text>')
    return f"{x0} {y0} {w} {h}", "".join(out)


# ══ 方案二・行軍卷 ══
LINES = {"yingru": ("潁川汝南", "changshe", "huangjin_camp"), "nanyang": ("南陽", "wan_city", "nanyang_huangjin_camp"), "jizhou": ("冀州", "luzhi_camp", "julu_altar")}


def shortest(a, c):
    prev, q = {a: None}, deque([a])
    while q:
        x = q.popleft()
        if x == c:
            break
        for y in neighbors.get(x, []):
            if y not in prev:
                prev[y] = x
                q.append(y)
    path, x = [], c
    while x is not None:
        path.append(x)
        x = prev[x]
    return path[::-1]


def scroll_map():
    W, H = 380, 112 * 3 + 16
    out = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="#F4EEE2"/>']
    y = 8
    for rid, (name, start, end) in LINES.items():
        A, B = P[start], P[end]
        ax, ay = B["x"] - A["x"], B["y"] - A["y"]
        n2 = ax * ax + ay * ay or 1
        proj = lambda p: ((p["x"] - A["x"]) * ax + (p["y"] - A["y"]) * ay) / n2  # noqa: E731
        rank = {"guan": 0, None: 1, "huang": 2}  # 不照地理：官軍的在左、沒人佔的在中、黃巾的在右，各自照官→巾的軸排
        row = sorted([p for p in places if p["region"] == rid and st[p["id"]]["kind"] in ("neutral", "line", "base", "fixed")], key=lambda p: (rank[holder(p["id"])], proj(p)))
        gap, cy = 46, y + 60
        me_i = next((i for i, p in enumerate(row) if p["id"] == ME), 1)
        off = 0.4 * W - 24 - me_i * gap  # 你擺在四成的位置
        off = min(off, 24)
        out.append(f'<clipPath id="c-{rid}"><rect x="6" y="{y}" width="{W - 12}" height="108"/></clipPath>')
        out.append(f'<rect x="6" y="{y}" width="{W - 12}" height="108" rx="8" fill="#EBDFC4" stroke="#C9B896"/>')
        out.append(f'<g clip-path="url(#c-{rid})">')
        for i, p in enumerate(row):
            x = off + 24 + i * gap
            side = holder(p["id"])
            out.append(f'<rect x="{x - gap / 2:.0f}" y="{cy - 10}" width="{gap}" height="20" fill="{SIDES[side][2] if side else "#D9D3C4"}"/>')
        out.append(f'<line x1="-999" y1="{cy}" x2="9999" y2="{cy}" stroke="#8C7B62" stroke-width="2"/>')
        for i, p in enumerate(row):
            x = off + 24 + i * gap
            pid, me = p["id"], p["id"] == ME
            side = holder(pid)
            fg, bg = SIDE_INK[side]
            if i > 0 and holder(row[i - 1]["id"]) and side and holder(row[i - 1]["id"]) != side:
                out.append(f'<line x1="{x - gap / 2:.0f}" y1="{cy - 24}" x2="{x - gap / 2:.0f}" y2="{cy + 24}" stroke="{RED}" stroke-width="4"/><text x="{x - gap / 2:.0f}" y="{cy - 28}" font-size="9.5" text-anchor="middle" fill="{RED}" font-weight="700">前線</text>')
            out.append(f'<circle cx="{x:.0f}" cy="{cy}" r="{10 if p["big"] else 8}" fill="{bg}" stroke="{fg}" stroke-width="2"/><text x="{x:.0f}" y="{cy + 3.5}" font-size="9.5" text-anchor="middle" fill="{fg}" font-weight="700" style="font-family:serif">{p["glyph"]}</text>')
            if me:
                out.append(f'<circle cx="{x:.0f}" cy="{cy}" r="15" fill="none" stroke="{RED}" stroke-width="2.2"/><path d="M {x + 11:.0f} {cy - 12} V {cy - 30} L {x + 26:.0f} {cy - 25} L {x + 11:.0f} {cy - 20}" fill="{RED}"/>')
            short = p["name"].split("（")[0]
            if len(short) > 4:
                short = short[:4]
            out.append(f'<text x="{x:.0f}" y="{cy + 30}" font-size="9.5" text-anchor="middle" fill="{INK}" font-weight="{700 if me else 500}" style="font-family:serif">{short}</text>')
            if prime(pid):
                out.append(f'<rect x="{x - 6:.0f}" y="{cy - 31}" width="12" height="12" rx="1.5" fill="{RED}"/><text x="{x:.0f}" y="{cy - 22}" font-size="8.5" text-anchor="middle" fill="#fff" style="font-family:serif">寶</text>')
            ins = sorted(p["insights"], key=lambda i: i != p["strong"])[:2]
            out.append("".join(f'<text x="{x - 6 + k * 12:.0f}" y="{cy + 41}" font-size="9" text-anchor="middle" font-weight="700" fill="{INS[i][1]}" style="font-family:serif">{INS[i][0]}</text>' for k, i in enumerate(ins)))
        out.append("</g>")
        out.append(f'<rect x="6" y="{y}" width="{W - 12}" height="22" rx="8" fill="#EBDFC4" opacity=".92"/><text x="14" y="{y + 16}" font-size="12" font-weight="700" fill="{INK}" style="font-family:serif;letter-spacing:2px">{name}</text>')
        out.append(f'<text x="{W - 14}" y="{y + 16}" font-size="10" text-anchor="end" fill="#6B5A44">◀ 官軍　　黃巾 ▶　（可橫捲）</text>')
        y += 112
    return f"0 -55 {W} {H + 55}", "".join(out)


OUT.mkdir(exist_ok=True)
(OUT / "方案一-天下圖.html").write_text(page("天下圖", "0 -130 900 1470", tianxia_map(), '<span class="k">天下</span><span class="q">🔍 找地點、找人物</span><span>⏱ 版圖</span>', MINI, "xMidYMin meet"), encoding="utf-8")
vb, body = region_map()
(OUT / "方案一-區圖.html").write_text(page("區圖", vb, body, '<span class="k">‹ 天下</span><span class="q">潁川汝南 ▾</span><span>⏱ 版圖</span>', CARD, "xMidYMin meet"), encoding="utf-8")
vb, body = scroll_map()
(OUT / "方案二-行軍卷.html").write_text(page("行軍卷", vb, body, '<span class="k">三條戰線</span><span class="q">🔍 找地點、找人物</span>', CARD, "xMidYMin meet"), encoding="utf-8")
print("寫了三張（方案一天下圖、區圖；方案二行軍卷）")
