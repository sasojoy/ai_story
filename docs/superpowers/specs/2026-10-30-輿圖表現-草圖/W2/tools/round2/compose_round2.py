"""compose_round2.py：第二輪重拍之後，對照-4（去輿圖帶目標）、對照-5（抽屜三格）照新的四張重拼（排法照 W2 tools/compose_w2.py；
W2-1 沒重拍，用資料夾裡那一張 JPG）。數字照 retake 的 measure.json 寫。"""
import io
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
W2B = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2b"
W2 = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_1654dfc8-5ce-1\docs\superpowers\specs\2026-10-30-輿圖表現-草圖\W2"
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 18)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 13)
with open(os.path.join(W2B, "out", "retake", "measure.json"), encoding="utf-8") as f:
    M = json.load(f)


def labeled(im, title, sub):
    head = 52
    p = Image.new("RGB", (im.width, im.height + head), "white")
    p.paste(im, (0, head))
    d = ImageDraw.Draw(p)
    d.text((8, 4), title, fill="#2a231c", font=FONT)
    d.text((8, 30), sub, fill="#6e5e49", font=SMALL)
    return p


def panel(path, title, sub):
    return labeled(Image.open(path).convert("RGB").resize((375, 812), Image.LANCZOS), title, sub)


def row(name, panels):
    gap = 16
    img = Image.new("RGB", (sum(p.width for p in panels) + gap * (len(panels) - 1), max(p.height for p in panels)), "white")
    x = 0
    for p in panels:
        img.paste(p, (x, 0))
        x += p.width + gap
    img.save(os.path.join(W2, name), quality=88)
    print("saved", name, img.size)


def L(n):
    return os.path.join(W2B, "out", "retake", n + ".png")


m3, m4, m5, m6 = (M[k] for k in ("W2-3-去輿圖-375", "W2-4-去輿圖護糧-375", "W2-5-抽屜一排卡-375", "W2-6-抽屜全開-375"))
row("對照-4-去輿圖帶目標.jpg", [
    panel(L("W2-3-去輿圖-375"), "江湖頁本週卡「去輿圖」（章回：長社）", f"第二輪：你與長社一起框、留白照螢幕 px（倍率 {m3['z']}，第一輪 0.79）"),
    panel(L("W2-4-去輿圖護糧-375"), "護糧（長社→汝南）那一件的「去輿圖」", f"第二輪：你、下一站、終點三點一起框（倍率 {m4['z']}，第一輪 0.96 只框兩頭）"),
])
row("對照-5-抽屜三格.jpg", [
    panel(os.path.join(W2, "W2-1-打開-375淺.jpg"), "一行（底條）", "沒點地點時最低那一格"),
    panel(L("W2-5-抽屜一排卡-375"), "一排卡", f"第二輪：真觸控點把手一下（抽屜 {m5['drawerPx']}px，沒開任何一處的卡）"),
    panel(L("W2-6-抽屜全開-375"), "全開", f"第二輪：真觸控把手拖到頂；收起的：{'、'.join(m6.get('hudHidden') or []) or '沒有'}"),
])
