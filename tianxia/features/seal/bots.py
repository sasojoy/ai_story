"""假人看到玉璽選項怎麼按（開發規範手冊 3.8；全部拆包第 28 批：原本 bot_policy.score 的 seal 那一段照抄）。

奪璽單挑假人一律被代打（玉璽碎片設計 14.1），選單上的 seal: 招就算出現也不按；在不在場只看 last_seen，假人永遠不記。
"""
from __future__ import annotations

from tianxia.core.option import Option


def score(option: Option) -> float | None:
    """None＝假人不按（seal: 一律不按）。"""
    return None
