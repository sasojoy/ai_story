"""挑定之後那一輪的草圖：真實畫面轉 JPEG（品質 88），三組對比並排（甲是做進程式的），爐火小籤四種狀態一條。
python compose_picks.py <拍圖的 scratch 資料夾> <草圖資料夾/挑定>"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SP, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 30)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 24)
PAPER, INK, RED = (245, 239, 226), (40, 30, 20), (150, 60, 30)
sys.stdout.reconfigure(encoding="utf-8")


def side_by_side(items, target, scale=0.5, crop=None):
    """items：[(甲乙丙, 說明, Image)]；甲底下多一行「做進程式的（我先選的）」。"""
    shots = [img.crop(crop) if crop else img for _, _, img in items]
    w, h = shots[0].size
    sw, sh = int(w * scale), int(h * scale)
    head, gap = 90, 24
    out = Image.new("RGB", (len(shots) * sw + (len(shots) + 1) * gap, sh + head + gap), PAPER)
    draw = ImageDraw.Draw(out)
    for i, ((mark, note, _), img) in enumerate(zip(items, shots)):
        x = gap + i * (sw + gap)
        draw.text((x, 14), f"{mark}　{note}", fill=INK, font=FONT)
        if mark == "甲":
            draw.text((x, 54), "做進程式的（我先選的）", fill=RED, font=SMALL)
        out.paste(img.resize((sw, sh), Image.LANCZOS), (x, head))
    out.save(OUT / target, quality=88)
    print(target, out.size)


def stack(images, crop):
    parts = [img.crop(crop) for img in images]
    w = parts[0].size[0]
    out = Image.new("RGB", (w, sum(p.size[1] for p in parts) + 16 * (len(parts) - 1)), PAPER)
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.size[1] + 16
    return out


opened = SP / "shots-open"
load = lambda folder, name: Image.open(SP / folder / f"{name}.png").convert("RGB")  # noqa: E731

# 一、爐火小籤看不了時寫什麼（今天用掉了／錢不夠）：甲 短字＋點了講整句；乙 小籤直接寫原因
FIRE = (0, 380, 750, 720)
side_by_side([
    ("甲", "短字、點了講整句", stack([load("shots-used", "對比-小籤-甲-看不了寫短字-used"), load("shots-poor", "對比-小籤-甲-看不了寫短字-poor")], FIRE)),
    ("乙", "小籤直接寫原因", stack([load("shots-used", "對比-小籤-乙-看不了寫原因-used"), load("shots-poor", "對比-小籤-乙-看不了寫原因-poor")], FIRE)),
], "對比-小籤看不了.jpg", scale=0.75)

# 爐火小籤四種狀態（還沒看、看過了、今天用掉了、錢不夠），375 淺
strip = [load("shots-open", "爐火小籤-375淺"), load("shots-ready", "爐火小籤-看過了-375淺"),
         load("shots-used", "對比-小籤-甲-看不了寫短字-used"), load("shots-poor", "對比-小籤-甲-看不了寫短字-poor")]
side_by_side([("　", n, img) for n, img in zip(("還沒看", "看過了", "今天用掉了", "錢不夠"), strip)],
             "爐火小籤-四種狀態-375淺.jpg", scale=0.6, crop=FIRE)

# 二、裝備庫 320 寬（右邊放不下二乘二）
side_by_side([
    ("甲", "二乘二改排名字底下", load("shots-open", "對比-裝備庫320-甲-二乘二改排名字底下")),
    ("乙", "照舊排右邊・欄寬 52%", load("shots-open", "對比-裝備庫320-乙-照舊排右邊-欄寬52%")),
    ("丙", "照舊排右邊・欄寬 11.4em", load("shots-open", "對比-裝備庫320-丙-照舊排右邊-欄寬11.4em")),
], "對比-裝備庫320.jpg", scale=0.6)

# 三、長名字放進圓印
side_by_side([
    ("甲", "橫寫折兩行", load("shots-open", "對比-長名字-甲-橫寫折兩行")),
    ("乙", "直寫、右起", load("shots-open", "對比-長名字-乙-直寫右起")),
    ("丙", "原型的縮字", load("shots-open", "對比-長名字-丙-原型的縮字")),
], "對比-長名字.jpg")

# 真實畫面
for png in sorted(opened.glob("*.png")):
    if png.name.startswith("對比-"):
        continue
    Image.open(png).convert("RGB").save(OUT / f"{png.stem}.jpg", quality=88)
Image.open(SP / "shots-ready" / "爐火小籤-看過了-375淺.png").convert("RGB").save(OUT / "爐火小籤-看過了-375淺.jpg", quality=88)
total = sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
print("files", len(list(OUT.iterdir())), "MB", round(total / 1e6, 2))
