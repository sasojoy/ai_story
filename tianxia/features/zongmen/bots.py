"""假人的拜入：走到一門的山門，照「名號｜門派」擲一次，合得來的就拜（同一個假人對同一門永遠一樣，每一輪重看不改主意）；不叛出。
山門前同門獻上來的一式，照「名號｜那一式」擲，一半的假人肯試練（不獻式、不學式：那兩樣在俠客頁上）。
畫面上看不出誰是假人。"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from tianxia.characters import name_key
from tianxia.core.option import Option

if TYPE_CHECKING:
    from tianxia.engine import Game

JOIN_SCORE = 25.0  # 不花體力，低過軍令與懸賞
JOIN_SHARE = 0.4  # 走到山門的假人有多少會拜
TRY_SCORE = 20.0  # 山門前同門獻的一式：有一半的假人肯花心得試練
TRY_SHARE = 0.5


def _roll(name: str, sect_id: str) -> float:
    digest = hashlib.sha256(f"zongmen|{name_key(name)}|{sect_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def score(ctx: Game, option: Option) -> float | None:
    verb, _, rest = option.id.partition(":")[2].partition(":")
    if verb == "join":
        return JOIN_SCORE if _roll(ctx.state.player.name, rest) < JOIN_SHARE else None
    if verb == "try" and option.enabled:
        return TRY_SCORE if _roll(ctx.state.player.name, f"try|{rest}") < TRY_SHARE else None
    return None
