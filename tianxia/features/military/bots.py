"""假人看到機緣、伏筆的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 `if kind == "opp": return None`，全部拆包第 34 批拿了
opp:、fs: 兩個前綴之後搬來）。

假人不做機緣（正式版乙一）：opp: 一律不按；fs:（伏筆的最後一步）原本沒有專門一行，走到 score 最後的 `return None`，結果一樣是不按。
整季機器人（bot.pick）在選項進分數之前就用 FORESHADOW_OPTIONS 整批濾掉 fs:、opp:、talk:clue:、talk:opp:（核心的 pick，不動）；
對話裡的 talk:opp:、talk:clue: 由人物情誼包的 bots.py 回 None。
"""
from __future__ import annotations

from tianxia.core.option import Option


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    return None
