"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import admin_actions, day_actions, letter_actions, view, xingshi_actions


TABLE = {
    "letter_problem": letter_actions.letter_problem,
    "conquest_letter": letter_actions.conquest_letter,
    "_conquest_tick": day_actions.conquest_tick,
    "_deliver_conquest": day_actions.deliver_conquest,
    "_xingshi_start": xingshi_actions.start,
    "_xingshi_open": xingshi_actions.open_ticket,
    "_xingshi_finish": xingshi_actions.finish,
    "xingshi_waiting": xingshi_actions.waiting,
    "release_xingshi": xingshi_actions.release,
    "xingshi_request": xingshi_actions.request,
    "settle_xingshi": xingshi_actions.settle,
    "xingshi_view": xingshi_actions.view,
    "admin_xingshi_now": xingshi_actions.admin_now,
    "conquest_view": view.conquest_view,
    "admin_conquest_set": admin_actions.conquest_set,
    "admin_conquest_progress": admin_actions.conquest_progress,
    "admin_conquest_letter": admin_actions.conquest_letter,
    "admin_conquest_cancel": admin_actions.conquest_cancel,
    "admin_conquest_choices": view.admin_choices,
}
