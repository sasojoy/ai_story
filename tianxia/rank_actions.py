"""第 3、4 階的行動（第一季設計 5.5；計畫 2026-10-06-第一季正式版-戊一）：黃巾「在一地煽動起事」、豪強「修築塢堡」、
在任的豪強第 4 階「趁亂占據郡縣」。誰做得了、在哪裡做得了、這週還剩幾次。推動與記功由引擎（Game._rank_action）做。

階一律讀 ranks.rank_of（不讀 PlayerState.rank：存檔的階停在 3，第 4 階是這一週在任，計畫丁）：有資格、還沒在任的人是 3，
做得了修築塢堡、做不了趁亂占據郡縣；週一輪替掉出席次，下一次選單上占據郡縣就不見了。"""
from __future__ import annotations

from . import calendar, ranks
from .models import Content, RankAction
from .rules import front_of, in_chaos, season_one
from .state import GameState

WEIGHT = {3: 5, 4: 10}  # 替軍令記功算幾次（軍令文件第二節、4.3）


def mine(state: GameState, content: Content) -> list[RankAction]:
    """此刻做得了的行動：自己陣營的、階夠的；開關關著、散人沒有。"""
    p = state.player
    if not season_one(content, state.world) or p.faction is None:
        return []
    rank = ranks.rank_of(state)
    return [a for a in content.orders.rank_actions if a.faction == p.faction and rank >= a.rank]


def where_ok(state: GameState, content: Content, action: RankAction, loc_id: str) -> bool:
    """這個地點做得了：有戰線；寫了 tags 的要帶其中一個標籤；chaos_only 的要那條戰線在亂局。"""
    front = front_of(content, loc_id)
    if front is None:
        return False
    if action.tags and not set(action.tags) & set(content.locations[loc_id].tags):
        return False
    return not action.chaos_only or in_chaos(state, content, front)


def _key(state: GameState, content: Content, action: RankAction) -> str:
    return f"{calendar.point(state.world.time, content, state.world).week}:{action.id}"


def left(state: GameState, content: Content, action: RankAction) -> int:
    """這一週（季曆）還能做幾次。"""
    return action.weekly - state.player.rank_action_weeks.get(_key(state, content, action), 0)


def count(state: GameState, content: Content, action: RankAction) -> None:
    """記這週一次（不論成敗）；只留這一週的（換週時舊的那幾筆丟掉）。"""
    key = _key(state, content, action)
    week = key.partition(":")[0]
    kept = {k: v for k, v in state.player.rank_action_weeks.items() if k.partition(":")[0] == week}
    kept[key] = kept.get(key, 0) + 1
    state.player.rank_action_weeks = kept


def weight(action: RankAction) -> int:
    """替軍令記功算幾次：第 3 階 5 次、第 4 階 10 次。"""
    return WEIGHT[action.rank]
