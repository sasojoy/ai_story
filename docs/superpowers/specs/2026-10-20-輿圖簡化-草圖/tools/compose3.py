from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
HERE = Path(r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray----------claude-worktrees-serene-galileo-46e759\809cb46d-34d6-4713-96aa-0a3fd28bf9c7\scratchpad\mapdisc")
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 30)
items = [("一甲-現在的山水加古輿圖記號", "一甲：現在的設色山水＋古輿圖記號"), ("一乙-工筆手繪", "一乙：工筆手繪（山樹河官道、印章框）"), ("一丙-絹本設色", "一丙：絹本設色（青綠赭石、金印、卷軸邊）")]
panels = []
for name, title in items:
    im = Image.open(HERE / f"{name}.png").crop((0, 120, 750, 1510))
    out = Image.new("RGB", (im.width, im.height + 64), "#FBF6EA")
    ImageDraw.Draw(out).text((14, 14), title, fill="#2B241B", font=FONT)
    out.paste(im, (0, 64)); panels.append(out)
w = sum(p.width for p in panels) + 48
canvas = Image.new("RGB", (w, panels[0].height), "#D9D2C2"); x = 0
for p in panels: canvas.paste(p, (x, 0)); x += p.width + 24
canvas.save(HERE / "對照-古輿圖三版.png"); print(canvas.size)
