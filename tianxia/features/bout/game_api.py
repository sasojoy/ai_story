"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import arena_actions, duel_actions


TABLE = {
    # 頭目的查詢（本體在 tianxia/features/bout/duel_actions.py，全部拆包第 12 批）：舊探索在原位叫，探索包經 ctx 問
    "_boss_face": duel_actions.boss_face,
    "_boss_ready": duel_actions.boss_ready,
    # 本體在 tianxia/features/bout/duel_actions.py（全部拆包第 12 批：單挑類的仗此刻要抄的防具減損），這裡留一行委派——戰力快照
    # （_battle_gear）、奪璽單挑的參戰者與沒參戰的持有者（kin、game）在叫
    "_duel_cut": duel_actions.duel_cut,
    "_duel_start": duel_actions.duel_start,
    "duel_free_text_prompt": duel_actions.duel_free_text_prompt,
    "duel_free_text_note": duel_actions.duel_free_text_note,
    "duel_text_request": duel_actions.duel_text_request,
    "_duel_side": duel_actions.duel_side,
    "duel_gamble": duel_actions.duel_gamble,
    "_duel_finish": duel_actions.duel_finish,
    "_arena_bare": arena_actions.arena_bare,
    "arena_power": arena_actions.arena_power,
    "arena_left": arena_actions.arena_left,
    "_arena_fight_problem": arena_actions.arena_fight_problem,
    "_arena_options": arena_actions.arena_options,
    "_arena_join": arena_actions.arena_join,
    "arena_crowd_request": arena_actions.arena_crowd_request,
    "apply_arena_crowd": arena_actions.apply_arena_crowd,
    "_deliver_arena": arena_actions.deliver_arena,
}
