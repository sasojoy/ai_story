"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import explore_actions, explore_base, outing_actions, outing_rules


def _rare_boost(ctx):
    return outing_rules.rare_boost(ctx.state, ctx.content)


TABLE = {
    "_practice_tier": explore_base.practice_tier,
    "_rare_boost": _rare_boost,
    "_explore": explore_base.explore,
    "_legend_find": explore_base.legend_find,
    "_explore_weights": explore_base.explore_weights,
    "_explore_can": explore_base.explore_can,
    "_wild_foes": explore_base.wild_foes,
    "_home_gather": explore_actions.home_gather,
    "_outing_on": explore_actions.outing_on,
    "_outing_plan": explore_actions.outing_plan_at,
    "mostly_here": explore_actions.mostly_here,
    "outing_plan": explore_actions.outing_plan,
    "map_mostly": explore_actions.map_mostly,
    "_outing_fight": explore_actions.outing_fight,
    "fatigue_next": explore_actions.fatigue_next,
    "outing_go": outing_actions.outing_go,
    "outing_view": outing_actions.outing_view,
    "outing_can_go": outing_actions.outing_can_go,
    "_outing_watched": outing_actions.outing_watched,
    "outing_say": outing_actions.outing_say,
    "outing_tale_request": outing_actions.outing_tale_request,
    "outing_set_tale": outing_actions.outing_set_tale,
    "outing_ink_left": outing_actions.outing_ink_left,
    "admin_erase_inscription": outing_actions.admin_erase_inscription,
    # core_rest
    "_scrap_find": explore_base.scrap_find,
}
