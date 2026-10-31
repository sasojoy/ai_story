"""擂台形象的動作（功能包 tianxia/features/looks/）。ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import journal  # 核心（江湖紀錄）

from tianxia.state import JournalEntry

from . import rules

if TYPE_CHECKING:
    from tianxia.engine import Game

TITLE = "形象"  # 江湖紀錄的標題


def look_of(ctx: Game) -> str:
    """這個人上擂台穿哪一套（報名、更新分身、挑人那一刻記下來）：形象關著是預設；假人照名號挑；真人照自己換上的。"""
    if not rules.on(ctx.content):
        return rules.DEFAULT
    if ctx.state.player.bot:
        return rules.bot_look(ctx.content, ctx.state.player.name)
    wallet = ctx._wallet()
    return rules.DEFAULT if wallet is None else rules.worn(ctx.content, wallet, ctx._mall_owner())


def _shop(ctx: Game) -> dict[str, str]:
    """哪一套此刻在萬寶閣賣（look id → 商品 id）：照商品表裡寫了 look 的那幾件。"""
    return {item.look: item.id for item in ctx.content.mall.values() if item.look}


def view(ctx: Game) -> dict | None:
    wallet = ctx._wallet()
    if wallet is None or not rules.on(ctx.content):
        return None
    return rules.view(ctx.content, wallet, ctx._mall_owner(), _shop(ctx))


def wear(ctx: Game, look: str) -> list[str]:
    """換上一套（萬寶閣「形象」那一頁）；換了寫一則「形象」江湖紀錄。已經報名擂台的，分身下一次更新才換（同兵器）。"""
    wallet = ctx._wallet()
    if wallet is None or not rules.on(ctx.content):
        return ctx._log([rules.OFF])
    done, line = rules.wear(ctx.content, wallet, ctx._mall_owner(), look)
    if done:
        journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line]))
    return ctx._log([line])
