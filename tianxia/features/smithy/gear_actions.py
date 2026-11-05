"""裝備庫那一列的修與淬煉（全部拆包第 41 批；鐵匠鋪與合成流程 3.4）：走修練頁那條路（/api/menxia/repair_item、temper_item），不受店裡選單只列 8 顆的限制。
原本 Game 上的 3 個方法，Game 留 repair_item、temper_item 兩個一行委派給 server 與測試。計畫 docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md 1.1。
第一個參數 ctx 是 Game。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import armor  # 共用規則層
from tianxia import weapons  # 共用規則層
from tianxia import equipment  # 共用規則層
from tianxia import journal  # 核心
from tianxia.journal import Draft  # 核心

from . import smithing
from . import trade_actions

if TYPE_CHECKING:
    from tianxia.engine import Game


def repair_item(ctx: Game, item_id: str) -> list[str]:
    """裝備庫那一列的「修」（鐵匠鋪與合成流程 3.4；MENXIA_ACTIONS["repair_item"]，id 是「兵:N」「甲:N」）：見 _gear_work。"""
    return gear_work(ctx, str(item_id), "repair")


def temper_item(ctx: Game, item_id: str) -> list[str]:
    """裝備庫那一列的「淬煉」（鐵匠鋪與合成流程 3.4；MENXIA_ACTIONS["temper_item"]）：見 _gear_work。"""
    return gear_work(ctx, str(item_id), "temper")


def gear_work(ctx: Game, item_id: str, what: str) -> list[str]:
    """修或淬煉裝備庫裡（或身上）的一件（what 是 repair 或 temper）：跟身上那件同一套規則（weapons／armor.repair、smithing.temper 的 item_id：
    工錢、素材〔淬煉自動挑最便宜的一階〕、淬煉上限、修回滿），做完那一件還在原來的地方、不換上。走修練頁那條路（/api/menxia/…），
    不受店裡選單只列 8 顆的限制；擋法同 smith_forge／_trade_open（鐵匠鋪開著、那一串是眼前的選單：休季、決戰開打時拒，不收錢）。
    花了錢或料之後照 smith_upgrade 的路：掌櫃那一句換成這一下的（_shop_after：修、淬煉、被拒的原因）、擲鐵匠順口（_smith_clue，跟選單上
    smith:repair／temper 一樣只在真的花了錢或料之後）、寫一則「鐵匠鋪」江湖紀錄；被拒絕的什麼都不動、不擲、不寫。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not trade_actions.trade_open(ctx, True):
        return ctx._log([equipment.NOT_NOW])
    p.shop_clue = ""
    slot = next((sl for sl in equipment.DISMANTLABLE if equipment.target(p, sl, item_id) is not None), None)
    if slot is None:
        ctx._shop_after(equipment.RACK_MISSING, what)
        return ctx._log([f"（{equipment.RACK_MISSING}。）"])
    gear = armor if slot == "armor" else weapons
    problem = gear.repair_problem(s, c, item_id) if what == "repair" else smithing.temper_problem(s, c, slot, item_id)
    ctx._shop_after(problem, what)
    silver_before, mats_before = p.stats.get("silver", 0), sum(p.materials.values())
    msgs = gear.repair(s, c, item_id) if what == "repair" else smithing.temper(s, c, slot, item_id)
    if problem is not None:
        return ctx._log(msgs)
    if p.stats.get("silver", 0) < silver_before or sum(p.materials.values()) < mats_before:
        clue = ctx._smith_clue(paid=p.stats.get("silver", 0) < silver_before)
        if clue:
            p.shop_clue = clue[0]
        msgs = msgs + clue
    journal.add_entry(s, Draft(weapons.SMITH).entry(s.world.time, msgs))
    ctx._save_season()
    return ctx._log(msgs)
