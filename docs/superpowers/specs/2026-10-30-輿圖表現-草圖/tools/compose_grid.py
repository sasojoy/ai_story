# 把一輪的手機截圖排成幾列（每一列一個版本、每一欄一個畫面），列頭寫版本名、欄頭寫畫面名。PIL，字型 msjh.ttc。
# 用法：python compose_grid.py <輪的資料夾名>   （在這個資料夾跑；吐 ../<資料夾名>.png）
# 每一輪的格子寫在底下 GRIDS；新的一輪加一筆。截圖寬度不一（320 寬的）照高等比縮。
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 22)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 15)
GRIDS = {
    "第11輪-一張到底對照": {
        "cols": ["① 打開", "② 點潁川郊野", "③ 縮到天下", "④ 320 寬"],
        "rows": [
            ("甲 Joy 10/30「一張到底」（develop 現在的）", "淡彩水墨底圖、畫的小圖、搜尋列與篩選、抽屜一排卡；勢力範圍是「塗層」開關", ["甲1-打開.jpg", "甲2-點一處.jpg", "甲4-天下.jpg", "甲6-320寬.jpg"]),
            ("乙 我們談定的戰略圖（第 10 輪）", "地塊裁到區界、戰線、危險度徽、區名＋🔍＋小地圖、箭頭牌、底條一行", ["乙1-打開.jpg", "乙2-點一處.jpg", "乙4-天下.jpg", "乙6-320寬.jpg"]),
            ("丙 結合：甲的身子、乙的衣服", "Joy 的底圖、小圖、拖縮、搜尋、抽屜、卡一行不改；地塊、戰線、危險度徽、區名＋🔍＋小地圖、箭頭牌、抽屜收成一行蓋上去", ["丙1-打開.jpg", "丙2-點一處.jpg", "丙4-天下.jpg", "丙6-320寬.jpg"]),
        ],
    },
}
GAP, PAD, HEAD, ROWHEAD = 18, 18, 40, 58
name = sys.argv[1] if len(sys.argv) > 1 else "第11輪-一張到底對照"
grid = GRIDS[name]
src = HERE.parent / name
out = HERE.parent / f"{name}.png"
H = 812
rows = []
for title, sub, files in grid["rows"]:
    imgs = []
    for f in files:
        im = Image.open(src / f).convert("RGB")
        w = round(im.width * H / im.height)
        imgs.append(im.resize((w, H)))
    rows.append((title, sub, imgs))
colw = [max(r[2][i].width for r in rows) for i in range(len(grid["cols"]))]
W = PAD * 2 + sum(colw) + GAP * (len(colw) - 1)
TH = HEAD + len(rows) * (ROWHEAD + H + GAP) + PAD
canvas = Image.new("RGB", (W, TH), "#F4EFE4")
draw = ImageDraw.Draw(canvas)
x = PAD
for i, c in enumerate(grid["cols"]):
    draw.text((x, 10), c, font=FONT, fill="#2C2C2A")
    x += colw[i] + GAP
y = HEAD
for title, sub, imgs in rows:
    draw.text((PAD, y), title, font=FONT, fill="#2C2C2A")
    draw.text((PAD, y + 32), sub, font=SMALL, fill="#8A8577")
    y += ROWHEAD
    x = PAD
    for i, im in enumerate(imgs):
        canvas.paste(im, (x, y))
        draw.rectangle([x - 1, y - 1, x + im.width, y + H], outline="#C9BFA8")
        x += colw[i] + GAP
    y += H + GAP
canvas.save(out)
print("ok", out, canvas.size)
