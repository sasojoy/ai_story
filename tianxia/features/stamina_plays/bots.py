"""假人看到體力玩法的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 ambush／works 那一段）。
設伏、屯糧由 take_turn 的 _stamina_play 做（護衛、犒軍、探望 aid: 同理），不交給打分數：這一包的選項假人在 score 裡一律不按。"""
from __future__ import annotations

from tianxia.core.option import Option


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按（ambush:、works:）。"""
    return None
