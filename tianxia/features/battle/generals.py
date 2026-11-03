"""龍頭上陣（Joy 2026-10-17 清單第 2 條「大決戰雙方龍頭武將應該要參與且有份量」；數字在 Config.battle.generals）。全部拆包第 8 批從
tianxia/generals.py 搬進決戰包（舊名是別名：sys.modules，同一個模組物件）；誰上陣、份量、池子的挑法（on、pick）留在共用規則層
tianxia/chiefs.py（共用規則層的 siege.commanders 也讀），這裡照舊 re-export（generals.on、generals.pick 是同一個函式物件）。

決戰開集結那一刻（world._open_claimed），每一方照那條戰線（沒寫戰線的照決戰的大區）取在場的前幾位大勢人物上陣，寫進
BattleInstance.commanders。回合裡怎麼打在 battle_instance（call_orders、_strike_commanders）；收場之後敗走的人扣聲威
（after_battle，progress.apply_battle_outcome 一開頭叫；攻城的留守在 sieges.settle_siege 叫）。只 import models、state、world_state、figures、
battle_instance、chiefs。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import battle_instance, figures  # 共用規則層（戰鬥規則核心）；過渡：待搬（大勢人物：敗走扣聲威）
from tianxia.chiefs import on, pick  # noqa: F401  共用規則層（龍頭上陣的挑法）：這一包的 on_muster 用、照舊 re-export 給 generals.on、generals.pick
from tianxia.models import BattleDef, Content
from tianxia.state import Rumor

if TYPE_CHECKING:
    from tianxia.world_state import WorldStateStore

SLAY_RUMOR = "{battle}上，{who}陣前擊退{name}。"  # 待 joy 潤：天下大事（最後一擊的人具名）
FALL_RUMOR = "{battle}上，{name}陣前敗走。"
MUSTER_LINE = "{battle}集結：{rows}親自上陣。"  # 待 joy 潤：天下大事
RANK_NAMES = ("主將", "副將", "偏將", "裨將")


def on_muster(world: WorldStateStore, content: Content, definition: BattleDef) -> list[str]:
    """剛開集結（world._open_claimed，不在任何 mutate 裡）：派人物上陣、天下大事一句。開關關著、沒人上陣什麼都不寫。"""
    if not on(content):
        return []
    from tianxia.world import _season_vehicle  # noqa: PLC0415  過渡：待搬（季的事用的空殼玩家；world → generals：延後 import）

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


def after_battle(
    world: WorldStateStore, content: Content, battle: battle_instance.BattleInstance, where: str | None = None, mutate=None,
) -> None:
    """收場之後：這一場敗走的人物聲威 −fall_prestige（figures.defeat，不受一天只扣一次與一天上限的限制，可能直接退場、照退場的規則回來），
    天下大事一句（最後一擊的人具名）。每一位只扣一次（Commander.settled 記在戰鬥那一列）。季終收兵的不扣。
    攻城戰（領地爭奪第二批）的留守也走這裡：where 是那一場的名字（攻城・地點），mutate 是改那一場的那一個（store.mutate_siege）；
    沒給照決戰（定義的名字、mutate_battle）。"""
    gen = content.config.battle.generals
    due = [c for c in battle.commanders if c.fallen_round is not None and not c.settled and c.fid in content.figures]
    if battle.unfinished or not due:
        return
    from tianxia.world import _season_vehicle  # noqa: PLC0415  過渡：待搬（季的事用的空殼玩家）

    if where is None:
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

    (mutate or world.mutate_battle)(_mark)
    for c in battle.commanders:
        if c.fid in keys:
            c.settled = True
