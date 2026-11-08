"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions


TABLE = {
    "story_start": actions.story_start,
    "story_cards": actions.story_cards,
    "story_seen": actions.story_seen,
    "story_card_view": actions.story_card_view,
    "_story_begin": actions.story_begin,
    "_story_tick": actions.story_tick,
    "_mirror_squad": actions.mirror_squad,
    "_story_close_season": actions.close_season,
}
