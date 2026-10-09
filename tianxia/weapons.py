"""兵器（docs/superpowers/specs/2026-10-09-兵器-design.md）。

第一批（拿著就有用）：武學的兵器種類、身上那把的加成與鋒利度、鐵匠鋪的買、修、換、打贏掉落、角色卡那一行。
這個模組只 import models、state、martial_arts、world_state；team 反過來呼叫它（player_boost、_styled_fighters），
所以這裡不 import team——要武學本體的地方由呼叫端傳進來。
"""
from __future__ import annotations

import hashlib

from .martial_arts import MartialArt, counters
from .models import Content
from .state import GameState, Weapon
from .world_state import WorldStateStore


def art_weapon(art_id: str | None, content: Content, world: WorldStateStore) -> str | None:
    """這門武學配哪一種兵器（2.3）：內容裡的照 SkillDef.weapon；全服登記的合成武學照底（武學＋意境）一代一代往上找，
    武學＋武學從兩門來源挑一個（照 art id 的 sha256，同一門每次都一樣）；舊的自創武學推不出來是 None。內功一律 None。"""
    seen: set[str] = set()
    while art_id and art_id not in seen:
        seen.add(art_id)
        if art_id in content.skills:
            return content.skills[art_id].weapon
        art = world.get_skill(art_id)
        if art is None or art.kind != "武學":
            return None
        if art.base:
            art_id = art.base
            continue
        if art.parents:
            kinds = [art_weapon(p, content, world) for p in sorted(art.parents)]
            kinds = [k for k in kinds if k]
            if not kinds:
                return None
            return kinds[hashlib.sha256(art.id.encode("utf-8")).digest()[0] % len(kinds)]
        return None
    return None


def usable(weapon: Weapon | None, art: MartialArt | None, content: Content, world: WorldStateStore) -> bool:
    """這把兵器配不配得上身上這門武學（2.3）：開關開著、兩樣都有、種類一樣。"""
    return (
        content.config.weapons.enabled and weapon is not None and art is not None
        and art_weapon(art.id, content, world) == weapon.kind
    )


def edge_factor(content: Content, weapon: Weapon) -> float:
    """鋒利度係數（3.4）：全鈍剩 edge_floor，滿的是 1。"""
    floor = content.config.weapons.edge_floor
    return floor + (1 - floor) * max(0, min(100, weapon.edge)) / 100


def bonus(weapon: Weapon | None, art: MartialArt | None, content: Content, world: WorldStateStore) -> float:
    """這把兵器現在給幾成威力（3.1～3.4）：配不上是 0；（階＋品質＋淬煉＋屬性搭配）夾在 0 以上，再乘鋒利度係數。
    每次現算、不快取：換了武學、修了、鈍了，下一場就照新的算。"""
    if not usable(weapon, art, content, world):
        return 0.0
    rule = content.config.weapons
    base = rule.tier_bonus.get(str(weapon.tier), 0.0) + rule.quality_bonus.get(weapon.quality, 0.0)
    base += rule.temper_step * weapon.tempers
    if weapon.attribute == art.attribute:
        base += rule.match
    elif counters(weapon.attribute, art.attribute) or counters(art.attribute, weapon.attribute):
        base -= rule.match
    return max(0.0, base) * edge_factor(content, weapon)


def style_factor(weapon: Weapon | None, art: MartialArt | None, content: Content, world: WorldStateStore, style) -> float:
    """一門打不遍（3.3）：兵器屬性落在大場面對手怕的那一路 ×(1＋style_soft)、最會對付的那一路 ×(1－style_hard)。
    配不上的兵器、不是大場面（style 是 None）都是 1。"""
    if style is None or not usable(weapon, art, content, world):
        return 1.0
    rule = content.config.weapons
    if weapon.attribute == style.soft:
        return 1 + rule.style_soft
    if weapon.attribute == style.hard:
        return 1 - rule.style_hard
    return 1.0


EDGE_WARNING = "你的{name}刀口鈍了，找間鐵匠鋪修一修。"  # 待 joy 潤


def wear(state: GameState, content: Content, tier: str) -> list[str]:
    """打完一場，身上那把扣鋒利度（3.4，照結果）；第一次鈍到 edge_warn 以下回一句提醒（只一次，修好才重設）。
    劇情戰與全服決戰不呼叫這裡（engine._file_battle 擋劇情戰；決戰不走 _file_battle）。"""
    rule, p = content.config.weapons, state.player
    if not rule.enabled or p.weapon is None:
        return []
    p.weapon.edge = max(0, p.weapon.edge - rule.wear.get(tier, 0))
    if p.weapon.edge < rule.edge_warn and not p.edge_warned:
        p.edge_warned = True
        return [EDGE_WARNING.format(name=p.weapon.name)]
    return []
