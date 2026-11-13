"""江湖錄（功能包；開發規範手冊 3.2）：奇遇紀錄與圖鑑。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

功能包只 import 核心（tianxia/core/ 與手冊 3.1 的核心模組）、共用規則層（registry.SHARED）與自己這一包。
路由寫在 routes.py，第一行有開關的 gate，關著回 404。新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class CodexFeature(Feature):
    name = "codex"
    prefix = "codex"  # 沒有選項：畫面上的動作都走 /api/codex/*
    web = ("codex.js", "codex.css")  # 俠客頁「江湖錄」那一頁（web/cultivation.js 照 S.main.codex 加那一顆分頁）
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ("codex",)  # PlayerState.codex（CodexBook）
    # 跟著帳號走（Joy 2026-11-13「做」，設計稿決定一照建議）：開著的時候在 on_season_start 照帶；不寫進 carried——season.carry 那一張表
    # 是核心的、改要點頭，關著換季的那一季就不帶（PR 寫退版風險）
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return ctx.content.config.codex.enabled  # 預設關：Config.codex.enabled

    def on_sync(self, ctx, elapsed: float) -> None:
        from . import rules  # noqa: PLC0415

        if not ctx.state.player.bot:  # 假人不記（沒有人看）
            rules.scan(ctx.state, ctx.content)

    def after_action(self, ctx) -> list[str]:
        from . import rules  # noqa: PLC0415

        if self.enabled(ctx) and not ctx.state.player.bot:
            rules.scan(ctx.state, ctx.content)
        return []

    def on_season_start(self, ctx, old) -> None:
        from . import rules  # noqa: PLC0415

        rules.carry(old, ctx.state, ctx.content)

    def status(self, ctx) -> dict:
        from . import view  # noqa: PLC0415

        return {} if ctx.state.player.bot else {"codex": view.status(ctx)}

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)


FEATURE = CodexFeature()
