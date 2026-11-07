"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions


TABLE = {
    # 本體在 tianxia/features/guide/actions.py（全部拆包第 22 批：新手引導），這裡留一行委派
    "_note_gift": actions.note_gift,
    # 本體在 tianxia/features/guide/actions.py（全部拆包第 22 批：新手引導），這裡留一行委派
    "_top_up_line": actions.top_up_line,
    "_graduate": actions.graduate,
    # 本體在 tianxia/features/guide/actions.py（全部拆包第 22 批：新手引導），這裡留一行委派
    "_begin_enlistment": actions.begin_enlistment,
    "_greet_rejoin": actions.greet_rejoin,
    # 這一季的新角色走不走開局第一分鐘（opening.on）。
    "_opening_on": actions.opening_on,
    # 新角色站到城門口、端出三選一（opening.begin）。
    "_opening_begin": actions.opening_begin,
    # 還停在城門口三選一上（opening.pending）。
    "_opening_pending": actions.opening_pending,
    # 三選一選完那一下：那位人物的信與護送委託（opening.deliver），回紀錄的那一句。
    "_opening_deliver": actions.opening_deliver,
    # 三選一還沒選就簽到的那一句（opening.GATE）。
    "_opening_gate": actions.opening_gate,
    # 開場那一則江湖紀錄的引導那幾行（guide.tutorial_intro）。
    "_tutorial_intro": actions.tutorial_intro,
    # 引導裡說話的人（guide.speakers）：_note_guide 照它分開「下一步的話」與「✔ 與獎勵」。
    "_guide_speakers": actions.guide_speakers,
    # 本體在 tianxia/features/guide/actions.py（全部拆包第 22 批：新手引導），這裡留一行委派
    "enlist_glow": actions.enlist_glow,
    "guide_box": actions.guide_box,
    "_hint": actions.hint,
    "_hint_triggers": actions.hint_triggers,
    "_check_hints": actions.check_hints,
    "_nearest_to": actions.nearest_to,
    "_newbie_go": actions.newbie_go,
    "newbie_view": actions.newbie_view,
    "newbie_drifter": actions.newbie_drifter,
    # 本體在 tianxia/features/guide/actions.py（全部拆包第 22 批：新手引導），這裡留一行委派
    "set_hints_off": actions.set_hints_off,
    "guide_ack": actions.guide_ack,
    # 本體在 tianxia/features/guide/actions.py（全部拆包第 22 批：新手引導），這裡留一行委派
    "_rest": actions.rest,
    "howto_text": actions.howto_text,
    # 本體在 tianxia/features/guide/actions.py（全部拆包第 22 批：新手引導），這裡留一行委派
    "skip_tutorial": actions.skip_tutorial,
    "view_orders": actions.view_orders,
    "view_map": actions.view_map,
    # 本體在 tianxia/features/guide/actions.py（全部拆包第 22 批：新手引導），這裡留一行委派
    "view_tab": actions.view_tab,
    "prologue_view": actions.prologue_view,
    "onboard_view": actions.onboard_view,
    "prologue_recap": actions.prologue_recap,
    "quest_text": actions.quest_text,
    "_stamina_help": actions.stamina_help,
    "_war_help": actions.war_help,
    # core_imports（第二輪第 98 批：原本是 Game 本體上的方法）
    "_note_action": actions.note_action,
}
