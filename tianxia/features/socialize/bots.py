"""假人看到求見選單的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 call 那一段，全部拆包第 21 批拿了 call: 前綴之後搬來，照人物對話）。

假人不求見大勢人物（不呼叫模型）；名望不夠的求見永遠按得下去（只是被打發，武學與成長設計 9.1），更不能給分；萬一停在求見選單上，只會按返回。
`act:call`、`act:socialize` 是 act 子動詞（第 57 批接進 Verb 的只有按下去與標題），分數還在 bot_policy 的 act: 那一段（socialize_starts_dialogue、socialize_is_futile）。
"""
from __future__ import annotations

from tianxia.core.option import Option


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    _, _, arg = option.id.partition(":")
    return 0.0 if arg == "back" else None
