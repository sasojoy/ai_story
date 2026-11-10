"""假人收到結義邀請的回法（同名帖：等一下才回，有時答應、有時婉拒、有時不理等它作廢）。假人不主動邀人。
擲骰照「名號｜邀請編號」：同一張、同一個假人永遠一樣，每一輪重看不會改主意。畫面上看不出誰是假人。"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from tianxia.characters import name_key
from tianxia.core.option import Option

from . import actions, rules

if TYPE_CHECKING:
    from tianxia.engine import Game

ANSWER_SCORE = 30.0  # 要回的那一顆（不花體力，低過軍令與懸賞）


def _roll(name: str, offer_id: str) -> float:
    digest = hashlib.sha256(f"jieyi|{name_key(name)}|{offer_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def score(ctx: Game, option: Option) -> float | None:
    verb, _, offer_id = option.id.partition(":")[2].partition(":")
    if verb == "gather":  # 義聚（第二批）：體力缺得夠多才按（同真人：滿的時候按了白按）
        bk = actions.book(ctx)
        g = actions.gather_view(ctx, bk) if bk is not None else None
        short = ctx.content.config.stamina_max - ctx.state.player.stamina
        return ANSWER_SCORE if g and g["ready"] and short >= g["n"] else None
    bk = actions.book(ctx)
    offer = rules.find(bk, offer_id, ctx.now) if bk is not None else None
    if offer is None:
        return None
    cfg = ctx.content.config.jieyi
    if ctx.now - offer.sent_at < cfg.bot_reply_seconds:
        return None
    roll = _roll(ctx.state.player.name, offer_id)
    want = "yes" if roll < cfg.bot_accept_share else "no" if roll < cfg.bot_accept_share + cfg.bot_reject_share else None
    return ANSWER_SCORE if verb == want else None
