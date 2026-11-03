"""草圖資料夾收尾：每一組「對比-<組>-<甲乙丙>-<說明>.png」並排成一張「對比-<組>.jpg」（上面寫甲乙丙與說明，甲是做進程式的那一種），
其餘的 PNG 一律轉成 JPEG（品質 88）省空間，原本的 PNG 刪掉。用法：python compose.py <草圖根>"""
import re
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(sys.argv[1])
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 30)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 24)
for batch in ("A", "C", "E"):
    folder = ROOT / batch
    groups = defaultdict(list)
    for png in sorted(folder.glob("對比-*.png")):
        m = re.match(r"對比-(.+?)-([甲乙丙])-(.+)\.png$", png.name)
        groups[m.group(1)].append((m.group(2), m.group(3), png))
    for group, items in groups.items():
        items.sort(key=lambda x: "甲乙丙".index(x[0]))
        shots = [Image.open(p).convert("RGB") for _, _, p in items]
        w, h = shots[0].size
        scale = 0.5
        sw, sh = int(w * scale), int(h * scale)
        head, gap = 90, 24
        out = Image.new("RGB", (len(shots) * sw + (len(shots) + 1) * gap, sh + head + gap), (245, 239, 226))
        draw = ImageDraw.Draw(out)
        for i, ((mark, note, _), img) in enumerate(zip(items, shots)):
            x = gap + i * (sw + gap)
            draw.text((x, 14), f"{mark}　{note}", fill=(40, 30, 20), font=FONT)
            if mark == "甲":
                draw.text((x, 54), "做進程式的（我先選的）", fill=(150, 60, 30), font=SMALL)
            out.paste(img.resize((sw, sh), Image.LANCZOS), (x, head))
        target = folder / f"對比-{group}.jpg"
        out.save(target, quality=88)
        print("composite", target.name, out.size)
    for png in folder.glob("*.png"):
        Image.open(png).convert("RGB").save(png.with_suffix(".jpg"), quality=88)
        png.unlink()
total = sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())
print("total MB", round(total / 1e6, 1))
