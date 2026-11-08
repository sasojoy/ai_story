"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批的寫法；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。_settle_season_start、_showdown_mark 只有這一包叫，不掛。"""
from __future__ import annotations

from . import actions


TABLE = {
    "admin_open_season": actions.admin_open_season,
    "admin_end_season": actions.admin_end_season,
    "admin_next_season": actions.admin_next_season,
    "admin_pause_clock": actions.admin_pause_clock,
    "admin_resume_clock": actions.admin_resume_clock,
    "admin_fires": actions.admin_fires,
    "admin_fire": actions.admin_fire,
    "admin_push_trend": actions.admin_push_trend,
    "_timetable_refusal": actions._timetable_refusal,  # noqa: SLF001  決戰包的管理者工具、軍情包經 ctx 叫
    "_timetable_event": actions._timetable_event,  # noqa: SLF001  同上
    "admin_schedule": actions.admin_schedule,
    "admin_jump_next": actions.admin_jump_next,
    "admin_set_trend": actions.admin_set_trend,
    "admin_resolve_event": actions.admin_resolve_event,
    "admin_clear_lock": actions.admin_clear_lock,
}
