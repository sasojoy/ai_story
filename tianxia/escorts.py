"""歷史武將同行第六節：大決戰打完，隨主人上陣的同伴回江湖（docs/superpowers/specs/2026-10-18-歷史武將同行-design.md）。

收場那一刻（engine._apply_battle_outcome，龍頭上陣的 generals.after_battle 之後）全服放掉 owner、在 CompanionProgress.parted_from
記下原主人（9.6）；原主人自己的 Game 補這一場的戰報時（_file_showdown）把他拿出隊伍、寫一句，同步或按招募之前（_settle_partings）
把情誼乘 Config.companions.parted_keep（無條件捨去）。季終收兵、管理者取消的那一場（unfinished）不算派過。
打到一半主人已經放走他、叛投放掉、或被別人招走的，收場時不動（owner 不是主人了）。只 import roster、battle_instance。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import battle_instance, roster
from .models import Content

if TYPE_CHECKING:
    from .world_state import CompanionProgress, WorldStateStore

# 待 joy 潤
RETURN_LINE = "{name}隨你打完這一仗，回江湖去了。"
FELL_RETURN_LINE = "{name}在陣前敗走，打完這一仗就回江湖去了。"
PARTED_LINE = "{name}離開之後，你們之間淡了些（情誼 {before}→{after}）。"
PARTED_TITLE = "同伴回江湖"


def due(battle: battle_instance.BattleInstance) -> list[tuple[str, battle_instance.Escort]]:
    """這一場還沒放回江湖的隨行同伴：（主人名號, 同伴）。"""
    return [(name, p.escort) for name, p in battle.participants.items() if p.escort is not None and not p.escort.released]


def after_battle(world: WorldStateStore, content: Content, battle: battle_instance.BattleInstance) -> None:
    """收場那一刻全服放掉這一場每一位上陣同伴的 owner（不必等主人上線，別人馬上就能招；第六節【PM】），記下原主人，
    released 寫回戰鬥那一列（只放一次）。開關關著、收兵或取消的那一場不動。"""
    rows = due(battle)
    if battle.unfinished or not rows or not roster.on(content):
        return
    for owner, e in rows:

        def _free(progress: CompanionProgress, owner: str = owner) -> None:
            if not roster.owns(progress.owner, owner):  # 打到一半放走、叛投放掉、別人招走：不動
                return
            progress.owner = None
            if not any(roster.owns(n, owner) for n in progress.parted_from):
                progress.parted_from.append(owner)

        world.update_companion(e.cid, _free)
    owners = {owner for owner, _ in rows}

    def _mark(b: battle_instance.BattleInstance) -> None:
        if b.record_id == battle.record_id:
            for owner in owners:
                q = b.participants.get(owner)
                if q is not None and q.escort is not None:
                    q.escort.released = True

    world.mutate_battle(_mark)
    for _, e in rows:
        e.released = True
