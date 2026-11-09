"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import departure, go_actions, menu, party


TABLE = {
    # 主畫面的「走法」切換（本體在 tianxia/features/travel/menu.py；留一行委派給 server、腳本與測試）。
    "set_move_mode": menu.set_move_mode,
    # 出發（本體在 tianxia/features/travel/departure.py，全部拆包第 48 批；留一行委派給人物帶路、腳本與測試）。
    "_depart": departure.depart,
    # 補算已經到了的站（本體在 tianxia/features/travel/departure.py；留一行委派給 sync、advance，位置就是行為）。
    "_arrivals": departure.arrivals,
    # 抵達一站，事件 arrive 的發布點（本體在 tianxia/features/travel/departure.py；留一行委派給核心契約測試）。
    "_arrive": departure.arrive,
    # 安排前往（本體在 tianxia/features/travel/go_actions.py；留一行委派給 /api/travel、假人與測試）。
    "travel": go_actions.travel,
    # 用這種走法安排前往這裡，不行的原因（本體在 tianxia/features/travel/go_actions.py；留一行委派給 /api/travel 與測試）。
    "travel_refusal": go_actions.travel_refusal,
    # 答應結伴同行（本體在 tianxia/features/travel/party.py；留一行委派給玩家互動包 answer_invite）。
    "_join": party.join,
    # 答應跟 leader 結伴同行，不行的原因（本體在 tianxia/features/travel/party.py；留一行委派給玩家互動包 bots.answer_call）。
    "join_refusal": party.join_refusal,
    # 場景底下結伴同行的那一行（本體在 tianxia/features/travel/party.py；/api/main 的 party 那一格直接叫本體，這一行留給測試）。
    "party_view": party.party_view,
}
