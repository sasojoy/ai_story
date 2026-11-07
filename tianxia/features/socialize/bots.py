"""假人看到求見選單的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 call 那一段，全部拆包第 21 批拿了 call: 前綴之後搬來，照人物對話）。

假人不求見大勢人物（不呼叫模型）；名望不夠的求見永遠按得下去（只是被打發，武學與成長設計 9.1），更不能給分；萬一停在求見選單上，只會按返回。
`act:call`（不按）、`act:socialize`（act_socialize）是 act 子動詞，第 60 批接進 Verb.bot；bot_idle 問 idle_call（bot.pick 那一條原本的排除）。
"""
from __future__ import annotations

from tianxia.core.option import Option

ACT_SCORE = 0.8  # act:socialize 的底分（bot_policy.ACT_SCORES["socialize"] 同一個數；照鐵匠鋪 SMITH_SCORE 前例）


def act_socialize(game) -> float | None:
    """act:socialize：這一下開口是閒聊或求見大勢人物（要模型、假人不寫字）、或只會被擋在門外的，不按；其餘照 ACT_SCORE。"""
    return None if game.socialize_starts_dialogue() or game.socialize_is_futile() else ACT_SCORE


def idle_call(game, option: Option) -> bool:
    """整季機器人（bot.pick）：名望不夠的求見按下去只是被打發、永遠按得下去，不排除的話「沒事可做就推進時間」的訊號會失效（同 act:rest）。"""
    oid = option.id
    return oid.startswith("call:") and oid != "call:back" and not game.can_meet_figure(oid.partition(":")[2])


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    _, _, arg = option.id.partition(":")
    return 0.0 if arg == "back" else None
