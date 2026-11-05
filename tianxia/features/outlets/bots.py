"""假人看到銀兩出口與捐軍備兩串選單的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 dadian、donate 兩段，
全部拆包第 43 批拿了 donate:、dadian: 前綴之後搬來）。

萬一停在打點那一間店裡只會離開（每一顆都 0.0）；萬一停在軍需官那一串裡只會離開（捐由 look_after 的 bot.donate_spare 直接捐，不按這一串的鈕）。
`act:donate`、`act:dadian` 是 act 子動詞，分數（None：假人不進）還在 bot_policy 的 act: 那一段（前綴 act 是核心的，掛鉤問不到）。
"""
from __future__ import annotations

from tianxia.core.option import Option


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    kind, _, arg = option.id.partition(":")
    if kind == "dadian":  # 萬一停在打點那一間店裡：只會離開
        return 0.0
    # 萬一停在軍需官那一串裡（捐軍備）：只會離開；捐由 look_after 的 bot.donate_spare 直接捐，不按這一串的鈕
    return 0.0 if arg == "back" else None
