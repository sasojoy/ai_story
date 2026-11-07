"""鐵匠鋪的開爐（全部拆包第 41 批）：開爐一次（一步一步單子的 forge-go 與店面的直接開爐共用）、店面打造頁的預覽、直接開爐、看火候。
原本 Game 上的 4 個方法，Game 留 smith_line、smith_forge、smith_furnace 三個一行委派給 server（MAIN_ACTIONS、/api/smith_line）與測試。
計畫 docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md 1.1。第一個參數 ctx 是 Game。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import weapons  # 共用規則層
from tianxia import equipment  # 共用規則層
from tianxia import silver  # 共用規則層
from tianxia import journal  # 核心
from tianxia.journal import Draft  # 核心
from tianxia import prologue as prologue_rules  # 共用規則層（序章）

from . import shop_view
from . import smithing
from . import trade_actions

if TYPE_CHECKING:
    from tianxia.engine import Game
    from tianxia.state import Equipment


def smith_forge_once(ctx: Game, kind: str, main: str, aux: str) -> tuple[Equipment | None, list[str], dict]:
    """開爐一次（一步一步單子的 forge-go 與店面的直接開爐共用）：防具的品質擲骰用自己的亂數（不動 Game.rng，FB-129；打造隱藏配方
    設計 9.3），兵器照舊用 Game.rng；不叫模型、一次做完（打造隱藏配方設計第八節）。打成了收起單子（同一顆連按兩下、兩個分頁，第二下
    已經不在選單上：Review Focus 1），掌櫃那一句照打出來的（品質、名器、神器）；被拒絕照原因。回（那一件, 訊息, report）。"""
    s, c = ctx.state, ctx.content
    problem = smithing.forge_problem(s, c, kind, main, aux)
    rng = smithing.own_rng(s, smithing.recipe_key(kind, main, aux)) if smithing.is_armor(kind) else ctx.rng
    report: dict = {}
    item, msgs = smithing.forge(s, c, ctx.world, kind, main, aux, rng=rng, report=report)
    if item is not None:
        s.player.smith_draft = None
        ctx._shop_say(shop_view.forged_key(item))
    else:
        ctx._shop_after(problem, "refused")
    return item, msgs, report


def smith_line(ctx: Game, kind: str, main: str | None = None, aux: str | None = None) -> dict:
    """店面打造頁爐裡放了什麼，這一爐會怎樣（shop_view.smith_line；/api/smith_line）。只讀。"""
    return shop_view.smith_line(ctx.state, ctx.content, ctx.world, str(kind), main or None, aux or None)


def smith_forge(ctx: Game, kind: str, main: str, aux: str) -> list[str]:
    """店面的直接開爐（店面獨立介面設計 2.3、6.3；MAIN_ACTIONS["smith_forge"]）：店開著（picking_smith、人在鐵匠鋪），
    smithing.forge_problem 整個重驗才打——打的是同一個 smithing.forge（隱藏配方、神器原品與仿品、首位發現、名望回饋、熟手次數都照現在），
    跟一步一步單子的開爐同一條（_smith_forge_once：防具自己的亂數、兵器 Game.rng），打完收起單子；鐵匠順口照擲（同 _smith）。
    一爐一則「打造」江湖紀錄（不併進上一則）；被拒絕的不收錢、不收料、不寫紀錄，掌櫃那一句換成原因。
    出爐卡給網頁：ctx.smith_result（shop_view.forged_card；被拒絕是 None）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    ctx.smith_result = None
    if not p.picking_smith or not equipment.smith_open(s, c) or not ctx._shop_live():
        return ctx._log([equipment.NOT_NOW])  # 鐵匠鋪那一串不在眼前的選單上（決戰開打、休季）：同一步一步的開爐，按不下去
    p.shop_clue = ""
    silver, mats = p.stats.get("silver", 0), sum(p.materials.values())
    item, msgs, report = smith_forge_once(ctx, str(kind), str(main), str(aux))
    if item is None:
        return ctx._log(msgs)
    if p.stats.get("silver", 0) < silver or sum(p.materials.values()) < mats:
        clue = ctx._smith_clue(paid=p.stats.get("silver", 0) < silver)
        if clue:
            p.shop_clue = clue[0]
        msgs = msgs + clue
    journal.add_entry(s, Draft(smithing.FORGE_TITLE).entry(s.world.time, msgs))
    ctx.smith_result = shop_view.forged_card(s, c, ctx.world, item, report)
    ctx._save_season()
    return ctx._log(msgs)


def smith_furnace(ctx: Game) -> list[str]:
    """打造頁爐火上的「看火候」（鐵匠鋪與合成流程 3.2；MAIN_ACTIONS["smith_furnace"]）：叫跟打點頁、選單 act:furnace 同一支 silver.furnace
    （價錢、一天一次、序章不能用、下一爐用掉、只管打造不管煉製，一字不改），所以打點帳簿那一格讀的是同一個 furnace_ready。
    擋法同 smith_forge／_trade_open：銀兩出口開著（silver.on）、店開著而且那一串是眼前的選單（休季、決戰開打時選單上沒有它，拒）——
    不直接送 act:furnace，因為店開著時選單是店裡那一串，act:furnace 不在上面，Game.choose 會拒。看成了寫一則「鐵匠鋪」紀錄（同 smith_upgrade）；
    被拒絕的不收錢、不寫紀錄。不擲鐵匠順口、不動掌櫃那一句（走打點那條路本來就不擲）。"""
    s, c = ctx.state, ctx.content
    if not trade_actions.trade_open(ctx, silver.on(c, s.world)):
        return ctx._log([equipment.NOT_NOW])
    day, prologue = ctx._pill_day(), prologue_rules.active(s, c)
    problem = silver.furnace_problem(s, c, day, prologue)
    msgs = silver.furnace(s, c, day, prologue)
    if problem is None:
        journal.add_entry(s, Draft(weapons.SMITH).entry(s.world.time, msgs))
        ctx._save_season()
    return ctx._log(msgs)
