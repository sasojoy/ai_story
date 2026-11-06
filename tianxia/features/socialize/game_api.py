"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions, menus, view


TABLE = {
    "_talk_cap": view.talk_cap,
    "_social_plan": view.social_plan,
    "_socialize": actions.socialize,
    "_can_meet": view.figure_can_meet,
    "can_meet_figure": view.public_can_meet,
    "_brush_off": actions.brush_off,
    "_talks_used": view.talks_used,
    "_talks_left": view.talks_left,
    "_count_talk": actions.count_talk,
    "_audience_hall": view.audience_hall,
    "_socialize_figure": view.socialize_figure,
    "_talked_out_note": view.talked_out_note,
    "_audience_intro": menus.audience_intro,
    "socialize_starts_dialogue": view.starts_dialogue,
    "socialize_is_futile": view.is_futile,
    "_deliver_fortune": actions.deliver_fortune,
}
