"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import admin, muster, progress, sieges, view


TABLE = {
    # 本體在 tianxia/features/battle/muster.py（全部拆包第 7 批：集結、投效、挑同伴），這裡留一行委派
    "_ally_follows_battle": muster.ally_follows_battle,
    # 本體在 tianxia/features/battle/muster.py（全部拆包第 7 批：集結、投效、挑同伴），這裡留一行委派
    "_escort_carry": muster.escort_carry,
    "_settle_partings": muster.settle_partings,
    "_sieges": sieges.sieges,
    "battles_now": progress.battles_now,
    "battle_now": progress.battle_now,
    "_battle_now": progress.battle_now,
    # 本體在 tianxia/features/battle/muster.py（全部拆包第 7 批：集結、投效、挑同伴），這裡留一行委派
    "_joinable": muster.joinable,
    "_definition_of": sieges.definition_of,
    "_tick_siege": sieges.tick_siege,
    "_cancel_siege": sieges.cancel_siege,
    "_settle_siege": sieges.settle_siege,
    # 本體在 tianxia/features/battle/progress.py（全部拆包第 8 批：推進與結算），這裡留一行委派
    "_battle_status": progress.battle_status,
    "_showdown_status": progress.showdown_status,
    "_battle_for_me": progress.battle_for_me,
    "_shelve_unfinished_battle": progress.shelve_unfinished_battle,
    "_advance_battle_round": progress.advance_battle_round,
    "_run_battle_tick": progress.run_battle_tick,
    "_apply_battle_outcome": progress.apply_battle_outcome,
    "_merit_line": progress.merit_line,
    # 本體在 tianxia/features/battle/progress.py（全部拆包第 8 批：推進與結算），這裡留一行委派
    "_apply_outcome_trends_and_flags": progress.apply_outcome_trends_and_flags,
    "_deliver_battle_results": view.deliver_battle_results,
    "_file_showdown": view.file_showdown,
    "_annal_showdown": view.annal_showdown,
    "_showdown_pay": view.showdown_pay,
    "_showdown_credits": view.showdown_credits,
    # 本體在 tianxia/features/battle/progress.py（全部拆包第 8 批：推進與結算），這裡留一行委派
    "_watching_battle": progress.watching_battle,
    "_fighting": progress.fighting,
    # 本體在 tianxia/features/battle/muster.py（全部拆包第 7 批：集結、投效、挑同伴），這裡留一行委派
    "_free_agent": muster.free_agent,
    "_at_battle": muster.at_battle,
    "_sync_battle_presence": muster.sync_battle_presence,
    "rally_region": muster.rally_region,
    "battle_gauge": view.battle_gauge,
    "siege_banner": view.siege_banner,
    "record_gauge": view.record_gauge,
    "card_gauge": view.card_gauge,
    "_battle_scene_text": view.battle_scene_text,
    "_battle_spotlight": view.battle_spotlight,
    # 本體在 tianxia/features/battle/muster.py（全部拆包第 7 批：集結、投效、挑同伴），這裡留一行委派
    "_battle_menu": muster.battle_menu,
    "_battle_options": muster.battle_options,
    "battle_free_text_prompt": view.battle_free_text_prompt,
    "battle_free_text_note": view.battle_free_text_note,
    "battle_text_request": view.battle_text_request,
    "submit_battle_custom_action": view.submit_battle_custom_action,
    "battle_tale_request": view.battle_tale_request,
    "apply_battle_tales": view.apply_battle_tales,
    "_tale_battles": view.tale_battles,
    # 本體在 tianxia/features/battle/muster.py（全部拆包第 7 批：集結、投效、挑同伴），這裡留一行委派
    "_battle_choose": muster.battle_choose,
    "_battle_choose_in": muster.battle_choose_in,
    "_showdown_tier4": view.showdown_tier4,
    "admin_battles": admin.admin_battles,
    "admin_start_battle": admin.admin_start_battle,
    "admin_cancel_battle": admin.admin_cancel_battle,
    "admin_showdowns": admin.admin_showdowns,
    "cancelled_showdowns": admin.cancelled_showdowns,
    "admin_start_showdown": admin.admin_start_showdown,
    "battle_on_screen": view.battle_on_screen,
}
