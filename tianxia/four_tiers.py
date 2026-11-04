"""素材四階（docs/superpowers/specs/2026-10-17-正式季整合-design.md 第四、五章；正式季整合第 2 批）的小規則。

一到三階是一般的料，第四階（神品）才是神器的料。四階只從幾條路來（這一批只有鐵匠鋪的三換四），不能賣、不能捐、不算糧草、
不能送人、設伏搶不走（4.6）。開關在 Config.four_tiers（測試內容關著）。只 import models，誰都能叫它。
"""
from __future__ import annotations

import random

from .models import Content, Material, Tier4Named

TIER = 4  # 神品：神器的料
TOP_COMMON = 3  # 一般的料最高到三階（拆四階裝備回三階，12.3 第 37 條、5.3；四階裝備淬煉收三階以上那一條，鐵匠鋪與合成流程 3.7 改成一律收一階）


def on(content: Content) -> bool:
    """素材四階的規則開著沒（Config.four_tiers.enabled）。"""
    return content.config.four_tiers.enabled


def is_tier4(material: Material | None) -> bool:
    """這一樣是四階的料（神器的料，不在人與人之間轉手、不算糧草）。不看開關：料本身就是四階。"""
    return material is not None and material.tier >= TIER


def count_text(n: int) -> str:
    """「一季兩個」的那個字：2 寫「兩」，其餘照 rules.count_word（這裡不 import rules）。"""
    from .rules import count_word  # noqa: PLC0415  rules 會間接 import 用到這裡的模組

    return "兩" if n == 2 else count_word(n)


def tier4_id(content: Content, material_id: str) -> bool:
    """同 is_tier4，給只有素材 id 的地方。"""
    return is_tier4(content.materials.get(material_id))


def named_chance(content: Content, main: str, aux: str) -> float:
    """這一爐（沒打中隱藏配方時）出四階名器的機會（正式季整合 5.2）：主料四階 named_main、主輔都四階 named_both，其餘 0；開關關著 0。"""
    if not on(content) or not tier4_id(content, main):
        return 0.0
    rule = content.config.four_tiers
    return rule.named_both if tier4_id(content, aux) else rule.named_main


def pick_named(content: Content, slot: str, kind: str | None, attribute: str, rng: random.Random) -> Tier4Named | None:
    """照這一爐的亂數，從名字表裡合欄位、合種類（兵器）、合屬性的那幾條挑一個；沒有合用的是 None（照一般的打）。"""
    pool = [e for e in content.tier4_named.values()
            if e.slot == slot and e.attribute == attribute and (slot != "weapon" or e.kind == kind)]
    return rng.choice(pool) if pool else None
