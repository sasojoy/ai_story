"""假人的馴野馬：走到有野馬群的地方、身上沒有良駒以上的馬，照「名號｜地點」擲一次，一半的人肯花體力馴（同一個假人對同一處永遠一樣）。
奪馬、論功賜馬是打贏就有，假人照真人一樣拿，不另寫。畫面上看不出誰是假人。"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from tianxia import mounts
from tianxia.characters import name_key
from tianxia.core.option import Option

if TYPE_CHECKING:
    from tianxia.engine import Game

TAME_SCORE = 8.0  # 同馬市（bot_policy.MARKET_SCORE）
TAME_SHARE = 0.5


def _roll(name: str, loc_id: str) -> float:
    digest = hashlib.sha256(f"horses|{name_key(name)}|{loc_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def score(ctx: Game, option: Option) -> float | None:
    if option.id != "horses:tame" or not option.enabled:
        return None
    p = ctx.state.player
    riding = mounts.riding(ctx.state, ctx.content)
    if riding is not None and riding.tier >= 2:
        return None
    return TAME_SCORE if _roll(p.name, p.location) < TAME_SHARE else None
