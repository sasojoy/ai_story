"""凌煙閣（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

掛鉤照 tianxia/core/features.py 的表；用得到哪一個才寫哪一個。功能包只 import 核心（tianxia/core/ 與手冊 3.1 的核心模組）、共用規則層（registry.SHARED）與自己這一包。
玩家動作（main_actions、menxia_actions）、管理者工具（admin_tools）、API（routes）、鎖外三段式（outlock）寫在包的 routes.py，掛鉤裡才 from . import routes（手冊第十五節 G10）；路由第一行要有開關的 gate，關著丟 404（例 features/heroines/routes.py，test_shell_stays_thin 逐包打）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class LingyanFeature(Feature):
    name = "lingyan"
    prefix = "lingyan"  # 沒有選項：閣是一整頁唯讀的 /lingyan
    # 遊戲裡只有見聞「江湖史」頂上一張入口（web/lingyan.js 的 lingyanEntryHtml；app.js 那一段照 typeof 叫）；閣本身是 /lingyan 一整頁（hall_html）
    web = ("lingyan.js", "lingyan.css")
    content: tuple[str, ...] = ()  # 內容檔（手冊 G8）：相對於 tianxia/features/lingyan/content/，例 ("lingyan.json",)、("events/lingyan.json",)；宣告了就要有那個檔，不放 repo 的 content/
    player_fields: tuple[str, ...] = ()  # 認領的 PlayerState 欄位（新欄位加在核心 state.py、名字帶包名前綴，標 Field(<預設>, json_schema_extra=QUIET)，不標 test_shell_stays_thin 紅，先過 PM：手冊第十五節 G7）
    carried: tuple[str, ...] = ()  # 上面那些裡換季照帶走的

    def enabled(self, ctx) -> bool:
        return ctx.content.config.lingyan.enabled  # 預設關：讀 Config.lingyan.enabled，tuning 的 enabled: bool = False；數字在 tianxia/core/tuning/lingyan.py

    def status(self, ctx) -> dict:
        """江湖畫面多一格 lingyan（開著才有；入口照它畫）。關著一個鍵都不多。"""
        return {"lingyan": True} if self.enabled(ctx) else {}

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)


FEATURE = LingyanFeature()
