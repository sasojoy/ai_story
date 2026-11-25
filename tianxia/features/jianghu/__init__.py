"""江湖頁重排（功能包；開發規範手冊 3.2；Joy 2026-11-25「方向對」、決定卡「開始做，先不上線」）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

掛鉤照 tianxia/core/features.py 的表；用得到哪一個才寫哪一個。功能包只 import 核心（tianxia/core/ 與手冊 3.1 的核心模組）、共用規則層（registry.SHARED）與自己這一包。
玩家動作（main_actions、menxia_actions）、管理者工具（admin_tools）、API（routes）、鎖外三段式（outlock）寫在包的 routes.py，掛鉤裡才 from . import routes（手冊第十五節 G10）；路由第一行要有開關的 gate，關著丟 404（例 features/heroines/routes.py，test_shell_stays_thin 逐包打）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class JianghuFeature(Feature):
    name = "jianghu"
    prefix = "jianghu"  # 沒有選項：只換江湖頁的畫法，按的都是原本的選項
    web: tuple[str, ...] = ("jianghu.js", "jianghu.css")  # 江湖頁閒著時的新排法（web/main.js 的 pageJianghu 問 jhOn，開著就交給 jhPageHtml）
    content: tuple[str, ...] = ()  # 內容檔（手冊 G8）：相對於 tianxia/features/jianghu/content/，例 ("jianghu.json",)、("events/jianghu.json",)；宣告了就要有那個檔，不放 repo 的 content/
    player_fields: tuple[str, ...] = ()  # 認領的 PlayerState 欄位（新欄位加在核心 state.py、名字帶包名前綴，標 Field(<預設>, json_schema_extra=QUIET)，不標 test_shell_stays_thin 紅，先過 PM：手冊第十五節 G7）
    carried: tuple[str, ...] = ()  # 上面那些裡換季照帶走的

    def enabled(self, ctx) -> bool:
        return ctx.content.config.jianghu.enabled  # 預設關：讀 Config.jianghu.enabled，tuning 的 enabled: bool = False；數字在 tianxia/core/tuning/jianghu.py


    def status(self, ctx) -> dict:
        from . import view  # noqa: PLC0415

        return {} if ctx.state.player.bot else {"jianghu": view.status(ctx)}


FEATURE = JianghuFeature()
