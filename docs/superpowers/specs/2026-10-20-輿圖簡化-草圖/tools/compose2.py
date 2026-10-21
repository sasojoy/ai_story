from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
HERE = Path(r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray----------claude-worktrees-serene-galileo-46e759\809cb46d-34d6-4713-96aa-0a3fd28bf9c7\scratchpad\mapdisc")
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 30)
items = [("風格一-古輿圖", "一：古輿圖（紙本手繪、淡彩領地、朱印）"), ("風格二-戰棋版圖", "二：戰棋版圖（六角格、整塊上色）"), ("風格三-極簡節點", "三：極簡節點（平底、圓點＝領地）")]
panels = []
for name, title in items:
    im = Image.open(HERE / f"{name}.png").crop((0, 120, 750, 1510))
    out = Image.new("RGB", (im.width, im.height + 64), "#FBF6EA")
    ImageDraw.Draw(out).text((14, 14), title, fill="#2B241B", font=FONT)
    out.paste(im, (0, 64)); panels.append(out)
w = sum(p.width for p in panels) + 24 * 2
canvas = Image.new("RGB", (w, panels[0].height), "#D9D2C2"); x = 0
for p in panels: canvas.paste(p, (x, 0)); x += p.width + 24
canvas.save(HERE / "對照-三種風格.png"); print(canvas.size)
