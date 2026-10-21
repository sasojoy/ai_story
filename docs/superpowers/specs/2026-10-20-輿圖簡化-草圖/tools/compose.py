# 把三版（甲乙丙）的 375 截圖裁掉狀態列與分頁列、並排、加標題（PIL，字型微軟正黑）
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 30)
BOX = (0, 300, 750, 1510)  # 2 倍像素：從搜尋框到抽屜的動作那一排
GAP, HEAD = 24, 64


def panel(name, title):
    im = Image.open(HERE / f"{name}-375.png").crop(BOX)
    out = Image.new("RGB", (im.width, im.height + HEAD), "#FBF6EA")
    d = ImageDraw.Draw(out)
    d.text((14, 14), title, fill="#2B241B", font=FONT)
    out.paste(im, (0, HEAD))
    return out


def row(items, out_name):
    panels = [panel(n, t) for n, t in items]
    w = sum(p.width for p in panels) + GAP * (len(panels) - 1)
    canvas = Image.new("RGB", (w, panels[0].height), "#D9D2C2")
    x = 0
    for p in panels:
        canvas.paste(p, (x, 0))
        x += p.width + GAP
    canvas.save(HERE / out_name)
    print(out_name, canvas.size)


row([("甲", "甲：只畫領地，點了才看"), ("乙", "乙：領地連成一片"), ("丙", "丙：意境也寫在圖上")], "對照-甲乙丙.png")
row([("原", "現在"), ("甲", "甲：只畫領地，點了才看")], "對照-現在對甲.png")
