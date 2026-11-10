"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions, create


def _create_on(ctx):
    return create.on(ctx.content)


def _create_allowed(ctx):
    return create.allowed(ctx.state, ctx.content)


def _create_price(ctx):
    return create.price(ctx.state, ctx.content)


TABLE = {
    # 開爐首次取名或挑選的 A 段（煉製包 actions.forge_request；server.prepare_forge、bot_policy.tend_arts 在鎖內呼叫）：這一爐要不要模型？
    # 要就回送模型的單子，不要是 None。只讀、不改狀態。
    "forge_request": actions.forge_request,
    # 煉製頁的開爐（煉製包 actions.forge）：只剩兩個意境（不同的＝合成、同一種的兩份＝揣摩）。proposed 是鎖外先取好的（名字, 說明）（C 段）。
    "forge": actions.forge,
    "forge_line": actions.forge_line,
    # 化入（意境合成改版，煉製包 actions.infuse）：others 化進 body；改版沒開的季回一句話。
    "infuse": actions.infuse,
    # 兩格都放好時煉製頁的預覽卡（煉製包 actions.forge_preview）。只讀。
    "forge_preview": actions.forge_preview,
    # 爐裡只放了一個意境時，另一格放得進來的每一個合不合得了（煉製包 actions.forge_picks）。只讀。
    "forge_picks": actions.forge_picks,
    # 執器：內功或武學、兵器種類或行功之法（煉製包 actions.begin）。只開單、不收錢、不寫紀錄。
    "create_begin": actions.begin,
    # 擺式：火柴人的九個角度（煉製包 actions.pose）。只改單子。
    "create_pose": actions.pose,
    # 立意的 A 段（煉製包 actions.intent_request）：送得出去回傳要在鎖外請模型讀的單子，不行回傳那一句話。
    "create_request": actions.intent_request,
    # 立意（C 段，或直接呼叫；煉製包 actions.intent）：reading 是鎖外讀好的；沒給（假人、整季機器人、腳本）照關鍵字表讀。
    "create_intent": actions.intent,
    # 重讀這句意的 A 段（煉製包 actions.reread_request）：送得出去回傳要在鎖外請模型讀的單子，不行回傳那一句話。
    "create_reread_request": actions.reread_request,
    # 重悟帖：重讀這句意（C 段，煉製包 actions.reread）。reading 是 None（模型叫不動）什麼都不改、不扣帖。
    "create_reread": actions.reread,
    # 重悟帖：成了形直接重骰（煉製包 actions.reroll）。只改單子與帖數。
    "create_reroll": actions.reroll,
    # 回頭重擺式或重立意（煉製包 actions.back）。
    "create_back": actions.back,
    # 立名：付心得、登記（煉製包 actions.name，一律上品）；move 是招名（空的照模型起的）。
    "create_name": actions.name,
    "create_cancel": actions.cancel,
    # 煉製頁「自創」那一塊（煉製包 actions.view）。只讀。
    "create_view": actions.view,
    # craft（全部拆包第 44 批）：新手引導碰到才說的 h_create 問的三個查詢服務（只讀；原本引導包直接 import create）
    # 自創開著沒（create.on）。
    "_create_on": _create_on,
    # 此刻能不能自創：不能是原因，能是 None（create.allowed）。
    "_create_allowed": _create_allowed,
    # 這一門自創要付多少心得（create.price）。
    "_create_price": _create_price,
    # core_rest
    "_deliver_echoes": actions.deliver_echoes,
}
