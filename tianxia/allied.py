"""第一季豪強分屬兩軍（docs/superpowers/specs/2026-10-15-第一季豪強分屬兩軍-design.md；企劃者 2026-10-15 定稿）。

蓋了第一季章、而且豪強分屬兩軍的章是開著的季（on），劇本裡有 allies 的陣營（地方豪強）要依附其中一軍，算那一軍的人：
敵我一律讀 side_of；頭銜、門派、部下、晉升、行動表、機緣照舊讀 PlayerState.faction。名冊（faction_rolls）的鍵寫 roll_key
（「haoqiang@guan」），資料庫結構不動。開關關著時 side_of 就是 faction、roll_key 就是陣營 id，一個字都不變。
只 import models、state、calendar。"""
from __future__ import annotations

from . import calendar
from .models import Content, FactionDef
from .state import GameState, WorldState

SEP = "@"


def on(content: Content, world: WorldState) -> bool:
    """這一季豪強分屬兩軍：蓋了第一季的章（calendar.season_one_on，同 rules.season_one），而且開季時這個章是開著的。"""
    return calendar.season_one_on(world, content) and world.haoqiang_allied


def allies_of(content: Content, faction_id: str | None) -> list[FactionDef]:
    """這個陣營可以依附的幾軍（照劇本的順序）；不是要依附的陣營是空的。"""
    found = content.scenario.find_faction(faction_id)
    return [f for f in content.scenario.factions if found is not None and f.id in found.allies]


def side_of(state: GameState, content: Content) -> str | None:
    """敵我的一個讀法：依附的季、依附了一軍的人是那一軍；其他人是自己的陣營（散人 None）。"""
    p = state.player
    if p.ally is not None and on(content, state.world):
        return p.ally
    return p.faction


def needs_ally(state: GameState, content: Content) -> bool:
    """投靠了要依附的陣營、還沒挑一邊（拜入曹氏莊院那一下）：選單只剩選邊（Game.options）。"""
    p = state.player
    return on(content, state.world) and p.ally is None and bool(allies_of(content, p.faction))


def roll_key(faction: str, ally: str | None) -> str:
    """名冊的鍵：依附了一軍是「陣營@那一軍」，其他是陣營 id。"""
    return f"{faction}{SEP}{ally}" if ally else faction


def split_key(key: str) -> tuple[str, str | None]:
    """名冊的鍵 → （陣營, 依附的那一軍或 None）。"""
    faction, _, ally = key.partition(SEP)
    return faction, ally or None


def side_of_key(key: str | None) -> str | None:
    """名冊的鍵 → 算哪一方。"""
    if key is None:
        return None
    faction, ally = split_key(key)
    return ally or faction


def faction_totals(rolls: dict[str, int]) -> dict[str, int]:
    """名冊照陣營（身分）數：補假人、腳本照它。"""
    out: dict[str, int] = {}
    for key, n in rolls.items():
        faction = split_key(key)[0]
        out[faction] = out.get(faction, 0) + n
    return out


def side_totals(rolls: dict[str, int]) -> dict[str, int]:
    """名冊照那一方數：名冊那一句、假人選邊照它。"""
    out: dict[str, int] = {}
    for key, n in rolls.items():
        side = side_of_key(key) or key
        out[side] = out.get(side, 0) + n
    return out


def gentry_totals(rolls: dict[str, int]) -> dict[str, int]:
    """每一軍裡有幾個依附的人（名冊那一句的括號）。"""
    out: dict[str, int] = {}
    for key, n in rolls.items():
        ally = split_key(key)[1]
        if ally is not None:
            out[ally] = out.get(ally, 0) + n
    return out


def hidden_trends(content: Content, world: WorldState) -> set[str]:
    """依附的季不存在的大勢線：只有要依附的陣營（豪強）當目標的線（割據）。"""
    if not on(content, world):
        return set()
    armies = [f for f in content.scenario.factions if not f.allies]
    gentry = [f for f in content.scenario.factions if f.allies]
    return {t for f in gentry for t in f.goals if not any(t in a.goals for a in armies)}
