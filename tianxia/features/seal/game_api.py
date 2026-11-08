"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions, admin, card, duel_actions


TABLE = {
    # 領地爭奪的季探索撿玉璽碎片（玉璽包 actions；事件 outing 的 seal 那一格直接叫包的，這一行只剩測試叫）。
    "_seal_find": actions.seal_find,
    # 戴著碎片時不含碎片戰力的份量快照（玉璽包 actions；_battle_marks 原位與決戰包 progress 經 ctx 叫）。
    "_seal_bare": actions.seal_bare,
    # 天命之爭手上有碎片的人份量加權（玉璽包 actions；決戰包 muster、progress 經 ctx 叫）。
    "_mandate_weight": actions.mandate_weight,
    # 玉璽碎片的事補送到自己手上（玉璽包 actions；第 28 批的奪璽單挑那幾個方法原位叫，決戰包 progress 經 ctx 叫；sync 走 deliver_results 掛鉤）。
    "_deliver_seal_results": actions.deliver_results,
    # 一場奪璽單挑寫成自己的戰報與紀錄（玉璽包 actions；包裡補送直接叫，這一行只剩測試叫）。
    "_file_seal": actions.file_seal,
    # 天命之爭定下來（玉璽包 actions；管理者「定結果」原位叫、包的收場經 ctx 叫——scripts/measure_seal.py 換掉這一個）。
    "_mandate_settle": actions.mandate_settle,
    # 時刻表決戰收場時的玉璽碎片（玉璽包 actions；事件 battle_end 的 seal 那一格直接叫包的，這一行只剩測試叫）。
    "_seal_settle": actions.settle,
    # 本體在玉璽包 tianxia/features/seal/duel_actions.py（第 28 批），這裡一行委派。
    "_seal_challengers": duel_actions.challengers,
    # 本體在玉璽包 tianxia/features/seal/duel_actions.py（第 28 批），這裡一行委派。
    "_seal_spectators": duel_actions.spectators,
    # 本體在玉璽包 tianxia/features/seal/duel_actions.py（第 28 批），這裡一行委派。
    "_seal_side_of": duel_actions.side_of,
    # 本體在玉璽包 tianxia/features/seal/duel_actions.py（第 28 批），這裡一行委派。
    "seal_free_text_prompt": duel_actions.free_text_prompt,
    # 本體在玉璽包 tianxia/features/seal/duel_actions.py（第 28 批），這裡一行委派。
    "seal_free_text_note": duel_actions.free_text_note,
    # 本體在玉璽包 tianxia/features/seal/duel_actions.py（第 28 批），這裡一行委派。
    "seal_text_request": duel_actions.text_request,
    # 本體在玉璽包 tianxia/features/seal/duel_actions.py（第 28 批），這裡一行委派。
    "seal_gamble": duel_actions.gamble,
    # 本體在玉璽包 tianxia/features/seal/card.py（第 28 批），這裡一行委派。
    "seal_view": card.view,
    # 本體在玉璽包 tianxia/features/seal/card.py（第 28 批），這裡一行委派。
    "seal_use": card.use,
    # 本體在玉璽包 tianxia/features/seal/duel_actions.py（第 28 批），這裡一行委派。
    "seal_duel_card": duel_actions.duel_card,
    # 管理者「強制現世」（領地爭奪的季改成現在藏一片；本體在玉璽包 admin.py，管理者工具走 routes.py 的 admin_tools，這個名字測試叫）。
    "admin_seal_emerge": admin.emerge,
    # 本體在玉璽包 tianxia/features/seal/admin.py（第 28 批），這裡一行委派。
    "admin_seal_assign": admin.assign,
    # 本體在玉璽包 tianxia/features/seal/admin.py（第 28 批），這裡一行委派。
    "admin_seal_duel": admin.duel,
    # 本體在玉璽包 tianxia/features/seal/admin.py（第 28 批），這裡一行委派。
    "admin_seal_fix": admin.fix,
    # 本體在玉璽包 tianxia/features/seal/admin.py（第 28 批），這裡一行委派。
    "admin_seal_cancel": admin.cancel,
    # 管理者「隱沒判斷」（本體在玉璽包 admin.py，管理者工具走 routes.py 的 admin_tools，這個名字測試叫）。
    "admin_seal_sink_check": admin.sink_check,
    # 管理者「蓋天命之季」（本體在玉璽包 admin.py，管理者工具走 routes.py 的 admin_tools，這個名字測試與輿圖包的測試叫）。
    "admin_seal_mandate": admin.mandate,
    # 本體在玉璽包 tianxia/features/seal/admin.py（第 28 批），這裡一行委派。
    "admin_seal_choices": admin.choices,
}
