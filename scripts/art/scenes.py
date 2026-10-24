"""地點場景圖（六張，750×450）：五個大區各一張、天下一張。畫面只有水墨，沒有字。"""
from __future__ import annotations

from lib import (bare_tree, birds, boat, brush, building, figure, flag, grass, ground, horse, mist, mountain, moon, pine,
                 rng_for, roof, smoke, splatter, stroke, svg, tent, wall, wash, water, willow)

W, H = 750, 450


def yingru() -> str:
    """潁川汝南：潁水繞田、長社城樓、楊柳、官道上一個人。"""
    r = rng_for("潁川汝南")
    b = []
    b.append(mountain(r, -40, 500, 215, 120, 0.10, 6, 4))
    b.append(mountain(r, 300, 800, 220, 140, 0.16, 4, 3))
    b.append(mist(0, 150, W, 90, 0.7))
    # 長社城：城下先鋪一層地
    b.append(wash([(440, 262), (750, 258), (750, 300), (430, 300)], 0.1, 6, r, 2))
    b.append(wall(r, 470, 740, 262, 34, 0.55, 14))
    b.append(building(r, 560, 230, 90, 70, 2, 0.8))
    b.append(flag(r, 650, 232, 40, 0.8))
    # 田：橫的淡筆
    for i in range(9):
        y = 290 + i * 16
        b.append(stroke([(20 + i * 6, y), (330 - i * 10, y + r.uniform(-2, 2))], 1.2, r, 0.25 + i * 0.03, 1))
    # 潁水：從左中彎到右下
    river = [(0, 262), (120, 268), (250, 300), (330, 350), (420, 385), (560, 410), (750, 420)]
    b.append(wash([(x, y - 10) for x, y in river] + [(x, y + 26) for x, y in reversed(river)], 0.07, 2, r, 1))
    b.append(water(r, 60, 700, 300, 7, 0.3))
    # 楊柳與人
    b.append(willow(r, 150, 262, 70))
    b.append(willow(r, 215, 258, 58, 0.7))
    b.append(ground(r, 388, W, 0.14, 8))
    b.append(stroke([(380, 450), (430, 400), (520, 386), (640, 392)], 3.5, r, 0.18, 2))
    b.append(figure(r, 470, 404, 46, hat=True, pole=False))
    b.append(pine(r, 690, 395, 60))
    b.append(birds(r, 300, 110, 5, 0.6))
    b.append(splatter(r, 120, 420, 14, 40, 2, 0.5))
    return svg(W, H, "".join(b))


def nanyang() -> str:
    """南陽：宛城大牆與門樓、淯水、渡船、城外松林。"""
    r = rng_for("南陽")
    b = []
    b.append(mountain(r, -60, 420, 200, 100, 0.12, 6, 3))
    b.append(mountain(r, 350, 820, 205, 115, 0.18, 4, 4))
    b.append(mist(0, 140, W, 80, 0.7))
    b.append(wall(r, 60, 700, 268, 52, 0.7, 24))
    b.append(building(r, 320, 220, 120, 95, 3, 0.9))
    b.append(wash([(360, 268), (400, 268), (400, 232), (380, 222), (360, 232)], 0.9, 0, r, 1))  # 城門
    b.append(flag(r, 300, 224, 46, 0.85, -1))
    b.append(flag(r, 470, 226, 44, 0.85))
    b.append(ground(r, 285, W, 0.1, 6))
    b.append(wash([(0, 330), (W, 322), (W, 450), (0, 450)], 0.06, 4, r, 2))  # 淯水
    b.append(water(r, 20, 740, 335, 9, 0.32))
    b.append(boat(r, 120, 372, 70))
    b.append(boat(r, 520, 400, 90))
    b.append(pine(r, 40, 300, 75))
    b.append(pine(r, 700, 296, 68, 0.85))
    b.append(pine(r, 655, 302, 50, 0.7))
    b.append(birds(r, 520, 125, 4, 0.5))
    b.append(splatter(r, 400, 430, 16, 50, 2, 0.4))
    return svg(W, H, "".join(b))


def jizhou() -> str:
    """冀州：廣宗平野、遠處城影、近處營柵帳篷與旗、道壇、烏鴉與枯草。"""
    r = rng_for("冀州")
    b = []
    b.append(mountain(r, -80, 830, 190, 150, 0.08, 10, 5))
    b.append(mist(0, 120, W, 100, 0.8))
    b.append(wall(r, 420, 640, 200, 16, 0.35, 12))
    b.append(building(r, 500, 186, 44, 40, 2, 0.45))
    b.append(ground(r, 205, W, 0.08, 8))
    # 道壇：土臺與幡
    b.append(wash([(60, 300), (200, 300), (185, 262), (75, 262)], 0.55, 0, r, 1))
    b.append(wash([(85, 262), (175, 262), (168, 240), (92, 240)], 0.7, 0, r, 1))
    for fx in (70, 130, 190):
        b.append(flag(r, fx, 262, 80, 0.85, 1 if fx < 150 else -1))
    b.append(smoke(r, 130, 240, 90, 0.3))
    # 營柵與帳篷
    for i in range(14):
        x = 300 + i * 30
        b.append(stroke([(x, 318), (x + r.uniform(-2, 2), 290 - r.uniform(0, 8))], 3, r, 0.8, 0.6))
    b.append(stroke([(296, 300), (720, 296)], 2, r, 0.7, 1))
    for i, x in enumerate((330, 420, 520, 620)):
        b.append(tent(r, x, 290, 70 - i * 4, 44, 0.8))
    b.append(flag(r, 480, 246, 60, 0.9))
    b.append(flag(r, 680, 250, 50, 0.9, -1))
    b.append(figure(r, 300, 360, 50, hat=False, pole=True))
    b.append(figure(r, 345, 366, 52, hat=True, pole=True))
    for i in range(10):
        b.append(grass(r, r.uniform(20, 730), r.uniform(330, 440), 5, r.uniform(8, 16), 0.5))
    b.append(bare_tree(r, 700, 330, 90))
    b.append(birds(r, 560, 140, 7, 0.75))
    b.append(splatter(r, 200, 420, 18, 60, 2.2, 0.45))
    return svg(W, H, "".join(b))


def luoyang() -> str:
    """洛陽：宮闕層層、北邙山、洛水石橋、松與水氣。"""
    r = rng_for("洛陽")
    b = []
    b.append(mountain(r, 380, 900, 215, 95, 0.14, 6, 3))
    b.append(mountain(r, -100, 450, 218, 130, 0.1, 8, 3))
    b.append(mist(0, 150, W, 80, 0.7))
    # 臺基與宮殿
    b.append(wash([(150, 268), (600, 268), (590, 246), (160, 246)], 0.45, 0, r, 1))
    b.append(building(r, 300, 246, 150, 120, 3, 0.9))
    b.append(building(r, 180, 246, 90, 70, 2, 0.75))
    b.append(building(r, 480, 246, 90, 70, 2, 0.75))
    b.append(stroke([(150, 268), (600, 268)], 2.5, r, 0.8, 0.5))
    b.append(ground(r, 275, W, 0.1, 6))
    # 洛水與石橋
    b.append(wash([(0, 330), (W, 326), (W, 450), (0, 450)], 0.06, 4, r, 2))
    b.append(water(r, 30, 720, 340, 8, 0.3))
    b.append(brush([(240, 330), (300, 300), (380, 292), (460, 300), (520, 330)], 5, r, 0.85, 1))
    for i in range(5):
        x = 262 + i * 56
        b.append(stroke([(x, 330), (x + 8, 312 - i % 2 * 4)], 3, r, 0.7, 0.5))
    b.append(figure(r, 372, 294, 36, hat=True))
    b.append(pine(r, 70, 322, 85))
    b.append(pine(r, 130, 326, 60, 0.8))
    b.append(pine(r, 690, 318, 78))
    b.append(birds(r, 150, 130, 4, 0.5))
    b.append(splatter(r, 600, 420, 14, 50, 2, 0.4))
    return svg(W, H, "".join(b))


def youzhou() -> str:
    """幽州：北地丘陵、烽燧、奔馬、桑樹、雁。"""
    r = rng_for("幽州")
    b = []
    b.append(mountain(r, -60, 500, 230, 110, 0.14, 6, 3))
    b.append(mountain(r, 300, 820, 236, 128, 0.2, 4, 3))
    b.append(mist(0, 160, W, 90, 0.7))
    # 烽燧
    b.append(wash([(600, 236), (660, 236), (650, 150), (610, 150)], 0.8, 0, r, 1))
    b.append(wash([(604, 152), (656, 152), (656, 142), (604, 142)], 0.9, 0, r, 0.5))
    b.append(smoke(r, 630, 142, 80, 0.35))
    b.append(ground(r, 250, W, 0.12, 8))
    # 丘陵近景
    b.append(wash([(0, 300), (200, 270), (420, 290), (750, 262), (750, 450), (0, 450)], 0.08, 6, r, 3))
    # 桑樹
    for x, h in ((90, 70), (160, 55), (700, 65)):
        b.append(bare_tree(r, x, 298, h))
        b.append(wash([(x - h * 0.35, 298 - h * 0.6), (x + h * 0.4, 298 - h * 0.65), (x + h * 0.2, 298 - h * 1.05), (x - h * 0.25, 298 - h * 0.95)], 0.35, 3, r, 3))
    # 奔馬三匹
    b.append(horse(r, 300, 400, 70))
    b.append(horse(r, 420, 420, 80))
    b.append(horse(r, 200, 425, 62, 0.8))
    b.append(splatter(r, 330, 430, 24, 70, 2.4, 0.5))
    for i in range(12):
        b.append(grass(r, r.uniform(20, 730), r.uniform(320, 445), 4, r.uniform(8, 14), 0.5))
    b.append(birds(r, 100, 110, 7, 0.7))
    return svg(W, H, "".join(b))


def tianxia() -> str:
    """天下：大山、雲氣、長河、一條路與一個人。沒有圖的地點用這一張。"""
    r = rng_for("天下")
    b = []
    b.append(mountain(r, -100, 420, 240, 60, 0.22, 2, 3))
    b.append(mountain(r, 250, 900, 250, 40, 0.3, 2, 4))
    b.append(mountain(r, -60, 800, 258, 150, 0.1, 10, 5))
    b.append(mist(0, 170, W, 110, 0.85))
    b.append(wash([(0, 340), (W, 330), (W, 450), (0, 450)], 0.07, 4, r, 2))
    b.append(water(r, 40, 720, 345, 8, 0.3))
    b.append(stroke([(0, 420), (160, 395), (330, 388), (480, 372), (750, 360)], 4, r, 0.2, 2))
    b.append(figure(r, 330, 392, 54, hat=True, pole=True))
    b.append(pine(r, 60, 380, 95))
    b.append(pine(r, 120, 388, 60, 0.8))
    b.append(pine(r, 700, 372, 85))
    b.append(birds(r, 470, 120, 6, 0.6))
    b.append(splatter(r, 200, 430, 20, 60, 2.4, 0.45))
    return svg(W, H, "".join(b))


SCENES = {"yingru": yingru, "nanyang": nanyang, "jizhou": jizhou, "luoyang": luoyang, "youzhou": youzhou, "tianxia": tianxia}
