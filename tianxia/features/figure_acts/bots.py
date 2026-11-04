"""假人看到護衛、犒軍、探望、盤算的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 ("ambush", "works", "aid") 那一行，全部拆包第 31 批拿了
aid: 前綴之後搬來；plan: 原本落到 score 最後的 None，現在也由這裡回）。

護衛、犒軍、探望由 take_turn 的 _stamina_play 挑（bot_policy 的體力玩法清單，核心原位）做，不交給打分數；盤算假人不碰。
"""
from __future__ import annotations

from tianxia.core.option import Option


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    return None
