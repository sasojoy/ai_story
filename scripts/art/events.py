"""事件插圖（二十種類型，750×420）：每一類一張，事件照類型掛。構圖簡單：一兩個主題物件、淡墨的地。"""
from __future__ import annotations

from lib import (bare_tree, birds, boat, brush, building, figure, flag, grass, ground, horse, mist, mountain, moon, pine,
                 rng_for, roof, smoke, splatter, stroke, svg, tent, wall, wash, water, willow, INK, fmt)

W, H = 750, 420


def _far(r, op=0.1):
    return mountain(r, -60, 820, 200, 120, op, 8, 4) + mist(0, 130, W, 90, 0.8)


def checkpoint() -> str:
    """哨卡盤查：柵門、橫木、持矛的戍卒、排隊的人。"""
    r = rng_for("哨卡")
    b = [_far(r)]
    for i in range(10):
        x = 220 + i * 34
        b.append(stroke([(x, 300), (x, 230 - r.uniform(0, 10))], 4, r, 0.85, 0.6))
    b.append(stroke([(214, 250), (530, 246)], 3, r, 0.8, 1))
    b.append(brush([(240, 292), (560, 262)], 6, r, 0.9, 1))  # 橫木
    b.append(figure(r, 300, 330, 70, hat=True, pole=True))
    b.append(figure(r, 520, 334, 66, hat=True, pole=True))
    b.append(figure(r, 110, 350, 58, hat=True, lean=4))
    b.append(figure(r, 60, 356, 50, hat=False))
    b.append(ground(r, 340, W))
    b.append(pine(r, 690, 320, 80))
    return svg(W, H, "".join(b))


def ferry() -> str:
    r = rng_for("渡口")
    b = [_far(r, 0.12)]
    b.append(wash([(0, 250), (W, 244), (W, 420), (0, 420)], 0.06, 4, r, 2))
    b.append(water(r, 20, 730, 262, 10, 0.3))
    b.append(boat(r, 240, 330, 170))
    b.append(figure(r, 300, 322, 50, hat=True))
    b.append(figure(r, 340, 322, 46, hat=False))
    for i in range(6):
        b.append(grass(r, 60 + i * 14, 250 + r.uniform(-4, 4), 5, 26, 0.6))
    for i in range(5):
        b.append(grass(r, 640 + i * 16, 258, 5, 22, 0.6))
    b.append(willow(r, 90, 236, 80))
    b.append(birds(r, 500, 110, 4, 0.5))
    return svg(W, H, "".join(b))


def camp() -> str:
    r = rng_for("營寨")
    b = [_far(r)]
    for i in range(16):
        x = 120 + i * 32
        b.append(stroke([(x, 300), (x + r.uniform(-2, 2), 262 - r.uniform(0, 10))], 3.5, r, 0.85, 0.6))
    b.append(stroke([(116, 278), (610, 274)], 2, r, 0.7, 1))
    b.append(tent(r, 180, 262, 110, 70))
    b.append(tent(r, 330, 262, 90, 58, 0.75))
    b.append(tent(r, 460, 262, 120, 76))
    b.append(flag(r, 300, 262, 90))
    b.append(flag(r, 560, 262, 70, 0.85, -1))
    b.append(smoke(r, 420, 262, 70, 0.3))
    b.append(figure(r, 90, 344, 64, hat=False, pole=True))
    b.append(figure(r, 660, 346, 62, hat=True, pole=True))
    b.append(ground(r, 340, W))
    return svg(W, H, "".join(b))


def talisman() -> str:
    """符水道壇：供桌、香爐、長幡、跪拜的人。"""
    r = rng_for("符水")
    b = [_far(r, 0.08)]
    b.append(wash([(200, 300), (560, 300), (545, 270), (215, 270)], 0.55, 0, r, 1))
    b.append(wash([(240, 270), (520, 270), (520, 258), (240, 258)], 0.85, 0, r, 0.8))
    b.append(wash([(360, 258), (400, 258), (396, 232), (364, 232)], 0.9, 0, r, 1))  # 爐
    b.append(smoke(r, 380, 232, 110, 0.35))
    for x, side in ((230, 1), (530, -1)):
        b.append(stroke([(x, 300), (x, 120)], 2.5, r, 0.9, 0.4))
        b.append(wash([(x, 125), (x + side * 36, 125), (x + side * 34, 250), (x, 240)], 0.8, 0, r, 2))
    b.append(figure(r, 310, 356, 52, hat=False, lean=6))
    b.append(figure(r, 440, 358, 50, hat=False, lean=-6))
    b.append(figure(r, 120, 350, 56, hat=True))
    b.append(ground(r, 340, W))
    b.append(pine(r, 680, 310, 70))
    return svg(W, H, "".join(b))


def refugees() -> str:
    r = rng_for("流民")
    b = [_far(r, 0.12)]
    b.append(bare_tree(r, 640, 320, 120))
    b.append(stroke([(0, 360), (200, 340), (420, 336), (750, 322)], 4, r, 0.18, 2))
    xs = (120, 170, 215, 280, 330, 390)
    for i, x in enumerate(xs):
        b.append(figure(r, x, 350 + r.uniform(-6, 6), 54 + r.uniform(-8, 8), hat=i % 2 == 0, pole=i % 3 == 0, lean=3))
    b.append(wash([(140, 292), (168, 292), (164, 276), (144, 276)], 0.9, 0, r, 1))  # 包袱
    b.append(ground(r, 350, W, 0.14))
    b.append(birds(r, 480, 120, 6, 0.7))
    b.append(splatter(r, 250, 400, 16, 50, 2, 0.4))
    return svg(W, H, "".join(b))


def farm() -> str:
    r = rng_for("田")
    b = [_far(r)]
    for i in range(10):
        y = 250 + i * 16
        b.append(stroke([(20 + i * 8, y), (730 - i * 12, y + r.uniform(-3, 3))], 1.4, r, 0.22 + i * 0.03, 1.2))
    b.append(building(r, 560, 240, 90, 56, 1, 0.75))
    b.append(willow(r, 650, 240, 64))
    # 犁與拉犁的人
    b.append(figure(r, 300, 356, 70, hat=True, lean=10))
    b.append(brush([(330, 330), (420, 356), (440, 362)], 4, r, 0.9, 1))
    b.append(wash([(430, 352), (460, 344), (470, 366), (448, 372)], 0.9, 0, r, 1))
    b.append(figure(r, 470, 368, 54, hat=False, lean=4))
    b.append(ground(r, 360, W, 0.12))
    b.append(birds(r, 150, 130, 3, 0.5))
    return svg(W, H, "".join(b))


def market() -> str:
    r = rng_for("市集")
    b = [_far(r, 0.06)]
    for i, x in enumerate((60, 260, 470)):
        b.append(wash([(x, 300), (x + 170, 300), (x + 160, 220), (x + 10, 220)], 0.18, 0, r, 1))
        b.append(wash([(x - 10, 226), (x + 180, 226), (x + 190, 196), (x - 20, 196)], 0.8, 0, r, 2))  # 棚
        b.append(stroke([(x, 300), (x, 226)], 2.5, r, 0.8, 0.5))
        b.append(stroke([(x + 170, 300), (x + 170, 226)], 2.5, r, 0.8, 0.5))
        for k in range(4):
            cx = x + 25 + k * 40
            b.append(f'<ellipse cx="{cx}" cy="294" rx="14" ry="7" fill="{INK}" fill-opacity="0.55"/>')
    b.append(flag(r, 250, 300, 110, 0.9, -1))
    for x in (120, 200, 330, 400, 520, 600):
        b.append(figure(r, x, 352 + r.uniform(-6, 6), 56 + r.uniform(-6, 6), hat=r.random() < 0.5))
    b.append(ground(r, 345, W))
    return svg(W, H, "".join(b))


def tavern() -> str:
    r = rng_for("酒肆")
    b = [_far(r, 0.06)]
    b.append(building(r, 200, 300, 320, 150, 2, 0.8))
    b.append(flag(r, 540, 300, 120, 0.9))
    b.append(wash([(540, 180), (596, 180), (594, 240), (540, 236)], 0.85, 0, r, 2))  # 酒旗
    for i, x in enumerate((100, 140, 640)):
        b.append(f'<ellipse cx="{x}" cy="{300 - i % 2 * 4}" rx="18" ry="24" fill="{INK}" fill-opacity="0.85"/>')
        b.append(f'<ellipse cx="{x}" cy="{276 - i % 2 * 4}" rx="9" ry="4" fill="{INK}" fill-opacity="0.95"/>')
    b.append(f'<circle cx="236" cy="220" r="10" fill="#fbf7ee" stroke="{INK}" stroke-width="2"/>')
    b.append(stroke([(236, 200), (236, 210)], 2, r, 0.9, 0.3))
    b.append(figure(r, 330, 352, 56, hat=True))
    b.append(figure(r, 380, 354, 54, hat=False, lean=-4))
    b.append(ground(r, 342, W))
    b.append(moon(660, 90, 26))
    return svg(W, H, "".join(b))


def academy() -> str:
    r = rng_for("書院")
    b = [_far(r, 0.08)]
    b.append(building(r, 150, 300, 260, 130, 1, 0.8))
    for i in range(4):
        x = 200 + i * 40
        b.append(wash([(x, 296), (x + 20, 296), (x + 20, 236), (x, 236)], 0.9, 0, r, 0.5))
        for k in range(5):
            b.append(f'<rect x="{x + 3}" y="{241 + k * 11}" width="14" height="4" fill="#f4ede0" fill-opacity="0.8"/>')
    b.append(wash([(460, 300), (560, 300), (556, 262), (464, 262)], 0.6, 0, r, 1))
    b.append(f'<rect x="470" y="248" width="80" height="14" fill="#fbf7ee" stroke="{INK}" stroke-width="2"/>')
    b.append(figure(r, 512, 300, 50, hat=False))
    b.append(pine(r, 660, 310, 110))
    b.append(ground(r, 340, W))
    return svg(W, H, "".join(b))


def temple() -> str:
    r = rng_for("寺院")
    b = [_far(r, 0.1)]
    b.append(building(r, 230, 300, 240, 190, 4, 0.9))
    b.append(stroke([(560, 300), (560, 180)], 3, r, 0.9, 0.5))
    b.append(stroke([(520, 182), (600, 182)], 3, r, 0.9, 0.5))
    b.append(wash([(540, 186), (580, 186), (586, 236), (560, 248), (534, 236)], 0.95, 0, r, 1))  # 鐘
    b.append(smoke(r, 350, 300, 120, 0.25))
    b.append(figure(r, 150, 350, 56, hat=False))
    b.append(pine(r, 80, 320, 110))
    b.append(pine(r, 690, 318, 90))
    b.append(ground(r, 342, W))
    return svg(W, H, "".join(b))


def mountain_path() -> str:
    r = rng_for("山道")
    b = []
    b.append(mountain(r, -60, 500, 300, 60, 0.35, 0, 2))
    b.append(mountain(r, 350, 850, 320, 30, 0.5, 0, 2))
    b.append(wash([(300, 420), (520, 420), (600, 180), (700, 100), (750, 120), (750, 420)], 0.7, 0, r, 3))  # 崖
    b.append(mist(0, 80, 400, 120, 0.8))
    b.append(stroke([(0, 400), (160, 360), (300, 330), (420, 290), (560, 240)], 5, r, 0.2, 2))
    b.append(figure(r, 330, 334, 60, hat=True, pole=True, lean=6))
    b.append(wash([(312, 300), (342, 300), (338, 284), (316, 284)], 0.85, 0, r, 1))  # 藥簍
    b.append(pine(r, 620, 200, 80))
    b.append(pine(r, 120, 345, 70, 0.85))
    for i in range(8):
        b.append(grass(r, r.uniform(20, 300), r.uniform(360, 410), 4, 12, 0.5))
    b.append(birds(r, 80, 100, 4, 0.6))
    return svg(W, H, "".join(b))


def cave() -> str:
    r = rng_for("洞窟")
    b = []
    b.append(wash([(0, 420), (0, 60), (750, 40), (750, 420)], 0.55, 0, r, 4))
    b.append(wash([(260, 420), (250, 260), (310, 160), (430, 140), (520, 240), (520, 420)], 0.98, 0, r, 6))  # 洞口
    b.append(f'<ellipse cx="390" cy="330" rx="40" ry="70" fill="#f4ede0" fill-opacity="0.25" filter="url(#blur10)"/>')  # 火光
    b.append(figure(r, 390, 406, 70, hat=True, pole=False, opacity=0.35))
    for i in range(5):
        y = 404 - i * 12
        b.append(stroke([(300 + i * 10, y), (480 - i * 10, y)], 2, r, 0.35, 1))
    b.append(grass(r, 240, 420, 6, 24, 0.6))
    b.append(grass(r, 540, 418, 6, 22, 0.6))
    b.append(splatter(r, 390, 150, 26, 90, 2.2, 0.5))
    return svg(W, H, "".join(b))


def cart() -> str:
    r = rng_for("糧車")
    b = [_far(r)]
    b.append(stroke([(0, 380), (750, 350)], 5, r, 0.18, 2))
    # 車：板、麻袋、輪
    b.append(wash([(260, 330), (520, 322), (516, 300), (264, 306)], 0.9, 0, r, 1))
    for i in range(4):
        x = 280 + i * 58
        b.append(f'<ellipse cx="{x + 24}" cy="288" rx="28" ry="18" fill="{INK}" fill-opacity="0.85"/>')
    b.append(f'<circle cx="320" cy="350" r="28" fill="none" stroke="{INK}" stroke-width="6"/>')
    b.append(f'<circle cx="470" cy="346" r="28" fill="none" stroke="{INK}" stroke-width="6" stroke-dasharray="20 8" transform="rotate(25 470 346)"/>')  # 斷了的輪
    for a in (0, 60, 120):
        b.append(f'<line x1="292" y1="350" x2="348" y2="350" stroke="{INK}" stroke-width="3" transform="rotate({a} 320 350)"/>')
    b.append(brush([(260, 318), (180, 330), (140, 336)], 5, r, 0.9, 1))  # 轅
    b.append(wash([(60, 350), (150, 350), (160, 300), (120, 290), (60, 300)], 0.9, 0, r, 2))  # 牛
    b.append(brush([(60, 300), (40, 290), (30, 300)], 4, r, 0.9, 1))
    for lx in (70, 140):
        b.append(brush([(lx, 350), (lx, 378)], 8, r, 0.9, 0.5))
    b.append(figure(r, 580, 378, 62, hat=True, lean=-4))
    b.append(ground(r, 372, W))
    return svg(W, H, "".join(b))


def courier() -> str:
    r = rng_for("驛馬")
    b = [_far(r, 0.08)]
    b.append(stroke([(0, 380), (750, 360)], 5, r, 0.15, 2))
    b.append(horse(r, 260, 360, 110))
    # 騎士
    b.append(wash([(330, 300), (380, 294), (376, 250), (340, 248)], 0.96, 0, r, 2))
    b.append(f'<circle cx="358" cy="236" r="13" fill="{INK}"/>')
    b.append(wash([(338, 232), (358, 212), (380, 232)], 0.96, 0, r, 1))
    b.append(brush([(376, 262), (420, 250), (440, 236)], 6, r, 0.9, 1))
    b.append(splatter(r, 220, 370, 40, 90, 2.6, 0.5))
    b.append(stroke([(560, 372), (560, 260)], 3, r, 0.9, 0.4))
    b.append(wash([(560, 262), (608, 270), (604, 294), (560, 300)], 0.85, 0, r, 1.5))
    b.append(building(r, 600, 372, 100, 60, 1, 0.6))
    b.append(ground(r, 372, W))
    return svg(W, H, "".join(b))


def ruins() -> str:
    r = rng_for("舊壘")
    b = [_far(r, 0.12)]
    b.append(wash([(100, 340), (330, 340), (320, 250), (260, 236), (200, 262), (150, 240), (110, 270)], 0.55, 0, r, 3))
    b.append(wash([(420, 340), (560, 340), (556, 290), (500, 300), (470, 270), (430, 296)], 0.5, 0, r, 3))
    for i in range(14):
        x = 110 + r.uniform(0, 420)
        b.append(f'<rect x="{fmt(x)}" y="{fmt(r.uniform(250, 330))}" width="14" height="7" fill="{INK}" fill-opacity="0.35"/>')
    b.append(brush([(610, 350), (640, 230)], 4, r, 0.85, 1))  # 插在地上的矛
    b.append(wash([(640, 230), (628, 236), (632, 206), (652, 200)], 0.9, 0, r, 1))
    b.append(bare_tree(r, 60, 345, 100))
    for i in range(14):
        b.append(grass(r, r.uniform(20, 730), r.uniform(330, 410), 5, r.uniform(10, 20), 0.55))
    b.append(birds(r, 400, 110, 6, 0.75))
    b.append(ground(r, 345, W, 0.1))
    return svg(W, H, "".join(b))


def gate() -> str:
    r = rng_for("城門")
    b = [_far(r, 0.08)]
    b.append(wall(r, 0, 750, 300, 110, 0.65, 28))
    b.append(building(r, 300, 190, 150, 90, 2, 0.9))
    b.append(wash([(338, 300), (412, 300), (412, 236), (375, 216), (338, 236)], 0.95, 0, r, 1))
    b.append(flag(r, 290, 192, 50, 0.85, -1))
    b.append(flag(r, 460, 192, 50, 0.85))
    b.append(figure(r, 320, 350, 60, hat=True, pole=True))
    b.append(figure(r, 430, 350, 60, hat=True, pole=True))
    for x in (120, 170, 215, 560, 610):
        b.append(figure(r, x, 358 + r.uniform(-4, 4), 52, hat=r.random() < 0.6))
    b.append(ground(r, 350, W))
    return svg(W, H, "".join(b))


def manor() -> str:
    r = rng_for("莊院")
    b = [_far(r, 0.1)]
    b.append(wall(r, 120, 640, 300, 60, 0.5, 20))
    b.append(building(r, 320, 300, 120, 80, 1, 0.9))
    b.append(wash([(360, 300), (400, 300), (400, 262), (360, 262)], 0.95, 0, r, 1))
    b.append(building(r, 180, 240, 110, 70, 2, 0.7))
    b.append(building(r, 470, 240, 110, 70, 2, 0.7))
    b.append(f'<circle cx="345" cy="270" r="7" fill="#fbf7ee" stroke="{INK}" stroke-width="2"/>')
    b.append(f'<circle cx="415" cy="270" r="7" fill="#fbf7ee" stroke="{INK}" stroke-width="2"/>')
    b.append(pine(r, 70, 310, 90))
    b.append(willow(r, 690, 300, 80))
    b.append(figure(r, 250, 352, 56, hat=False))
    b.append(ground(r, 345, W))
    return svg(W, H, "".join(b))


def pirates() -> str:
    r = rng_for("水寇")
    b = []
    b.append(moon(620, 90, 34))
    b.append(mountain(r, -60, 820, 210, 150, 0.14, 8, 4))
    b.append(wash([(0, 230), (W, 226), (W, 420), (0, 420)], 0.08, 4, r, 2))
    b.append(water(r, 20, 730, 240, 12, 0.3))
    b.append(boat(r, 120, 310, 150, 0.9, False))
    b.append(figure(r, 200, 304, 52, hat=True, pole=True))
    b.append(figure(r, 240, 304, 48, hat=False))
    b.append(boat(r, 420, 350, 180, 0.95, False))
    b.append(figure(r, 500, 344, 56, hat=True))
    b.append(brush([(520, 300), (470, 250)], 3, r, 0.9, 1))  # 撓鉤
    b.append(brush([(470, 250), (458, 262)], 3, r, 0.9, 0.5))
    for i in range(8):
        b.append(grass(r, 60 + i * 12, 232 + r.uniform(-3, 3), 4, 30, 0.6))
    for i in range(6):
        b.append(grass(r, 660 + i * 14, 240, 4, 26, 0.6))
    return svg(W, H, "".join(b))


def sparring() -> str:
    r = rng_for("比武")
    b = [_far(r, 0.06)]
    b.append(ground(r, 330, W, 0.14, 8))
    b.append(figure(r, 300, 350, 90, hat=False, lean=14))
    b.append(brush([(330, 290), (420, 250)], 6, r, 0.95, 1))
    b.append(figure(r, 470, 356, 88, hat=True, lean=-12))
    b.append(brush([(440, 300), (360, 262)], 6, r, 0.95, 1))
    b.append(splatter(r, 385, 300, 50, 70, 2.6, 0.55))
    for x in (80, 130, 630, 680):
        b.append(figure(r, x, 332, 44, hat=r.random() < 0.5, opacity=0.6))
    b.append(flag(r, 700, 330, 90, 0.8))
    return svg(W, H, "".join(b))


def stealth() -> str:
    r = rng_for("夜探")
    b = []
    b.append(wash([(0, 0), (W, 0), (W, H), (0, H)], 0.22, 0))
    b.append(moon(140, 80, 30))
    for i in range(18):
        x = 220 + i * 30
        b.append(stroke([(x, 300), (x + r.uniform(-2, 2), 236 - r.uniform(0, 10))], 4, r, 0.9, 0.6))
    b.append(stroke([(216, 262), (760, 258)], 2.5, r, 0.8, 1))
    b.append(tent(r, 300, 236, 90, 56, 0.7))
    b.append(tent(r, 440, 236, 110, 66, 0.75))
    b.append(f'<circle cx="400" cy="250" r="30" fill="#fbf7ee" fill-opacity="0.3" filter="url(#blur10)"/>')
    b.append(figure(r, 150, 360, 56, hat=False, lean=16))  # 貓著腰的人
    b.append(figure(r, 560, 300, 40, hat=True, pole=True, opacity=0.6))
    for i in range(10):
        b.append(grass(r, r.uniform(20, 300), r.uniform(330, 410), 5, r.uniform(10, 20), 0.6))
    b.append(splatter(r, 150, 400, 18, 50, 2, 0.4))
    return svg(W, H, "".join(b))


EVENTS = {
    "checkpoint": checkpoint, "ferry": ferry, "camp": camp, "talisman": talisman, "refugees": refugees, "farm": farm,
    "market": market, "tavern": tavern, "academy": academy, "temple": temple, "mountain_path": mountain_path, "cave": cave,
    "cart": cart, "courier": courier, "ruins": ruins, "gate": gate, "manor": manor, "pirates": pirates, "sparring": sparring,
    "stealth": stealth,
}
EVENT_NAMES = {
    "checkpoint": "哨卡盤查", "ferry": "渡口船家", "camp": "營寨", "talisman": "符水道壇", "refugees": "流民逃卒", "farm": "田畝",
    "market": "市集", "tavern": "酒肆", "academy": "書院藏書", "temple": "寺院", "mountain_path": "山道採藥", "cave": "洞窟地窖",
    "cart": "糧車牛車", "courier": "驛馬急報", "ruins": "舊壘遺跡", "gate": "城門", "manor": "莊院塢堡", "pirates": "水寇夜泊",
    "sparring": "比武角力", "stealth": "夜探潛行",
}
