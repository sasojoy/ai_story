"""大勢人物像（第一批三位，600×800）：照 web/hero.webp 的做法畫成墨色剪影、不畫臉，用冠、巾、盔與手上的東西認人。
一個人一塊連著的外形（袍、袖、腿合成一個多邊形），邊上帶飛墨，衣褶用紙色的淡筆畫在墨裡。"""
from __future__ import annotations

from lib import INK, PAPER, brush, fmt, rng_for, splatter, stroke, svg, wash

W, H = 600, 800
GROUND = 735


def _shadow(r) -> str:
    return wash([(150, GROUND + 6), (450, GROUND + 6), (430, GROUND + 28), (170, GROUND + 28)], 0.14, 10, r, 3)


def _body(r, pts, amount: float = 2.5) -> str:
    return wash(pts, 0.96, 0, r, amount)


def _fold(r, pts, width: float = 3, opacity: float = 0.22) -> str:
    """墨裡的衣褶：紙色的淡筆。"""
    return brush(pts, width, r, opacity, 1.5).replace(INK, PAPER)


def _hem(r, x0: float, x1: float, y: float, n: int = 7) -> str:
    """下擺：幾筆短的濃墨往下拖，再撒墨點。"""
    out = []
    for i in range(n):
        x = x0 + (x1 - x0) * (i + 0.5) / n
        out.append(brush([(x - 14, y - 4), (x + r.uniform(-4, 4), y + r.uniform(2, 8)), (x + 14, y - 4)], r.uniform(10, 18), r, 0.55, 1))
    out.append(splatter(r, (x0 + x1) / 2, y + 6, 40, (x1 - x0) * 0.4, 2.4, 0.6))
    return "".join(out)


def _head(x: float, y: float, rr: float) -> str:
    return f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(rr)}" fill="{INK}" fill-opacity="0.96"/>'


def luzhi() -> str:
    """盧植：高高的梁冠、長鬚、寬袖儒服垂到地，雙手籠在袖裡捧著一卷簡。站得正。"""
    r = rng_for("盧植")
    x, hy = 300, 196
    b = [_shadow(r)]
    outline = [(268, 232), (236, 246), (205, 266), (176, 300), (150, 345), (126, 420), (116, 480), (138, 492), (190, 470),
               (182, 560), (172, 650), (166, 728), (434, 728), (428, 650), (418, 560), (410, 470), (462, 492), (484, 480),
               (474, 420), (450, 345), (424, 300), (395, 266), (364, 246), (332, 232)]
    b.append(_body(r, outline, 3))
    # 袖口與襟的褶
    b.append(_fold(r, [(205, 300), (190, 420), (175, 470)], 3, 0.18))
    b.append(_fold(r, [(395, 300), (410, 420), (425, 470)], 3, 0.18))
    b.append(_fold(r, [(300, 250), (296, 400)], 2.5, 0.2))
    b.append(_fold(r, [(230, 520), (236, 700)], 2, 0.14))
    b.append(_fold(r, [(370, 520), (364, 700)], 2, 0.14))
    # 簡：橫的一卷，露出幾條白
    b.append(wash([(236, 436), (364, 436), (364, 472), (236, 472)], 0.98, 0, r, 0.5))
    for i in range(9):
        sx = 244 + i * 14
        b.append(f'<rect x="{sx}" y="{442}" width="4" height="24" fill="{PAPER}" fill-opacity="0.9"/>')
    b.append(splatter(r, 300, GROUND, 36, 120, 2.4, 0.55))
    b.append(_head(x, hy, 46))
    # 長鬚
    b.append(wash([(x - 28, hy + 30), (x + 28, hy + 30), (x + 16, hy + 140), (x + 4, hy + 168), (x - 6, hy + 168), (x - 18, hy + 140)], 0.92, 0, r, 2.5))
    b.append(_fold(r, [(x - 4, hy + 60), (x - 2, hy + 150)], 1.5, 0.15))
    # 進賢冠：前低後高的梁冠，冠梁三道，兩條纓帶垂到胸前
    b.append(wash([(x - 42, hy - 32), (x + 42, hy - 32), (x + 52, hy - 100), (x + 10, hy - 122), (x - 36, hy - 104)], 0.96, 0, r, 1.5))
    for i in range(3):
        b.append(_fold(r, [(x - 30 + i * 22, hy - 40), (x - 22 + i * 24, hy - 100)], 1.5, 0.25))
    b.append(stroke([(x - 32, hy - 18), (x - 48, hy + 70)], 2.5, r, 0.9, 1))
    b.append(stroke([(x + 32, hy - 18), (x + 48, hy + 70)], 2.5, r, 0.9, 1))
    b.append(splatter(r, 130, 470, 18, 40, 2, 0.5))
    b.append(splatter(r, 470, 470, 18, 40, 2, 0.5))
    return svg(W, H, "".join(b), paper=False, grain=False)


def bocai() -> str:
    """波才：黃巾裹頭、巾尾飛揚，短打束腰，一手叉腰，一手提環首刀，兩腿站開。"""
    r = rng_for("波才")
    x, hy = 290, 198
    b = [_shadow(r)]
    outline = [(262, 236), (226, 250), (190, 270), (160, 310), (142, 370), (136, 420), (158, 436), (190, 420), (205, 390),
               (210, 440), (196, 470), (188, 560), (176, 600), (166, 660), (150, 730), (216, 730), (226, 660), (248, 610),
               (290, 598), (332, 610), (354, 660), (364, 730), (430, 730), (414, 660), (404, 600), (416, 560), (424, 470),
               (436, 420), (470, 400), (512, 466), (546, 458), (520, 400), (476, 320), (440, 282), (396, 266), (352, 250), (318, 236)]
    b.append(_body(r, outline, 3))
    # 腰帶、束口與褶
    b.append(_fold(r, [(200, 470), (420, 466)], 5, 0.28))
    b.append(_fold(r, [(240, 300), (250, 450)], 2.5, 0.16))
    b.append(_fold(r, [(340, 300), (332, 450)], 2.5, 0.16))
    b.append(_fold(r, [(190, 640), (184, 720)], 3, 0.2))
    b.append(_fold(r, [(396, 640), (402, 720)], 3, 0.2))
    b.append(_fold(r, [(160, 330), (150, 410)], 2, 0.18))
    # 環首刀：直背長刃從手上往下斜出，刀環在上
    b.append(wash([(516, 470), (542, 470), (520, 640), (500, 730), (486, 724), (494, 640)], 0.97, 0, r, 1))
    b.append(_fold(r, [(528, 490), (500, 700)], 2, 0.3))
    b.append(f'<circle cx="534" cy="446" r="13" fill="none" stroke="{INK}" stroke-width="7"/>')
    b.append(wash([(508, 462), (550, 462), (550, 474), (508, 474)], 0.97, 0, r, 0.5))
    b.append(_fold(r, [(436, 300), (470, 400), (512, 466)], 3, 0.3))
    b.append(_fold(r, [(210, 440), (190, 400), (160, 330)], 3, 0.3))
    b.append(splatter(r, 290, GROUND, 30, 110, 2.2, 0.5))
    b.append(_head(x, hy, 42))
    # 巾：額上一圈、腦後兩條巾尾往左飛
    b.append(wash([(x - 48, hy - 16), (x + 48, hy - 16), (x + 46, hy - 40), (x - 46, hy - 40)], 0.97, 0, r, 1))
    b.append(_fold(r, [(x - 40, hy - 28), (x + 40, hy - 28)], 2, 0.3))
    b.append(wash([(x - 44, hy - 30), (x - 120, hy - 80), (x - 200, hy - 60), (x - 150, hy - 50), (x - 62, hy - 14)], 0.9, 0, r, 3))
    b.append(wash([(x - 42, hy - 22), (x - 120, hy + 4), (x - 186, hy + 36), (x - 130, hy - 6), (x - 58, hy - 6)], 0.86, 0, r, 3))
    b.append(splatter(r, x - 180, hy - 20, 16, 40, 2, 0.5))
    b.append(splatter(r, 520, 700, 20, 50, 2.2, 0.5))
    return svg(W, H, "".join(b), paper=False, grain=False)


def huangfusong() -> str:
    """皇甫嵩：兜鍪頂著纓、肩甲、魚鱗甲、披風往一邊揚，手按劍柄，長靴。"""
    r = rng_for("皇甫嵩")
    x, hy = 310, 186
    b = [_shadow(r)]
    # 披風：先畫在後面
    b.append(wash([(250, 262), (400, 262), (450, 360), (500, 480), (552, 640), (560, 730), (500, 700), (440, 600), (396, 520), (300, 480), (230, 380)], 0.7, 0, r, 5))
    b.append(_fold(r, [(430, 330), (500, 560), (520, 690)], 3, 0.14))
    outline = [(284, 224), (240, 240), (200, 252), (166, 262), (156, 320), (160, 400), (150, 470), (172, 496), (206, 478),
               (204, 520), (190, 600), (198, 606), (210, 730), (296, 730), (300, 640), (318, 640), (322, 730), (408, 730),
               (420, 606), (430, 600), (416, 520), (414, 480), (452, 470), (472, 440), (466, 390), (460, 320), (454, 262),
               (420, 252), (380, 240), (336, 224)]
    b.append(_body(r, outline, 2.5))
    # 肩甲
    b.append(wash([(150, 262), (236, 254), (230, 318), (154, 324)], 0.98, 0, r, 2))
    b.append(wash([(384, 254), (470, 262), (466, 324), (390, 318)], 0.98, 0, r, 2))
    b.append(_fold(r, [(160, 290), (226, 286)], 2, 0.25))
    b.append(_fold(r, [(394, 286), (460, 290)], 2, 0.25))
    # 魚鱗甲：胸前幾排留白的弧
    for row in range(8):
        y = hy + 112 + row * 22
        for i in range(7):
            cx = x - 66 + i * 22 + (11 if row % 2 else 0)
            b.append(f'<path d="M{cx - 9} {y} q9 12 18 0" fill="none" stroke="{PAPER}" stroke-opacity="0.5" stroke-width="2"/>')
    # 甲裙：橫的幾道
    for i in range(3):
        b.append(_fold(r, [(204, 520 + i * 28), (416, 520 + i * 28)], 2, 0.2))
    # 靴
    b.append(_fold(r, [(214, 660), (296, 660)], 3, 0.25))
    b.append(_fold(r, [(322, 660), (404, 660)], 3, 0.25))
    # 劍：手按在柄上，劍身往右下
    b.append(wash([(400, 462), (456, 462), (456, 476), (400, 476)], 0.98, 0, r, 0.5))
    b.append(brush([(428, 480), (496, 716)], 11, r, 0.97, 0.8))
    b.append(_fold(r, [(430, 500), (490, 700)], 1.5, 0.3))
    b.append(splatter(r, 310, GROUND, 30, 100, 2.2, 0.5))
    b.append(_head(x, hy, 40))
    # 兜鍪：圓頂、帽簷、頂上一簇纓往後飛
    b.append(wash([(x - 50, hy - 8), (x + 50, hy - 8), (x + 46, hy - 58), (x + 20, hy - 84), (x - 20, hy - 84), (x - 46, hy - 58)], 0.97, 0, r, 1.5))
    b.append(wash([(x - 60, hy - 8), (x + 60, hy - 8), (x + 64, hy + 4), (x - 64, hy + 4)], 0.97, 0, r, 1))
    b.append(_fold(r, [(x - 30, hy - 50), (x + 30, hy - 50)], 2, 0.25))
    b.append(brush([(x, hy - 84), (x - 30, hy - 130), (x - 80, hy - 150)], 9, r, 0.9, 2))
    b.append(brush([(x, hy - 84), (x - 10, hy - 136), (x - 46, hy - 170)], 7, r, 0.85, 2))
    b.append(splatter(r, x - 70, hy - 140, 12, 30, 1.8, 0.5))
    b.append(splatter(r, 540, 690, 22, 50, 2.2, 0.5))
    return svg(W, H, "".join(b), paper=False, grain=False)


FIGURES = {"luzhi": luzhi, "bocai": bocai, "huangfusong": huangfusong}
