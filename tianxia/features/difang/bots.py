"""假人看到地方大事的選項怎麼按（開發規範手冊 3.8）：照公開行動出力（設計稿「假人照公開行動補位、看不出來，也不寫字」）。
第一幕不用按（探索、打贏本來就算）；第二幕挑一個做法、第三幕上前，都是一人一次（一天一次），按過就灰掉，不會卡住整季的推進。"""
from __future__ import annotations

from tianxia.core.option import Option

WAY_SCORE = 12.0  # 路過這一區就出個手（低過軍令與懸賞）
STRIKE_SCORE = 12.0
CLAIM_SCORE = 30.0  # 謝禮：有就領（挑哪一份照選項先後，分數一樣取第一顆）


def score(option: Option) -> float | None:
    if not option.enabled:
        return None
    arg = option.id.partition(":")[2]
    if arg.startswith("claim:"):
        return CLAIM_SCORE
    return WAY_SCORE if arg.startswith("way:") else STRIKE_SCORE if arg == "strike" else None
