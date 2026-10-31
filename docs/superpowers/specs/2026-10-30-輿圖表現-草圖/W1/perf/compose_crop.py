"""compose_crop.py <crop 資料夾> <輸出 JPG>：倍率 2.4、像素比 3 的同一塊地，V（向量）｜R（點陣）並排，每一張再放大兩倍（最近鄰，看得到像素）。
上一排：潁川郡（你那一塊，紅框）與潁水河畔（黃巾）相接的那一角＋戰線白邊；下一排：拒馬河（可出陣，橘虛框）的一角。"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

src, out = sys.argv[1:3]
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 22)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 16)


def tile(name, title, sub):
    im = Image.open(os.path.join(src, name)).convert("RGB")
    im = im.resize((im.width * 2, im.height * 2), Image.NEAREST)
    head = 64
    p = Image.new("RGB", (im.width, im.height + head), "white")
    p.paste(im, (0, head))
    d = ImageDraw.Draw(p)
    d.text((10, 4), title, fill="#2a231c", font=FONT)
    d.text((10, 36), sub, fill="#6e5e49", font=SMALL)
    return p


rows = [
    [tile("crop-V.png", "V 向量（SVG）", "紅框・戰線白邊・區內框；倍率 2.4、像素比 3"), tile("crop-R.png", "R 點陣（canvas 3278×4880）", "同一塊、同一個倍率；烤的大小到上限，近看只有需要的一半")],
    [tile("crop-orange-V.png", "V 向量", "拒馬河：可出陣的橘虛框"), tile("crop-orange-R.png", "R 點陣", "同一塊")],
]
gap = 16
W = sum(t.width for t in rows[0]) + gap
H = sum(max(t.height for t in r) for r in rows) + gap
img = Image.new("RGB", (W, H), "white")
y = 0
for r in rows:
    x = 0
    for t in r:
        img.paste(t, (x, y))
        x += t.width + gap
    y += max(t.height for t in r) + gap
img.save(out, quality=90)
print("ok", img.size)
