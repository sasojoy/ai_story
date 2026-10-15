"""探索三選一（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第三節）：找素材、找事件、靜心感悟。

act:explore 留作展開的入口（engine.IDLE_MARK：切磋、論武、假人、網頁都認它是「閒著」）：開關開著時按了不花體力、只回 PICK 那一句；
三種各自一個 id（explore:gather|seek|sense），一樣的體力。這裡放純規則（id、字、找素材給什麼、撞不撞怪、自己的亂數）；
打一場、抽事件、有所感在 engine.Game._explore_mode。擲骰一律用自己的亂數（rng_for），不碰 Game.rng。
開關（Config.explore_modes.enabled）關著時引擎照舊照地點比例自動抽（Game._explore）。"""
from __future__ import annotations

import random

from . import materials
from .models import Content, Location

PREFIX = "explore:"
GATHER, SEEK, SENSE = "gather", "seek", "sense"
MODES = (GATHER, SEEK, SENSE)
NAMES = {GATHER: "找素材", SEEK: "找事件", SENSE: "靜心感悟"}  # 待 joy 潤
PICK = "探索要選一種：找素材、找事件，或靜心感悟。"  # 待 joy 潤：按「探索」本身的回話
NO_SENSE = "這裡悟不出什麼"  # 待 joy 潤（設計 3.3；鈕上不帶句號）
SENSE_LATER = "選錯了做法，這裡要過一陣子才悟得出"  # 待 joy 潤：這個遊戲日在這裡選錯過做法
GATHER_LINE = "你在{place}四下翻找。"  # 待 joy 潤
GATHER_NONE = "翻了一陣，沒找到什麼能用的。"  # 待 joy 潤
FOE_LINE = "你正翻找著，{foe}突然殺出！"  # 待 joy 潤
SEEK_NONE = "你四處走走，這一帶眼下沒什麼事。"  # 待 joy 潤


def on(content: Content) -> bool:
    return content.config.explore_modes.enabled


def option_id(mode: str) -> str:
    return f"{PREFIX}{mode}"


def rng_for(season: int, name: str, serial: int, what: str) -> random.Random:
    """這一次探索、這一個用途自己的亂數：季數｜名號｜第幾次探索（PlayerState.explore_seq）｜用途。決定性，不動 Game.rng。"""
    return random.Random(f"探索|{season}|{name}|{serial}|{what}")


def is_town(content: Content, loc: Location) -> bool:
    return content.config.explore_mix_of(loc.tags).kind == "town"


def gather_finds(content: Content, loc: Location, rng: random.Random) -> list[str]:
    """找素材撿到的素材 id（設計 3.1 的表）：屬性照這裡寫的素材（Location.materials），沒寫就從同階全部挑；城鎮 town_chance 一個一階；
    其餘一定一個一階，照危險度 second_tier 的機會再一個二階。三階不從這裡來。"""
    cfg = content.config.explore_modes
    kinds = {content.materials[m].attribute for m in loc.materials if m in content.materials}

    def one(tier: int) -> str | None:
        pool = [m for m in materials.by_tier(content, tier) if m.attribute in kinds] or materials.by_tier(content, tier)
        return rng.choice(pool).id if pool else None

    if is_town(content, loc):
        found = [one(1)] if rng.random() < cfg.town_chance else []
    else:
        found = [one(1)]
        if rng.random() < cfg.second_tier.get(loc.danger, 0.0):
            found.append(one(2))
    return [mid for mid in found if mid is not None]


def encounter_due(content: Content, loc: Location, rng: random.Random) -> bool:
    """找素材撞不撞上怪：城鎮不撞，其餘 encounter_chance。"""
    return not is_town(content, loc) and rng.random() < content.config.explore_modes.encounter_chance
