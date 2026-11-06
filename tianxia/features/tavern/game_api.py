"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions, rules


def _tavern_on(ctx):
    return rules.on(ctx.content)


def _tavern_here(ctx):
    return rules.here(ctx.state, ctx.content)


def _tavern_at(ctx, loc_id):
    return rules.tavern_at(ctx.content, loc_id)


TABLE = {
    "_tavern_open": actions.tavern_open,
    # guide（全部拆包第 22 批）：酒肆的查詢服務——新手引導包（碰到才說的 h_tavern、新手目標「去酒肆」）問酒肆，包不能 import 包
    "_tavern_on": _tavern_on,
    "_tavern_here": _tavern_here,
    "_tavern_at": _tavern_at,
    "_tavern_enter": actions.tavern_enter,
    "_tavern_price": actions.tavern_price,
    "tavern_do": actions.tavern_do,
    "_tavern_run": actions.tavern_run,
    "_deliver_watches": actions.deliver_watches,
    "_tavern_hit_problem": actions.tavern_hit_problem,
    "_tavern_hit_check": actions.tavern_hit_check,
    "_tavern_hit_fight": actions.tavern_hit_fight,
    "_deliver_hits": actions.deliver_hits,
    "_tavern_ask_facts": actions.tavern_ask_facts,
    "tavern_chatter_request": actions.tavern_chatter_request,
    "apply_tavern_chatter": actions.apply_tavern_chatter,
    "tavern_ask_request": actions.tavern_ask_request,
    "tavern_ask": actions.tavern_ask_reply,
    "tavern_view": actions.tavern_view,
}
