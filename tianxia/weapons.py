"""兵器（docs/superpowers/specs/2026-10-09-兵器-design.md）。

第一批（拿著就有用）：武學的兵器種類、身上那把的加成與鋒利度、鐵匠鋪的買、修、換、打贏掉落、角色卡那一行。
這個模組只 import models、state、martial_arts、world_state；team 反過來呼叫它（player_boost、_styled_fighters），
所以這裡不 import team——要武學本體的地方由呼叫端傳進來。
"""
from __future__ import annotations

import hashlib

from .models import Content
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
