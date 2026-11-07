"""假人看到機緣、伏筆的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 `if kind == "opp": return None`，全部拆包第 34 批拿了
opp:、fs: 兩個前綴之後搬來）。

假人不做機緣（正式版乙一）：opp: 一律不按；fs:（伏筆的最後一步）原本沒有專門一行，走到 score 最後的 `return None`，結果一樣是不按。
整季機器人（bot.pick）在選項進分數之前就濾掉 fs:、opp:（這一包的 bot_always，第 60 批）與 talk:clue:、talk:opp:（人物情誼包的 bot_always）；
對話裡的 talk:opp:、talk:clue: 由人物情誼包的 bots.py 回 None。
第 2 階行動、接下糧車、應召的分數（原本 bot_policy.score 的 act: 那幾行）第 60 批搬來，Verb.bot 問。
"""
from __future__ import annotations

from tianxia.core.option import Option

RANK2_SCORE = 0.5  # 第 2 階行動（正式版乙一）：跟守勢行動一樣的底分（bot_policy.DUTY_SCORE 同一個數）；替軍令記功的加分是計畫戊的事
CONVOY_SCORE = 30.0  # 接下糧車：只在有護糧軍令的起點出現（bot_policy.ORDER_SCORE 同一個數）
SUMMONS_SCORE = 50.0  # 應召（計畫 T5）：只在召見的地點出現（bot_policy.SUMMONS_SCORE 同一個數）


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    return None
