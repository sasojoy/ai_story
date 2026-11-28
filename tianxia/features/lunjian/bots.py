"""假人看到門派論劍的選項怎麼按（開發規範手冊 3.8）：拜了門的那幾位照名號雜湊有 bot_sign_share 會報名（每週重擲），報過了不再更新分身；
贏來的素材、禮匣有就開、有就挑（挑哪一類照選項先後）。"""
from __future__ import annotations

from tianxia.core.option import Option

from . import actions, rules

SIGN_SCORE = 10.0  # 低過軍令與懸賞
LOOT_SCORE = 30.0


def wants(ctx) -> bool:
    """這一位這一週報不報（照名號＋季＋週雜湊）。"""
    share = float(ctx.content.config.lunjian.bot_sign_share)
    return rules.roll("假報名", ctx.state.player.name, actions._season(ctx), actions._week(ctx)).random() < share


def idle(ctx, option: Option) -> bool:
    """按了也白按的那幾顆：報過了的「更新分身」、這一週擲到不報的「報名」。"""
    if option.id != "lunjian:sign":
        return False
    return actions.signed(ctx) or not wants(ctx)


def score(ctx, option: Option) -> float | None:
    if not option.enabled:
        return None
    arg = option.id.partition(":")[2]
    if arg == "sign":
        return None if idle(ctx, option) else SIGN_SCORE
    if arg.startswith("claim:") or arg in ("open", "open_top"):
        return LOOT_SCORE
    return None
