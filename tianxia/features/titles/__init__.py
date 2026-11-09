"""稱號與官職（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

掛鉤照 tianxia/core/features.py 的表；用得到哪一個才寫哪一個。功能包只 import 核心（tianxia/core/ 與手冊 3.1 的核心模組）、共用規則層（registry.SHARED）與自己這一包。
玩家動作（main_actions、menxia_actions）、管理者工具（admin_tools）、API（routes）、鎖外三段式（outlock）寫在包的 routes.py，掛鉤裡才 from . import routes（手冊第十五節 G10）；路由第一行要有開關的 gate，關著丟 404（例 features/heroines/routes.py，test_shell_stays_thin 逐包打）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class TitlesFeature(Feature):
    name = "titles"
    prefix = "titles"  # 選項 id 的前綴：titles:…（核心只把這個前綴的 id 交給這一包）
    web = ("titles.js", "titles.css")  # 畫面（手冊 G9）：web/ 底下的檔名，例 ("titles.js", "titles.css")。js 的 script 由伺服器照這裡生成，不要手改 index.html 的 script；新鈕在 web/titles.js 寫 titlesClick 加 registerClicks，不加進 app.js；css 的 link 接在 index.html 最後一行 link 之後（不要排到 map.css、shop.css 前面），它與 tests/kit/webharness.APP_FILES 手寫
    content: tuple[str, ...] = ()  # 內容檔（手冊 G8）：相對於 tianxia/features/titles/content/，例 ("titles.json",)、("events/titles.json",)；宣告了就要有那個檔，不放 repo 的 content/
    player_fields = ("titles_pin", "titles_worn")  # 認領的 PlayerState 欄位（新欄位加在核心 state.py、名字帶包名前綴，標 Field(<預設>, json_schema_extra=QUIET)，不標 test_shell_stays_thin 紅，先過 PM：手冊第十五節 G7）
    carried: tuple[str, ...] = ()  # 上面那些裡換季照帶走的

    def enabled(self, ctx) -> bool:
        return ctx.content.config.titles.enabled  # 預設關：讀 Config.titles.enabled，tuning 的 enabled: bool = False；數字在 tianxia/core/tuning/titles.py


    def on_sync(self, ctx, elapsed: float) -> None:
        """每週結算（季曆換週後第一個同步的人替全服頒）＋此刻戴哪一個、新名號收進名號簿。"""
        from . import actions  # noqa: PLC0415

        actions.on_sync(ctx)

    def status(self, ctx) -> dict:
        """江湖畫面頂層的 titles：戴著的、自己挑的、手上有的與還沒拿到的（換戴那一格）。"""
        from . import actions  # noqa: PLC0415

        return {"titles": actions.view(ctx)}

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)


FEATURE = TitlesFeature()
