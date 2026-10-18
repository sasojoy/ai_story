"""武學技能分檔（Joy 2026-10-17「下品 1-2 個、極低機率出現高階技能；中品 2-3、低機率；上品 3-4、中機率」；數字在 Config.skill_slots）。

| 東西 | 做什麼 |
|---|---|
| 三階 | 低階＝八個一般功效（層數照 depth.py 的一脈相承）、中階＝特別功效、高階＝content/traits.json 的 high（一個屬性一個） |
| 格數 | 自己那一份的品質定亮幾格（slot_count；絕學照上品） |
| 填法 | 層數最多的一般功效 → 首創走向的特別功效 → 其他來路的一般功效（層數多的先）→ 空格擲中階或低階（layout） |
| 高階 | 照品質擲（每升一品照新品質再擲一次，中了就留著），佔最後一格（high_of） |
| 未開 | 來路的功效比格子多時，多的還沒亮；修練升品才亮，到了絕學全部亮起 |

只管自己合成的武學（不在 content.skills 的）：內容寫的（本命、基礎、部下）照舊全亮。層數決定「哪幾個、多強」，品質決定「亮幾個」。
擲骰照「技能|名號|功法 id|…」的雜湊：不碰 Game.rng、不存檔，同一個人同一門同一品永遠一樣，舊存檔不用修。
全服登記的那一份不動（一脈相承照它傳，看的是來路、不是誰亮了幾格），只有玩家自己那一份的「身上的樣子」（apply）帶格子。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .martial_arts import QUALITIES, MartialArt
from .models import Content, HighTrait
from .state import GameState

SPECIAL_MARK = "特:"  # dormant 裡沒亮的特別功效
TIERS = {"low": 1, "mid": 2, "high": 3, "top": 4}  # 介面的檔次（skillview.melt_judge 的 traits[].tier：凡、良、精、極）


def _roll(*parts: object) -> float:
    digest = hashlib.sha256("|".join(str(p) for p in ("技能", *parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def on(content: Content, art: MartialArt | None) -> bool:
    """這一門照格子算：開關開著、有功效表、是自己合成的（不在內容裡）。"""
    return (
        art is not None and content.config.skill_slots.enabled and bool(content.traits.general) and art.id not in content.skills
    )


def slot_count(content: Content, who: str, art_id: str, quality: str) -> int:
    """這一品亮幾格：絕學照上品那時的格數（同一個雜湊）。"""
    key = "上品" if quality == "絕學" else quality
    lo, hi, p = (content.config.skill_slots.slots.get(key) or [1, 1, 0.0])[:3]
    return int(hi) if _roll(who, art_id, "格", key) < p else int(lo)


def high_of(content: Content, who: str, art: MartialArt, quality: str, rolled: str | None = None) -> HighTrait | None:
    """擲到的高階技能（照主屬性給；這一門的主屬性沒有高階技能就沒有）：合成擲到 rolled 那一品時照那一品擲一次，
    之後修練每升一品照新品質再擲一次，哪一次中了就是它。rolled 沒記（舊資料、別處拿到的）當下品起算。"""
    rates = content.config.skill_slots.high_rate
    pick = next((h for h in content.traits.high if h.attribute == art.attribute), None)
    if pick is None or quality not in QUALITIES:
        return None
    start = QUALITIES.index(rolled) if rolled in QUALITIES else 0
    for q in QUALITIES[min(start, QUALITIES.index(quality)): QUALITIES.index(quality) + 1]:
        if _roll(who, art.id, "高", q) < rates.get(q, 0.0):
            return pick
    return None


def high(content: Content, high_id: str | None) -> HighTrait | None:
    if not high_id:
        return None
    return next((h for h in content.traits.high if h.id == high_id), None)


@dataclass
class Layout:
    """一門的格子：lit 照順序（("g", 屬性) 一般功效、("s", id) 特別功效、("h", id) 高階），dormant 是還沒亮的；
    extra_traits 是空格擲到的低階（屬性，一層）、extra_specials 是空格擲到的中階。"""

    slots: int
    lit: list[tuple[str, str]] = field(default_factory=list)
    dormant: list[tuple[str, str]] = field(default_factory=list)
    extra_traits: list[str] = field(default_factory=list)
    extra_specials: list[str] = field(default_factory=list)


def layout(content: Content, who: str, art: MartialArt, quality: str, rolled: str | None = None) -> Layout:
    from .traits import traits_of

    mine = traits_of(art)
    ranked = sorted(dict.fromkeys(mine), key=lambda a: (-mine.count(a), mine.index(a)))
    source: list[tuple[str, str]] = [("g", a) for a in ranked[:1]]
    if art.special:
        source.append(("s", art.special))
    source += [("g", a) for a in ranked[1:]]
    n = slot_count(content, who, art.id, quality)
    top = high_of(content, who, art, quality, rolled)
    room = max(1, n - (1 if top is not None else 0))  # 只有一格的下品擲中高階：主功效照留，高階多一格
    if quality == "絕學" and len(source) > room:  # 練到絕學來路的功效全部亮起，不留「未開」（Joy 2026-10-17）
        room = len(source)
        n = room + (1 if top is not None else 0)
    out = Layout(slots=n, lit=source[:max(0, room)], dormant=source[max(0, room):])
    have_g = {a for k, a in out.lit if k == "g"} | {a for k, a in out.dormant if k == "g"}
    have_s = {i for k, i in out.lit + out.dormant if k == "s"}
    pool_s = sorted(t.id for t in content.traits.special if t.pool)
    pool_g = [t.attribute for t in content.traits.general]
    i = 0
    while len(out.lit) < room:
        mid = _roll(who, art.id, "空", i) < content.config.skill_slots.extra_mid
        choices = [s for s in pool_s if s not in have_s] if mid else [g for g in pool_g if g not in have_g]
        if not choices:  # 這一階都有了：換另一階
            mid = not mid
            choices = [s for s in pool_s if s not in have_s] if mid else [g for g in pool_g if g not in have_g]
        if not choices:
            break
        pick = choices[int(_roll(who, art.id, "挑", i) * len(choices))]
        if mid:
            have_s.add(pick)
            out.extra_specials.append(pick)
            out.lit.append(("s", pick))
        else:
            have_g.add(pick)
            out.extra_traits.append(pick)
            out.lit.append(("g", pick))
        i += 1
    if top is not None:
        out.lit.append(("h", top.id))
    return out


def apply(state: GameState, content: Content, art: MartialArt | None) -> MartialArt | None:
    """玩家自己那一份「身上的樣子」：traits 只留亮了的一般功效（層數照來路）再接空格擲到的低階，special 沒亮就拿掉，
    另記空格的中階、高階與未開的。art 要是 team.player_art 那一份（品質照自己修到的）。不照格子算的原樣回。"""
    if art is None or not on(content, art):
        return art
    from .traits import traits_of

    lay = layout(content, state.player.name, art, art.quality, state.player.art_rolled.get(art.id))
    lit_g = {a for k, a in lay.lit if k == "g"}
    mine = traits_of(art)
    kept = [a for a in mine if a in lit_g and a not in lay.extra_traits] + lay.extra_traits
    special = art.special if ("s", art.special) in lay.lit else None
    dormant = [a if k == "g" else SPECIAL_MARK + a for k, a in lay.dormant]
    high_id = next((i for k, i in lay.lit if k == "h"), None)
    return art.model_copy(update={
        "traits": kept or [art.attribute], "special": special, "extra_specials": lay.extra_specials, "high": high_id, "dormant": dormant,
    })
