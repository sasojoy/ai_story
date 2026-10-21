# 整體地圖重排（三國志戰略版的概念：出生州在外圈、高級資源地在內圈）：一張「環圖」看圈怎麼分，一張天下圖照新的分法上色。
# 分法是我的提案（用現有的 42 個地點、不動座標），等企劃者改；字待 joy 潤。
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mock6  # noqa: E402
from mock5 import INK, MINI, OUT, P, PAPER, RED, b, page, places  # noqa: E402

# ── 提案的分圈（地點 id → 圈）：outer_guan／outer_huang 出生州（基礎資源、開季就是自家）、inner 高級資源（中立）、core 核心 ──
RING = {}
for pid in ["mengjin_ford", "beimang_hill", "baima_temple", "dajiangjun_fu", "luoyang_palace", "luoyang_road",  # 洛陽
            "wan_city", "yu_river", "xinye", "nanyang_road", "nanyang_wilds", "lulin_zhai", "nanyang_huangjin_camp"]:  # 南陽（南陽黃巾營改成官軍的前哨）
    RING[pid] = "outer_guan"
for pid in ["yanshan_foot", "market_town", "loushang_village", "zhuo_county", "zhuo_militia_hall", "juma_river",  # 幽州
            "xiaquyang", "guangzong", "julu_altar", "haozu_fort", "luzhi_camp", "baima_ford"]:  # 冀州（盧植營改成黃巾的前哨）
    RING[pid] = "outer_huang"
for pid in ["guan_camp", "songshan_foot", "yingchuan", "yingchuan_wilds", "huangjin_camp", "yingchuan_academy", "yingshui", "changshe",
            "hilltop_wilds", "runan_wilds", "cao_manor", "runan", "qiao_county", "runan_market", "runan_academy"]:  # 潁川汝南：內圈
    RING[pid] = "inner"
for pid in ["deep_mountain", "nanhua_guan"]:  # 核心：嵩山深處、南華觀（玉璽碎片藏在這裡）
    RING[pid] = "core"
# 南華觀的 id 可能不叫 nanhua_guan：照名字找
for p in places:
    if p["name"] == "南華觀":
        RING.pop("nanhua_guan", None)
        RING[p["id"]] = "core"
missing = [p["name"] for p in places if p["id"] not in RING]
assert not missing, missing

FILL = {"outer_guan": "#8FAACB", "outer_huang": "#E3C06A", "inner": "#D6D0C1", "core": "#E8C86A"}


def ring_holder(pid):
    return {"outer_guan": "guan", "outer_huang": "huang"}.get(RING[pid])


def ring_prime(pid):
    return RING[pid] in ("inner", "core")


mock6.holder = ring_holder
mock6.prime = ring_prime
mock6.fills_override = FILL


# 天下圖照新的分法：內圈、核心的格子顏色另給（高級＝淡灰、核心＝金）
def tianxia_map3():
    import re
    svg = mock6.tianxia_map2()
    # 核心那幾格：照「離哪個地點最近」已經是沒人佔的灰，這裡把核心地點畫成大一點的金印
    for p in places:
        if RING[p["id"]] == "core":
            svg += f'<rect x="{p["x"] - 11}" y="{p["y"] - 11}" width="22" height="22" rx="3" fill="{RED}" stroke="{PAPER}" stroke-width="2"/><text x="{p["x"]}" y="{p["y"] + 6}" font-size="15" text-anchor="middle" fill="#fff" style="font-family:serif">璽</text>'
    svg = re.sub(r'<text x="(\d+)" y="(\d+)" font-size="24"[^>]*>.*?</text>', "", svg)  # 數字那一行拿掉，換成圈的名字
    for r in b["regions"]:
        tag = {"luoyang": "官軍出生州", "nanyang": "官軍出生州", "youzhou": "黃巾出生州", "jizhou": "黃巾出生州", "yingru": "中原・高級資源"}[r["id"]]
        svg += f'<text x="{r["cx"]}" y="{r["cy"] + 24}" font-size="22" text-anchor="middle" font-weight="700" fill="{INK}" stroke="{PAPER}" stroke-width="6" paint-order="stroke" style="font-family:serif">{tag}</text>'
    return svg


# ── 環圖（示意）：三圈 ──
def ring_diagram():
    W, H = 380, 560
    cx, cy = 190, 250
    out = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="#F4EEE2"/>']
    out.append(f'<path d="M {cx} {cy - 210} A 210 210 0 0 0 {cx} {cy + 210} Z" fill="{FILL["outer_guan"]}" stroke="{INK}" stroke-width="1.5"/>')
    out.append(f'<path d="M {cx} {cy - 210} A 210 210 0 0 1 {cx} {cy + 210} Z" fill="{FILL["outer_huang"]}" stroke="{INK}" stroke-width="1.5"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="128" fill="{FILL["inner"]}" stroke="{INK}" stroke-width="1.5"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="46" fill="{FILL["core"]}" stroke="{RED}" stroke-width="2.5"/>')
    t = lambda x, y, s, size=12, w=400, fill=INK, anchor="middle": f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{w}" fill="{fill}" style="font-family:serif">{s}</text>'  # noqa: E731
    out.append(t(cx - 118, cy - 150, "官軍出生州", 14, 700, "#3D5F8F"))
    out.append(t(cx - 118, cy - 132, "洛陽・南陽", 12))
    out.append(t(cx - 120, cy + 150, "基礎資源・開季就是自家", 9.5, fill="#4A4234"))
    out.append(t(cx - 120, cy + 166, "宛城、新野、洛陽宮城…", 9.5, fill="#4A4234"))
    out.append(t(cx + 118, cy - 150, "黃巾出生州", 14, 700, "#B9821A"))
    out.append(t(cx + 118, cy - 132, "冀州・幽州", 12))
    out.append(t(cx + 120, cy + 150, "基礎資源・開季就是自家", 9.5, fill="#4A4234"))
    out.append(t(cx + 120, cy + 166, "廣宗、涿郡、鉅鹿道壇…", 9.5, fill="#4A4234"))
    out.append(t(cx, cy - 100, "中原（潁川・汝南）", 14, 700))
    out.append(t(cx, cy - 82, "高級資源領地・開季中立", 11, fill="#4A4234"))
    out.append(t(cx, cy - 66, "強對手、高階回饋；兩軍從外往內搶", 10, fill="#4A4234"))
    out.append(t(cx, cy + 76, "長社、潁川郡、汝南、黃巾別部營寨…", 10, fill="#4A4234"))
    out.append(t(cx, cy - 6, "核心", 14, 700, RED))
    out.append(t(cx, cy + 12, "嵩山深處・南華觀", 10.5))
    out.append(t(cx, cy + 26, "玉璽碎片", 10, fill=RED))
    for ang in (150, 30, 210, 330):  # 外圈往內的箭頭
        import math
        x1, y1 = cx + 190 * math.cos(math.radians(ang)), cy + 190 * math.sin(math.radians(ang))
        x2, y2 = cx + 140 * math.cos(math.radians(ang)), cy + 140 * math.sin(math.radians(ang))
        out.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{RED}" stroke-width="3" marker-end="url(#arr)"/>')
    out.insert(1, f'<defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="{RED}"/></marker></defs>')
    out.append(t(cx, cy + 232, "出生州在外圈、高級資源在內圈、核心在中間；", 12, fill="#4A4234"))
    out.append(t(cx, cy + 250, "兩軍各從自己那半邊往中原推，中原每一塊兩邊都碰得到。", 12, fill="#4A4234"))
    out.append(t(cx, cy + 282, "【提案，等企劃者改】出生點要跟著搬：官軍出序章到洛陽、黃巾到冀州。", 10.5, fill=RED))
    return f"0 0 {W} {H}", "".join(out)


OUT.mkdir(exist_ok=True)
(OUT / "重排-天下圖.html").write_text(page("天下圖（重排）", "0 -130 900 1470", tianxia_map3(), '<span class="k">天下</span><span class="q">🔍 找地點、找人物</span><span>⏱ 版圖</span>', MINI, "xMidYMin meet"), encoding="utf-8")
vb, body = ring_diagram()
(OUT / "重排-環圖.html").write_text(page("環圖", vb, body, '<span class="k">圈怎麼分（示意）</span>', "", "xMidYMin meet"), encoding="utf-8")
print("寫了重排-天下圖、重排-環圖")
