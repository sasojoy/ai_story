"""假人看到鐵匠鋪的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 smith 那一段與 bot_policy._smith_want，全部拆包第 41 批拿了
smith: 前綴之後搬來，照決戰包）。bot_policy 照舊留著 _smith_want（一行，叫這裡的 want）與 SMITH_SCORE、FORGE_SCORE 這幾個名字（tests/bots/test_bot_policy.py、
tests/gear 直接讀；數同一個）。`act:smith`（進鐵匠鋪）的分數第 60 批搬來（enter，Verb.bot 問）。

整季機器人與假人共用的 smith_want、forge_step、_forge_plans、forge_ready、FORGE_SILVER_RESERVE 第二輪第 89 批從 bot 搬來（bot 留 re-export，visit_smith 與測試照舊讀那幾個名字）；
bot.trade_at_smith、bot.keep_book_names 不搬，留在假人殼。**模組層不准碰 engine 與假人殼**（bot 模組層 import 這個檔）。
"""
from __future__ import annotations

from tianxia import armor, equipment, team, weapons
from tianxia.core.option import Option

from . import smithing

SMITH_SCORE = 8.0  # 鐵匠鋪：跟揭懸賞一樣急，兵器配不上是白白少一截威力（bot_policy.SMITH_SCORE = BOUNTY_SCORE 同一個數）
FORGE_SCORE = SMITH_SCORE  # 人在城鎮、身上湊得出一爐又付得起（forge_ready）時進鐵匠鋪再多這麼多（FB-144；說明在 bot_policy.FORGE_SCORE，同一個數）


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
