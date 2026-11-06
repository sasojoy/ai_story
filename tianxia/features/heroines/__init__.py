"""女子與隱線（功能包；開發規範手冊 3.2）：幾位女子透過一條奇事出場、走完留在當地可以交談；開了成人內容的人另有一條隱線
（設計稿「三位女子出場」，Joy 2026-11-06「開工」、尺度「那先甲就好」）。README.md 寫這一包做什麼、導覽與設計稿。

- rules.py：純規則（她出不出現、隱線端不端得出來、給模型的那幾行、過濾）。
- actions.py：「此地還能做」的那一顆、端在眼前時的選單、成人內容開關、換季。
- routes.py：設定頁的成人內容開關（/api/heroines/adult）。
- 接在別處的：figures.placed_characters（還不出現的女子不在任何地方）、companion_agent（提示多幾行、扮演誰、寫回來的過濾）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome

PREFIX = "heroines"


class HeroinesFeature(Feature):
    name = "heroines"
    prefix = PREFIX  # heroines:open:<人物>、heroines:yes、heroines:no
    content = ("heroines.json",)  # content.py 照舊讀進 Content.heroines
    player_fields: tuple[str, ...] = ("heroines", "heroines_adult")
    carried: tuple[str, ...] = ("heroines_adult",)  # 成人內容的開關換季照帶（on_season_start 抄過去）；隱線換季重來

    def enabled(self, ctx) -> bool:
        from . import rules  # noqa: PLC0415

        return rules.on(ctx.content)

    def options(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.options(ctx)

    def menu(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.menu(ctx)

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.title(ctx, arg), run=lambda: actions.act(ctx, arg))

    def status(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.status(ctx)

    def on_season_start(self, ctx, old) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_season_start(ctx, old)

    def bot_pick(self, ctx, option):
        return None  # 假人不走這條線（開關在假人身上永遠是關的，選項本來就不會出現）

    def routes(self, shell):
        from . import routes  # noqa: PLC0415

        return routes.router(shell)

    def check_content(self, content, need) -> None:
        from . import checks  # noqa: PLC0415

        checks.check(content, need)


FEATURE = HeroinesFeature()
