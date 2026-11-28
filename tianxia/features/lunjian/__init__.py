"""門派論劍（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

- rules.py：純規則（內容檔、幾點抽籤開打、誰上台、師兄補位、抽籤配對、分身對分身打一場、三場算輸贏、禮匣開出什麼）。
- actions.py：報名（lunjian:sign）、時刻到了誰先同步誰抽籤開打、各自同步補賞、挑素材（lunjian:claim:<素材>）、開禮匣（lunjian:open、
  lunjian:open_top）、畫面那一份（main.lunjian）。
- judge.py：開打前請模型判兩邊的戰策（鎖外；打法第四版）。routes.py：POST /api/lunjian/plan（自己寫的戰策）與背景那一條（判讀寫回）。
- bots.py：假人照公開行動報名、挑老法子、開匣。checks.py：內容檔的驗證。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome


class LunjianFeature(Feature):
    name = "lunjian"
    prefix = "lunjian"  # lunjian:sign（報名、更新分身）、lunjian:claim:<素材 id>（挑一份四階）、lunjian:open、lunjian:open_top（開禮匣）
    web: tuple[str, ...] = ("lunjian.js", "lunjian.css")  # 江湖頁眼下那一件與點開的那一頁（main.lunjian）
    content: tuple[str, ...] = ("lunjian.json",)  # 包自己讀（rules.FILE），Content 不加欄位
    player_fields: tuple[str, ...] = ("lunjian",)  # PlayerState.lunjian：贏來還沒用的素材、禮匣、朱印
    carried: tuple[str, ...] = ()  # 禮匣、素材換季照帶，在 on_season_start 抄過去（同江湖錄、慢慢長出來；不走 carried：開關關著換季就不帶）

    def enabled(self, ctx) -> bool:
        return ctx.content.config.lunjian.enabled  # 預設關：讀 Config.lunjian.enabled；數字在 tianxia/core/tuning/lunjian.py

    def options(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.options(ctx)

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.title(ctx), run=lambda: actions.act(ctx, arg))

    def on_season_start(self, ctx, old) -> None:
        from . import actions  # noqa: PLC0415

        actions.carry(ctx, old)

    def status(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.status(ctx)

    def on_sync(self, ctx, elapsed) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_sync(ctx)

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)

    def bot_idle(self, ctx, option) -> bool:
        if not option.id.startswith("lunjian:"):
            return False
        from . import bots  # noqa: PLC0415

        return bots.idle(ctx, option)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415

        return routes.router(shell)

    def threads(self, shell) -> None:
        """伺服器啟動時開判讀那一條（routes.start；開關關著不開）。"""
        from . import routes  # noqa: PLC0415

        routes.start(shell)

    def check_content(self, content, need) -> None:
        from . import checks  # noqa: PLC0415

        checks.check_content(content, need)


FEATURE = LunjianFeature()
