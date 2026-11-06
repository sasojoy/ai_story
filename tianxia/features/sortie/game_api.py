"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions, duel_actions, train_actions


TABLE = {
    "_sortie_line": actions.sortie_line,
    "_train_pick": train_actions.train_pick,
    "_train": train_actions.train,
    "_train_squad_ids": train_actions.train_squad_ids,
    "_duty_option": train_actions.duty_option,
    "drill_scale": train_actions.drill_scale,
    "_drill": train_actions.drill,
    "sorties_left": actions.sorties_left,
    "_sortie_foes": actions.sortie_foes,
    "_sortie_mode": actions.sortie_mode_of,
    "sortie_mode": actions.sortie_mode,
    "sortie_progress": actions.sortie_progress,
    "_melee_record": actions.melee_record,
    "_sortie": actions.sortie,
    "_sortie_rewards": actions.sortie_rewards,
    "_sortie_host": actions.sortie_host,
    "_sortie_hold": actions.sortie_hold,
    "duel_on": duel_actions.duel_on,
    "duel_convoy_here": duel_actions.duel_convoy_here,
    "_duel_squad": duel_actions.duel_squad,
    "sortie_go_problem": duel_actions.sortie_go_problem,
    "sortie_go": duel_actions.sortie_go,
    "sortie_cards": duel_actions.sortie_cards,
    "sortie_card": duel_actions.sortie_card,
    "sortie_duel_tick": duel_actions.sortie_duel_tick,
    "_train_push": train_actions.train_push,
    "train_trend_push": train_actions.train_trend_push,
}
