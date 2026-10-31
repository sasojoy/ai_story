"""compose3.py <live 資料夾> <丙的資料夾> <輸出資料夾>：W1 後續（10/31）重拍的六張存 JPG（兩倍像素），重拼對照-1～3（同 compose2.py 的排法）；
對照-4（線寬）沒變、不重做。"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

live, ref, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 18)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 13)

for s in ["W1-1-打開-375淺", "W1-1b-打開-375深", "W1-2-點一處-375", "W1-3-打開-320", "W1-4-打開-1280", "W1-5-丙的倍率-375"]:
    Image.open(os.path.join(live, s + ".png")).convert("RGB").save(os.path.join(out, s + ".jpg"), quality=86)


def labeled(im, title, sub):
    head = 52
    p = Image.new("RGB", (im.width, im.height + head), "white")
    p.paste(im, (0, head))
    d = ImageDraw.Draw(p)
    d.text((8, 4), title, fill="#2a231c", font=FONT)
    d.text((8, 30), sub, fill="#6e5e49", font=SMALL)
    return p


def panel(path, size, title, sub):
    return labeled(Image.open(path).convert("RGB").resize(size, Image.LANCZOS), title, sub)


def row(name, panels):
    gap = 16
    img = Image.new("RGB", (sum(p.width for p in panels) + gap * (len(panels) - 1), max(p.height for p in panels)), "white")
    x = 0
    for p in panels:
        img.paste(p, (x, 0))
        x += p.width + gap
    img.save(os.path.join(out, name), quality=88)


def R(n):
    return os.path.join(ref, n)


def L(n):
    return os.path.join(live, n + ".png")


row("對照-1-打開.jpg", [
    panel(R("丙1-打開.jpg"), (375, 812), "丙1 打開（草圖）", "倍率 1.5；取景、區名、小地圖、底條是 W2"),
    panel(L("W1-1-打開-375淺"), (375, 812), "W1 打開（Joy 的取景）", "倍率 1.15＝中景；右下汝南荒野：中立正在翻＝紅框"),
    panel(L("W1-5-丙的倍率-375"), (375, 812), "W1 放到丙的倍率", "倍率 1.5＝近景（有危險度徽）：比線寬用"),
])
row("對照-2-點一處.jpg", [
    panel(R("丙2-點一處.jpg"), (375, 812), "丙2 點潁川郊野（草圖）", "點小圖"),
    panel(L("W1-2-點一處-375"), (375, 812), "W1 點潁川郊野那一塊地", "真的點在地上（離小圖 26px 以上）"),
])
row("對照-3-320寬.jpg", [
    panel(R("丙6-320寬.jpg"), (320, 568), "丙6 320 寬（草圖）", "倍率 1.28"),
    panel(L("W1-3-打開-320"), (320, 568), "W1 320 寬", "倍率 1.15（中景）"),
])
print("ok", sorted(os.listdir(out)))
