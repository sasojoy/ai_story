"""屯糧練兵的動作（功能包 tianxia/features/stamina_plays/；原本是 Game 上的 _works_act，開發規範手冊 3.2）。ctx 是 Game（第一階）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import calendar, wins
from tianxia.rules import season_one

from . import works_rules

if TYPE_CHECKING:
    from tianxia.engine import Game


def act(ctx: Game, arg: str) -> list[str]:
    """屯糧練兵（works:stockpile）：重驗、扣體力、記進這一季；第一季規則開著時記一點貢獻（同捐軍備的寫法）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if arg == "stockpile":
        side = works_rules.stock_spot(s, c)
        cfg = c.config.stockpile
        if side is None or p.stamina < cfg.stamina:
            return ["（此刻無法這麼做。）"]
        p.stamina -= cfg.stamina
        n = works_rules.stockpile(s, side)
        msgs = [works_rules.STOCK_DONE.format(side=c.scenario.faction_name(side, side), n=n)]
        cost = cfg.stamina
    else:
        return ["（此刻無法這麼做。）"]
    if ctx._draft is not None:
        ctx._draft.changes.append(f"體力 -{cost}")
    if p.faction is not None and season_one(c, s.world):
        contrib = c.config.contrib_per_push
        wins.credit(p, c, s.world, calendar.point(s.world.time, c, s.world).week, contrib)
        msgs.append(f"貢獻 +{contrib}")
    return msgs
