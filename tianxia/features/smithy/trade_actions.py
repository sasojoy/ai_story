"""鐵匠鋪的收購與升階（全部拆包第 41 批；素材與經濟設計第四、五節）：選單的 smith:sell／upgrade 與店面的 smith_sell／smith_upgrade 共用。
原本 Game 上的 5 個方法，Game 留 smith_sell、smith_upgrade 兩個一行委派給 server、整季機器人與假人（bot.trade_at_smith）、測試。
計畫 docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md 1.1。第一個參數 ctx 是 Game。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import weapons  # 共用規則層
from tianxia import equipment  # 共用規則層
from tianxia import economy  # 共用規則層
from tianxia import journal  # 核心
from tianxia.journal import Draft  # 核心

if TYPE_CHECKING:
    from tianxia.engine import Game


def trade_sell(ctx: Game, mid: str, count: int) -> list[str]:
    """鐵匠鋪收購（素材與經濟設計第五節；選單的 smith:sell 與店面的 smith_sell 共用）：economy.sell，掌櫃那一句照這一下的擋法。"""
    s, c = ctx.state, ctx.content
    if not c.config.economy.sell:
        return [equipment.NOT_NOW]
    material = c.materials.get(mid)
    dark = material is not None and economy.black_market(s, c, material.tier)  # 名聲 5.2：掌櫃換黑市那一句
    ctx._shop_after(economy.sell_problem(s, c, mid, count), "black_market" if dark else "sell")
    return economy.sell(s, c, mid, count)


def trade_upgrade(ctx: Game, attribute: str, tier: int) -> list[str]:
    """鐵匠鋪升階（素材與經濟設計第四節；選單的 smith:upgrade 與店面的 smith_upgrade 共用）：economy.upgrade，「一天」照回體丹的換日。"""
    s, c = ctx.state, ctx.content
    if not c.config.economy.upgrade:
        return [equipment.NOT_NOW]
    day = ctx._pill_day()
    ctx._shop_after(economy.upgrade_problem(s, c, attribute, tier, day), "upgrade")
    return economy.upgrade(s, c, attribute, tier, day)


def trade_open(ctx: Game, switch: bool) -> bool:
    """店面的素材買賣按得下去嗎：這一樣的開關開著、鐵匠鋪開著而且那一串是眼前的選單（同 smith_forge）。"""
    s, c = ctx.state, ctx.content
    return switch and s.player.picking_smith and equipment.smith_open(s, c) and ctx._shop_live()


def smith_sell(ctx: Game, mid: str, count: int = 1) -> list[str]:
    """店面的收購（素材與經濟設計第五節；MAIN_ACTIONS["smith_sell"]）：一次賣 count 個。賣成了寫一則「鐵匠鋪」紀錄；
    被拒絕的不動背包銀兩、不寫紀錄，掌櫃那一句換成原因。收購是鐵匠付錢，不擲鐵匠順口。"""
    s, c = ctx.state, ctx.content
    if not trade_open(ctx, c.config.economy.sell):
        return ctx._log([equipment.NOT_NOW])
    s.player.shop_clue = ""
    problem = economy.sell_problem(s, c, str(mid), count)
    msgs = trade_sell(ctx, str(mid), count)
    if problem is None:
        journal.add_entry(s, Draft(weapons.SMITH).entry(s.world.time, msgs))
        ctx._save_season()
    return ctx._log(msgs)


def smith_upgrade(ctx: Game, attribute: str, tier: int) -> list[str]:
    """店面的升階（素材與經濟設計第四節；MAIN_ACTIONS["smith_upgrade"]）：換一個。換成了寫一則「鐵匠鋪」紀錄、照舊擲鐵匠順口
    （花了銀兩與素材，同 _smith）；被拒絕的什麼都不動、不寫紀錄。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not trade_open(ctx, c.config.economy.upgrade):
        return ctx._log([equipment.NOT_NOW])
    p.shop_clue = ""
    problem = economy.upgrade_problem(s, c, str(attribute), int(tier), ctx._pill_day())
    msgs = trade_upgrade(ctx, str(attribute), int(tier))
    if problem is not None:
        return ctx._log(msgs)
    clue = ctx._smith_clue(paid=True)
    if clue:
        p.shop_clue = clue[0]
    msgs = msgs + clue
    journal.add_entry(s, Draft(weapons.SMITH).entry(s.world.time, msgs))
    ctx._save_season()
    return ctx._log(msgs)
