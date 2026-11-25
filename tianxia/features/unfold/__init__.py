"""慢慢長出來（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

掛鉤照 tianxia/core/features.py 的表；用得到哪一個才寫哪一個。功能包只 import 核心（tianxia/core/ 與手冊 3.1 的核心模組）、共用規則層（registry.SHARED）與自己這一包。
玩家動作（main_actions、menxia_actions）、管理者工具（admin_tools）、API（routes）、鎖外三段式（outlock）寫在包的 routes.py，掛鉤裡才 from . import routes（手冊第十五節 G10）；路由第一行要有開關的 gate，關著丟 404（例 features/heroines/routes.py，test_shell_stays_thin 逐包打）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class UnfoldFeature(Feature):
    name = "unfold"
    prefix = "unfold"  # 沒有選項：紅點滅走 /api/unfold/seen
    web = ("unfold.js", "unfold.css")  # 照 main.unfold 藏還沒長出來的分頁、亮剛長出來的紅點、新角色的提示畫成小事卡（web/unfold.js、unfold.css；藏的那一步在 app.js 的 shown()）
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ("unfold",)  # PlayerState.unfold（UnfoldBook）
    # 跟著帳號走：長出來的不因換季收回（on_season_start 照帶）；不寫進 carried——season.carry 那一張表是核心的
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return ctx.content.config.unfold.enabled  # 預設關：Config.unfold.enabled（tianxia/core/tuning/unfold.py）

    def _look(self, ctx) -> None:
        from . import rules  # noqa: PLC0415

        p = ctx.state.player
        if p.bot:  # 假人沒有人看，也不能因為少一本被看出來：不開本
            return
        pending = ctx._opening_pending()  # noqa: SLF001  核心服務（services_list.md）：城門口三選一還沒選
        if p.unfold is None:
            if not (self.enabled(ctx) and pending):  # 只有開關開著時新建、還站在城門口的角色才開本；舊角色全部攤開
                return
            p.unfold = rules.new_book()
            p.hints_seen.update(rules.REPLACED_HINTS)
        from . import cards  # noqa: PLC0415

        a = ctx.content.config.arts
        ready = frozenset({"tab:craft"}) if "tab:craft" not in p.unfold.grown and cards.fuse_pair(ctx) else frozenset()
        rules.grow(ctx.state, opening_pending=pending, ready=ready, create_price=a.create_first_xinde or a.create_xinde)
        if not pending:
            cards.look(ctx, p.unfold)

    def on_sync(self, ctx, elapsed: float) -> None:
        self._look(ctx)

    def after_action(self, ctx) -> list[str]:
        self._look(ctx)
        return []

    def on_season_start(self, ctx, old) -> None:
        if old is not None and old.player.unfold is not None and ctx.state.player.unfold is None:
            ctx.state.player.unfold = old.player.unfold.model_copy(deep=True)

    def status(self, ctx) -> dict:
        from . import rules  # noqa: PLC0415

        book = ctx.state.player.unfold
        if book is None or ctx.state.player.bot:
            return {}
        from . import cards  # noqa: PLC0415

        return {"unfold": {"hide": rules.hidden(book), "fresh": list(book.fresh), "card": cards.view(book)}}

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)


FEATURE = UnfoldFeature()
