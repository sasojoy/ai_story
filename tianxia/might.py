"""戰力（招式與絕學稿案第二輪「強」、第四輪：就叫戰力）：一個全身加總的數。

打架時引擎算本人那一份的威力（encounter.member_power；兩門武學的威力、四欄裝備、屬性），氣血當滿、不看對手的屬性與路數，
再乘上兩門槽裡的意境與招的加成（arts.effect_bonus，武學卡上的戰力同一套權重）：意境的效果是回合裡的機率，不乘的話裝了不會動。
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
    """此刻的戰力：本人那一份（同伴、部下不算），氣血當滿；再乘上身上兩門槽裡的意境與招（arts.effect_bonus，
    跟武學卡上的戰力 arts.rating 同一套權重）——不然意境的效果都是回合裡的機率，裝進去戰力一動也不動（Joy 2026-10-21
    「合出來我根本看不懂這是不是好的」）。"""
    from . import arts as arts_mod  # noqa: PLC0415  arts 經 team 間接 import 這裡

    arts = team.team_arts(state, content, world)
    members, _, boosts = team._fighters(state, content, world)
    if not members:
        return 0
    member = state.player.member
    bonus = sum(arts_mod.effect_bonus(content, arts[k]) for k in (member.wugong_id, member.neigong_id) if k in arts)
    return round(encounter.member_power(members[0], arts, None, 1.0, boosts[0]) * (1 + bonus))


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


def best_place(state: GameState, content: Content, world: WorldStateStore, insight_id: str) -> dict | None:
    """這一份意境裝在身上哪一格最強（Joy 2026-10-21「合成出來我當下還是不知道到底是好還是不好」）：身上兩門的每一格，
    顏色收得下的都在複本上試（空格直接裝、有東西的換下來；它原本裝在別格的先拆），回最好的那一格
    {art, name, i, swap（換下的意境名，空格是 None）, might}；身上沒有一格收得下是 None。寫死的武學（沒有槽）不算。"""
    from . import arts as arts_mod, insights  # noqa: PLC0415  arts 經 team 間接 import 這裡

    ins = insights.resolve(insight_id, content, world, state)
    if ins is None:
        return None
    member, best = state.player.member, None
    for art_id in (member.wugong_id, member.neigong_id):
        art = team.resolve_art(art_id, content, world) if art_id else None
        if art is None:
            continue
        slots = arts_mod.slots_of(state, content, art)
        colors = arts_mod.colors_of(art, len(slots))
        for i, held in enumerate(slots):
            if held == insight_id or not arts_mod.takes_at(art, colors[i], ins.attribute):
                continue
            trial = _copy(state)
            for key, row in trial.player.art_slots.items():  # 原本裝在別格的先拆（一份意境同時只裝一門一格）
                trial.player.art_slots[key] = [None if v == insight_id else v for v in row]
            row = arts_mod.slots_of(trial, content, art)
            row[i] = insight_id
            trial.player.art_slots[art_id] = row
            power = now(trial, content, world)
            if best is None or power > best["might"]:
                gone = insights.resolve(held, content, world, state) if held else None
                best = {"art": art_id, "name": art.name, "i": i, "swap": gone.name if gone else None, "might": power}
    return best
