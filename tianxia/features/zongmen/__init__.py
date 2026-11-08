"""門派（功能包；開發規範手冊 3.2；設計稿 https://claude.ai/artifact/9oVGtgs9mFApXsqVqf9Kis v6 卷二，Joy 2026-11-08「不錯，按照設計稿動工」）。
README.md 寫這一包做什麼、導覽與設計稿。第一批：門派不綁勢力（Content.sect_faction）、新的五門（Sect.switch 是 zongmen）在山門拜入與叛出、
門派身分換季照帶（on_season_start）。第二批：師門武譜（book.py 純規則；帳在全服的 SharedWorldState.sect_books，不分季）——
山門前試練（選項）、俠客頁門下那一段獻式與學式（routes.py 的 /api/do/zongmen_offer、zongmen_learn）。

掛鉤照 tianxia/core/features.py 的表；用得到哪一個才寫哪一個。功能包只 import 核心（tianxia/core/ 與手冊 3.1 的核心模組）、共用規則層（registry.SHARED）與自己這一包。
玩家動作（main_actions、menxia_actions）、管理者工具（admin_tools）、API（routes）、鎖外三段式（outlock）寫在包的 routes.py，掛鉤裡才 from . import routes（手冊第十五節 G10）；路由第一行要有開關的 gate，關著丟 404（例 features/heroines/routes.py，test_shell_stays_thin 逐包打）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome


class ZongmenFeature(Feature):
    name = "zongmen"
    prefix = "zongmen"  # 選項 id 的前綴：zongmen:…（核心只把這個前綴的 id 交給這一包）
    web = ("zongmen.js", "zongmen.css")  # 俠客頁門下那一段的師門武譜
    content: tuple[str, ...] = ()  # 內容檔（手冊 G8）：相對於 tianxia/features/zongmen/content/，例 ("zongmen.json",)、("events/zongmen.json",)；宣告了就要有那個檔，不放 repo 的 content/
    player_fields: tuple[str, ...] = ()  # 認領的 PlayerState 欄位（新欄位加在核心 state.py、名字帶包名前綴，標 Field(<預設>, json_schema_extra=QUIET)，不標 test_shell_stays_thin 紅，先過 PM：手冊第十五節 G7）
    carried: tuple[str, ...] = ()  # 上面那些裡換季照帶走的

    def enabled(self, ctx) -> bool:
        return ctx.content.config.zongmen.enabled  # 預設關：讀 Config.zongmen.enabled，tuning 的 enabled: bool = False；數字在 tianxia/core/tuning/zongmen.py

    def options(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.options(ctx)

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        from . import actions, rules  # noqa: PLC0415

        return Outcome(title=rules.TITLE, run=lambda: actions.choose(ctx, arg))

    def on_season_start(self, ctx, old) -> None:
        from . import actions  # noqa: PLC0415

        actions.carry(ctx, old)

    def status(self, ctx):
        from . import actions  # noqa: PLC0415

        view = actions.view(ctx)
        return {"zongmen": view} if view is not None else {}

    def main_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import

        return routes.main_actions(shell)

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)


FEATURE = ZongmenFeature()
