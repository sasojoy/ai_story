"""假人看到挑戰本人那一格怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 act:challenge: 那幾行，全部拆包第 60 批搬來，Verb.tail_bot 問）。

護衛、犒軍、探望 aid:、大勢人物的密謀 plan: 假人沒有要按的，bot_pick 照預設回 None，不在這裡。_crippled 與分數常數（CHALLENGE_SCORE、ORDER_SCORE、CHALLENGE_ODDS、STRIKE_ODDS）還在 bot_policy
（測試讀這幾個名字），所以經 `from tianxia import bot_policy` 延後 import（舊模組 import engine，包不能在模組載入時 import 它；第 47 批前例）；照模組屬性讀，測試換掉也生效。
"""
from __future__ import annotations

from tianxia import orders  # 共用規則層（軍令：打擊軍令有沒有點名他；照模組屬性叫，abacus 軌換掉 orders.strike_on）


def challenge(game, fid: str) -> float | None:
    """挑戰本人：打得贏才去（打不贏的、閉門不見的按不下去，本來就不在候選裡）。內傷走不動的不打，排在勝算之前（勝算是四十場模擬）；有打擊軍令點名他時五五波也去打（計畫 T6；豪強分屬兩軍照依附那一軍）。"""
    from tianxia import bot_policy as bp  # noqa: PLC0415  過渡：待搬（假人的分數與挑法還在舊模組）

    if bp._crippled(game):
        return None
    odds = game.challenge_odds(fid)
    if orders.strike_on(game.state, game.content, game._side(), fid):
        return bp.ORDER_SCORE + bp.CHALLENGE_SCORE if odds in bp.STRIKE_ODDS else None
    return bp.CHALLENGE_SCORE if odds in bp.CHALLENGE_ODDS else None
