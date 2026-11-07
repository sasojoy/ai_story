"""銀兩出口（21 天季，正式季整合 6.5；tianxia/silver.py 是數字與字，這裡是選單與五樣）：自家大本營的捐銀兩、醫館的名師指點與買破境丹、
鐵匠鋪的看火候、此地談得上話的大勢人物每一位一顆打點門路，都收進「打點」那一間店（不花體力）。
原本 Game 上的 8 個方法（_silver_options、_bribe_targets、_silver_act、_close_dadian、_silver_bribe、_silver_furnace、_silver_mentor、
_silver_donate；全部拆包第 43 批搬進來，行為一個字不變）；Game 留一行委派。`_at_clinic_town`（歸核心）留在 Game，包裡經 ctx 叫。
"""
from __future__ import annotations

from tianxia import economy, equipment, materials, prologue as prologue_rules, silver
from tianxia import figures  # 共用規則層（大勢人物：此地在場的人物；第 40 批收進）
from tianxia.core.option import Option
from tianxia.core.travel_base import TravelBlock  # 核心（動身被擋那一句的型別，core_seams）

from .donate_actions import credit


def silver_options(ctx) -> list[Option]:
    """銀兩出口的幾顆（silver.on 才有）：自家大本營的捐銀兩、醫館的名師指點與買破境丹、鐵匠鋪的看火候、此地談得上話的大勢人物
    每一位一顆打點門路。做不了的灰掉寫原因。"""
    s, c = ctx.state, ctx.content
    if not silver.on(c, s.world):
        return []
    opts: list[Option] = []
    if ctx._at_own_base():
        day, room = ctx._pill_day(), economy.donate_room(s, c, ctx._pill_day())
        problem = silver.donate_problem(s, c, day, room, c.config.economy.donate_daily_cap)
        if problem is None:
            amount = silver.donate_amount(s, c, day, room)
            opts.append(Option(id="act:silver_donate", label=silver.DONATE_LABEL.format(
                silver=amount, points=amount // c.config.silver_outlets.donate_per_point)))
        else:
            opts.append(Option(id="act:silver_donate", label=silver.DONATE_REFUSED.format(problem=problem), enabled=False))
    if ctx._at_clinic_town():
        cfg = c.config.silver_outlets
        problem = silver.mentor_problem(s, c, ctx._pill_day())
        opts.append(Option(id="act:mentor", enabled=problem is None, label=silver.MENTOR_REFUSED.format(problem=problem)
                           if problem else silver.MENTOR_LABEL.format(silver=cfg.mentor_silver, bonus=cfg.mentor_bonus)))
        problem, pill = silver.legend_problem(s, c), c.config.legend_item_name
        opts.append(Option(id="act:buy_legend", enabled=problem is None, label=silver.LEGEND_REFUSED.format(name=pill, problem=problem)
                           if problem else silver.LEGEND_LABEL.format(name=pill, silver=cfg.legend_silver, left=silver.legend_left(s, c))))
    for fid in bribe_targets(ctx):
        name, problem = c.figures[fid].name, silver.bribe_problem(s, c, fid, ctx._pill_day())
        opts.append(Option(id=f"act:bribe:{fid}", enabled=problem is None, label=silver.BRIBE_REFUSED.format(name=name, problem=problem)
                           if problem else silver.BRIBE_LABEL.format(name=name, silver=c.config.silver_outlets.bribe_silver,
                                                                     gain=silver.bribe_gain(s, c, fid))))
    if equipment.smith_open(s, c):
        problem = silver.furnace_problem(s, c, ctx._pill_day(), prologue_rules.active(s, c))
        opts.append(Option(id="act:furnace", enabled=problem is None, label=silver.FURNACE_REFUSED.format(problem=problem)
                           if problem else silver.FURNACE_LABEL.format(silver=c.config.silver_outlets.furnace_silver)))
    return opts


def bribe_targets(ctx) -> list[str]:
    """此地打點得了門路的大勢人物（6.5）：在場、談得上話（有對話人物）；不在路上。"""
    s, c = ctx.state, ctx.content
    if s.player.journey is not None:
        return []
    return [fid for fid in figures.present_at(s, c, s.player.location) if c.figures[fid].character is not None]


def silver_act(ctx, what: str) -> list[str]:
    """銀兩出口的五樣（act:silver_donate、mentor、furnace、buy_legend、bribe:<人物>）。"""
    if what == "silver_donate":
        return silver_donate(ctx)
    if what == "mentor":
        return mentor(ctx)
    if what == "furnace":
        return furnace(ctx)
    if what.startswith("bribe:"):
        return bribe(ctx, what.partition(":")[2])
    if not (silver.on(ctx.content, ctx.state.world) and ctx._at_clinic_town()):
        return [equipment.NOT_NOW]
    return silver.buy_legend(ctx.state, ctx.content)


def close_dadian(ctx) -> None:
    """收起「打點」那一間店與掮客那一句（同 economy.close_donate）。"""
    p = ctx.state.player
    p.picking_dadian = False
    p.shop_line, p.shop_clue, p.shop_hold = "", "", ""


def bribe(ctx, fid: str) -> list[str]:
    s, c = ctx.state, ctx.content
    if not (silver.on(c, s.world) and fid in bribe_targets(ctx)):
        return [equipment.NOT_NOW]
    return silver.bribe(s, c, fid, ctx._pill_day())


def furnace(ctx) -> list[str]:
    s, c = ctx.state, ctx.content
    if not (silver.on(c, s.world) and equipment.smith_open(s, c)):
        return [equipment.NOT_NOW]
    return silver.furnace(s, c, ctx._pill_day(), prologue_rules.active(s, c))


def mentor(ctx) -> list[str]:
    s, c = ctx.state, ctx.content
    if not (silver.on(c, s.world) and ctx._at_clinic_town()):
        return [equipment.NOT_NOW]
    return silver.mentor(s, c, ctx._pill_day())


def silver_donate(ctx) -> list[str]:
    """捐銀兩進軍需帳（6.5）：每 donate_per_point 兩記 1 點、捐成糧秣（慢），跟捐素材共用每天的點數上限；寫一則「捐銀兩」紀錄。"""
    s, c = ctx.state, ctx.content
    if not (silver.on(c, s.world) and ctx._at_own_base()):
        return [equipment.NOT_NOW]
    day = ctx._pill_day()
    room = economy.donate_room(s, c, day)
    problem = silver.donate_problem(s, c, day, room, c.config.economy.donate_daily_cap)
    if problem is not None:
        return [f"（{problem}。）"]
    amount, points = silver.take_donation(s, c, day, room)
    faction = c.scenario.faction(ctx._side())
    msgs = [silver.DONATE_DONE.format(silver=amount, faction=faction.name), f"銀兩 -{amount}"]
    msgs += credit(ctx, {materials.GRAIN_ATTRIBUTE: points})
    ctx._save_season()
    return msgs


def here_cell(ctx, loc, cost, odds) -> list[Option]:
    """here/dadian 那一格（core_seams，全部拆包第 56 批；原本在 Game._everyday_options）：銀兩出口（21 天季，正式季整合 6.5）：五樣收進「打點」那一間店（第 9 批畫面乙），不花體力。"""
    return [Option(id="act:dadian", label=silver.SHOP)] if silver_options(ctx) else []


def travel_block(state, content) -> TravelBlock | None:
    """block/outlets 那一格（core_seams，全部拆包第 56 批；原本在 atlas.travel_block，字與先後一字不動；待 joy 潤）：打點（21 天季的銀兩出口）、大本營的捐軍備（素材與經濟設計第六節）。"""
    p = state.player
    if p.picking_dadian:
        return TravelBlock("還在茶樓雅間裡，先離開才能安排前往", to_jianghu=True)
    if p.picking_donate:
        return TravelBlock("還在軍需官帳前，先離開才能安排前往", to_jianghu=True)
    return None
