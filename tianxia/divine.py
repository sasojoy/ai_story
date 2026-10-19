"""神器輪替與收集（正式季整合設計 5.6～5.8、10.3、10.4；第 10 批）：這個伺服器現世過哪幾件神器、每一季開哪幾件。

| 誰 | 做什麼 |
|---|---|
| 這裡 | 挑這一季的神器（lineup）、開季換季時蓋進季並記進全服登記（stamp） |
| forge_secrets | 蓋了章的季，神器照 WorldState.divine_lineup 開（active） |
| sqlite_world | 全服登記放在 SharedWorldState.divine（world 那一列的 JSON，同玉璽碎片）；開季、換季時叫 stamp；原品那一筆跨季 |

開關是 Config.forge_secrets.rotation（主機的緊急開關，測試內容關著）。輪替從下一個開季起生效：正在跑的季沒有章（divine_lineup 是 None），
照它開季時的挑法。只 import models、state、world_state、equipment。"""
from __future__ import annotations

import hashlib
import random

from . import equipment
from .models import Content, ForgeSecret
from .world_state import DivineRegistry, SharedWorldState

EXHAUSTED = "（新神器用完了：這一季的神器都是以前現世過的，請內容補新的神器。）"  # 待 joy 潤：主控台與管理者開季、換季的回話


def _rank(tianji: int, recipe_id: str) -> bytes:
    return hashlib.sha256(f"{tianji}|{recipe_id}|輪替".encode("utf-8")).digest()


def lineup(content: Content, registry: DivineRegistry, tianji: int) -> tuple[list[str], bool]:
    """這一季開哪幾件神器（5.6）：回（配方 id 照天機排好, 新神器是不是用完了）。
    登記還空著（這個伺服器第一次照這套規則開的季）：內容裡 wave 1 的九件全開。之後照天機挑 rotation_min～rotation_max 件：
    先放一件還沒現世過的，再補一件兵器、一件防具（那一欄開著的話），再照順序補滿；同一種兵器一季最多一件。
    件數不夠放下必要的就多放。欄位關著（equipment.on）的不挑也不要求。都現世過了就從全部挑、回 True。"""
    cfg = content.config.forge_secrets
    pool = [r for r in content.forge_secrets.values() if r.divine and equipment.on(content, r.slot)]
    if not registry.seen:
        return [r.id for r in pool if r.wave == 1], False
    order = sorted(pool, key=lambda r: _rank(tianji, r.id))
    count = random.Random(f"divine-lineup|{tianji}").randint(cfg.rotation_min, max(cfg.rotation_min, cfg.rotation_max))
    unseen = [r for r in order if r.id not in registry.seen]
    picked: list[ForgeSecret] = []

    def fits(r: ForgeSecret) -> bool:
        if any(p.id == r.id for p in picked):
            return False
        return not (r.slot == "weapon" and any(p.slot == "weapon" and p.kind == r.kind for p in picked))

    def take(candidates: list[ForgeSecret]) -> None:
        found = next((r for r in candidates if fits(r)), None)
        if found is not None:
            picked.append(found)

    take(unseen)
    for slot in ("weapon", "armor"):
        if any(r.slot == slot for r in pool) and not any(p.slot == slot for p in picked):
            take([r for r in order if r.slot == slot])
    for r in order:
        if len(picked) >= count:
            break
        if fits(r):
            picked.append(r)
    ids = {p.id for p in picked}
    return [r.id for r in order if r.id in ids], not unseen


def stamp(state: SharedWorldState, content: Content) -> None:
    """開季、換季那一刻（sqlite_world.open_season／next_season／自動開的第一季）：開關開著、內容有神器時，照全服登記挑這一季的神器，
    蓋進 state.season.divine_lineup、記進登記的現世過；新神器用完了記下這一季（主控台與管理者的回話照它提醒）。直接改 state。"""
    if not content.config.forge_secrets.rotation or not any(r.divine for r in content.forge_secrets.values()):
        return
    reg = state.divine
    ids, out = lineup(content, reg, state.tianji)
    state.season.divine_lineup = ids
    reg.seen += [i for i in ids if i not in reg.seen]
    if out:
        reg.exhausted = state.season_number


def exhausted_now(registry: DivineRegistry, season_number: int) -> bool:
    """這一季開的時候新神器已經用完了（管理者換季的回話、伺服器啟動時印）。"""
    return registry.exhausted is not None and registry.exhausted == season_number
