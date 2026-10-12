"""打造的隱藏配方（docs/superpowers/specs/2026-10-12-打造隱藏配方-design.md；第一批：名器、首位發現者、線索與鑄譜；神器是第二批）。

| 誰 | 做什麼 |
|---|---|
| 內容（content/forge_secrets.json） | 隱藏配方池：欄位、種類、主料與輔料的形狀（屬性＋階）、名器的名字、一句說明、三句口訣 |
| 這裡 | 這一季挑哪幾條（照天機）、這一爐合不合得上、首位發現者那一筆、名器的名字照內容讀、鑄譜（聽過的口訣、打中過的） |
| smithing | 打中了怎麼打、登記、傳聞、回饋 |

每季照天機從池子裡照「欄位:組」挑 Config.forge_secrets.per_season 條（全服同一批，換季換一批；這一欄的裝備關著就不挑）。認形狀不認素材 id；
主輔不交換；比對不擲骰。打中了的全服登記在 gear_recipes（鍵「鑄|配方 id」，名字欄寫鍵本身、不佔名字空間）。口訣三句：0 說書、1 鐵匠、2 殘譜；
玩家聽過的、打中過的記在鑄譜（PlayerState.forge_manual），只記這一季的。擲骰一律用自己的亂數（secret_recipes.roll），不動 Game.rng。
只 import models、state、equipment、weapons、armor、secret_recipes、world_state（型別）；smithing、engine、content 反過來用它。"""
from __future__ import annotations

import hashlib

from . import equipment
from .models import Content, ForgeSecret, ForgeSide, Material

PREFIX = "鑄|"  # gear_recipes 裡隱藏配方那幾列的鍵開頭（7.1）：不跟「融|」「合|」「兼|」「秘|」「兵|」「鎧|」撞；state.GearFind.id 用同一個字
GROUPS = tuple(f"{slot}:{group}" for slot in ("weapon", "armor") for group in ("1", "2", "3", "divine"))
SEED_PAIRS = ({"剛", "柔"}, {"快", "慢"})  # insights.merged_attribute 照種子挑的兩對：每季可能不同，隱藏配方不收（3.1）


def _rank(tianji: int, recipe_id: str) -> bytes:
    return hashlib.sha256(f"{tianji}|{recipe_id}|鑄法".encode("utf-8")).digest()


def group_of(recipe: ForgeSecret) -> str:
    """這一條屬於哪一組（3.2）：「欄位:主料的階」，神器配方是「欄位:divine」。"""
    return f"{recipe.slot}:divine" if recipe.divine else f"{recipe.slot}:{recipe.main.tier}"


def covers(side: ForgeSide) -> range:
    """這一樣料認哪幾階：寫死 tier 就是那一階，min_tier 是那一階到三階；都沒寫（壞資料，載入時擋）是空的。"""
    if side.tier is not None:
        return range(side.tier, side.tier + 1)
    if side.min_tier is not None:
        return range(side.min_tier, 4)
    return range(0)


def fits(side: ForgeSide, material: Material) -> bool:
    return material.attribute == side.attribute and material.tier in covers(side)


def active(content: Content, tianji: int) -> list[ForgeSecret]:
    """這一季（天機）的隱藏配方：照 per_season 每一組挑幾條，同一季全服同一批、換季換一批；這一欄的裝備關著（equipment.on）不挑。"""
    out: list[ForgeSecret] = []
    for group, count in content.config.forge_secrets.per_season.items():
        if count <= 0 or not equipment.on(content, group.partition(":")[0]):
            continue
        pool = sorted((r for r in content.forge_secrets.values() if group_of(r) == group), key=lambda r: _rank(tianji, r.id))
        out += pool[:count]
    return out


def key(recipe: ForgeSecret) -> str:
    return PREFIX + recipe.id


def match(content: Content, tianji: int, slot: str, kind: str | None, main: str, aux: str) -> ForgeSecret | None:
    """這一爐合得上這一季的哪一條隱藏配方（3.1）：欄位、兵器種類（防具不看）、主料、輔料各自對得上形狀；主輔不交換。不擲骰。"""
    if not content.forge_secrets or main not in content.materials or aux not in content.materials:
        return None
    m, a = content.materials[main], content.materials[aux]
    want = kind if slot == "weapon" else None
    return next((r for r in active(content, tianji) if r.slot == slot and r.kind == want and fits(r.main, m) and fits(r.aux, a)), None)
