"""假人看到馬市的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 market 那兩行，全部拆包第 42 批拿了 market: 前綴之後搬來，照鐵匠鋪）。
bot_policy 照舊留著 MARKET_SCORE 這個名字（tests/bots/test_bot_policy.py 直接讀；數同一個，8.0 = SMITH_SCORE = BOUNTY_SCORE）。`act:market`（進馬市）的分數
還在 bot_policy 的 act: 那一段（前綴 act 是核心的，掛鉤問不到），繼續用 MARKET_SCORE。

整季機器人與假人共用的底層（bot.market_want、bot.visit_market、bot.feed_mount、bot.wear_better）不搬（總表歸「假人三支不搬」），它們叫 Game 的公開方法（委派都留著）。
"""
from __future__ import annotations

from tianxia.core.option import Option

MARKET_SCORE = 8.0  # 馬市（裝備四欄設計第九節）：趕路疾行省體力，跟鐵匠鋪一樣急；真人會騎馬，假人也要（bot_policy.MARKET_SCORE = SMITH_SCORE 同一個數）


def score(game, option: Option) -> float | None:
    """選項的分數；None＝假人不會按。馬市上：照 bot.market_want 按那一顆（換、買、餵），沒事就離開。"""
    from tianxia import bot  # noqa: PLC0415  過渡：待搬（整季機器人與假人共用的底層 bot.py：這一批不搬，手冊 3.8 之後才拆）

    arg = option.id.partition(":")[2]
    return MARKET_SCORE if option.id == bot.market_want(game) else 0.0 if arg == "back" else None
