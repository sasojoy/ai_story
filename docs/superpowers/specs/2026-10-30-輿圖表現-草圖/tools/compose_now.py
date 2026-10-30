# 把「現況」四張手機截圖（375×812）並排成一張，每張上面寫是第幾層。PIL，字型 msjh.ttc。
# 用法：python compose_now.py  （在這個資料夾跑；吐 ../現況-四層.png）
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "現況"
OUT = HERE.parent / "現況-四層.png"
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 22)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 16)
PANELS = [
    ("1-第一層-打開第一眼.jpg", "① 打開第一眼", "只畫你＋走得到的"),
    ("2-第二層-點一處.jpg", "② 點一處", "卡半開"),
    ("3-第三層-全區.jpg", "③ 按「全區」", "名字框、寶、悟字"),
    ("4-第四層-天下.jpg", "④ 按「天下」", "大區、前線、寶"),
]
GAP, TOP, PAD = 18, 64, 18
imgs = [Image.open(SRC / f).convert("RGB") for f, _, _ in PANELS]
w, h = imgs[0].size
W = PAD * 2 + w * len(imgs) + GAP * (len(imgs) - 1)
H = TOP + h + PAD
canvas = Image.new("RGB", (W, H), "#F4EFE4")
draw = ImageDraw.Draw(canvas)
for i, (img, (_, title, sub)) in enumerate(zip(imgs, PANELS)):
    x = PAD + i * (w + GAP)
    draw.text((x, 10), title, font=FONT, fill="#2C2C2A")
    draw.text((x, 40), sub, font=SMALL, fill="#8A8577")
    canvas.paste(img, (x, TOP))
    draw.rectangle([x - 1, TOP - 1, x + w, TOP + h], outline="#C9BFA8")
canvas.save(OUT)
print("ok", OUT, canvas.size)
