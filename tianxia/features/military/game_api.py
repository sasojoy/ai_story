"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import admin_actions, fs_actions, opp_actions, order_actions, seat_actions


TABLE = {
    "_report_seat": seat_actions.report_seat,
    "_settle_plots": opp_actions.settle_plots,
    "_hear_after_stamina": fs_actions.hear_after_stamina,
    "_fs_asking_text": fs_actions.asking_text,
    "_fs_after_win": fs_actions.after_win,
    "_opp_on_win": opp_actions.on_win,
    "_hear_from_event": fs_actions.hear_from_event,
    "_admin_omen_choices": fs_actions.admin_choices,
    "_omen_talk_options": fs_actions.talk_options,
    "_fs_hear_talk": fs_actions.hear_talk,
    "_opp_hear_topic": opp_actions.hear_topic,
    "_opp_after_success": opp_actions.after_success,
    "_order_credit": order_actions.order_credit,
    "admin_issue_orders": admin_actions.issue_orders,
    "admin_rotate_seats": admin_actions.rotate_seats,
    "_summons_plan": admin_actions.summons_plan,
    "admin_summon": admin_actions.summon,
    "admin_give_opportunity": opp_actions.give_opportunity,
    "admin_give_fragment": fs_actions.give_fragment,
    "convoy_line": order_actions.convoy_line,
    "orders_view": order_actions.orders_view,
}
