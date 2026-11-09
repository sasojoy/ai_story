"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from tianxia.core.services import not_while_preparing

from . import clue, divine_actions, forge_actions, gear_actions, shelf_actions, trade_actions


TABLE = {
    "_smith": shelf_actions.smith,
    "smith_line": forge_actions.smith_line,
    "smith_forge": forge_actions.smith_forge,
    "smith_sell": trade_actions.smith_sell,
    "smith_upgrade": trade_actions.smith_upgrade,
    "smith_furnace": forge_actions.smith_furnace,
    "repair_item": gear_actions.repair_item,
    "temper_item": gear_actions.temper_item,
    "_smith_clue": clue.smith_clue,
    "name_divine": not_while_preparing(divine_actions.name_divine),
    "bind_art": not_while_preparing(divine_actions.bind_art),
}
