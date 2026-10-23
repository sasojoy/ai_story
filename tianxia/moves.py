"""以意成招（招式與絕學稿案第二節，Joy 2026-10-21 按建議）：自創武學的招從自創那幾步自己長出來，不借別人的。

| 哪一步 | 定什麼 |
|---|---|
| 擺式 | 勢（create.stance_of 照關節讀）：攻勢＝出招、守勢＝應招、變勢＝乘勢、起勢＝起手；內功除了起勢都是心法 |
| 立意 | 主屬性（第一格的顏色、MartialArt.attribute）配上勢，就是這一招做什麼（content/create_forms.json 的 moves，八路×四勢＋八種心法） |
| 意分 | 火候：生、熟、透（MartialArt.move_fire；Config.arts.move_fire_cuts 分段、move_fire 打折）。表上寫的是透＝約人物本命的八成 |
| 成形 | 稀有路數：那一格有稀有的版本時照 Config.arts.move_rare_odds 擲（MartialArt.move_rare） |
| 立名 | 招名（MartialArt.move_name；模型先填一個、玩家可改）；那一句話（move_say；模型寫，叫不動照表的套句） |
| 成數 | 一到 move_raw_levels 成招還「生」：表上會長的數再乘 move_raw_scale（team.tactic_holders 照自己練到的成數算） |

只 import models；認勢要姿勢的幾何（create.py），用到才 import。
"""
from __future__ import annotations

from .models import Content, CreateMove, TacticDef

STANCE_TIMING = {"攻勢": "出招", "守勢": "應招", "變勢": "乘勢", "起勢": "起手"}
STANCES = tuple(STANCE_TIMING)
FIRES = ("生", "熟", "透")
DEFAULT_FIRE = "熟"  # 這一版之前自創的（沒記火候）：當熟的
RAW_WORD = "招還生"  # 待 joy 潤
# 撞到稀有路數的招：卡上招那一行後面補這兩個字的小章（Joy 2026-10-23「玩家要怎樣才知道自己的是」）；網頁 tacticHtml 認同一串
RARE_WORD = "稀有路數"  # 待 joy 潤


def is_own(content: Content, art) -> bool:
    """自創的武學（玩家自己立的，有招）：不是內容武學、來歷是自創。合成、內容武學都不是。"""
    return art is not None and art.id not in content.skills and art.origin == "created" and bool(art.creator)


def fire_of(content: Content, score: int) -> str:
    """意分（加赤璋，夾之前）→ 火候：不到第一刀是生、不到第二刀是熟、其餘透。"""
    low, high = content.config.arts.move_fire_cuts
    return "生" if score <= low else "熟" if score <= high else "透"


def stance_of_art(content: Content, art) -> str:
    if getattr(art, "move_stance", "") in STANCE_TIMING:
        return art.move_stance
    from . import create  # create 會 import tactics，tactics 會 import 這裡

    return create.stance_of(create.icon_pose(content, art, art.weapon))


def timing_of(kind: str, stance: str) -> str:
    if kind == "內功":
        return "起手" if stance == "起勢" else "心法"
    return STANCE_TIMING.get(stance, "起手")


def cell(content: Content, attribute: str, timing: str, rare: bool = False) -> CreateMove | None:
    """表裡的那一格：rare 要稀有的版本、那一格沒有就用常見的。表裡沒有那一路（兼容並蓄沒有屬性）是 None。"""
    rows = [m for m in content.create_forms.moves if m.attribute == attribute and m.timing == timing]
    if rare:
        found = next((m for m in rows if m.rare), None)
        if found is not None:
            return found
    return next((m for m in rows if not m.rare), None)


def has_rare(content: Content, attribute: str, timing: str) -> bool:
    return any(m.rare for m in content.create_forms.moves if m.attribute == attribute and m.timing == timing)


def scaled(move: CreateMove, k: float) -> dict:
    """表上會長的那幾個數乘 k（rate 是發動率；mult 只乘多出 1 的那一截）；回 TacticDef 的欄位。"""
    rate = move.rate * k if "rate" in move.grow and move.rate < 1 else move.rate
    params = {}
    for key, v in move.params.items():
        if key not in move.grow:
            params[key] = v
        elif key == "mult":
            params[key] = round(1 + (v - 1) * k, 3)
        else:
            params[key] = round(v * k, 4)
    return {"rate": round(min(1.0, rate), 4), "params": params}


def build(content: Content, kind: str, attribute: str, stance: str, fire: str, rare: bool = False,
          name: str | None = None, say: str = "", level: int | None = None) -> TacticDef | None:
    """照路數、勢、火候算出這一招（TacticDef）。level 給了而且還在前幾成：會長的數再打折（招還生）。"""
    move = cell(content, attribute, timing_of(kind, stance), rare)
    if move is None:
        return None
    cfg = content.config.arts
    k = float(cfg.move_fire.get(fire, cfg.move_fire.get(DEFAULT_FIRE, 0.8)))
    if level is not None and level <= cfg.move_raw_levels:
        k *= cfg.move_raw_scale
    numbers = scaled(move, k)
    return TacticDef(
        name=name or move.name, timing=move.timing, kind=move.kind, desc=move.desc, rate=numbers["rate"],
        rounds=move.rounds, prep=move.prep, params=numbers["params"], say=say or move.say,
    )


MASTERED = "絕學"


def ascend(content: Content, move: CreateMove, tactic: TacticDef) -> TacticDef:
    """破境：招升為絕招——發動率升到必定，會長的數（rate 以外）再乘 Config.arts.ascend_scale（本來就必定的靠這一截變強）。"""
    k = content.config.arts.ascend_scale
    params = dict(tactic.params)
    for key in move.grow:
        if key == "rate" or key not in params:
            continue
        params[key] = round(1 + (params[key] - 1) * k, 3) if key == "mult" else round(params[key] * k, 4)
    return tactic.model_copy(update={"rate": 1.0, "params": params})


def ascended(art) -> bool:
    """這一份（玩家自己那一份，team.player_art）練成絕學了沒。"""
    return getattr(art, "quality", "") == MASTERED


def move_of(content: Content, art, level: int | None = None) -> TacticDef | None:
    """一門自創武學的招（不是自創的是 None）：存著的招名、火候、稀有；勢照存著的姿勢讀。
    art 是玩家自己那一份而且練成絕學了（ascended）：升為絕招（ascend，不再看招生不生）。"""
    if not is_own(content, art):
        return None
    stance = stance_of_art(content, art)
    fire = art.move_fire or DEFAULT_FIRE
    if ascended(art):
        base = build(content, art.kind, art.attribute, stance, fire, art.move_rare, art.move_name, art.move_say)
        row = cell(content, art.attribute, timing_of(art.kind, stance), art.move_rare)
        return ascend(content, row, base) if base is not None and row is not None else base
    return build(content, art.kind, art.attribute, stance, fire, art.move_rare, art.move_name, art.move_say, level)


PURE, WHOLE = "純", "渾"  # 待 joy 潤


def purity(colors: list[list[str]]) -> str | None:
    """開著的那幾格全單色是純、全任色是渾，其餘沒有。"""
    if not colors:
        return None
    if all(len(c) == 1 for c in colors):
        return PURE
    if all(not c for c in colors):
        return WHOLE
    return None


def look_bonus(content: Content, art) -> float:
    """純、渾在打的時候真的有用（稿案「強不強」）：自創的這一門功效層數多乘 1＋這麼多（Config.arts.pure_bonus／whole_bonus）。
    art 是玩家那一份（品級已照自己的）；不是自創的是 0。"""
    if not is_own(content, art):
        return 0.0
    cfg = content.config.arts
    n = max(1, int(cfg.slots.get(art.quality, 2)) + art.slot_adjust)
    found = purity([list(c) for c in art.slot_colors[:n]]) if len(art.slot_colors) >= n else None
    return cfg.pure_bonus if found == PURE else cfg.whole_bonus if found == WHOLE else 0.0


def raw(content: Content, level: int) -> bool:
    """這一成招還生不生（卡上寫「招還生」）。"""
    return level <= content.config.arts.move_raw_levels
