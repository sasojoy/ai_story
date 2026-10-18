"""龍頭上陣（Joy 2026-10-17 清單第 2 條「大決戰雙方龍頭武將應該要參與且有份量」；數字在 Config.battle.generals）。

決戰開集結那一刻（world._open_claimed），每一方照那條戰線（沒寫戰線的照決戰的大區）取在場的前幾位大勢人物上陣，寫進
BattleInstance.commanders。回合裡怎麼打在 battle_instance（call_orders、_strike_commanders）；收場之後敗走的人扣聲威
（after_battle，engine._apply_battle_outcome 一開頭叫）。只 import models、state、world_state、figures、atlas、battle_instance。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import atlas, battle_instance, figures
from .models import BattleDef, Content
from .state import GameState, Rumor

if TYPE_CHECKING:
    from .world_state import WorldStateStore

SLAY_RUMOR = "{battle}上，{who}陣前擊退{name}。"  # 待 joy 潤：天下大事（最後一擊的人具名）
FALL_RUMOR = "{battle}上，{name}陣前敗走。"
MUSTER_LINE = "{battle}集結：{rows}親自上陣。"  # 待 joy 潤：天下大事
RANK_NAMES = ("主將", "副將", "偏將", "裨將")


def on(content: Content) -> bool:
    return content.config.battle.generals.enabled and bool(content.figures)


def _in_battle(state: GameState, content: Content, definition: BattleDef, fid: str) -> bool:
    """這位人物此刻在不在這一場的戰場上：在場（active）、有所在；決戰寫了戰線就要在那條戰線上領兵，沒寫照大區。"""
    now = figures.state_of(state, content, fid)
    if now.status != "active" or not now.location:
        return False
    if definition.front is not None:
        return now.front == definition.front
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


def on_muster(world: WorldStateStore, content: Content, definition: BattleDef) -> list[str]:
    """剛開集結（world._open_claimed，不在任何 mutate 裡）：派人物上陣、天下大事一句。開關關著、沒人上陣什麼都不寫。"""
    if not on(content):
        return []
    from .world import _season_vehicle  # noqa: PLC0415  world → generals：延後 import

    season = world.get_season()
    rows = pick(_season_vehicle(content, season), content, definition)
    if not rows:
        return []

    def _snap(b: battle_instance.BattleInstance) -> None:
        if b.battle_id == definition.id and b.phase == "muster":
            b.commanders = [c.model_copy() for c in rows]

    world.mutate_battle(_snap)
    names = {f.id: f.name for f in definition.factions}
    text = "，".join(
        f"{names.get(f.id, f.id)}" + "、".join(f"{RANK_NAMES[c.rank]}{c.name}" for c in rows if c.faction == f.id)
        for f in definition.factions if any(c.faction == f.id for c in rows)
    )
    line = MUSTER_LINE.format(battle=definition.name, rows=text)
    world.mutate_season(lambda s: s.rumors.append(Rumor(time=s.time, text=line, layer="world")))
    return [f"⚔️ 【天下大事】{line}"]


def lineup(battle: battle_instance.BattleInstance, side: str) -> str:
    """決戰畫面：這一方上陣的人物與他們的氣血（「主將皇甫嵩（氣血 1200/1500）、副將朱儁（敗走）」）；沒有是空字串。"""
    rows = [c for c in battle.commanders if c.faction == side]
    if not rows:
        return ""
    return "、".join(
        f"{RANK_NAMES[c.rank]}{c.name}（" + ("敗走" if c.fallen_round is not None else f"氣血 {round(c.neili)}/{round(c.neili_cap)}") + "）"
        for c in sorted(rows, key=lambda c: c.rank)
    )


def after_battle(world: WorldStateStore, content: Content, battle: battle_instance.BattleInstance) -> None:
    """收場之後：這一場敗走的人物聲威 −fall_prestige（figures.defeat，不受一天只扣一次與一天上限的限制，可能直接退場、照退場的規則回來），
    天下大事一句（最後一擊的人具名）。每一位只扣一次（Commander.settled 記在戰鬥那一列）。季終收兵的不扣。"""
    gen = content.config.battle.generals
    due = [c for c in battle.commanders if c.fallen_round is not None and not c.settled and c.fid in content.figures]
    if battle.unfinished or not due:
        return
    from .world import _season_vehicle  # noqa: PLC0415

    definition = content.battles.get(battle.battle_id)
    where = definition.name if definition is not None else battle.battle_id

    def _hit(season) -> None:
        vehicle = _season_vehicle(content, season)
        for c in due:
            line = (SLAY_RUMOR.format(battle=where, who=c.felled_by, name=c.name) if c.felled_by
                    else FALL_RUMOR.format(battle=where, name=c.name))
            season.rumors.append(Rumor(time=season.time, text=line, layer="world"))
            if gen.fall_prestige:
                figures.defeat(vehicle, content, c.fid, gen.fall_prestige)

    world.mutate_season(_hit)
    keys = {c.fid for c in due}

    def _mark(b: battle_instance.BattleInstance) -> None:
        if b.record_id == battle.record_id:
            for c in b.commanders:
                if c.fid in keys:
                    c.settled = True

    world.mutate_battle(_mark)
    for c in battle.commanders:
        if c.fid in keys:
            c.settled = True
