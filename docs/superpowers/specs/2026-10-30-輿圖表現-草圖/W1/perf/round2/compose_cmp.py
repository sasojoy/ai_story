"""拼 FB-9070 的修前修後對照：python compose_cmp.py <輸出資料夾> <修後 commit>
每一列是同一個鏡頭的修前｜修後（裁地圖露出來的那一塊：CSS y 182～622），圈的是「區界落在塊內的那一截」（修前沒有框的那一段；shots.mjs 量的
border 框，兩版同一個位置）。對照-6 是倍率 1.15（打開＝Joy 的取景、以你為中心，另外兩個鏡頭同倍率對準南陽、北邊），對照-7 是倍率 1.5。"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SP = os.path.dirname(os.path.abspath(__file__))
OUT, AFTER = sys.argv[1:3]
SHOTS = os.path.join(SP, "out", "shots")
M = json.load(open(os.path.join(SHOTS, "after", "measure.json"), encoding="utf-8"))
MB = json.load(open(os.path.join(SHOTS, "before", "measure.json"), encoding="utf-8"))
DPR, Y0, Y1, SCALE = 2, 182, 622, 0.8
F_TITLE = ImageFont.truetype(r"C:\Windows\Fonts\msjhbd.ttc", 30)
F_SUB = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 20)
F_ROW = ImageFont.truetype(r"C:\Windows\Fonts\msjhbd.ttc", 24)
F_TAG = ImageFont.truetype(r"C:\Windows\Fonts\msjhbd.ttc", 19)
RING = (0, 150, 200)
LABEL = {
    "yingchuan": "潁川郡 紅框上緣", "nanyang_road": "南陽官道 橘框", "nanyang_wilds": "南陽郊野 橘框", "juma_river": "拒馬河畔 橘框",
    "xiaquyang": "下曲陽 內框", "baima_ford": "白馬津 淡橘框",
}


def panel(ver, view, circles, head, crop=(0, Y0, 375, Y1), scale=SCALE):
    cx, cy, cx1, cy1 = crop
    im = Image.open(os.path.join(SHOTS, ver, view + ".png")).convert("RGB").crop((cx * DPR, cy * DPR, cx1 * DPR, cy1 * DPR))
    d = ImageDraw.Draw(im)
    for cid in circles:
        b = M[view]["border"].get(cid)
        if not b:
            continue
        x0, y0, x1, y1 = b["box"]
        pad = 16
        box = [(x0 - pad - cx) * DPR, (y0 - pad - cy) * DPR, (x1 + pad - cx) * DPR, (y1 + pad - cy) * DPR]
        d.ellipse([v - 3 for v in box[:2]] + [v + 3 for v in box[2:]], outline="white", width=12)
        d.ellipse(box, outline=RING, width=6)
        tag = LABEL[cid]
        tw = d.textlength(tag, font=F_TAG)
        tx = min(max(box[0], 6), im.width - tw - 18)
        ty = box[1] - 40 if box[1] - 40 > 4 else box[3] + 6
        ty = min(ty, im.height - 38)
        d.rounded_rectangle([tx - 8, ty - 4, tx + tw + 8, ty + 30], radius=8, fill="white", outline=RING, width=3)
        d.text((tx, ty), tag, fill=RING, font=F_TAG)
    im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    top = 44
    p = Image.new("RGB", (im.width, im.height + top), "white")
    p.paste(im, (0, top))
    ImageDraw.Draw(p).text((6, 6), head, fill="#2a231c", font=F_ROW)
    return p


def sheet(name, title, sub, rows):
    gap, margin = 24, 20
    built = []
    for view, circles, words, *more in rows:
        kw = more[0] if more else {}
        a = panel("before", view, circles, f"修前 0fb784ed　倍率 {MB[view]['z']}", **kw)
        b = panel("after", view, circles, f"修後 {AFTER}　倍率 {M[view]['z']}", **kw)
        built.append((words, a, b))
    width = margin * 2 + max(a.width for _, a, _ in built) * 2 + gap
    head = 70 + 30 * len(sub)
    height = head + sum(46 + a.height + gap for _, a, _ in built) + margin
    img = Image.new("RGB", (width, height), (250, 246, 238))
    d = ImageDraw.Draw(img)
    d.text((margin, 18), title, fill="#2a231c", font=F_TITLE)
    for i, line in enumerate(sub):
        d.text((margin, 64 + 30 * i), line, fill="#6e5e49", font=F_SUB)
    y = head
    for words, a, b in built:
        d.text((margin, y + 8), words, fill="#2a231c", font=F_ROW)
        y += 46
        img.paste(a, (margin, y))
        img.paste(b, (margin + a.width + gap, y))
        y += a.height + gap
    path = os.path.join(OUT, name)
    img.save(path, quality=84, optimize=True)
    print(name, img.size, os.path.getsize(path))


SUB = ["同一個局面、同一個時刻（第 1 週・週六 11:00，季曆停住拍兩版）；375×812、兩倍像素，裁地圖露出來的那一塊",
       "圈的是區界落在塊內的那一截：修前那一段沒有框（框只描塊、伸出區界的那一截被裁掉），修後沿著看得到的那一塊描一整圈"]
sheet("對照-6-框補齊.jpg", "FB-9070 框補齊：倍率 1.15（打開）修前｜修後", SUB, [
    ("open", ["yingchuan"], "打開（Joy 的取景，以你為中心）：你那一塊潁川郡的紅框，修前缺上緣"),
    ("nanyang-1.15", ["nanyang_road", "nanyang_wilds"], "對準南陽官道：開季可出陣的中立寶地，橘虛框修前只剩跟鄰塊相接的那幾段"),
    ("north-1.15", ["juma_river", "xiaquyang"], "北邊：拒馬河畔的橘框、下曲陽（看得到的外框一半以上在區界上）的內框"),
])
sheet("對照-7-框補齊-近.jpg", "FB-9070 框補齊：倍率 1.5（近）修前｜修後", SUB, [
    ("here-1.5", ["yingchuan"], "以你為中心：潁川郡的紅框上緣"),
    ("nanyang-1.5", ["nanyang_road", "nanyang_wilds"], "南陽官道、南陽郊野的橘虛框"),
    ("juma-1.5", ["juma_river"], "拒馬河畔的橘虛框"),
    ("xiaquyang-1.5", ["xiaquyang"], "下曲陽的內框（中立、沒在翻＝淡灰細線；放大一倍看）", {"crop": (0, 330, 300, 565), "scale": 1.0}),
])
