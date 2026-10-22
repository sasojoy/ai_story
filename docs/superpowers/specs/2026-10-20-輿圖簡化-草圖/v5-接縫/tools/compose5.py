"""三種時刻各一張對照（甲乙丙三欄；每一欄上面是天下圖的潁川汝南那一角＋抽屜收著那一行，下面是區圖＋那一處的卡）。
用法：python compose5.py <輸出資料夾>"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 30)
FONT_B = ImageFont.truetype(r"C:\Windows\Fonts\msjhbd.ttc", 34)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 24)
SCALE = 0.75

TITLE = {
    "A": ("A 戰書下了、還沒開打", "汝南荒野（中立）：官軍推到 65，官帥下了戰書，約今天 12:00 攻城；那一塊凍結到打完"),
    "B": ("B 攻城戰正在打", "潁川郊野（官軍的）：黃巾推到 62 下了戰書，此刻集結・交戰中（看的人是官軍，守方）"),
    "C": ("C 打完（到換天前）", "荒丘（中立）：官軍的攻城戰打贏，剛易手、冷卻中"),
}
COLS = {
    "A": [("甲", "只在卡上，地圖不加記號"), ("乙", "區圖名字框旁「戰」字印＋天下圖那一格朱紅虛線框"), ("丙", "抽屜收著那一行多一條「戰書」")],
    "B": [("甲", "借現有的「激戰」：天下圖那一格紅光、區圖名字框一圈紅（會閃）"), ("乙", "區圖「戰」字印（會閃）＋天下圖那一格朱紅實線框"), ("丙", "抽屜收著那一行多一條「攻城」")],
    "C": [("甲", "只在卡上（地圖本來就畫剛易手）"), ("乙", "區圖名字框旁「克」字印（守住寫「守」）"), ("丙", "抽屜收著那一行多一條「戰果」")],
}
WORLD_BOX = (0, 990, 750, 1515)   # 天下圖：潁川汝南那一角＋抽屜收著那一行
REGION_BOX = (0, 300, 750, 1515)  # 區圖：名字框＋那一處的卡


def wrap(draw, text, font, width):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > width:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + ([cur] if cur else [])


for st in "ABC":
    cols = []
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    head = 18 + 40 * max(len(wrap(probe, f"{v}：{words}", FONT, 750 - 28)) for v, words in COLS[st]) + 10
    for v, words in COLS[st]:
        world = Image.open(SHOTS / f"{st}{v}-world.png").crop(WORLD_BOX)
        region = Image.open(SHOTS / f"{st}{v}-region.png").crop(REGION_BOX)
        label = wrap(probe, f"{v}：{words}", FONT, 750 - 28)
        col = Image.new("RGB", (750, head + world.height + 14 + region.height), "#FBF6EA")
        d = ImageDraw.Draw(col)
        for i, line in enumerate(label):
            d.text((14, 14 + 40 * i), line, fill="#2B241B", font=FONT)
        col.paste(world, (0, head))
        d.line([(0, head + world.height + 6), (750, head + world.height + 6)], fill="#D9D2C2", width=4)
        col.paste(region, (0, head + world.height + 14))
        cols.append(col)
    top = 110
    width = sum(c.width for c in cols) + 24 * (len(cols) - 1)
    height = top + max(c.height for c in cols)
    canvas = Image.new("RGB", (width, height), "#D9D2C2")
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, width, top - 8], fill="#F3ECDD")
    d.text((16, 12), TITLE[st][0], fill="#8E2A22", font=FONT_B)
    d.text((16, 62), TITLE[st][1], fill="#2B241B", font=SMALL)
    x = 0
    for c in cols:
        canvas.paste(c, (x, top))
        x += c.width + 24
    canvas = canvas.resize((int(width * SCALE), int(height * SCALE)), Image.LANCZOS)
    name = {"A": "對照-A-戰書下了到當晚.png", "B": "對照-B-攻城戰正在打.png", "C": "對照-C-打完.png"}[st]
    canvas.save(OUT / name, optimize=True)
    print(name, canvas.size, (OUT / name).stat().st_size)
