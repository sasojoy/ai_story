"""從 web/icon.svg 的樣子（朱紅底、白「勢」、圓角 14/64）出加入主畫面用的 PNG：`python scripts/make_icons.py web <字型檔>`。
字型是 Noto Serif CJK TC Bold（notofonts/noto-cjk 的 Serif/OTF/TraditionalChinese/NotoSerifCJKtc-Bold.otf，不進版控）；4 倍畫再縮，邊才滑。
iPhone 的 apple-touch-icon（180）滿版（iOS 自己切圓角）；Android 的 192／512 跟 SVG 同一個圓角；maskable 滿版、字縮在中間 80% 的安全圈裡。"""
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = sys.argv[2] if len(sys.argv) > 2 else "NotoSerifTC-Bold.otf"
RED, WHITE = (168, 50, 42, 255), (255, 255, 255, 255)
out = sys.argv[1]


def icon(size, *, rounded, glyph_ratio):
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if rounded:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=round(s * 14 / 64), fill=RED)
    else:
        d.rectangle([0, 0, s, s], fill=RED)
    font = ImageFont.truetype(FONT, round(s * glyph_ratio))
    l, t, r, b = d.textbbox((0, 0), "勢", font=font)
    w, h = r - l, b - t
    d.text(((s - w) / 2 - l, (s - h) / 2 - t), "勢", font=font, fill=WHITE)
    return im.resize((size, size), Image.LANCZOS)


icon(180, rounded=False, glyph_ratio=0.66).save(f"{out}/icon-180.png", optimize=True)   # iPhone 主畫面：iOS 自己切圓角，給滿版
icon(192, rounded=True, glyph_ratio=0.62).save(f"{out}/icon-192.png", optimize=True)    # Android／安裝提示：跟 icon.svg 同一個圓角
icon(512, rounded=True, glyph_ratio=0.62).save(f"{out}/icon-512.png", optimize=True)
icon(512, rounded=False, glyph_ratio=0.5).save(f"{out}/icon-512-maskable.png", optimize=True)  # maskable：滿版、字縮在中間 80% 的安全圈裡
for n in ("180", "192", "512", "512-maskable"):
    im = Image.open(f"{out}/icon-{n}.png")
    print(n, im.size, im.mode)
