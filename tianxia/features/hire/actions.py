"""招募同伴的動作（功能包 tianxia/features/hire/）：五項屬性的季，在城裡的酒肆花銀兩招一般 NPC 同伴（刀客、槍手、弓手、醫者、謀士）。
ctx 是 Game；名下與全服唯一照核心的 roster（共用規則層），屬性與季章照 attrset。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import attrset, roster, team
from tianxia.core.option import Option

if TYPE_CHECKING:
    from tianxia.engine import Game

# 待 joy 潤
LABEL = "招募{kind}【{name}】（{desc}銀兩 {cost}）"
NO_SILVER = "（銀兩不夠：招一位要 {cost} 兩。）"
FULL = "（名下已有 {n} 位同伴，招不了更多人。）"
GONE = "（他剛剛跟別人走了。）"
JOINED = "付了 {cost} 兩銀子，{kind}【{name}】收拾行囊，跟你上路了。"
TITLE = "招募同伴"


def on(ctx: Game) -> bool:
    """五項屬性的季（蓋了章）、Config.hire 開著；開季時親衛隊長開著的季（WorldState.guard_on）不再招（親衛隊長取代酒肆招募，Joy 2026-11-10「全部做完一起上」）。"""
    w = ctx.state.world
    return ctx.content.config.hire.enabled and attrset.on(ctx.content, w) and not w.guard_on


def _type(ctx: Game, key: str):
    return next((t for t in ctx.content.config.hire.types if t.key == key), None)


def free_here(ctx: Game) -> list[str]:
    """此地酒肆每一型還沒有主的第一位（內容的順序）。"""
    s, c = ctx.state, ctx.content
    seen: set[str] = set()
    out = []
    for cid, ch in c.characters.items():
        if ch.hire_at == s.player.location and ch.hire_type not in seen and roster.owned_by(ctx.world, cid) is None:
            seen.add(ch.hire_type)
            out.append(cid)
    return out


def price(ctx: Game) -> int:
    """招募價：Config.hire.cost，五項屬性的季照魅力打折（attrset.charm「hire」：魅力高便宜、低的貴一點；企劃者 2026-11-04）。"""
    return max(1, round(ctx.content.config.hire.cost * (1 - attrset.charm(ctx.state, ctx.content, "hire"))))


def options(ctx: Game) -> list[Option]:
    if not on(ctx) or ctx.state.player.journey is not None:
        return []
    s, c = ctx.state, ctx.content
    cost = price(ctx)
    full = len(roster.owned_companions(ctx.world, s.player.name)) >= c.config.companions.max_owned
    poor = s.player.stats.get("silver", 0) < cost
    out = []
    for cid in free_here(ctx):
        ch = c.characters[cid]
        kind = _type(ctx, ch.hire_type)
        desc = f"{ch.desc.rstrip('。')}，" if ch.desc else ""
        out.append(Option(id=f"hire:{cid}", label=LABEL.format(kind=kind.name, name=ch.name, desc=desc, cost=cost),
                          enabled=not (full or poor)))
    return out


def act(ctx: Game, cid: str) -> list[str]:
    s, c, w = ctx.state, ctx.content, ctx.world
    ch = c.characters.get(cid)
    if not on(ctx) or ch is None or ch.hire_type is None or ch.hire_at != s.player.location:
        return ["（此刻無法這麼做。）"]
    cost = price(ctx)
    n = len(roster.owned_companions(w, s.player.name))
    if n >= c.config.companions.max_owned:
        return [FULL.format(n=n)]
    if s.player.stats.get("silver", 0) < cost:
        return [NO_SILVER.format(cost=cost)]
    if not w.try_recruit(cid, s.player.name, cap=c.config.companions.max_owned):
        return [GONE] if roster.owned_by(w, cid) is not None else [FULL.format(n=n)]
    s.player.stats["silver"] -= cost
    roster._seed_starting_skills(w, cid, ch)
    kind = _type(ctx, ch.hire_type)
    return [JOINED.format(cost=cost, kind=kind.name, name=ch.name)] + team.add_to_team(s, cid)
