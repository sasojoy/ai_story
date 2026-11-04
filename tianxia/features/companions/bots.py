"""假人看到人物對話的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 talk 那一段，全部拆包第 20 批拿了 talk:、parley: 前綴之後搬來，照宴客）。

假人不跟大勢人物閒聊、不求事（不呼叫模型，也不寫自由文字）：萬一停在對話裡，只會按「告辭」；對話裡的其他選項（talk:N、talk:say、talk:plan、條件的接與不接、
還債、請他兌現、伏筆的片段 talk:clue:、機緣的話題 talk:opp:）與帶路的路上說一句（parley:road）一律不按。
"""
from __future__ import annotations

from tianxia.core.option import Option


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    kind, _, arg = option.id.partition(":")
    return 0.0 if kind == "talk" and arg == "leave" else None
