# 把一輪的幾張手機截圖（375×812）並排成一張，每張上面寫甲乙丙丁與一句話。PIL，字型 msjh.ttc。
# 用法：python compose_round.py <輪的資料夾名>   （在這個資料夾跑；吐 ../<資料夾名>.png）
# 每一輪的面板寫在底下 ROUNDS；新的一輪加一筆。
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 22)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 15)
ROUNDS = {
    "第1輪-第一眼": [
        ("甲-現況.jpg", "甲 現況", "你＋五條路，其餘淡畫；字疊、本週切邊"),
        ("乙-整理過.jpg", "乙 同一個想法，整理過", "淡圖拿掉、字不疊、本週不切邊"),
        ("丙-整區當第一眼.jpg", "丙 打開就是整區", "少一層；名字框、寶、悟字全在"),
        ("丁-路先列出來.jpg", "丁 路先列出來", "上面一小片圖，下面五條路一列一條"),
    ],
    "第2輪-風格": [
        ("甲-木刻古輿圖.jpg", "甲 木刻古輿圖", "紙、墨、地名框、朱印；底下一張路引"),
        ("乙-兵棋沙盤.jpg", "乙 兵棋沙盤", "沙盤、棋子、旗；底下一塊令牌"),
        ("丙-文字路引.jpg", "丙 文字路引", "整頁是一張路引，只有一小格略圖"),
    ],
    "第3輪-沙盤三面": [
        ("1-第一眼.jpg", "① 打開第一眼", "名字牌挑空位擺；木托盤"),
        ("2-點一處.jpg", "② 點潁川郊野", "棋子抬起、路點亮、令牌換成卡"),
        ("3-天下.jpg", "③ 天下", "整張沙盤：五塊盤、小棋、三條戰線的繩"),
    ],
    "第4輪-燈下": [
        ("甲-一步.jpg", "甲 燈下一步", "只亮你＋走得到的；遠的有關的掛在邊上"),
        ("乙-兩步.jpg", "乙 燈下兩步", "再多亮一圈"),
        ("丙-全區.jpg", "丙 全區（第 3 輪的①）", "全亮，對照用"),
    ],
    "第5輪-全套": [
        ("1-燈下兩步.jpg", "① 打開：燈下兩步", "第 4 輪定的"),
        ("2-點亮的.jpg", "② 點潁川郊野（亮的）", "抬起、路點亮、卡"),
        ("3-點暗的.jpg", "③ 點汝南荒野（暗釘）", "那一枚點亮、圖框包進來、卡"),
        ("4-全區.jpg", "④ 全區", "全亮"),
        ("5-天下.jpg", "⑤ 天下", "整張沙盤"),
    ],
}
GAP, TOP, PAD = 18, 66, 18
name = sys.argv[1] if len(sys.argv) > 1 else "第1輪-第一眼"
panels = ROUNDS[name]
src = HERE.parent / name
out = HERE.parent / f"{name}.png"
imgs = [Image.open(src / f).convert("RGB") for f, _, _ in panels]
w, h = imgs[0].size
W = PAD * 2 + w * len(imgs) + GAP * (len(imgs) - 1)
H = TOP + h + PAD
canvas = Image.new("RGB", (W, H), "#F4EFE4")
draw = ImageDraw.Draw(canvas)
for i, (img, (_, title, sub)) in enumerate(zip(imgs, panels)):
    x = PAD + i * (w + GAP)
    draw.text((x, 10), title, font=FONT, fill="#2C2C2A")
    draw.text((x, 42), sub, font=SMALL, fill="#8A8577")
    canvas.paste(img.resize((w, h)), (x, TOP))
    draw.rectangle([x - 1, TOP - 1, x + w, TOP + h], outline="#C9BFA8")
canvas.save(out)
print("ok", out, canvas.size)
