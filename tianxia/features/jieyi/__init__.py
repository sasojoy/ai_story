"""結義（功能包；開發規範手冊 3.2；設計稿 https://claude.ai/artifact/9oVGtgs9mFApXsqVqf9Kis v2 卷一，Joy 2026-11-07「甲先不做……先做丙，跨季保留關係」）。
README.md 寫這一包做什麼、導覽與設計稿。

- rules.py：純規則（誰在哪一組、能不能邀、答應、割袍斷義、名號與排行）。
- actions.py：玩家卡「邀他結義」（載入這一包就登記進核心 cards.ACTIONS）、此地還能做的答應／婉拒、割袍斷義、給畫面的那一份。
- bots.py：假人收到結義邀請的回法；routes.py：/api/do/jieyi_leave。
- 帳在全服的 SharedWorldState.jieyi（不分季，換季不清）；沒有 PlayerState 欄位。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome

from . import actions as _actions  # noqa: F401  「邀他結義」登記進玩家卡的動作表（cards.ACTIONS）；載入這一包就登記


class JieyiFeature(Feature):
    name = "jieyi"
    prefix = "jieyi"  # jieyi:yes:<邀請>、jieyi:no:<邀請>
    web = ("jieyi.js", "jieyi.css")  # 俠客頁門下那一段的結義
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return ctx.content.config.jieyi.enabled  # 數字在 tianxia/core/tuning/jieyi.py（Config.jieyi）

    def options(self, ctx):
        return _actions.options(ctx)

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        return Outcome(title=_actions.TITLE, run=lambda: _actions.answer(ctx, arg))

    def status(self, ctx):
        view = _actions.view(ctx)
        return {"jieyi": view} if view is not None else {}

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)

    def main_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import

        return routes.main_actions(shell)


FEATURE = JieyiFeature()
