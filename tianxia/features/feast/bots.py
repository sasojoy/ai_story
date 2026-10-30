"""假人看到宴客的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 feast 那一段）。
路過擺著宴的地方就入席，入了席挑一句固定的敬酒詞（不寫自己的，同放手一搏）；離席不按。"""
from __future__ import annotations

from tianxia.core.option import Option

FEAST_SCORE = 8.0  # 入席：不花體力，路過就坐一下（低過軍令與懸賞）
FEAST_TOAST_SCORE = 50.0  # 坐下了就敬酒（不然卡在宴席的選單上）


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    arg = option.id.partition(":")[2]
    return None if arg == "leave" else FEAST_TOAST_SCORE if arg.startswith("toast:") else FEAST_SCORE
