"""人物情誼（功能包；開發規範手冊 3.2）：同伴招募與名下、人物心意、託付與勸降、來信與委託、人物頁。全部拆包第 19 批（人物情誼一）搬進來；
人物對話與 NPC 智能（companion_agent、parley，`talk:`、`parley:`）是第 20 批搬進來的（talk_actions、parley_actions、bots.py）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

選項前綴 `errand:`（託付：交信、探營、勸降）、`talk:`（跟人物談著的選項：上一輪給的、自己說、商量打法、條件的接與不接、還債、請他兌現、伏筆與機緣的話題、告辭）、
`parley:`（帶路的路上跟他說一句）；招募是核心 `act:` 的子動詞（`act:recruit`、`act:recruit:<id>`，總表第 57 批）。`talk:`、`parley:` 的 choose 留在 Game.choose 原位
（要帶鎖外生成好的一輪 prepared 與驗過的那句話，掛鉤的簽名放不下；第 57 批「選單上、不建紀錄」那一格再看），這一包只拿前綴問 bot_pick。enabled 一直是 True
（招募 Config.companions、書信 Config.figure_life.letters、心意與託付 Config.jianfa 各有自己的開關，包本身沒有總開關）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome


class CompanionsFeature(Feature):
    name = "companions"
    prefix = ("errand", "talk", "parley")  # 託付（errand:<動詞>:<id>）；整季機器人不按（要寫字、不收託付）；人物對話 talk:*、帶路的路上 parley:road（假人只按告辭，見 bots.py）
    bot_always = ("errand:",)  # 整季機器人不收託付，萬一有也不按（勸降要寫字；原本 bot.pick 的排除清單）
    content = ("events/stances.json",)  # 人物心意開的事件（總表附錄甲）；content.py 照舊讀（第 62 批起照它載）；檔名照舊
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）。換季全部跟著新角色重來；parted_done（同伴回江湖的減半記號）第 7 批決戰包認領了，第 7 批 PM 認定第 4 條留到這一包再看：
    # 寫它的 settle_partings 還在決戰包，這一批照留
    player_fields = (
        "stance_notes", "errands", "letters", "letter_day", "letter_seq", "cheers",
        # 第 20 批（審查補認領）：人物對話（companion_agent）的私有狀態與 NPC 智能 2.0（parley）這一季的帳；talks_today、picking_audience 留給第 21 批（交友求見）
        "pending_companion", "dialogue_history", "used_dialogue_options", "last_offered_dialogue", "turns_since_consolidation",
        "talk_memos", "talk_prev", "parley_days", "parley_terms", "parley_owed", "parley_backing", "parley_debts", "parley_records",
        "parley_escort", "parley_road_leg",
    )
    # 對話紀錄、說過的話、梳理的輪數換季照帶（Game._reset_player_for_new_season；history_start 是它從 dialogue_history 的長度算的，不另認領）
    carried: tuple[str, ...] = ("dialogue_history", "used_dialogue_options", "turns_since_consolidation")

    def enabled(self, ctx) -> bool:
        return True

    def choose(self, ctx, kind, arg):
        """託付（交信、探營、勸降的 C 段）；勸降按下去只叫出輸入框那一下在建紀錄之前，核心原位問 Game._errand_ask（計畫 1.5）。"""
        if kind != "errand":  # talk:、parley: 的 choose 留在 Game.choose 原位（帶 prepared 與驗過的那句話）
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.errand_title(ctx, arg), run=lambda: actions.errand_act(ctx, arg))

    def bot_pick(self, ctx, option):
        """假人看到 talk:、parley: 的選項怎麼按（原本 bot_policy.score 的 talk 那一段）；errand: 整季機器人不收、伺服器假人在 take_turn 打分數之前就濾掉，沒有分數（None）。"""
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)


FEATURE = CompanionsFeature()
