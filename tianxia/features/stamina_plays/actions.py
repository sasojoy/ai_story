"""體力玩法的選項（功能包 tianxia/features/stamina_plays/；原本是 Game._stamina_play_options 的前半，開發規範手冊 3.2）。
ctx 是 Game（第一階）。選單順序是「設伏／收伏 → 屯糧 → 護衛 → 功能包的選項 → 盤算」：護衛以後的留在 Game._stamina_play_options（接縫），
這裡只給前兩段，所以不能改成 Feature.options 登記（會排進 FEATURES 的順序，跑到護衛之後）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import roster
from tianxia.core.option import Option
from tianxia.core.travel_base import TravelBlock  # 核心（動身被擋那一句的型別，core_seams）

from . import ambush_rules, works_rules

if TYPE_CHECKING:
    from tianxia.engine import Game


def options(ctx: Game) -> list[Option]:
    """「此地還能做」裡的體力玩法：守著埋伏時只有「收伏」；否則這裡設得了伏的每一段路一顆、屯糧一顆。
    劫不到人的（散人沒揭通緝、新手期）不畫設伏鈕。序章裡、休季沒有：那一道門在 Game._stamina_play_options（整串選單一起擋）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    opts: list[Option] = []
    if p.ambush is not None:
        to = c.locations[p.ambush.to].name
        opts.append(Option(id="ambush:lift", label=ambush_rules.LIFT_LABEL.format(to=to, until=ctx.stamp(p.ambush.until))))
    elif ambush_rules.on(c) and ambush_rules.has_prey(s, c) and not roster.raid_newbie(s, c):
        for to in ambush_rules.roads(s, c):
            label = ambush_rules.SET_LABEL.format(to=c.locations[to].name)
            opts.append(ctx._cost_option(f"ambush:set:{to}", label, c.config.ambush.stamina))
    stock = works_rules.stock_spot(s, c)
    if stock is not None:
        name = c.scenario.faction_name(stock, stock)
        label = works_rules.STOCK_LABEL.format(side=name, n=s.world.supply.get(stock, 0))
        opts.append(ctx._cost_option("works:stockpile", label, c.config.stockpile.stamina))
    return opts


def travel_block(state, content) -> TravelBlock | None:
    """block/ambush 那一格（core_seams，全部拆包第 56 批；原本在 atlas.travel_block，字一字不動）：設伏劫道，守著埋伏不能移動（沒有分身）；待 joy 潤。"""
    return TravelBlock("正守著埋伏，先收伏才能動身", to_jianghu=True) if state.player.ambush is not None else None
