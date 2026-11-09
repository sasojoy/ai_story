"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions


TABLE = {
    "_epiphany_begin": actions.epiphany_begin,
    "_epiphany_name": actions.epiphany_name,
    "epiphany_request": actions.epiphany_request,
    "epiphany_names": actions.epiphany_names,
    "sense_request": actions.sense_request,
    "sense_draw": actions.sense_draw,
    "_sense_missed": actions.sense_missed,
    "_sense_start": actions.sense_start,
    "_epiphany_title": actions.epiphany_title,
    "_sense_prologue_choice": actions.prologue_choice,
    "_sense_here": actions.sense_here,
    "method_help": actions.method_help,
}
