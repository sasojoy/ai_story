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


def smith_upgrade(ctx: Game, attribute: str, tier: int, count: int = 1) -> list[str]:
    """店面的升階（素材與經濟設計第四節；MAIN_ACTIONS["smith_upgrade"]）：換一個；count 大於 1 而且一次熬到底開著
    （Config.economy.upgrade_batch）時連換到夠（economy.upgrade_many，夾在 upgrade_max）。換成了寫一則「鐵匠鋪」紀錄、照舊擲一次
    鐵匠順口（花了銀兩與素材，同 _smith；連換也只擲一次）；被拒絕的什麼都不動、不寫紀錄。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not trade_open(ctx, c.config.economy.upgrade):
        return ctx._log([equipment.NOT_NOW])
    p.shop_clue = ""
    problem = economy.upgrade_problem(s, c, str(attribute), int(tier), ctx._pill_day())
    if count > 1 and c.config.economy.upgrade_batch and problem is None:
        msgs = economy.upgrade_many(s, c, str(attribute), int(tier), ctx._pill_day(), int(count))
        ctx._shop_after(None, "upgrade")
    else:
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


LEFTOVER_TITLE = "鐵匠鋪"  # 待 joy 潤：換季那一則紀錄的標題
LEFTOVER_LINE = "上一季沒用完的素材（{items}），鐵匠照價收了，折成 {silver} 兩給你當盤纏。"  # 待 joy 潤
LEFTOVER_CAPPED = "上一季沒用完的素材（{items}），鐵匠收了，最多只肯折 {silver} 兩給你當盤纏。"  # 待 joy 潤：到了 leftover_cap


def leftover_value(content, old) -> tuple[int, int]:
    """上一季背包裡的素材折多少（Config.economy.leftover_silver：階 → 一個幾兩；不在表上的階不算）：回（折了幾兩〔夾在 leftover_cap〕, 算了幾個）。"""
    econ = content.config.economy
    prices = {int(k): v for k, v in econ.leftover_silver.items()}
    total = count = 0
    for mid, n in old.player.materials.items():
        material = content.materials.get(mid)
        if material is None or n <= 0 or prices.get(material.tier, 0) <= 0:
            continue
        total += prices[material.tier] * n
        count += n
    return (min(total, econ.leftover_cap) if econ.leftover_cap else total), count


def leftover(ctx: Game, old) -> list[str]:
    """開季那一刻（SmithyFeature.on_season_start；新的存檔已經接上）：上一季背包裡的素材照 leftover_value 折成銀兩加進新角色、寫一則紀錄。
    表是空的（測試內容、舊設定）、上一季背包是空的都什麼都不做。素材本來就不跨季，這裡只是不讓它白白不見。"""
    c = ctx.content
    silver, count = leftover_value(c, old)
    if silver <= 0:
        return []
    p = ctx.state.player
    p.stats["silver"] = p.stats.get("silver", 0) + silver
    by_tier: dict[int, int] = {}
    for mid, n in old.player.materials.items():
        if mid in c.materials and n > 0:
            by_tier[c.materials[mid].tier] = by_tier.get(c.materials[mid].tier, 0) + n
    items = "、".join(f"{TIER_WORDS.get(t, t)} {n} 個" for t, n in sorted(by_tier.items()))
    econ = c.config.economy
    full = sum(int(v) * by_tier.get(int(k), 0) for k, v in econ.leftover_silver.items())
    line = (LEFTOVER_CAPPED if econ.leftover_cap and full > econ.leftover_cap else LEFTOVER_LINE).format(items=items, silver=silver)
    msgs = [line, f"銀兩 +{silver}"]
    ctx._write(LEFTOVER_TITLE, msgs)
    return msgs


TIER_WORDS = {1: "一階", 2: "二階", 3: "三階", 4: "四階"}
