"""假人看到鐵匠鋪的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 smith 那一段與 bot_policy._smith_want，全部拆包第 41 批拿了
smith: 前綴之後搬來，照決戰包）。bot_policy 照舊留著 _smith_want（一行，叫這裡的 want）與 SMITH_SCORE、FORGE_SCORE 這幾個名字（tests/bots/test_bot_policy.py、
tests/gear 直接讀；數同一個）。`act:smith`（進鐵匠鋪）的分數還在 bot_policy 的 act: 那一段（前綴 act 是核心的，掛鉤問不到），繼續用 SMITH_SCORE、FORGE_SCORE。

整季機器人與假人共用的底層（bot.smith_want、bot.forge_step、bot.forge_ready、bot.trade_at_smith、bot.keep_book_names）不搬（總表歸「假人三支不搬」），
它們叫 Game 的公開方法（委派都留著）。
"""
from __future__ import annotations

from tianxia.core.option import Option

SMITH_SCORE = 8.0  # 鐵匠鋪：跟揭懸賞一樣急，兵器配不上是白白少一截威力（bot_policy.SMITH_SCORE = BOUNTY_SCORE 同一個數）


def want(game) -> str | None:
    """此刻在鐵匠鋪最該按的那一顆：單子開著時只照 bot.forge_step（下一步或「不打了」）；不然先照 bot.smith_want（換、買、修，兵器防具兩頁），
    沒事再照 bot.forge_step（打造與換上打出來的那把，打造第二批 PM 決定第 3 條）。都沒事是 None。不淬煉、不拆。"""
    from tianxia import bot  # noqa: PLC0415  過渡：待搬（整季機器人與假人共用的底層，總表歸「假人三支不搬」）

    if game.state.player.smith_draft is not None:
        return bot.forge_step(game)
    return bot.smith_want(game) or bot.forge_step(game)


def score(game, option: Option) -> float | None:
    """選項的分數；None＝假人不會按。鐵匠鋪上：照 want 按那一顆（換買修、打造與換上打出來的那把，含切頁），沒事就離開；不淬煉、不拆，萬一停在單子上只按「不打了」。"""
    arg = option.id.partition(":")[2]
    return SMITH_SCORE if option.id == want(game) else 0.0 if arg in ("back", "forge-cancel") else None
