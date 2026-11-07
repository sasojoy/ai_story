"""龍頭上陣的挑法（Joy 2026-10-17 清單第 2 條「大決戰雙方龍頭武將應該要參與且有份量」；數字在 Config.battle.generals）：誰上陣、份量、池子。

共用規則層（tianxia/core/registry.py 的 SHARED）：決戰包開集結那一刻派人上陣（tianxia/features/battle/generals.py 的 on_muster）與共用規則層的
攻城留守（siege.commanders）都讀這一份。全部拆包第 8 批把 generals 搬進決戰包時，siege 讀的這一塊（原本 generals 的 on、_in_battle、pick，
本體一字不改）留在這一層（第 15 批 PM 認定第 2 條：不然共用規則層 import 包）；決戰包的 generals 照舊 re-export on、pick（同一個函式物件）。
**測試要換挑法請換這裡的 chiefs.on、chiefs.pick**：換掉 generals.on／generals.pick（或舊名 tianxia.generals 的）只改到決戰包開集結派人上陣
（on_muster 叫的是包裡那個名字），攻城的留守（siege.commanders 叫 chiefs）照舊——搬之前兩處都讀 generals，換一個名字兩處都變（第 8 批審查 nit）。
只 import models、state、figures、atlas、battle_instance。
"""
from __future__ import annotations

from . import atlas, figures
from .core import battle_base as battle_instance
from .models import BattleDef, Content
from .state import GameState


def on(content: Content) -> bool:
    return content.config.battle.generals.enabled and bool(content.figures)


def _in_battle(state: GameState, content: Content, definition: BattleDef, fid: str) -> bool:
    """這位人物此刻在不在這一場的戰場上：在場（active）、有所在；決戰寫了戰線就要在那條戰線上領兵，沒寫照大區。"""
    now = figures.state_of(state, content, fid)
    if now.status != "active" or not now.location:
        return False
    if definition.front is not None:
        # 「大勢人物擴充」（PR #58）的 figures.line_of：沒有戰線的人物照所在地點的大區算在哪條線上；那一份還沒合進來時照戰線
        line = figures.line_of(state, content, fid) if hasattr(figures, "line_of") else now.front
        return line == definition.front
    if definition.region is None or now.location not in content.locations:
        return False
    region = atlas.region_of(content, now.location)
    return region is not None and region.id == definition.region


def pick(state: GameState, content: Content, definition: BattleDef) -> list[battle_instance.Commander]:
    """這一場要上陣的人物：每一方照人物表的順序（位階）取前 len(ranks) 位。份量＝實力（照他挑戰本人那支隊伍此刻的難度，
    同 battle_instance.strength）× 位階倍數 ×（0.5＋0.5×此刻聲威÷開季聲威，最多 1）；池子照位階，不看聲威。"""
    tuning = content.config.battle
    gen = tuning.generals
    out: list[battle_instance.Commander] = []
    for side in definition.factions:
        rank = 0
        for fid, fig in content.figures.items():
            if rank >= len(gen.ranks) or rank >= len(gen.pool):
                break
            if fig.faction != side.id or fig.squad not in content.squads or not _in_battle(state, content, definition, fid):
                continue
            now = figures.state_of(state, content, fid)
            might = battle_instance.strength(tuning, content.squads[fig.squad].difficulty)
            standing = min(1.0, now.prestige / fig.start_prestige) if fig.start_prestige else 1.0
            score = round(might * gen.ranks[rank] * (0.5 + 0.5 * standing), 1)
            out.append(battle_instance.Commander(
                fid=fid, name=fig.name, faction=side.id, rank=rank, score=score,
                neili=gen.pool[rank], neili_cap=gen.pool[rank], prestige=now.prestige,
            ))
            rank += 1
    return out
