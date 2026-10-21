# 企劃者選「一甲的山水＋一乙的印章框與羅盤」，但線條跟圓圈太多：兩種收法。
# 清甲：州界點劃線拿掉、路統一成一種淡線、領地淡彩融成一片（不像一顆顆圓）、你只剩一圈。
# 清乙：同清甲，再把領地的淡彩整個拿掉——誰的領地只看地名框的顏色（藍官軍、黃黃巾、灰沒人佔），山水完全乾淨。
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mock import frame  # noqa: E402
from mock2 import INS, ME, OUT, RED, VB, b, compass, holder, icon, in_view, places, prime  # noqa: E402

WASH_DEF = '<filter id="wash" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="2" seed="3" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="20"/><feGaussianBlur stdDeviation="11"/></filter>'
SIDE_INK = {"guan": ("#3D5F8F", "#DCE5F0"), "huang": ("#B9821A", "#F4E7C2"), None: ("#8F8B82", "#EFEBE2")}


def clean_base():
    """現在的設色山水底圖，線條收一收：州界不畫線（大區的淡色留著）、三種路都換成同一種淡淡的實線"""
    svg = re.sub(r"^<svg\b[^>]*>", "", b["svg"]).replace("</svg>", "")
    svg = svg.replace('stroke="#A88F62"', 'stroke="none"')  # 州界點劃線
    svg = svg.replace(' stroke-dasharray="5 4"', "").replace('stroke="#9C7E58"', 'stroke="#BFAE8E"').replace('stroke-width="1.8"', 'stroke-width="1.4"')  # 官道虛線
    svg = svg.replace('stroke="#8E6B45"', 'stroke="#C6B698"').replace('stroke-width="5.2"', 'stroke-width="3.2"').replace('stroke="#F1E7CF"', 'stroke="#F4EDDC"')  # 雙線大路
    svg = svg.replace(' stroke-dasharray="1.5 4"', "").replace('stroke="#86704F"', 'stroke="#CDBFA3"')  # 小路
    return svg


def wash_soft():
    out = []
    for p in places:
        c = holder(p["id"])
        if c and in_view(p, 160):
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="86" fill="{ {"guan": "#9DB4D3", "huang": "#E7C778"}[c]}"/>')
    return f'<g filter="url(#wash)" opacity=".42">{"".join(out)}</g>'


def marks2(ink, paper, colored_boxes):
    out = []
    for p in places:
        if not in_view(p):
            continue
        pid, me = p["id"], p["id"] == ME
        side = holder(pid)
        fg, bg = SIDE_INK[side] if colored_boxes else (RED if p["big"] else ink, paper)
        out.append(f'<g transform="translate({p["x"]},{p["y"]})">{icon(p["glyph"], SIDE_INK[side][0] if colored_boxes else ink, paper)}</g>')
        if me:
            out.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="18" fill="none" stroke="{RED}" stroke-width="2.6"/>'
                       f'<path d="M {p["x"] + 15} {p["y"] - 15} V {p["y"] - 42} L {p["x"] + 36} {p["y"] - 35} L {p["x"] + 15} {p["y"] - 27}" fill="{RED}" stroke="{RED}" stroke-width="1.5"/>')
        label = p["name"] + ("（你）" if me else "")
        size = 13.5 if p["big"] else 12
        nx = p["x"] + 16
        if p["big"] or colored_boxes:  # 印章框：大城一定有；清乙每一處都有（框的顏色就是誰的領地）
            wd = size * len(label) + 8
            out.append(f'<rect x="{nx - 4}" y="{p["y"] - 9}" width="{wd:.0f}" height="19" fill="{bg}" stroke="{fg}" stroke-width="{1.4 if p["big"] else 1}" opacity=".94"/>')
            out.append(f'<text x="{nx}" y="{p["y"] + 5}" font-size="{size}" font-weight="{700 if p["big"] else 500}" fill="{ink}" style="font-family:serif">{label}</text>')
            end = nx - 4 + wd + 4
        else:
            out.append(f'<text x="{nx}" y="{p["y"] + 5}" font-size="{size}" font-weight="500" fill="{ink}" stroke="{paper}" stroke-width="3.5" paint-order="stroke" style="font-family:serif">{label}</text>')
            end = nx + size * len(label) + 3
        if prime(pid):
            out.append(f'<rect x="{end:.0f}" y="{p["y"] - 7}" width="15" height="15" rx="2" fill="{RED}"/><text x="{end + 7.5:.0f}" y="{p["y"] + 4.5}" font-size="11" text-anchor="middle" fill="#fff" style="font-family:serif">寶</text>')
        ids = sorted(p["insights"], key=lambda i: i != p["strong"])[:2]
        for k, i in enumerate(ids):
            name, col = INS[i]
            out.append(f'<text x="{nx + k * 13:.0f}" y="{p["y"] + 21}" font-size="10.5" font-weight="700" fill="{col}" stroke="{paper}" stroke-width="3" paint-order="stroke" opacity=".9" style="font-family:serif">{name}</text>')
    return "".join(out)


INK, PAPER = "#2B241B", "#F2EAD6"
x0, y0, w, h = VB
base = clean_base()
a = f"<defs>{WASH_DEF}</defs>{base}" + wash_soft() + marks2(INK, PAPER, colored_boxes=False) + compass(x0 + 48, y0 + 640, INK, PAPER)
c = base + marks2(INK, PAPER, colored_boxes=True) + compass(x0 + 48, y0 + 640, INK, PAPER)
(OUT / "清甲-淡彩融成一片.html").write_text(frame("清甲", a, "background:#E9E2CC"), encoding="utf-8")
(OUT / "清乙-只看地名框的顏色.html").write_text(frame("清乙", c, "background:#E9E2CC"), encoding="utf-8")
print("寫了兩張（清甲、清乙）")
