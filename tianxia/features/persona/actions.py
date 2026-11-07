"""人物性子跟 Game 打交道的那一半：同步時替全服結算到今天、寫勸過的人的行狀。"""
from __future__ import annotations

from tianxia.core import annal_base as annals  # 核心（行狀記一筆，第 29 批之二）

from . import rules


def on_sync(ctx) -> None:
    """結算到今天（這一天第一個同步的人替全服算）：算了就把共用賽季存回去（輪詢只存角色，不存會被下一個人重算一次）。
    再替自己記勸成的行狀（行狀在角色存檔裡，照一般同步存）。"""
    s, c = ctx.state, ctx.content
    day = s.world.persona_day
    rules.settle(s, c)
    if s.world.persona_day != day:
        ctx._save_season()
    for entry, line in rules.annals_due(s, c):
        annals.note(s, c, annals.STANCE, line, 2, figure=entry.who, time=entry.at)
