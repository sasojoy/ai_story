"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions


def _battle_ult(ctx):
    return actions.battle_ult(ctx)


TABLE = {
    # 擂台形象：這個人此刻穿哪一套（功能包 looks；空字串＝斗笠小子）。
    "arena_look": actions.look_of,
    # 招式動畫：這個人此刻出招疊哪一張光效（功能包 looks；空字串＝沒有）。
    "arena_move": actions.move_of,
    # 決戰放手一搏送出那一刻身上的絕招（功能包 looks；回合 MVP 演它）：沒穿、沒有導演稿是 None。
    "_battle_ult": _battle_ult,
    # 回合 MVP（功能包 looks）：包著回合結算，結算完挑一位、回合紀錄多一行。
    "_round_mvp": actions.round_mvp,
}
