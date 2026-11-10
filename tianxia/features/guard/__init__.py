"""親衛隊長（功能包；開發規範手冊 3.2；設計稿 https://claude.ai/artifact/7Sra7sBo7njyH34B2Nr7Su，Joy 2026-11-09「其他都按照建議」）。
README.md 寫這一包做什麼、導覽與設計稿。第一批：遇見與成長。

- rules.py：純規則（帳、心性、固定事件、給模型的提示與夾法）；texts.py：固定的字（開場、名字表、固定事件）。
- actions.py：「此地還能做」那幾顆、接管的選單、什麼時候冒出一件事、親衛隊長那一頁的那一份、換季照帶。
- routes.py：/api/do/guard_rename、guard_along、guard_say（鎖外三段式）與背景生事件（OutlockJob guard）。
- bots.py：假人的分數（假人也養一個，走固定事件、不叫模型）。
- 換季：season.carry 那一格照帶（不看開關），on_season_start 收拾眼前那一件。
- web/guard.js、guard.css：俠客頁「同伴」最上面的親衛隊長那一頁。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome


class GuardFeature(Feature):
    name = "guard"
    prefix = "guard"  # guard:meet、save、leave、part、back、adopt:<男|女>、open、pick:<i>、later
    web = ("guard.js", "guard.css")  # 俠客頁「同伴」最上面的親衛隊長那一頁（cultivation.js 的同伴那一頁叫 guardHtml）
    content: tuple[str, ...] = ()  # 第一批的固定字在 texts.py
    player_fields: tuple[str, ...] = ("guard",)  # PlayerState.guard（GuardBook）
    carried: tuple[str, ...] = ("guard",)  # 跟著帳號走：換季照帶（season.carry 那一格，不看開關；收拾在 on_season_start）

    def enabled(self, ctx) -> bool:
        return ctx.content.config.guard.enabled  # 預設關；數字在 tianxia/core/tuning/guard.py

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

    def on_sync(self, ctx, elapsed) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_sync(ctx, elapsed)

    def on_day(self, ctx) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_day(ctx)

    def after_action(self, ctx) -> list[str]:
        if not self.enabled(ctx):  # 接縫掛鉤不問 enabled：自己問
            return []
        from . import actions  # noqa: PLC0415

        return actions.after_action(ctx)

    def on_season_start(self, ctx, old) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_season_start(ctx, old)

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415

        return routes.outlock(shell)

    # core_seams：season.carry 的 guard 那一格（順序在 SEAM_ORDER；不看開關：開關關著換季也照帶，打開時人還在）
    _seams = None

    def seams(self):
        if self._seams is None:
            from tianxia.core.features import SeamHook  # noqa: PLC0415

            self._seams = (SeamHook("season.carry", "guard", _carry_season),)
        return self._seams


def _carry_season(ctx, old, fresh) -> None:
    fresh.player.guard = old.player.guard  # 親衛隊長（features/guard）：整份照帶，收拾在 on_season_start（開關開著時）


FEATURE = GuardFeature()
