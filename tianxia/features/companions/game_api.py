"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from tianxia.core.services import not_while_preparing

from . import actions, parley_actions, talk_actions


def _parley_owed_line(ctx, name):
    return parley_actions.owed_line(name)


TABLE = {
    "_recruit_target": actions.recruit_target,
    "_recruit_targets": actions.recruit_targets,
    "_recruitable_here": actions.recruitable_here,
    "dialogue_request": talk_actions.dialogue_request,
    "_checked_prepared": talk_actions.checked_prepared,
    "voice_stance": actions.voice_stance,
    "figure_view": actions.figure_view,
    "persuade_request": actions.persuade_request,
    "persuade": actions.persuade,
    "letter_view": actions.letter_view,
    "read_letter": actions.read_letter,
    "decline_letter": actions.decline_letter,
    "morning_mail": actions.morning_mail,
    "letter_request": actions.letter_request,
    "apply_letter": actions.apply_letter,
    "_open_dialogue": talk_actions.open_dialogue,
    # 人物情誼包回答懸賞榜包（道謝信、守約、兌現；services.py 二、查詢服務 # bounties）
    "_letter_thank": actions.letter_thank,
    "_parley_settle_task": parley_actions.settle_task,
    "_parley_keep": parley_actions.keep,
    "_parley_owed_line": _parley_owed_line,
    "_parley_ask_label": parley_actions.ask_label,
    "_last_talk_line": talk_actions.last_talk_line,
    "affinity_text": talk_actions.affinity_text,
    "_annal_talk": talk_actions.annal_talk,
    "say_max": talk_actions.say_max,
    "_parley_lists": parley_actions.lists,
    "_parley_prompt": parley_actions.prompt,
    "_parley_options": parley_actions.options,
    "_parley_backing_here": parley_actions.backing_here,
    "roster_lines": actions.roster_lines,
    "owned_companions": actions.owned_companions,
    "add_to_team": not_while_preparing(actions.add_to_team),
    "remove_from_team": not_while_preparing(actions.remove_from_team),
    "release_companion": not_while_preparing(actions.release_companion),
    "release_view": actions.release_view,
}
