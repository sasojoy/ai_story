"""修練包的動作（全部拆包第 23 批）。ctx 就是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的。

- 拜師學藝（learn:）：原本 Game.choose 的 learn 那一支、Game._action_title 的那一格。
"""
from __future__ import annotations

from tianxia import library


# ── 拜師學藝（learn:；choose 掛鉤，__init__.py）──


def learn_title(ctx, skill_id: str) -> str:
    """這一下江湖紀錄的標題（原本 Game._action_title 的 learn 那一格）。"""
    return f"學藝・{ctx.content.skills[skill_id].name}"


def learn(ctx, skill_id: str) -> list[str]:
    """學一門（原本 Game.choose 的 learn 那一支）：共用規則層的 library.learn。"""
    return library.learn(ctx.state, ctx.content, skill_id)
