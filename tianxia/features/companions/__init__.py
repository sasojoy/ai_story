"""人物情誼（功能包；開發規範手冊 3.2）：同伴招募與名下、人物心意、託付與勸降、來信與委託、人物頁。全部拆包第 19 批（人物情誼一）搬進來；
人物對話與 NPC 智能（companion_agent、parley，`talk:`、`parley:`）是第 20 批。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

選項前綴 `errand:`（託付：交信、探營、勸降）；招募是核心 `act:` 的子動詞（`act:recruit`、`act:recruit:<id>`，總表第 57 批）。enabled 一直是 True
（招募 Config.companions、書信 Config.figure_life.letters、心意與託付 Config.jianfa 各有自己的開關，包本身沒有總開關）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome


class CompanionsFeature(Feature):
    name = "companions"
    prefix = "errand"  # 託付（errand:<動詞>:<id>）；整季機器人不按（要寫字、不收託付）
    bot_always = ("errand:",)  # 整季機器人不收託付，萬一有也不按（勸降要寫字；原本 bot.pick 的排除清單）
    content = ("events/stances.json",)  # 人物心意開的事件（總表附錄甲）；content.py 照舊讀（第 62 批起照它載）；檔名照舊
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）。換季全部跟著新角色重來；parted_done（同伴回江湖的減半記號）第 7 批決戰包認領了，第 7 批 PM 認定第 4 條留到這一包再看：
    # 寫它的 settle_partings 還在決戰包，這一批照留
    player_fields = ("stance_notes", "errands", "letters", "letter_day", "letter_seq", "cheers")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True

    def choose(self, ctx, kind, arg):
        """託付（交信、探營、勸降的 C 段）；勸降按下去只叫出輸入框那一下在建紀錄之前，核心原位問 Game._errand_ask（計畫 1.5）。"""
        if kind != self.prefix:
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.errand_title(ctx, arg), run=lambda: actions.errand_act(ctx, arg))

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)


FEATURE = CompanionsFeature()
