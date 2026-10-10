"""合到舊的（武學與成長設計 12.2）：一個組合這一季第一次被合時，可能合到一個已知的合成物，而不是長新的。

| 誰 | 做什麼 |
|---|---|
| 規則（這裡） | 候選、機會、擲骰（配方加天機的雜湊，不用真的亂數）、模型沒挑到時的退路 |
| 模型 | 候選兩個以上時挑意思最接近的一個（fusion 開單、naming.pick 叫模型） |

候選：這一季靠合成長出來的（origin 是 fused 的武學、合併出來的意境），種類、屬性、正邪跟這個組合本來會得到的一樣；
包括你自己身上的、連放進爐裡的那一樣也算（企劃者 2026-10-05：「旋風腿＋風」合出旋風腿可以接受；「就是隨機出現新武學，
但是一旦公式訂了就不能再變」——判一次、登記成配方，這一季就照表）。
基礎武學、名將武學、內容寫好的意境都不在全服登記表裡，所以不會是候選——不然 5 心得可能合到一門絕學。
"""
from __future__ import annotations

import hashlib
from typing import TypeVar

from .martial_arts import Insight, MartialArt
from .models import Content
from .world_state import WorldStateStore

T = TypeVar("T", MartialArt, Insight)


def _unit(seed: str) -> float:
    """0 到 1（含 0、不含 1）之間、只看 seed 的數：同一個配方同一季永遠一樣。
    取 53 位（浮點數的有效位數）：64 位的整數除以 2**64，最大那幾個值會被四捨五入成剛好 1.0。"""
    return (int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big") >> 11) / 2**53


def chance(content: Content, candidates: int) -> float:
    cfg = content.config
    return min(cfg.land_chance_cap, cfg.land_chance_per_candidate * candidates)


def lands(content: Content, key: str, tianji: int, candidates: int) -> bool:
    """這個組合會不會合到舊的。沒有候選一定長新的。"""
    return candidates > 0 and _unit(f"{tianji}|{key}|land") < chance(content, candidates)


def rule_pick(candidates: list[T], key: str, tianji: int) -> T:
    """規則挑一個：只看配方、天機與候選的 id，跟清單順序無關。candidates 不可以是空的（呼叫端先用 lands 確認至少有一個）。"""
    ordered = sorted(candidates, key=lambda c: c.id)
    return ordered[min(len(ordered) - 1, int(_unit(f"{tianji}|{key}|pick") * len(ordered)))]


def choose(candidates: list[T], key: str, tianji: int, picked_name: str | None) -> T:
    """模型挑的名字對得上某個候選就用它，否則（沒挑、挑了清單外的、C 段時候選變了）改由規則挑。
    candidates 不可以是空的（同 rule_pick）：呼叫端只在 lands 說要合到舊的、也就是至少有一個候選時才呼叫。"""
    for candidate in candidates:
        if picked_name is not None and candidate.name == picked_name:
            return candidate
    return rule_pick(candidates, key, tianji)


def art_candidates(
    world: WorldStateStore, kind: str, attribute: str, lean: str,
) -> list[MartialArt]:
    return [
        art for art in world.fused_arts()
        if (art.kind, art.attribute, art.lean) == (kind, attribute, lean) and not art.secret  # 秘方合的是內容寫好的那一門
    ]


def insight_candidates(world: WorldStateStore, attribute: str, lean: str) -> list[Insight]:
    return [
        insight for insight in world.merged_insights()
        if (insight.attribute, insight.lean) == (attribute, lean) and not insight.secret
    ]
