"""傳承的純規則（架構方向 v2 第六節）：換季那一刻照上一季的傳評比，正氣、邪氣、機緣各自變動一次。

- 評比的六樣（inputs）：tasks 懸賞與人物託付辦成幾件、merit 陣營貢獻＋決戰場數＋首功、fame 名望、relations 跟人物的好感合計、good 善名、evil 惡名。
- 增量（gains）：正氣＝curve(good × 權重)、邪氣＝curve(evil × 權重)、機緣＝curve(其餘四樣各乘權重的合計)。curve 是平方根或 log(1 + x)：
  遞減，認真玩的人領先、差距不會無限拉開。
- 結算（settle）：新的值＝舊的值 × keep（七成）＋增量。停一季的人照樣往回落，不會永遠追不上。
- 門路（reached）：值到 LegacyTier.at 就給那一道的旗標（內容的條件 flags_all 讀）；只給門路，不加屬性、不加威力。
"""
from __future__ import annotations

import math

from tianxia.core import bounty_base  # 核心（這一季完成了幾張懸賞，core_seams）
from tianxia.models import Content, LegacyRules, LegacyTier
from tianxia.state import GameState, LegacyBook

AXES = ("zheng", "xie", "luck")
NAMES = {"zheng": "正氣", "xie": "邪氣", "luck": "機緣"}  # 待 joy 潤
LUCK_FROM = ("tasks", "merit", "fame", "relations")


def rules(content: Content) -> LegacyRules:
    return content.config.legacy


def on(content: Content) -> bool:
    return rules(content).enabled


def inputs(old: GameState, content: Content) -> dict[str, float]:
    """上一季的傳（old 是上一季的存檔）：評比的六樣，原始的數（還沒乘權重）。"""
    p = old.player
    known = set(content.characters) | set(content.figures)
    return {
        "tasks": float(bounty_base.done_count(p) + sum(1 for e in p.errands if e.status == "done")),
        "merit": float(max(0, p.contrib) + p.showdowns + p.top_merits),
        "fame": float(max(0, p.stats.get("fame", 0))),
        "relations": float(sum(max(0, v) for k, v in p.affinities.items() if k in known)),
        "good": float(max(0, p.stats.get("good", 0))),
        "evil": float(max(0, p.stats.get("evil", 0))),
    }


def curve(x: float, kind: str) -> float:
    x = max(0.0, x)
    return math.sqrt(x) if kind == "sqrt" else math.log1p(x)


def gains(raw: dict[str, float], r: LegacyRules) -> dict[str, float]:
    w = r.weights
    luck = sum(raw.get(k, 0.0) * w.get(k, 0.0) for k in LUCK_FROM)
    return {
        "zheng": round(curve(raw.get("good", 0.0) * w.get("good", 0.0), r.curve), 2),
        "xie": round(curve(raw.get("evil", 0.0) * w.get("evil", 0.0), r.curve), 2),
        "luck": round(curve(luck, r.curve), 2),
    }


def settle(book: LegacyBook, got: dict[str, float], r: LegacyRules, season: int) -> LegacyBook:
    """換季那一刻結算一次：舊的留 keep 成再加增量；記下這一季結算過、加了多少。回新的一份（不改傳進來的）。"""
    out = book.model_copy(deep=True)
    for axis in AXES:
        setattr(out, axis, round(getattr(book, axis) * r.keep + got.get(axis, 0.0), 2))
    out.gains = dict(got)
    out.settled = season
    return out


def reached(book: LegacyBook, r: LegacyRules) -> list[tuple[str, LegacyTier]]:
    """此刻到了的門路（照 zheng、xie、luck，各自由低到高）。"""
    return [(axis, tier) for axis in AXES for tier in r.tiers.get(axis, []) if getattr(book, axis) >= tier.at]


def all_flags(r: LegacyRules) -> set[str]:
    return {tier.flag for tiers in r.tiers.values() for tier in tiers}


def shown(value: float) -> int:
    """寫給玩家看的值：整數（無條件捨去）。"""
    return int(math.floor(value + 1e-9))


def summary(book: LegacyBook, r: LegacyRules) -> list[str]:
    """季初那一則：三項的值與這一季加了多少，接著寫這一季給了你什麼（待 joy 潤）。"""
    parts = []
    for axis in AXES:
        gain = book.gains.get(axis, 0.0)
        parts.append(f"{NAMES[axis]} {shown(getattr(book, axis))}" + (f"（+{shown(gain)}）" if shown(gain) > 0 else ""))
    lines = ["上一季的傳結算了：" + "、".join(parts) + "。"]
    opened = [tier.text for _, tier in reached(book, r)]
    if opened:
        lines.append("這一季給了你：" + "；".join(opened) + "。")
    return lines
