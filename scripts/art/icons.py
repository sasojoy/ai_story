"""圖示（三十個，64×64，透明底）：選項前的水墨圖示、五屬性、九類東西與裝備四欄、四格與此地。
每一個是幾筆粗線加一兩塊墨，認得出就好；畫面上縮到 20～28px。"""
from __future__ import annotations

from lib import INK, brush, fmt, rng_for, splatter, stroke, svg, wash

S = 64


def _svg(name: str, body: str) -> str:
    return svg(S, S, body, paper=False, grain=False)


def fist() -> str:  # 臂力
    r = rng_for("臂力")
    b = [wash([(14, 30), (46, 26), (52, 40), (44, 54), (18, 54), (10, 42)], 0.95, 0, r, 1)]
    for i in range(3):
        b.append(stroke([(20 + i * 10, 26), (22 + i * 10, 38)], 3, r, 0.5, 0.3))
    b.append(brush([(10, 42), (4, 30), (12, 18)], 7, r, 0.95, 0.8))
    return _svg("臂力", "".join(b))


def wind() -> str:  # 身法
    r = rng_for("身法")
    b = [brush([(6, 22), (30, 16), (52, 22), (58, 30)], 5, r, 0.95, 0.8),
         brush([(10, 36), (34, 32), (56, 40)], 4, r, 0.85, 0.8),
         brush([(16, 50), (40, 46), (52, 54)], 3, r, 0.7, 0.8)]
    return _svg("身法", "".join(b))


def bone() -> str:  # 根骨：山一樣的骨
    r = rng_for("根骨")
    b = [wash([(6, 54), (24, 18), (36, 36), (44, 24), (58, 54)], 0.95, 0, r, 1)]
    b.append(f'<circle cx="24" cy="16" r="5" fill="{INK}"/>')
    return _svg("根骨", "".join(b))


def lamp() -> str:  # 悟性：一盞燈
    r = rng_for("悟性")
    b = [wash([(22, 56), (42, 56), (40, 40), (24, 40)], 0.95, 0, r, 1),
         wash([(32, 10), (40, 24), (36, 38), (28, 38), (24, 24)], 0.9, 0, r, 1),
         stroke([(18, 58), (46, 58)], 4, r, 0.95, 0.3)]
    b.append(splatter(r, 32, 8, 6, 8, 1.2, 0.6))
    return _svg("悟性", "".join(b))


def book() -> str:  # 博聞：一卷竹簡
    r = rng_for("博聞")
    b = []
    for i in range(6):
        x = 10 + i * 9
        b.append(wash([(x, 14), (x + 6, 14), (x + 6, 50), (x, 50)], 0.95, 0, r, 0.5))
    b.append(stroke([(6, 22), (60, 22)], 2.5, r, 0.9, 0.3))
    b.append(stroke([(6, 42), (60, 42)], 2.5, r, 0.9, 0.3))
    return _svg("博聞", "".join(b))


def crossed() -> str:  # 對手：交叉的兩把刀
    r = rng_for("對手")
    b = [brush([(12, 52), (52, 12)], 7, r, 0.95, 0.6), brush([(12, 12), (52, 52)], 7, r, 0.95, 0.6)]
    b.append(wash([(8, 48), (16, 56), (12, 60), (4, 52)], 0.95, 0, r, 0.5))
    b.append(wash([(48, 56), (56, 48), (60, 52), (52, 60)], 0.95, 0, r, 0.5))
    return _svg("對手", "".join(b))


def leave() -> str:  # 離開：一條路往遠處
    r = rng_for("離開")
    b = [wash([(8, 58), (56, 58), (36, 14), (28, 14)], 0.9, 0, r, 1)]
    b.append(stroke([(32, 52), (32, 22)], 3, r, 0.3, 0.3))
    b.append(brush([(40, 12), (50, 6), (58, 8)], 3, r, 0.8, 0.5))
    return _svg("離開", "".join(b))


def speak() -> str:  # 說話：一句話的框
    r = rng_for("說話")
    b = [wash([(8, 12), (56, 12), (56, 40), (30, 40), (18, 54), (20, 40), (8, 40)], 0.95, 0, r, 1)]
    for i in range(3):
        b.append(f'<circle cx="{22 + i * 10}" cy="26" r="3" fill="#f4ede0"/>')
    return _svg("說話", "".join(b))


def ingot() -> str:  # 銀兩：元寶
    r = rng_for("銀兩")
    b = [wash([(6, 36), (16, 24), (48, 24), (58, 36), (50, 48), (14, 48)], 0.95, 0, r, 1)]
    b.append(brush([(20, 24), (32, 14), (44, 24)], 5, r, 0.95, 0.5))
    return _svg("銀兩", "".join(b))


def scroll() -> str:  # 心得：一卷軸
    r = rng_for("心得")
    b = [wash([(14, 14), (50, 14), (50, 50), (14, 50)], 0.9, 0, r, 1)]
    b.append(f'<circle cx="14" cy="32" r="7" fill="{INK}"/>')
    b.append(f'<circle cx="50" cy="32" r="7" fill="{INK}"/>')
    for i in range(3):
        b.append(stroke([(22, 24 + i * 8), (42, 24 + i * 8)], 2, r, 0.6, 0.3))
    b[-3:] = [x.replace(INK, "#f4ede0") if "stroke" in x else x for x in b[-3:]]
    return _svg("心得", "".join(b))


def banner() -> str:  # 名望：一面旗
    r = rng_for("名望")
    b = [stroke([(14, 60), (14, 6)], 4, r, 0.95, 0.3), wash([(14, 8), (56, 14), (50, 26), (56, 38), (14, 34)], 0.9, 0, r, 1.2)]
    return _svg("名望", "".join(b))


def lotus() -> str:  # 善
    r = rng_for("善")
    b = [wash([(32, 10), (42, 28), (32, 40), (22, 28)], 0.9, 0, r, 1), wash([(10, 26), (28, 32), (22, 44), (8, 38)], 0.85, 0, r, 1), wash([(54, 26), (36, 32), (42, 44), (56, 38)], 0.85, 0, r, 1)]
    b.append(brush([(8, 52), (32, 48), (56, 52)], 4, r, 0.8, 0.5))
    return _svg("善", "".join(b))


def wolf() -> str:  # 惡
    r = rng_for("惡")
    b = [wash([(10, 50), (18, 24), (26, 32), (34, 14), (42, 32), (54, 22), (56, 50)], 0.95, 0, r, 1)]
    b.append(f'<circle cx="26" cy="40" r="3" fill="#f4ede0"/>')
    b.append(f'<circle cx="42" cy="40" r="3" fill="#f4ede0"/>')
    return _svg("惡", "".join(b))


def sword() -> str:  # 兵器
    r = rng_for("兵器")
    b = [brush([(32, 6), (32, 42)], 7, r, 0.95, 0.3), stroke([(18, 42), (46, 42)], 5, r, 0.95, 0.3), stroke([(32, 42), (32, 58)], 4, r, 0.9, 0.3)]
    b.append(wash([(28, 6), (36, 6), (32, 0)], 0.95, 0, r, 0.3))
    return _svg("兵器", "".join(b))


def armor() -> str:  # 防具
    r = rng_for("防具")
    b = [wash([(12, 12), (24, 8), (40, 8), (52, 12), (50, 40), (32, 58), (14, 40)], 0.95, 0, r, 1)]
    for row in range(3):
        for i in range(3):
            cx = 22 + i * 10 + (5 if row % 2 else 0)
            b.append(f'<path d="M{cx - 4} {20 + row * 10} q4 6 8 0" fill="none" stroke="#f4ede0" stroke-width="1.5"/>')
    return _svg("防具", "".join(b))


def horsehead() -> str:  # 坐騎
    r = rng_for("坐騎")
    b = [wash([(14, 58), (20, 30), (30, 14), (44, 8), (50, 18), (58, 30), (46, 34), (40, 44), (40, 58)], 0.95, 0, r, 1)]
    b.append(wash([(42, 6), (48, 2), (50, 14)], 0.95, 0, r, 0.5))
    for i in range(4):
        b.append(stroke([(22 + i * 3, 30 - i * 5), (12 + i * 3, 22 - i * 5)], 2.5, r, 0.8, 0.5))
    return _svg("坐騎", "".join(b))


def jade() -> str:  # 寶物
    r = rng_for("寶物")
    b = [f'<circle cx="32" cy="32" r="22" fill="{INK}" fill-opacity="0.95"/>', f'<circle cx="32" cy="32" r="7" fill="#f4ede0"/>']
    b.append(brush([(14, 20), (24, 12)], 3, r, 0.4, 0.3).replace(INK, "#f4ede0"))
    return _svg("寶物", "".join(b))


def gourd() -> str:  # 丹藥
    r = rng_for("丹藥")
    b = [f'<circle cx="32" cy="42" r="16" fill="{INK}" fill-opacity="0.95"/>', f'<circle cx="32" cy="20" r="10" fill="{INK}" fill-opacity="0.95"/>']
    b.append(stroke([(26, 8), (38, 8)], 4, r, 0.95, 0.3))
    b.append(stroke([(22, 14), (42, 14)], 2, r, 0.6, 0.3).replace(INK, "#f4ede0"))
    return _svg("丹藥", "".join(b))


def ore() -> str:  # 素材
    r = rng_for("素材")
    b = [wash([(8, 50), (20, 22), (34, 14), (50, 24), (56, 50)], 0.95, 0, r, 1)]
    b.append(wash([(30, 30), (40, 26), (44, 38), (32, 42)], 0.9, 0, r, 0.5).replace(INK, "#f4ede0"))
    return _svg("素材", "".join(b))


def letter() -> str:  # 書信
    r = rng_for("書信")
    b = [wash([(8, 16), (56, 16), (56, 50), (8, 50)], 0.95, 0, r, 0.8)]
    b.append(brush([(10, 18), (32, 36), (54, 18)], 3, r, 0.9, 0.5).replace(INK, "#f4ede0"))
    return _svg("書信", "".join(b))


def order() -> str:  # 軍令：令旗
    r = rng_for("軍令")
    b = [stroke([(12, 60), (12, 4)], 4, r, 0.95, 0.3), wash([(12, 6), (58, 20), (12, 34)], 0.95, 0, r, 1)]
    b.append(f'<circle cx="26" cy="20" r="4" fill="#f4ede0"/>')
    return _svg("軍令", "".join(b))


def bounty() -> str:  # 懸賞：榜文
    r = rng_for("懸賞")
    b = [wash([(12, 8), (52, 8), (52, 56), (12, 56)], 0.95, 0, r, 0.8)]
    for i in range(4):
        b.append(stroke([(20, 18 + i * 10), (44, 18 + i * 10)], 2.5, r, 0.9, 0.3).replace(INK, "#f4ede0"))
    b.append(f'<circle cx="40" cy="46" r="5" fill="none" stroke="#f4ede0" stroke-width="2"/>')
    return _svg("懸賞", "".join(b))


def seal() -> str:  # 託付：一方印
    r = rng_for("託付")
    b = [wash([(14, 30), (50, 30), (50, 56), (14, 56)], 0.95, 0, r, 0.6), wash([(22, 30), (42, 30), (40, 14), (32, 8), (24, 14)], 0.95, 0, r, 0.8)]
    b.append(f'<rect x="22" y="38" width="20" height="10" fill="#f4ede0" fill-opacity="0.8"/>')
    return _svg("託付", "".join(b))


def compass() -> str:  # 探索
    r = rng_for("探索")
    b = [f'<circle cx="32" cy="32" r="24" fill="none" stroke="{INK}" stroke-width="5"/>', wash([(32, 10), (38, 32), (32, 54), (26, 32)], 0.95, 0, r, 0.5)]
    b.append(f'<circle cx="32" cy="32" r="4" fill="#f4ede0"/>')
    return _svg("探索", "".join(b))


def spear() -> str:  # 出陣
    r = rng_for("出陣")
    b = [brush([(10, 56), (50, 16)], 6, r, 0.95, 0.4), wash([(44, 8), (58, 6), (56, 20)], 0.95, 0, r, 0.5)]
    b.append(stroke([(40, 20), (48, 30)], 3, r, 0.8, 0.5))
    return _svg("出陣", "".join(b))


def friends() -> str:  # 交友
    r = rng_for("交友")
    b = [f'<circle cx="22" cy="20" r="9" fill="{INK}"/>', f'<circle cx="44" cy="22" r="8" fill="{INK}"/>']
    b.append(wash([(6, 56), (38, 56), (34, 34), (10, 34)], 0.95, 0, r, 1))
    b.append(wash([(34, 56), (60, 56), (58, 38), (36, 38)], 0.85, 0, r, 1))
    return _svg("交友", "".join(b))


def bolt() -> str:  # 移動
    r = rng_for("移動")
    b = [wash([(36, 4), (16, 36), (30, 36), (24, 60), (50, 26), (36, 26)], 0.95, 0, r, 1)]
    return _svg("移動", "".join(b))


def house() -> str:  # 此地
    r = rng_for("此地")
    b = [wash([(10, 32), (32, 10), (54, 32), (48, 32), (48, 56), (16, 56), (16, 32)], 0.95, 0, r, 1)]
    b.append(f'<rect x="27" y="40" width="10" height="16" fill="#f4ede0"/>')
    return _svg("此地", "".join(b))


def anvil() -> str:  # 剛
    r = rng_for("剛")
    b = [wash([(6, 24), (58, 24), (50, 34), (36, 36), (36, 50), (46, 56), (18, 56), (28, 50), (28, 36), (14, 34)], 0.95, 0, r, 0.8)]
    return _svg("剛", "".join(b))


def reed() -> str:  # 柔
    r = rng_for("柔")
    b = [brush([(20, 58), (24, 36), (18, 12)], 4, r, 0.9, 0.8), brush([(32, 58), (34, 30), (40, 8)], 4, r, 0.95, 0.8), brush([(44, 58), (46, 40), (56, 20)], 3.5, r, 0.85, 0.8)]
    return _svg("柔", "".join(b))


ICONS = {
    "str": fist, "agi": wind, "con": bone, "wis": lamp, "lore": book,
    "foe": crossed, "leave": leave, "speak": speak, "silver": ingot, "xinde": scroll, "fame": banner, "good": lotus, "evil": wolf,
    "weapon": sword, "armor": armor, "mount": horsehead, "treasure": jade, "pill": gourd, "material": ore,
    "letter": letter, "order": order, "bounty": bounty, "errand": seal,
    "explore": compass, "sortie": spear, "friends": friends, "move": bolt, "here": house,
    "gang": anvil, "rou": reed,
}
ICON_NAMES = {
    "str": "臂力", "agi": "身法", "con": "根骨", "wis": "悟性", "lore": "博聞", "foe": "對手", "leave": "離開", "speak": "說話",
    "silver": "銀兩", "xinde": "心得", "fame": "名望", "good": "善", "evil": "惡", "weapon": "兵器", "armor": "防具", "mount": "坐騎",
    "treasure": "寶物", "pill": "丹藥", "material": "素材", "letter": "書信", "order": "軍令", "bounty": "懸賞", "errand": "託付",
    "explore": "探索", "sortie": "出陣", "friends": "交友", "move": "移動", "here": "此地", "gang": "剛", "rou": "柔",
}
