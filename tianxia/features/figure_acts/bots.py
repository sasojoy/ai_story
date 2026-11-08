"""假人看到挑戰本人那一格怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 act:challenge: 那幾行，全部拆包第 60 批搬來，Verb.tail_bot 問）。

護衛、犒軍、探望 aid:、大勢人物的密謀 plan: 假人沒有要按的，bot_pick 照預設回 None，不在這裡。_crippled、ORDER_SCORE 別包也讀，第二輪第 89 批搬進共用層 bot_base，一律寫 `bot_base.X`，測試換 bot_base 的才打得到；
CHALLENGE_SCORE、CHALLENGE_ODDS、STRIKE_ODDS 只有這一包與整季機器人讀，同一批從 bot_policy、bot 搬來，舊名 re-export。**模組層不准碰 engine 與假人殼**（bot、bot_policy 模組層 import 這個檔）。
"""
from __future__ import annotations

from tianxia import bot_base, orders  # 共用規則層（軍令：打擊軍令有沒有點名他；照模組屬性叫，tally 軌換掉 orders.strike_on）

# 挑戰打得贏的大勢人物本人（T4）：比探索、交友高，比推大勢的遊歷低（一點大勢抵十分）——前線上照舊遊歷，
# 前線以外遇上了才打；「打擊大勢人物」軍令讓假人專程去找人是 T6 的事
CHALLENGE_SCORE = 1.5
CHALLENGE_ODDS = ("穩勝", "有把握")  # 挑戰本人只挑這兩種勝算（整季機器人與伺服器假人共用；挑戰每季都有設計第九節）
STRIKE_ODDS = CHALLENGE_ODDS + ("五五波",)  # 有打擊軍令點名這位人物時，五五波也去打


def challenge(game, fid: str) -> float | None:
    """挑戰本人：打得贏才去（打不贏的、閉門不見的按不下去，本來就不在候選裡）。內傷走不動的不打，排在勝算之前（勝算是四十場模擬）；有打擊軍令點名他時五五波也去打（計畫 T6；豪強分屬兩軍照依附那一軍）。"""
    if bot_base._crippled(game):
        return None
    odds = game.challenge_odds(fid)
    if orders.strike_on(game.state, game.content, game._side(), fid):
        return bot_base.ORDER_SCORE + CHALLENGE_SCORE if odds in STRIKE_ODDS else None
    return CHALLENGE_SCORE if odds in CHALLENGE_ODDS else None
