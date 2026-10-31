"""假人看到酒肆的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 tavern 那一段，主動搬六包第 10 批搬來）。
酒肆裡的打聽由 bot_policy.take_turn 的 _tavern 那一步另外做（進去、問一件、出門；TAVERN_CHANCE 照舊在 bot_policy）；
萬一停在酒肆的選單上，只按「出酒肆」。"""
from __future__ import annotations

from tianxia.core.option import Option


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    return 0.0 if option.id.partition(":")[2] == "back" else None
