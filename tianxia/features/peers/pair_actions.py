"""同一對人這個遊戲日的帳（切磋、贈物、論武各一本）與贈物一天的次數（原本 Game 上的 _spar_pair、_pair_left、_pair_tick、gifts_left、
gift_day_left、gift_day_tick；全部拆包第 37 批搬進來，行為一個字不變）。切磋、論武的帳還是它們自己（第 38 批）經 Game 的委派叫 pair_left、pair_tick。
"""
from __future__ import annotations

from tianxia.characters import name_key
from tianxia.rules import game_day


def pair_key(ctx, other: str) -> str:
    """同一對人的帳本鍵：兩個名號（不分大小寫）排序後接起來，誰發的都記在同一本。"""
    return "|".join(sorted((name_key(ctx.state.player.name), name_key(other))))


def pair_left(ctx, tally: dict[str, list[int]], cap: int, other: str) -> int:
    """這一對人這個遊戲日在這本帳上還剩幾次（切磋、贈物、論武各一本，都在這一季的 WorldState；帳記的是別的遊戲日就當沒用過）。"""
    day, count = tally.get(pair_key(ctx, other), (0, 0))
    used = count if day == game_day(ctx.content, ctx.state.world) else 0
    return max(0, cap - used)


def pair_tick(ctx, tally: dict[str, list[int]], other: str) -> None:
    """這一對人這個遊戲日在這本帳上記一次。呼叫端自己 _save_season。"""
    day, key = game_day(ctx.content, ctx.state.world), pair_key(ctx, other)
    last_day, count = tally.get(key, (0, 0))
    tally[key] = [day, (count if last_day == day else 0) + 1]


def gifts_left(ctx, other: str) -> int:
    """這一對人這個遊戲日還能贈物幾次（Config.gift_per_pair_day，不分誰送誰；FB-116）。"""
    return pair_left(ctx, ctx.state.world.gift_tally, ctx.content.config.gift_per_pair_day, other)


def gift_day_left(ctx) -> int:
    """今天（回體丹的換日）還能送幾次東西（Config.gift_per_day；0＝不限）。"""
    cap, p = ctx.content.config.gift_per_day, ctx.state.player
    if cap <= 0:
        return 1
    return max(0, cap - (p.gifts_today if p.gift_day == ctx._pill_day() else 0))


def gift_day_tick(ctx) -> None:
    p, day = ctx.state.player, ctx._pill_day()
    p.gifts_today = (p.gifts_today if p.gift_day == day else 0) + 1
    p.gift_day = day
