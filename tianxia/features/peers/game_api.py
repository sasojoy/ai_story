"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions, discuss_actions, invite_actions, mingtie_actions, pair_actions, raid_actions


TABLE = {
    # 同一對人的帳本鍵（玩家互動包 pair_actions.pair_key）。
    "_spar_pair": pair_actions.pair_key,
    # 這一對人這個遊戲日在這本帳上記一次（玩家互動包 pair_actions.pair_tick）。
    "_pair_tick": pair_actions.pair_tick,
    # 答應（yes）、婉拒（no）、收回（cancel）一張邀請（玩家互動包 invite_actions.answer_invite；切磋、論武第 38 批搬進包、包內直接叫，這一行留給測試）。
    "answer_invite": invite_actions.answer_invite,
    # 答應了卻沒成、邀請已經收掉：發邀請的那個人下次同步看到一句（玩家互動包 invite_actions.tell_sender；移動包的結伴同行〔party.py〕經 ctx 叫它，切磋、論武在包內直接叫）。
    "_tell_sender": invite_actions.tell_sender,
    # 玩家互動包 discuss_actions.items 的一行委派（全部拆包第 38 批；測試叫）。
    "discuss_items": discuss_actions.items,
    # 玩家互動包 discuss_actions.cost_of 的一行委派（全部拆包第 38 批；測試叫）。
    "_discuss_cost": discuss_actions.cost_of,
    # 玩家互動包 discuss_actions.merge_problem 的一行委派（全部拆包第 38 批；包裡經 other 叫，測試換掉對方那一份）。
    "discuss_problem": discuss_actions.merge_problem,
    # 玩家互動包 discuss_actions.item_problem 的一行委派（全部拆包第 38 批；測試叫）。
    "discuss_item_problem": discuss_actions.item_problem,
    # 玩家互動包 raid_actions.is_shown 的一行委派（全部拆包第 38 批；測試叫）。
    "raid_shown": raid_actions.is_shown,
    # 玩家互動包 raid_actions.refusal 的一行委派（全部拆包第 38 批；測試叫）。
    "raid_refusal": raid_actions.refusal,
    # 玩家互動包 raid_actions.odds_word 的一行委派（全部拆包第 38 批；測試叫）。
    "raid_odds": raid_actions.odds_word,
    # 玩家互動包 raid_actions.targets 的一行委派（全部拆包第 38 批；測試叫）。
    "raid_targets": raid_actions.targets,
    # 玩家互動包 raid_actions.raid 的一行委派（全部拆包第 38 批；測試叫）。
    "raid": raid_actions.raid,
    # 玩家互動包 raid_actions.flee_odds 的一行委派（全部拆包第 38 批；包裡經 ctx 叫；測試換掉它）。
    "raid_flee_odds": raid_actions.flee_odds,
    # 玩家互動包 raid_actions.fled 的一行委派（全部拆包第 38 批；包裡經 ctx 叫；scripts/sim_season_one.py 換掉它數跑掉幾次）。
    "_raid_fled": raid_actions.fled,
    # 玩家互動包 raid_actions.take_spoils 的一行委派（全部拆包第 38 批；包裡經 ctx 叫；scripts/sim_season_one.py 換掉它）。
    "_raid_spoils": raid_actions.take_spoils,
    # 玩家互動包 raid_actions.raid_record 的一行委派（全部拆包第 38 批；包裡經 ctx 叫；sim 腳本換掉它數截殺）。
    "_raid_record": raid_actions.raid_record,
    # 場景底下「此地還有誰」：[{name, side}]，照名號排序（玩家互動包 actions.peers_here，全部拆包第 37 批）。
    "peers_here": actions.peers_here,
    # 此刻在你這裡的那個人那一份 Game（玩家互動包 actions.peer）；不在這裡是 None。
    "_peer": actions.peer,
    # 玩家卡（玩家互動包 actions.peer_card）；他不在這裡了是 None。
    "peer_card": actions.peer_card,
    # 玩家卡上的鈕按下去之前要不要先請模型（玩家互動包 actions.peer_request；論武的首創取名的 A 段）。
    "peer_request": actions.peer_request,
    # 按了玩家卡上的一顆鈕（玩家互動包 actions.peer_act）。
    "peer_act": actions.peer_act,
    # 今天還能送幾次東西（玩家互動包 pair_actions.gift_day_left）。
    "gift_day_left": pair_actions.gift_day_left,
    # 見聞「名帖匣」（玩家互動包 mingtie_actions.view）。
    "mingtie_view": mingtie_actions.view,
    # 名帖定稿（玩家互動包 mingtie_actions.make）。
    "make_mingtie": mingtie_actions.make,
    # 檢舉一張名帖（玩家互動包 mingtie_actions.report）。
    "report_mingtie": mingtie_actions.report,
    # 管理者「名帖檢舉」（玩家互動包 mingtie_actions.admin_reports；管理者工具這一批不搬）。
    "admin_mingtie_reports": mingtie_actions.admin_reports,
    # 撤下一張名帖（玩家互動包 mingtie_actions.admin_remove）。
    "admin_mingtie_remove": mingtie_actions.admin_remove,
    # 放回名帖（玩家互動包 mingtie_actions.admin_restore）。
    "admin_mingtie_restore": mingtie_actions.admin_restore,
    # 場景底下「別人遞給你、還沒回的」打招呼、結伴、切磋邀請（玩家互動包 actions.calls_here）。
    "calls_here": actions.calls_here,
}
