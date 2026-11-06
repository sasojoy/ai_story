"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import admin_actions, challenge, yuedan_actions


def _yuedan_line(ctx, content, name):
    return yuedan_actions.yuedan.line_for(ctx.state, content, name)


TABLE = {
    "yuedan_request": yuedan_actions.request,
    "apply_yuedan": yuedan_actions.apply,
    "_snubbed_character": challenge.snubbed_character,
    "_challenge_options": challenge.options,
    "challenge_odds": challenge.odds,
    "_figure_squad": challenge.figure_squad,
    "_rout": challenge.rout,
    "_challenge_reward": challenge.win_reward,
    "_figure_tier3": challenge.tier3,
    "_figure_tier4": challenge.tier4,
    "_challenge": challenge.challenge,
    "admin_fallen": admin_actions.fallen,
    "admin_revive_figure": admin_actions.revive_figure,
    # 玩家卡上月旦評那一句（這一週許劭對他說的；大勢人物包的月旦評，玩家互動包 social.card 經這裡問，不直接 import 大勢人物包）。
    "_yuedan_line": _yuedan_line,
}
