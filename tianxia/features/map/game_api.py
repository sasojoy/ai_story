"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions


TABLE = {
    # 本體在 tianxia/features/map/actions.py（全部拆包第 49 批：輿圖），這裡留一行委派（_map_foes 測試會換掉、包裡也經 ctx 叫；_fierce_line 留給 same_behavior 的 strip 軌直接叫）
    "map_base": actions.map_base,
    "map_state": actions.map_state,
    "_map_foes": actions.map_foes,
    "_fierce_line": actions.fierce_line,
    "world_map_svg": actions.world_map_svg,
    "minimap_svg": actions.minimap_svg,
    "map_legend": actions.map_legend,
    "map_header": actions.map_header,
    "map_places": actions.map_places,
    "place_detail": actions.place_detail,
    "travel_options": actions.travel_options,
    # 探索包問輿圖包的兩個查詢（原本探索包直接 import mapview、mapdata；包不能 import 包，經這兩行問）
    "_map_open_places": actions.open_places,
    "_map_mostly_here": actions.mostly_here,
}
