"""假人看到單挑的選項怎麼按（開發規範手冊 3.8；全部拆包第 12 批：原本 bot_policy.score 的 duel、arena 那兩段照抄）。

頭目戰、擂台打到一半的那一招由 bot_policy.take_turn 前面照架勢出（duel_move，不交給打分數）；報名、更新分身、挑一場由 bot_policy._arena
一次做完（打開擂台、按那一顆、還開著就返回）。這裡只回分數：萬一停在擂台邊只會返回。
idle：整季機器人（bot.pick）不按的那兩顆（第 60 批；原本 bot.py 從 engine 拿 DUEL_FLEE、ARENA_YIELD）。
"""
from __future__ import annotations

from tianxia.core.option import Option

from . import arena_rules, duel_actions


def idle(option: Option) -> bool:
    """頭目戰的抽身退走、擂台的認輸下台：打到一半一直按得下去，機器人照出招打完。"""
    return option.id in (duel_actions.FLEE_ID, arena_rules.YIELD_ID)


def score(option: Option) -> float | None:
    """None＝假人不按。"""
    kind, _, arg = option.id.partition(":")
    if kind == "duel":
        return None  # 頭目戰在 take_turn 前面就出招了（duel_move）
    if kind == "arena":  # 擂台由 _arena 一次做完；萬一停在擂台邊只會返回，打到一半由 take_turn 照架勢出招
        return 0.0 if arg == "back" else None
    return None
