"""假人看到鐵匠鋪的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 smith 那一段與 bot_policy._smith_want，全部拆包第 41 批拿了
smith: 前綴之後搬來，照決戰包）。bot_policy 照舊留著 _smith_want（一行，叫這裡的 want）與 SMITH_SCORE、FORGE_SCORE 這幾個名字（tests/bots/test_bot_policy.py、
tests/gear 直接讀；數同一個）。`act:smith`（進鐵匠鋪）的分數第 60 批搬來（enter，Verb.bot 問）。

整季機器人與假人共用的 smith_want、forge_step、_forge_plans、forge_ready、FORGE_SILVER_RESERVE 第二輪第 89 批從 bot 搬來（bot 留 re-export，測試照舊讀那幾個名字）；
TIER3_WANT、TIER4_WANT、TRADE_SILVER_RESERVE、keep_book_names、trade_want、trade_at_smith、visit_smith 第 101 批從 bot 搬來，DIVINE_NAME_CHANCE、_name_originals 同一批從 bot_policy 搬來（舊名 re-export 同一批物件）。
素材留多少（trade_keep、TRADE_MOVES）捐軍備也讀，在共用層 bot_base，一律寫 `bot_base.X`。**模組層不准碰 engine 與假人殼**（bot、bot_policy 模組層 import 這個檔）。
"""
from __future__ import annotations

import random
from collections.abc import Callable
from typing import TYPE_CHECKING

from tianxia import armor, bot_base, economy, equipment, forge_secrets, four_tiers, team, weapons
from tianxia.core.option import Option

from . import smithing

if TYPE_CHECKING:
    from tianxia.engine import Game

SMITH_SCORE = 8.0  # 鐵匠鋪：跟揭懸賞一樣急，兵器配不上是白白少一截威力（bot_policy.SMITH_SCORE = BOUNTY_SCORE 同一個數）
FORGE_SCORE = SMITH_SCORE  # 人在城鎮、身上湊得出一爐又付得起（forge_ready）時進鐵匠鋪再多這麼多（FB-144；說明在 bot_policy.FORGE_SCORE，同一個數）
TIER3_WANT = 2  # 素材四階關著（舊規則）：那個屬性的三階少於這麼多才升三階（一把神器要兩個三階）
TIER4_WANT = 2  # 素材四階：那個屬性的四階少於這麼多才三換四（一件神器要主輔兩個四階，正式季整合 8.1）
TRADE_SILVER_RESERVE = 30  # 升階付完工錢至少還留幾兩（療傷用，同 MOUNT_SILVER_RESERVE）
DIVINE_NAME_CHANCE = 0.3  # 打出神器原品之後，每一輪按「沿用譜名」的機會（不在打出來那一下就定，照人的步調，同 answer_call）【預設】


def want(game) -> str | None:
    """此刻在鐵匠鋪最該按的那一顆：單子開著時只照 forge_step（下一步或「不打了」）；不然先照 smith_want（換、買、修，兵器防具兩頁），
    沒事再照 forge_step（打造與換上打出來的那把，打造第二批 PM 決定第 3 條）。都沒事是 None。不淬煉、不拆。"""
    if game.state.player.smith_draft is not None:
        return forge_step(game)
    return smith_want(game) or forge_step(game)


def enter(game) -> float | None:
    """act:smith（鐵匠鋪）：有要換、要買、要修、要打的才進去（不然只是開了又離開）；湊得出一爐又付得起再多 FORGE_SCORE。"""
    if not want(game):
        return None
    return SMITH_SCORE + (FORGE_SCORE if forge_ready(game) else 0.0)


def score(game, option: Option) -> float | None:
    """選項的分數；None＝假人不會按。鐵匠鋪上：照 want 按那一顆（換買修、打造與換上打出來的那把，含切頁），沒事就離開；不淬煉、不拆，萬一停在單子上只按「不打了」。"""
    arg = option.id.partition(":")[2]
    return SMITH_SCORE if option.id == want(game) else 0.0 if arg in ("back", "forge-cancel") else None


def smith_want(game: Game) -> str | None:
    """在鐵匠鋪最該按的那一顆（整季機器人與伺服器假人共用；兵器設計第六節、裝備四欄設計第九節）：兵器頁照 weapons.wanted（換、買、修），
    防具頁照 armor.wanted（換、買、修）。停在的那一頁有事先做；這一頁沒事、另一頁有事才回切頁那一顆（smith:page:<頁>），
    下一輪再回真正的動作——不會來回切。還沒進門時照進門會停的那一頁算（equipment.first_page）。打造、淬煉、拆解不在這裡
    （伺服器假人的打造與換上打出來的那把在 forge_step，bot_policy._smith_want 接在這之後；整季機器人的打造與淬煉在 visit_smith
    另外做；淬煉、拆解假人都不做）。都沒事是 None。"""
    s, c, w = game.state, game.content, game.world
    member = s.player.member
    moves = {
        "weapon": weapons.wanted(s, c, w, team.player_art(s, c, w, member.wugong_id)),
        "armor": armor.wanted(s, c, team.player_art(s, c, w, member.neigong_id)),
    }
    here = equipment.page(s.player, c) if s.player.picking_smith else equipment.first_page(c)
    if moves.get(here) is not None:
        return moves[here]
    other = next((slot for slot, move in moves.items() if move is not None), None)
    return None if other is None else f"smith:page:{other}"


# 伺服器假人打一爐之後至少留幾兩（療傷、修）。PM 2026-10-13（FB-144）從 30 降到 10：假人到鐵匠鋪時身上多半只有幾十兩，留 30 兩
# 一整季一爐都打不成
FORGE_SILVER_RESERVE = 10


def forge_step(game: Game) -> str | None:
    """伺服器假人在鐵匠鋪打造的下一顆（打造第二批，PM 2026-10-12 決定第 3 條）：照整季機器人的 forge_plan／armor_plan 挑這一爐
    （一般組合、名器、偶然碰上的神器配方都照打；不讀口訣），回單子的下一步——打開 → 種類 → 主料 → 輔料 → 開爐（防具沒有種類）；
    單子跟這一爐對不上（存檔留下的、計畫變了）回「不打了」。沒有要打的時候，兵器頁上裝備庫裡有比手上更好的那把就換上
    （smithing.better_in_rack；防具的換上 armor.wanted 本來就會）；這一頁沒事、另一頁有一爐要打回切頁那一顆（同 smith_want）。
    工錢付了之後剩不到 FORGE_SILVER_RESERVE 兩的那一爐不打。不淬煉、不拆。沒事是 None。"""
    s, c, w = game.state, game.content, game.world
    p = s.player
    art = team.player_art(s, c, w, p.member.wugong_id)
    plans = _forge_plans(game)
    d = p.smith_draft
    if d is not None:
        plan = plans.get(smithing.slot_of(d.kind))
        if plan is None:
            return smithing.CANCEL
        kind, main, aux = plan
        if d.kind not in (None, kind) or d.main not in (None, main) or d.aux not in (None, aux):
            return smithing.CANCEL
        if d.kind is None:
            return f"{smithing.KIND}{kind}"
        if d.main is None:
            return f"{smithing.MAIN}{main}"
        if d.aux is None:
            return f"{smithing.AUX}{aux}"
        return f"{smithing.GO}{kind}:{main}:{aux}"
    here = equipment.page(p, c) if p.picking_smith else equipment.first_page(c)
    if plans.get(here) is not None:
        return smithing.OPEN
    better = smithing.better_in_rack(s, c, w, art) if here == "weapon" else None
    if better is not None:
        return f"smith:wield:{better.id}"
    other = next((slot for slot, plan in plans.items() if plan is not None and slot != here), None)
    return None if other is None else f"smith:page:{other}"


def _forge_plans(game: Game) -> dict[str, tuple[str, str, str] | None]:
    """這一刻兵器、防具各要打的那一爐（smithing.forge_plan／armor_plan），工錢付了之後剩不到 FORGE_SILVER_RESERVE 兩的當沒有。
    兩樣都要人在有鐵匠鋪的城鎮（forge_plan、armor_plan 自己會問）。"""
    s, c, w = game.state, game.content, game.world
    p = s.player

    def affordable(plan):
        if plan is None:
            return None
        cost = smithing.price(c, smithing.tier_of(c, plan[1]), smithing.slot_of(plan[0]), s)
        return plan if p.stats.get("silver", 0) - cost >= FORGE_SILVER_RESERVE else None

    return {
        "weapon": affordable(smithing.forge_plan(s, c, w, team.player_art(s, c, w, p.member.wugong_id))),
        "armor": affordable(smithing.armor_plan(s, c, w, team.player_art(s, c, w, p.member.neigong_id))),
    }


def forge_ready(game: Game) -> bool:
    """人在城鎮的鐵匠鋪、身上湊得出一爐又付得起（留得下 FORGE_SILVER_RESERVE）：bot_policy 給「進鐵匠鋪」多加 FORGE_SCORE（FB-144）。"""
    return any(plan is not None for plan in _forge_plans(game).values())


def keep_book_names(game: Game) -> None:
    """整季機器人打出神器原品：一律按「沿用譜名」（Game.name_divine(keep=True)；設計第十一節：整季機器人不上線，不用擔心看得出來）。"""
    for item_id in forge_secrets.unnamed_originals(game.state, game.world):
        game.name_divine(item_id, keep=True)


def trade_want(game: Game) -> tuple | None:
    """鐵匠鋪的下一件素材買賣（素材與經濟計畫 B5；整季機器人與假人共用）：先升階、再賣，沒事是 None。
    素材四階開著時（正式季整合 8.1）：三換四是那個屬性的四階少於 TIER4_WANT、這一季還能換；其餘每一階照一般的料：高一階不夠換下一階、
    低一階比留的（trade_keep）多出一份以上；三階跟一、二階一樣多的賣、捐，四階不賣不捐（本來就不收）。關著照舊：
    升三階：那個屬性的三階少於 TIER3_WANT、二階夠換、今天還能換；升二階：二階不夠換一個三階、一階比留的（TRADE_KEEP）多出一份以上；
    升階付完工錢要剩 TRADE_SILVER_RESERVE；出來的屬性隨機（economy.upgrade_outcomes），出什麼收什麼、照舊往下算。
    賣：一階、二階多過留的量的部分。三階不賣。回 ("upgrade", 屬性, 階) 或 ("sell", 素材, 個數)。"""
    s, c = game.state, game.content
    econ = c.config.economy
    held = s.player.materials
    keep = bot_base.trade_keep(c)
    if econ.upgrade:
        day = game.econ_day()
        needs = economy.upgrade_needs(c)
        four = four_tiers.on(c)
        for attribute, tier in sorted(economy.upgradable(c), key=lambda pair: -pair[1]):  # 高階先
            high, low = economy.upgrade_pair(c, attribute, tier)
            need = needs[tier]
            if tier == four_tiers.TIER:  # 三換四（正式季整合 8.1）：那個屬性的四階少於 TIER4_WANT 就換，一季照規矩
                wanted = held.get(high.id, 0) < TIER4_WANT
            elif tier >= 3 and not four:  # 素材四階關著：舊規則，三階留著湊神器
                wanted = held.get(high.id, 0) < TIER3_WANT
            else:  # 一般的料（素材四階開著時三階也是）：高一階不夠換下一階、低一階比留的多出一份以上
                wanted = held.get(high.id, 0) < needs.get(tier + 1, need) and held.get(low.id, 0) >= keep.get(low.tier, 0) + need
            affordable = s.player.stats.get("silver", 0) - economy.upgrade_cost(s, c, tier) >= TRADE_SILVER_RESERVE
            if wanted and affordable and economy.upgrade_problem(s, c, attribute, tier, day) is None:
                return ("upgrade", attribute, tier)
    if econ.sell:
        for mid, n in sorted(held.items()):
            material = c.materials.get(mid)
            spare = keep.get(material.tier) if material is not None else None
            if spare is not None and n > spare and economy.sell_price_for(s, c, material.tier) is not None:
                return ("sell", mid, n - spare)
    return None


def trade_at_smith(game: Game) -> None:
    """人在鐵匠鋪（選單開著）時照 trade_want 升、賣到沒事為止（走店面的 Game.smith_upgrade／smith_sell，跟真人按鈕同一條）。
    不在鐵匠鋪什麼都不做：不為了它繞路。"""
    if not game.state.player.picking_smith:
        return
    for _ in range(bot_base.TRADE_MOVES):
        move = trade_want(game)
        if move is None:
            return
        before = dict(game.state.player.materials)
        if move[0] == "upgrade":
            game.smith_upgrade(move[1], move[2])
        else:
            game.smith_sell(move[1], move[2])
        if game.state.player.materials == before:
            return  # 被拒絕（店那一串不在眼前之類）：不再試


def visit_smith(game: Game) -> None:
    """城裡有鐵匠鋪就看一眼（兵器設計第六節、四欄設計第九節）：先在兵器頁照 weapons.wanted 換、買、修，再照 smithing.forge_plan
    打一把、把裝備庫裡更好的換上、淬煉手上那把、收掉打造的單子；再切到防具頁照 armor.wanted 換、買、修，照 smithing.armor_plan 打一件
    （打出來比身上那件好就換上：armor.wanted 先看裝備庫）、淬煉身上那件、收掉單子；最後離開。兵器的事先做完才切防具頁
    （打造與淬煉的鈕各在各頁）。每一頁換買修最多按四下。不花體力。假人不走這裡（bot_policy 照 smith_want 與 forge_step，打造但不淬煉）。"""
    s, c, w = game.state, game.content, game.world

    def art():
        return team.player_art(s, c, w, s.player.member.wugong_id)

    def inner():
        return team.player_art(s, c, w, s.player.member.neigong_id)

    def enabled() -> set[str]:
        return {o.id for o in game.options(odds=False) if o.enabled}

    def press(wanted: Callable[[], str | None]) -> None:
        for _ in range(4):
            move = wanted()
            if move is None or move not in enabled():
                break
            game.choose(move)

    def finish_draft() -> None:
        if s.player.smith_draft is not None and smithing.CANCEL in enabled():
            game.choose(smithing.CANCEL)  # 單子走到一半（按不下去）：收掉，不留在單子上（單子開著時也沒有切頁鈕、沒有離開）

    if s.pending_event or not equipment.smith_open(s, c):
        return
    if (smith_want(game) is None and not smithing.has_errand(s, c, w, art()) and not smithing.armor_errand(s, c, w, inner())
            and trade_want(game) is None):
        return
    if "act:smith" not in enabled():
        return
    game.choose("act:smith")
    trade_at_smith(game)  # 素材與經濟（計畫 B5）：先升階、把多的賣掉（賣了有錢買修打）
    if equipment.page(s.player, c) == "weapon":  # 進門停在兵器頁（武器關著時直接是防具頁，這一段跳過）
        press(lambda: weapons.wanted(s, c, w, art()))
        plan = smithing.forge_plan(s, c, w, art())
        if plan is not None:
            for oid in smithing.wizard_steps(*plan):
                if oid not in enabled():
                    break
                game.choose(oid)
        better = smithing.better_in_rack(s, c, w, art())
        if better is not None and f"smith:wield:{better.id}" in enabled():
            game.choose(f"smith:wield:{better.id}")
        weapon = s.player.weapon  # 淬煉最多幾次照這一把的品質（鐵匠鋪與合成流程 3.6）
        for _ in range(smithing.temper_cap(weapon, c) if weapon is not None else 0):
            if not smithing.temper_wanted(s, c, w, art()) or smithing.TEMPER not in enabled():
                break
            game.choose(smithing.TEMPER)
        finish_draft()
        if (armor.wanted(s, c, inner()) is not None or smithing.armor_errand(s, c, w, inner())) and "smith:page:armor" in enabled():
            game.choose("smith:page:armor")  # 防具的事在另一頁：兵器的事（含打造、淬煉）做完才切過去
    if equipment.page(s.player, c) == "armor":
        press(lambda: armor.wanted(s, c, inner()))
        plan = smithing.armor_plan(s, c, w, inner())
        if plan is not None:
            for oid in smithing.wizard_steps(*plan):
                if oid not in enabled():
                    break
                game.choose(oid)
            finish_draft()
            press(lambda: armor.wanted(s, c, inner()))  # 打出來進了裝備庫、比身上那件好：換上
        worn_armor = s.player.armor
        for _ in range(smithing.temper_cap(worn_armor, c) if worn_armor is not None else 0):
            if not smithing.armor_temper_wanted(s, c, w, inner()) or smithing.ARMOR_TEMPER not in enabled():
                break
            game.choose(smithing.ARMOR_TEMPER)
        finish_draft()
    if s.player.picking_smith:
        game.choose("smith:back")


def _name_originals(game: Game, rng: random.Random) -> list[str]:
    """神器原品定名（打造第二批，PM 2026-10-12 決定第 3 條）：一律「沿用譜名」（Game.name_divine(keep=True)，跟真人按那一顆一樣），
    每一把每一輪 DIVINE_NAME_CHANCE 的機會。亂數只在手上真的有等著定名的原品時才擲（沒有的假人一次都不擲，假人程式共用的亂數順序不變）。"""
    msgs: list[str] = []
    for item_id in forge_secrets.unnamed_originals(game.state, game.world):
        if rng.random() < DIVINE_NAME_CHANCE:
            msgs += game.name_divine(item_id, keep=True)
    return msgs
