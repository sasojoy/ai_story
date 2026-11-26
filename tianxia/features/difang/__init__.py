"""地方大事（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

- rules.py：純規則（開關、內容檔、這一週挑哪一件、三幕要多少、成算、一下多重）。
- actions.py：換週、三幕出力（outing、win 兩個事件的格；第二、三幕是此地還能做的選項）、收場（江湖史、饑荒、同步時領那一份）、畫面那一份（main.difang）。
- bots.py：假人照公開行動出力。checks.py：內容檔的驗證。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import BusHook, Feature, Outcome


class DifangFeature(Feature):
    name = "difang"
    prefix = "difang"  # difang:way:<i>（第二幕的做法）、difang:strike（第三幕上前）
    web: tuple[str, ...] = ("difang.js", "difang.css")  # 江湖頁眼下那一件與點開的那一頁（main.difang）
    content: tuple[str, ...] = ("difang.json",)  # 包自己讀（rules.FILE），Content 不加欄位
    player_fields: tuple[str, ...] = ()  # 沒有玩家欄位：帳全在 WorldState.difang
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return ctx.content.config.difang.enabled  # 預設關：讀 Config.difang.enabled；數字在 tianxia/core/tuning/difang.py

    def options(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.options(ctx)

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.title(ctx), run=lambda: actions.act(ctx, arg))

    # core_eventbus：第一幕的一份力（探索一顆收尾、打贏一場）
    _bus = None

    def bus(self):
        if self._bus is None:
            from . import actions  # noqa: PLC0415

            self._bus = (
                BusHook("outing", "difang", lambda ctx, loc_id: actions.on_outing(ctx, loc_id)),
                BusHook("win", "difang", lambda ctx, loc_id, squad_id: actions.on_win(ctx, loc_id, squad_id)),
            )
        return self._bus

    def status(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.status(ctx)

    def on_sync(self, ctx, elapsed) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_sync(ctx)

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    def check_content(self, content, need) -> None:
        from . import checks  # noqa: PLC0415

        checks.check_content(content, need)


FEATURE = DifangFeature()
