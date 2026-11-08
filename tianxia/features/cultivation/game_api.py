"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions, view


TABLE = {
    "_chuangong_ready": actions.chuangong_ready,
    # 服一枚破境丹強行衝絕學（修練包 actions.cultivate；籌備中被擋）。
    "cultivate": actions.cultivate,
    # 定名的 A 段（伺服器假人程式在行動鎖內呼叫；修練包 actions.mastery_request）：只讀。賽季籌備中是 None。
    "mastery_request": actions.mastery_request,
    # 替第一個練成絕學的武學取正式名字（修練包 actions.name_mastered；籌備中被擋）。
    "name_mastered": actions.name_mastered,
    # 絕學的契機（修練包 actions.seize_chance；服務清單二、查詢服務）：核心的單打服務 _seize 與決戰包的收場補送叫它。
    "_seize_chance": actions.seize_chance,
    # 改練：把功法庫裡的一門換上身（修練包 actions.switch_art；籌備中被擋）。
    "switch_art": actions.switch_art,
    # 破境卡那一句的 A 段（鎖內、只讀；修練包 actions.ascend_request）：有一張還沒寫那一句的卡，回請模型寫的單子；沒有是 None。
    "ascend_request": actions.ascend_request,
    # 破境卡那一句的 C 段（修練包 actions.ascend_line）：卡還是同一張才存。
    "ascend_line": actions.ascend_line,
    # 看過破境卡了，收掉（修練包 actions.ascend_dismiss）。
    "ascend_dismiss": actions.ascend_dismiss,
    # 把一個意境裝進一門武學的意境槽（修練包 actions.slot_insight；修練頁與煉製頁都走這裡，籌備中被擋）。
    "slot_insight": actions.slot_insight,
    # 把一個意境從武學的槽上拆下來（修練包 actions.unslot_insight；籌備中被擋）。
    "unslot_insight": actions.unslot_insight,
    # 熔煉：功法庫裡的一門熔成心得（修練包 actions.melt_art；籌備中被擋）。
    "melt_art": actions.melt_art,
    # 批量熔煉（修練包 actions.melt_many；籌備中被擋）。
    "melt_many": actions.melt_many,
    # 把一個意境化成心得（修練包 actions.melt_insight；籌備中被擋）。
    "melt_insight": actions.melt_insight,
    # 練成這一欄現在做不做得了（修練包 actions.practice_refusal；server 的修練頁照它把練成鈕灰掉）。
    "practice_refusal": actions.practice_refusal,
    # 練成：身上這一門加深一成（修練包 actions.practice；籌備中被擋）。
    "practice": actions.practice,
    # 挑成長配比的本體（修練包 actions.pick_growth；籌備中、沒有配比、已定這三步留在 pick_growth）。
    "_apply_growth": actions.pick_growth,
    # 把升級得到的屬性點分配到一項（修練包 actions.allocate_stat；配點那一句 actions.allocate_line；籌備中被擋）。
    "allocate_stat": actions.allocate_stat,
    # 傳功門下（修練包 actions.chuangong；籌備中被擋）。
    "chuangong": actions.chuangong,
    # 修練頁人物卡底下的傳功鈕（修練包 actions.chuangong_lessons；server.menxia_view 的 lessons）。
    "chuangong_lessons": actions.chuangong_lessons,
    "skill_detail": view.skill_detail,
    # 這個角色擁有的一門功法的功法卡（FB-006；修練包 view.art_detail）。
    "art_detail": view.art_detail,
    "member_card": view.member_card,
    "roster_cards": view.roster_cards,
    "menxia_rules": view.menxia_rules,
    # 修練頁與煉製頁摺起來的「屬性有什麼用」那一句（W2；修練包 view.attribute_note）。
    "attribute_note": view.attribute_note,
    "bag_text": view.bag_text,
    # 武學與意境的持有數與上限（修練包 view.holdings）。
    "holdings": view.holdings,
    "art_rows": view.art_rows,
    "insight_rows": view.insight_rows,
    # 等著自己取正式名字的那一門（第一個練成絕學；修練包 view.naming_row）；沒有是 None。
    "naming_row": view.naming_row,
}
