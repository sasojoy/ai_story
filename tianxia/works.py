"""屯糧練兵（後期體力玩法第一批，Joy 2026-10-16；Config.stockpile）的純規則。修築工事（替舊的拔河多撐幾點）2026-10-27 跟著舊拔河拿掉。

屯糧練兵：在自家控制的地方（大本營、自家的戰線地點）花體力替自己那一軍屯糧（WorldState.supply），下一場時刻表決戰開集結那一刻
（world._open_claimed → on_muster）換成起點往屯得多的那一軍偏 cap×(甲−乙)÷(甲＋乙＋soft)，四捨五入、最多 cap 點，
屯的量隨即清空。只有交戰兩軍（含依附那一軍的豪強，allied.side_of）；第一季規則開著的季才有（只有那種季有時刻表決戰）。

只讀寫傳進來的 GameState／WorldState；體力、紀錄、貢獻在 engine.Game。on_muster 自己開 mutate_season、mutate_battle，
只在 world._open_claimed（不在任何 mutate 裡）叫。"""
from __future__ import annotations

from . import allied, rules, territory
from .models import BattleDef, Content
from .state import GameState, Rumor, WorldState
from .world_state import WorldStateStore

# 玩家看得到的字（待 joy 潤）
STOCK_TITLE = "屯糧練兵"
STOCK_LABEL = "屯糧練兵（{side}已屯 {n}）"
STOCK_DONE = "你替{side}運糧、操練新兵，{side}這一回已屯 {n}。下一場決戰開集結時，屯得多的一方起手佔點便宜。"
MUSTER_LINE = "{battle}開集結，{a}屯了 {na}、{b}屯了 {nb}。{lean}"
LEAN_TO = "糧足兵精，起手往{side}偏了 {n} 點。"
LEAN_NONE = "兩軍屯得相當，起手不偏。"


def battle_sides(content: Content) -> set[str]:
    """時刻表決戰的交戰兩軍（屯糧只算這幾方）。"""
    return {f.id for b in content.battles.values() for f in b.factions}


def stockpile_on(content: Content, world: WorldState) -> bool:
    return content.config.stockpile.enabled and bool(content.scenario.factions) and rules.season_one(content, world) and not world.ended


def stock_side(state: GameState, content: Content) -> str | None:
    """你屯糧算在哪一軍：交戰兩軍之一（豪強分屬兩軍的季，依附的那一軍）；散人、不分屬兩軍的豪強是 None。"""
    side = allied.side_of(state, content)
    return side if side in battle_sides(content) else None


def stock_spot(state: GameState, content: Content) -> str | None:
    """這裡屯不屯得了糧：開關開著、這一季有時刻表決戰、你是交戰兩軍之一、這裡是自家的大本營或自家控制的地方。回那一軍或 None。"""
    if not stockpile_on(content, state.world):
        return None
    side = stock_side(state, content)
    if side is None:
        return None
    p = state.player
    owner = territory.controller(state.world, content, p.location) if territory.on(content) else territory.bases(content).get(p.location)
    return side if owner in {side, p.faction} and owner is not None else None


def stockpile(state: GameState, side: str) -> int:
    """屯一下（呼叫端先問 stock_spot、扣體力）：那一軍 +1，回那一軍此刻屯了幾下。"""
    w = state.world
    w.supply[side] = w.supply.get(side, 0) + 1
    return w.supply[side]


def lean(supply: dict[str, int], definition: BattleDef, content: Content) -> int:
    """起點偏幾點：正數往 factions[0]（決戰的推動方向照 factions[0] 是正向的約定），夾在 ±cap。"""
    cfg = content.config.stockpile
    if len(definition.factions) < 2:
        return 0
    a, b = supply.get(definition.factions[0].id, 0), supply.get(definition.factions[1].id, 0)
    if a + b + cfg.soft <= 0:
        return 0
    shift = round(cfg.cap * (a - b) / (a + b + cfg.soft))
    return max(-cfg.cap, min(cfg.cap, shift))


def muster_text(supply: dict[str, int], definition: BattleDef, shift: int) -> str:
    f0, f1 = definition.factions[0], definition.factions[1]
    if shift == 0:
        tail = LEAN_NONE
    else:
        tail = LEAN_TO.format(side=(f0 if shift > 0 else f1).name, n=abs(shift))
    return MUSTER_LINE.format(battle=definition.name, a=f0.name, na=supply.get(f0.id, 0), b=f1.name, nb=supply.get(f1.id, 0), lean=tail)


def on_muster(world: WorldStateStore, content: Content, definition: BattleDef) -> list[str]:
    """時刻表決戰剛開集結（world._open_claimed，不在任何 mutate 裡）：兩軍屯的量換成起點的偏移、快照進這一場（supply_lean）、整個清空，
    天下大事一句。兩軍都沒屯就什麼都不寫（一次讀、不開寫入）。"""
    if not content.config.stockpile.enabled or len(definition.factions) < 2:
        return []
    if not any(world.get_season().supply.get(f.id, 0) for f in definition.factions):
        return []
    got: dict[str, int] = {}
    text: dict[str, str] = {}

    def _take(season: WorldState) -> None:
        got.update({f.id: season.supply.get(f.id, 0) for f in definition.factions})
        season.supply = {}
        text["line"] = muster_text(got, definition, lean(got, definition, content))
        season.rumors.append(Rumor(time=season.time, text=text["line"], layer="world"))

    world.mutate_season(_take)
    shift = lean(got, definition, content)

    def _snap(b) -> None:
        if b.battle_id == definition.id and b.phase == "muster":
            b.supply_lean = dict(got)
            b.trend = b.trend_start = max(0, min(100, b.trend + shift))

    world.mutate_battle(_snap)
    return [f"🌾 【天下大事】{text['line']}"]
