"""compose_w2.py <live 資料夾> <丙的資料夾> <輸出資料夾>：W2 的十一張存 JPG（兩倍像素），拼對照圖（照 W1 compose3.py 的排法：每一格上面兩行字）。"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

live, ref, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 18)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 13)
SHOTS = ["W2-1-打開-375淺", "W2-2-點一處-375", "W2-3-去輿圖-375", "W2-4-去輿圖護糧-375", "W2-5-抽屜一排卡-375", "W2-6-抽屜全開-375",
         "W2-7-底條可出陣-375", "W2-8-中景-375", "W2-9-打開-360", "W2-10-打開-320", "W2-11-打開-1280"]
for s in SHOTS:
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


P375, P320 = (375, 812), (320, 568)
row("對照-1-打開.jpg", [
    panel(R("丙1-打開.jpg"), P375, "丙1 打開（草圖）", "倍率 1.5；本週沒有軍令"),
    panel(L("W2-1-打開-375淺"), P375, "W2 打開", "倍率 Z0＝1.5、中心＝你兩票＋腳下五站；本週護糧到長社"),
])
row("對照-2-點一處.jpg", [
    panel(R("丙2-點一處.jpg"), P375, "丙2 點潁川郊野（草圖）", "點小圖"),
    panel(L("W2-2-點一處-375"), P375, "W2 點潁川郊野那一塊地", "倍率 1.5 ≥ Z0：不飛，被擋住才挪（mvNudge）"),
])
row("對照-3-320寬.jpg", [
    panel(R("丙6-320寬.jpg"), P320, "丙6 320 寬（草圖）", "倍率 1.28"),
    panel(L("W2-10-打開-320"), P320, "W2 320 寬", "倍率 Z0＝320／250＝1.28；小地圖 64 寬"),
])
row("對照-4-去輿圖帶目標.jpg", [
    panel(L("W2-3-去輿圖-375"), P375, "江湖頁本週卡「去輿圖」（章回：長社）", "你與長社一起框進來（倍率 0.79 ≤ Z0）"),
    panel(L("W2-4-去輿圖護糧-375"), P375, "護糧（長社→汝南）那一件的「去輿圖」", "下一站與終點一起框進來（0.96）"),
])
row("對照-5-抽屜三格.jpg", [
    panel(L("W2-1-打開-375淺"), P375, "一行（底條）", "沒點地點時最低那一格"),
    panel(L("W2-5-抽屜一排卡-375"), P375, "一排卡", "把手點一下（Joy 原本的半開）"),
    panel(L("W2-6-抽屜全開-375"), P375, "全開", "再拉；右下兩顆收起、不掛箭頭牌"),
])
row("對照-6-底條與中景.jpg", [
    panel(L("W2-7-底條可出陣-375"), P375, "底條「可出陣 7 ›」按下去", "一排卡只列可出陣的、地圖上其餘淡掉"),
    panel(L("W2-8-中景-375"), P375, "中景（Z0 × 0.6＝0.9）", "名字：一步內、大地方、本週、寶、翻；沒有危險度徽與箭頭牌"),
    panel(L("W2-9-打開-360"), (360, 780), "360 寬打開", "倍率 1.44"),
])
print("ok", sorted(os.listdir(out)))
