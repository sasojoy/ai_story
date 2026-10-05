"""素材的掉落與背包（無限煉製第一刀，見 docs/superpowers/specs/2026-10-01-無限煉製-design.md §三、§四）。
素材不再拿去煉製（武學與成長計畫一 Task 8：煉製改成武學＋意境的合成，見 fusion.py）；現在的用途是糧草（押糧車）與伏筆。

純規則：只處理素材 id 與數量，不產生畫面文字（文字歸 `skillview.py`／呼叫端的訊息串）。
素材本身是 `content/materials.json` 的內容（`models.Material`：一個屬性 × 一個階）。

**刻意不做完整的道具系統**：沒有重量、沒有堆疊上限、不能丟棄。背包就是
`PlayerState.materials`（素材 id -> 數量），第一刀只要能存、能看、能燒掉。
"""
from __future__ import annotations

import math

import random

from .models import Content, Material, Squad
from .state import GameState

TIER_NAMES = {1: "凡品", 2: "靈品", 3: "天品"}

# 沒寫 drops 的對手走這張表（設計 §4.1）：難度上限 -> [(階, 機率), ...]。
# 內容不必每隻敵人都填掉落，難度本身就是強弱的唯一指標（見 models.Squad 的說明）。
DEFAULT_DROPS: tuple[tuple[float, tuple[tuple[int, float], ...]], ...] = (
    (20, ((1, 0.5),)),
    (70, ((1, 1.0), (2, 0.2))),
    (100, ((2, 1.0),)),
    (float("inf"), ((2, 1.0), (3, 0.25))),
)


def tier_label(material: Material) -> str:
    return TIER_NAMES.get(material.tier, str(material.tier))


def by_tier(content: Content, tier: int, attribute: str | None = None) -> list[Material]:
    """某一階的素材；給了屬性就只挑那個屬性，挑不到時退回同階的全部（內容缺一角也不會炸）。"""
    same_tier = [m for m in content.materials.values() if m.tier == tier]
    if attribute is None:
        return same_tier
    return [m for m in same_tier if m.attribute == attribute] or same_tier


GRANT_PREFIX = "獲得 "


def item_text(content: Content, material_id: str, count: int = 1) -> str:
    """一筆素材的寫法，例如「精鐵砂 ×1」：戰報的獲得與損失寫的就是它，訊息「獲得 精鐵砂 ×1」是它前面加 GRANT_PREFIX。"""
    return f"{content.materials[material_id].name} ×{count}"


def grant_line(item: str) -> str:
    """item_text 寫成給紀錄與訊息串的那一句：「精鐵砂 ×1」→「獲得 精鐵砂 ×1」。"""
    return GRANT_PREFIX + item


def grant(state: GameState, content: Content, material_id: str, count: int = 1) -> str | None:
    """放進背包，回傳一句「獲得 精鐵砂 ×1」；未知的素材 id 或數量 <= 0 時什麼都不做。"""
    if count <= 0 or material_id not in content.materials:
        return None
    bag = state.player.materials
    bag[material_id] = bag.get(material_id, 0) + count
    return grant_line(item_text(content, material_id, count))


def take(state: GameState, material_id: str, count: int = 1) -> bool:
    """從背包扣掉；不夠就什麼都不動、回傳 False。"""
    bag = state.player.materials
    if count <= 0 or bag.get(material_id, 0) < count:
        return False
    bag[material_id] -= count
    if bag[material_id] <= 0:
        del bag[material_id]
    return True


def held(state: GameState, material_id: str) -> int:
    return state.player.materials.get(material_id, 0)


# ── 糧草（計畫 T6 的最小版）：這一版沒有軍備物資，糧草＝背包裡的慢屬性素材（濃縮版內容表 4.0、計畫待決 6）──

GRAIN_ATTRIBUTE = "慢"


def _grain_value(content: Content, material: Material) -> int:
    """一個素材算幾份糧草（Config.grain_values，凡、靈、天）；階超出表的照最後一格。"""
    values = content.config.grain_values
    return values[min(material.tier, len(values)) - 1] if values else 0


def _grain_in_bag(state: GameState, content: Content) -> list[tuple[Material, int]]:
    """背包裡的慢屬性素材，低階在前（同階照內容順序）。"""
    order = {mid: i for i, mid in enumerate(content.materials)}
    items = [
        (content.materials[mid], n) for mid, n in state.player.materials.items()
        if mid in content.materials and n > 0 and content.materials[mid].attribute == GRAIN_ATTRIBUTE
    ]
    return sorted(items, key=lambda pair: (pair[0].tier, order.get(pair[0].id, 0)))


def grain_of(state: GameState, content: Content) -> int:
    """背包裡的糧草一共幾份。"""
    return sum(_grain_value(content, m) * n for m, n in _grain_in_bag(state, content))


def grain_plan(state: GameState, content: Content, amount: int) -> list[tuple[str, int]]:
    """交 amount 份糧草會用掉哪些素材（素材 id, 個數）：從低階的慢屬性素材開始，一個一個拿到夠為止（最後一個的份量可能
    超過，多的不找）。不動背包；不夠時回空串列。按鈕先寫給玩家看（T6 審查 M6），take_grain 照同一份拿。"""
    if amount <= 0 or grain_of(state, content) < amount:
        return []
    plan: list[tuple[str, int]] = []
    left = amount
    for material, n in _grain_in_bag(state, content):
        used = min(n, math.ceil(left / _grain_value(content, material)))
        if used:
            plan.append((material.id, used))
            left -= used * _grain_value(content, material)
        if left <= 0:
            break
    return plan


def take_grain(state: GameState, content: Content, amount: int) -> bool:
    """交出 amount 份糧草（照 grain_plan）。不夠就什麼都不動、回 False；amount <= 0 什麼都不拿、回 True。"""
    if amount <= 0:
        return True
    plan = grain_plan(state, content, amount)
    if not plan:
        return False
    for material_id, count in plan:
        take(state, material_id, count)
    return True


def _default_rolls(squad: Squad) -> tuple[tuple[int, float], ...]:
    for ceiling, rolls in DEFAULT_DROPS:
        if squad.difficulty < ceiling:
            return rolls
    return DEFAULT_DROPS[-1][1]


def roll_squad_drops(squad: Squad, content: Content, rng: random.Random) -> list[tuple[str, int]]:
    """打贏這支隊伍掉什麼：`Squad.drops` 寫了就照它，沒寫就走依難度的預設表。

    預設表挑的素材屬性跟著對手的屬性（`Squad.attribute`），沒填屬性就在同階裡隨機——
    「打剛的對手會掉剛的素材」讓玩家挑對手時有一點方向感。
    """
    if squad.drops:
        return [
            (drop.material, drop.count)
            for drop in squad.drops
            if drop.material in content.materials and rng.random() < drop.chance
        ]
    out: list[tuple[str, int]] = []
    for tier, chance in _default_rolls(squad):
        if rng.random() >= chance:
            continue
        pool = by_tier(content, tier, squad.attribute)
        if pool:
            out.append((rng.choice(pool).id, 1))
    return out


def bag_contents(state: GameState, content: Content) -> list[tuple[Material, int]]:
    """背包內容，照階由高到低、同階照屬性在內容裡的順序排（給畫面用）。"""
    order = {mid: i for i, mid in enumerate(content.materials)}
    items = [
        (content.materials[mid], n)
        for mid, n in state.player.materials.items()
        if mid in content.materials and n > 0
    ]
    return sorted(items, key=lambda pair: (-pair[0].tier, order.get(pair[0].id, 0)))
