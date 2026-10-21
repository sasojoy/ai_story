"""戰力（招式與絕學稿案第二輪「強」、第四輪：就叫戰力）：一個全身加總的數。

不另發明數字：就是打架時引擎算本人那一份的威力（encounter.member_power；兩門武學的威力、槽裡意境的加成、四欄裝備、
屬性），氣血當滿、不看對手的屬性與路數。勝算與打起來都是這個數在算，所以它不騙人。
寫在三個地方：修練頁標題那一行氣血旁邊（now）、換上清單每一件「換上後 142 → 151」（with_art、with_gear）、
自創成形那一步「換上這一門：現在 142 → 128，練滿 160」（with_new）。換的那幾個都在一份複本上換，不動存檔。
"""
from __future__ import annotations

from . import encounter, equipment, library, team
from .martial_arts import MAX_LEVEL, MartialArt
from .models import Content
from .state import GameState
from .world_state import WorldStateStore


def now(state: GameState, content: Content, world: WorldStateStore) -> int:
    """此刻的戰力：本人那一份（同伴、部下不算），氣血當滿。"""
    arts = team.team_arts(state, content, world)
    members, _, boosts = team._fighters(state, content, world)
    if not members:
        return 0
    return round(encounter.member_power(members[0], arts, None, 1.0, boosts[0]))


def _copy(state: GameState) -> GameState:
    """只複製玩家那一份（換武學、換裝備只動它），其餘照原物。"""
    return state.model_copy(update={"player": state.player.model_copy(deep=True)})


def with_art(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> int | None:
    """功法庫裡這一門換上身之後的戰力；換不上（不在庫裡、找不到）是 None。"""
    trial = _copy(state)
    if art_id not in trial.player.arts:
        return None
    team.switch_art(trial, content, world, art_id)
    return None if art_id in trial.player.arts else now(trial, content, world)


def with_gear(state: GameState, content: Content, world: WorldStateStore, item_id: str) -> int | None:
    """裝備庫裡這一件換上之後的戰力；換不上（路上的坐騎、欄位關著）是 None。"""
    trial = _copy(state)
    equipment.wield(trial, content, item_id, equipment.WIELDABLE)
    return None if any(i.id == item_id for i in trial.player.rack) else now(trial, content, world)


class _Shadow:
    """一份還沒登記的武學（自創成形那一步）：get_skill 認得它，其餘照原來的世界（只讀）。"""

    def __init__(self, world: WorldStateStore, art: MartialArt):
        self._world, self._art = world, art

    def get_skill(self, skill_id: str):
        return self._art if skill_id == self._art.id else self._world.get_skill(skill_id)

    def __getattr__(self, name):
        return getattr(self._world, name)


def with_new(
    state: GameState, content: Content, world: WorldStateStore, art: MartialArt, quality: str | None = None,
) -> tuple[int, int]:
    """一門還沒登記的武學換上身：（第一成的戰力, 練滿第十成的戰力）。"""
    trial = _copy(state)
    shadow = _Shadow(world, art)
    library.store_art(trial, art, quality)
    if art.id in trial.player.arts:
        team.switch_art(trial, content, shadow, art.id)
    slot = "neigong_level" if art.kind == "內功" else "wugong_level"
    first = now(trial, content, shadow)
    setattr(trial.player.member, slot, MAX_LEVEL)
    return first, now(trial, content, shadow)
