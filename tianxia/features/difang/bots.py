"""假人看到地方大事的選項怎麼按（開發規範手冊 3.8）：照公開行動出力（設計稿「假人照公開行動補位、看不出來，也不寫字」）。
赴大事一天最多三次、第三幕一天一次，按滿就灰掉，不會卡住整季的推進；赴了就挑做法（不留一則懸著）。"""
from __future__ import annotations

from tianxia.core.option import Option

GO_SCORE = 12.0  # 路過這一區就出個手（低過軍令與懸賞）
PICK_SCORE = 40.0  # 赴了就挑一個做法（不擲的那一個也行：照選項先後取第一顆）
STRIKE_SCORE = 12.0
CLAIM_SCORE = 30.0  # 謝禮：有就領（挑哪一份照選項先後，分數一樣取第一顆）


def score(option: Option) -> float | None:
    if not option.enabled:
        return None
    arg = option.id.partition(":")[2]
    if arg.startswith("claim:"):
        return CLAIM_SCORE
    if arg.startswith("pick:"):
        return PICK_SCORE
    return GO_SCORE if arg == "go" else STRIKE_SCORE if arg.startswith("strike:") else None
