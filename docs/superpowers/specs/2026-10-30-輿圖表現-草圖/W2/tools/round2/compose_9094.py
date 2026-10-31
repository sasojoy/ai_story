"""compose_9094.py <out 資料夾> <輸出 JPG>：FB-9094 的選項並排——四欄（現在、甲、乙、丙）× 三列（375 站潁水河畔打開、375 站豪族塢堡打開、
320 站潁川郡打開），每一格上面兩行字（這一張被蓋一半以上的兩步內小圖、縮字）；最上面一列每一欄的名字與 42 處的總數（cover_summary.json）。
截圖是兩倍像素，縮成一倍。"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

OUT, DEST = sys.argv[1], sys.argv[2]
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 18)
BOLD = ImageFont.truetype(r"C:\Windows\Fonts\msjhbd.ttc", 20)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 13)
NAMES = {"yingshui": "潁水河畔", "haozu_fort": "豪族塢堡", "yingchuan": "潁川郡"}
COLS = [
    ("opt-now", "now", "現在（W2 第二輪）", "小地圖 100 寬常駐；右下 ◎、全 兩顆"),
    ("opt-甲", "甲", "甲　取景避開 HUD", "打開時中心挪一點（倍率最多拉到 Z0×0.82）"),
    ("opt-乙", "乙", "乙　小地圖收成一顆", "搜尋鈕下一顆 40px「圖」，點了才展開；◎ 全 併一顆"),
    ("opt-丙", "丙", "丙　蓋住的當畫面外", "被蓋一半以上的兩步內掛箭頭牌"),
]
ROWS = [("yingshui", 375, 812), ("haozu_fort", 375, 812), ("yingchuan", 320, 568)]
summary = {}
with open(r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_1654dfc8-5ce-1\content\locations.json", encoding="utf-8") as f:
    PLACE = {x["id"]: x["name"] for x in json.load(f)}
p = os.path.join(OUT, "cover_summary.json")
if os.path.exists(p):
    with open(p, encoding="utf-8") as f:
        summary = json.load(f)
GAP, HEAD, TOP = 16, 54, 116
W = sum(375 for _ in COLS) + GAP * (len(COLS) - 1)
H = TOP + sum(h + HEAD + GAP for _, _, h in ROWS)
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
for ci, (tag, key, title, sub) in enumerate(COLS):
    x = ci * (375 + GAP)
    d.text((x + 8, 4), title, fill="#2a231c", font=BOLD)
    d.text((x + 8, 32), sub, fill="#6e5e49", font=SMALL)
    s = summary.get("cover-now" if key == "now" else f"cover-{key}")
    if s:
        line = "42 處打開・兩步內被蓋一半以上：" + "／".join(str(s[w]["half"]) for w in ("375", "360", "320")) + " 次"
        line2 = "（375／360／320）其中沒掛箭頭牌：" + "／".join(str(s[w]["nopill"]) for w in ("375", "360", "320"))
        line3 = "名字縮到 11px 的比例：" + "／".join(f"{round(100 * s[w]['ratio'], 1)}%" for w in ("375", "360", "320"))
        d.text((x + 8, 52), line, fill="#9e2b22", font=SMALL)
        d.text((x + 8, 70), line2, fill="#6e5e49", font=SMALL)
        d.text((x + 8, 88), line3, fill="#6e5e49", font=SMALL)
    with open(os.path.join(OUT, tag, "optshot.json"), encoding="utf-8") as f:
        shots = {(r["loc"], r["w"]): r for r in json.load(f)["R"]}
    y = TOP
    for loc, w, h in ROWS:
        r = shots[(loc, w)]
        half = [o for o in r["out"] if o["hop"] is not None and o["hop"] <= 2 and o["f"] >= 0.5]
        names = "、".join(f"{PLACE.get(o['id'], o['id'])}{'（有牌）' if o.get('pill') else ''}" for o in half) or "沒有"
        d.text((x + 8, y + 2), f"{w} 寬・站{NAMES[loc]}打開　倍率 {r['z']}", fill="#2a231c", font=FONT)
        d.text((x + 8, y + 28), f"兩步內被蓋一半以上：{names}　縮字 {r['tiny']}／{r['labs']}", fill="#6e5e49", font=SMALL)
        im = Image.open(os.path.join(OUT, tag, f"{loc}-{w}.png")).convert("RGB").resize((w, h), Image.LANCZOS)
        img.paste(im, (x, y + HEAD))
        y += h + HEAD + GAP
img.save(DEST, quality=86)
print("saved", DEST, img.size)
