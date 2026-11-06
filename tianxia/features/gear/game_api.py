"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import bench_actions, gift_actions, market_actions, views


TABLE = {
    # 馬市上的選擇：買、餵、換上，或離開（裝備包 market_actions；choose 的 market: 由包的 choose 掛鉤接走，測試直接叫這裡）。
    "_market": market_actions.market,
    # 修練頁的「換上」（裝備包 bench_actions；MENXIA_ACTIONS["wield"]）。
    "wield_weapon": bench_actions.wield_weapon,
    # 修練頁坐騎那一列的「餵」（裝備包 bench_actions；MENXIA_ACTIONS["feed"]，整季機器人與假人也走這裡）。
    "feed_mount": bench_actions.feed_mount,
    # 修練頁裝備庫的「拆解」（裝備包 bench_actions；MENXIA_ACTIONS["dismantle"]）。
    "dismantle_weapon": bench_actions.dismantle_weapon,
    # 批量拆解（裝備包 bench_actions，裝飾器 not_while_preparing 在包的函式上；MENXIA_ACTIONS["dismantle_many"]）。
    "dismantle_many": bench_actions.dismantle_many,
    # 名將贈禮（裝備包 gift_actions；choose 後半與事件檢定的 answer_event、answer_branch 叫）。
    "_general_gifts": gift_actions.general_gifts,
    # 此刻站在你身邊的人物（裝備包 gift_actions；名將贈禮與本命兵器照它寫當面交給你還是託人送來）。
    "_people_here": gift_actions.people_here,
    # 名將贈禮與本命兵器另起一則江湖紀錄（裝備包 gift_actions）。
    "_gift_entry": gift_actions.gift_entry,
    # 名將本命兵器（裝備包 gift_actions；choose、事件檢定叫，大勢人物包的挑戰本人打贏時經 ctx 叫）。
    "_signature_arms": gift_actions.signature_arms_due,
    # 修練頁「裝備」那一塊的資料（裝備包 views）。
    "gear_rows": views.gear_rows,
    # 見聞「榜單」的神器譜（裝備包 views；/api/boards 最後一張）。
    "divine_book_view": views.divine_book_view,
}
