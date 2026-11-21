"""異聞（功能包；開發規範手冊 3.2；設計 docs/superpowers/specs/2026-11-20-異聞-design.md，企劃者 2026-11-21「看過了，十題都照建議做」；
做法照總計畫 docs/superpowers/plans/2026-11-21-異聞-計畫.md）。README.md 寫這一包做什麼、導覽與設計稿。第 247 批：骨架、不叫模型的發掘、重放。

- rules.py：純規則（開關、季鐘、內容檔、種子、模板句、獎勵表）；store.py：旁檔 <db>-yiwen.sqlite。
- actions.py：探索撞見那一格（BUS_ORDER 的 outing）、選單接管、走一步、走完、放下、status（main.yiwen）。
- routes.py：鎖外工作的 op /api/do/yiwen_step（這一批是平鋪：進鎖就做，不叫模型）。
- checks.py：兩個內容檔的驗證（check_content）。bots.py：假人不碰這一包。
- 易名帖改名時旁檔裡的鍵跟著換：載入這一包就登記到核心 core/renames（旁檔在才開，關著的伺服器改名不建出空旁檔）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core import renames
from tianxia.core.features import BusHook, Feature, Outcome


def _rename(db_path, old: str, new: str) -> None:
    from . import store  # noqa: PLC0415

    if store.side_path(db_path).is_file():
        store.for_db(db_path).rename(old, new)


renames.register(_rename)


class YiwenFeature(Feature):
    name = "yiwen"
    prefix = "yiwen"  # yiwen:open（回到異聞）、yiwen:drop（放下／收起）：只有撞見之後接管選單的那兩顆；撞見卡上的鈕走 /api/do/yiwen_step
    web: tuple[str, ...] = ("yiwen.js", "yiwen.css")  # 撞見卡、每一幕、收尾卡（江湖頁；main.yiwen）
    content: tuple[str, ...] = ("yiwen_openings.json", "yiwen_lines.json")  # 包自己讀（rules.FILES），Content 不加欄位
    player_fields: tuple[str, ...] = ("yiwen",)  # PlayerState.yiwen（YiwenWalk；None 起家）
    carried: tuple[str, ...] = ()  # 換季清掉

    def enabled(self, ctx) -> bool:
        return ctx.content.config.yiwen.enabled  # 預設關；數字在 tianxia/core/tuning/yiwen.py；還要開季蓋章 WorldState.yiwen_on（rules.on）

    def menu(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.menu(ctx)

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.title(ctx), run=lambda: actions.act(ctx, arg))

    # core_eventbus：探索那一下撞見一則（BUS_ORDER 的 outing 那一列尾端；企劃者 2026-11-21「五處都可以」）
    _bus = None

    def bus(self):
        if self._bus is None:
            from . import actions  # noqa: PLC0415

            self._bus = (BusHook("outing", "yiwen", lambda ctx, loc_id: actions.on_explore(ctx, loc_id)),)
        return self._bus

    def status(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.status(ctx)

    def on_sync(self, ctx, elapsed) -> None:
        from . import actions  # noqa: PLC0415

        lines = actions.on_sync(ctx, elapsed)
        if lines:
            ctx._write(actions.GONE_TITLE, lines)

    def on_season_start(self, ctx, old) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_season_start(ctx, old)

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415

        return routes.outlock(shell)

    def check_content(self, content, need) -> None:
        from . import checks  # noqa: PLC0415

        checks.check_content(content, need)


FEATURE = YiwenFeature()
