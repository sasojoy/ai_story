"""傳承（功能包；開發規範手冊 3.2）：正氣、邪氣、機緣（換季那一刻照上一季的傳結算）與識海（帶一份神品意境到下一季、解封才用得到）。
這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

- rules.py：純規則（評比、增量、結算、門路）
- actions.py：換季結算、識海的選項與動作、江湖畫面的狀態
- bots.py：假人的分數
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome, SeamHook


class LegacyFeature(Feature):
    name = "legacy"
    prefix = "legacy"  # legacy:seal:<i>、legacy:skip、legacy:open、legacy:name:<i>
    bot_always = ("legacy:skip",)  # 開季時一直按得下去：整季機器人不按
    player_fields = ("legacy",)  # PlayerState.legacy（LegacyBook）
    web = ("legacy.js", "legacy.css")  # 傳承頁、識海頁的畫法（legacy.js 的 legacyPageHtml）與樣子
    carried = ("legacy",)  # 換季照帶（Game._reset_player_for_new_season，不看開關；結算在 on_season_start）

    def enabled(self, ctx) -> bool:
        return ctx.content.config.legacy.enabled

    def options(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.options(ctx)

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.title(ctx, arg), run=lambda: actions.act(ctx, arg))

    def status(self, ctx) -> dict:
        from . import actions  # noqa: PLC0415

        return actions.status(ctx)

    def prep(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.prep(ctx)

    def on_season_start(self, ctx, old) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_season_start(ctx, old)

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """season.carry 的 legacy 那一格（順序在 SEAM_ORDER；不看開關，同出陣那兩格；結算在 on_season_start）。"""
        if self._seams is None:
            self._seams = (SeamHook("season.carry", "legacy", _carry_season),)
        return self._seams


def _carry_season(ctx, old, fresh) -> None:
    fresh.player.legacy = old.player.legacy  # 傳承（features/legacy）


FEATURE = LegacyFeature()
