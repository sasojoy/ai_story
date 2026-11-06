"""宴客（大勢人物擴充第三批：人物設宴、玩家入席敬酒、席間最佳上天下大事；功能包，開發規範手冊 3.2、3.10 第 1 階的「有按鈕的小包」）。
README.md 寫這一包做什麼、導覽與設計稿。

- rules.py：純規則（原 tianxia/feasts.py；那個名字留成指到這裡的別名）
- actions.py：原本 Game 上的 _feast_*、feast_*（Game 留一行委派給 server 的三段式與場景卡）
- bots.py：假人的分數（原本 bot_policy.score 的那一段）
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome, WorldHook


class FeastFeature(Feature):
    name = "feast"
    prefix = "feast"  # feast:join:<id>、feast:toast:<i>、feast:leave
    bot_always = ("feast:",)  # 入席離席不花體力、一直按得下去：整季機器人不按（原本 bot.pick 的排除）
    player_fields = ("feasting", "feasts_paid")  # 坐在哪一場、這一季領過名望的宴；換季跟著新角色重來
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """宴客開著（figure_life 與 Config.figure_life.feasts），或這一季還有擺過的宴：關掉那一刻擺著的宴照散（world 的 settle 本來就
        「開關關著也照散」）、席間最佳的名望照領、坐著的人選單照收（搬包之前就是這樣，行為一個字不變）。"""
        from . import rules  # noqa: PLC0415

        return rules.on(ctx.content) or bool(ctx.state.world.feasts)

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

    def on_sync(self, ctx, elapsed) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_sync(ctx)

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    def scene(self, ctx):
        """自己眼前的場景卡（接縫掛鉤，全部拆包第 11 批；原本 Game._own_scene_text 擂台之後那一行）：坐在宴席上時是主人、地方、最近三句
        敬酒詞那一張；沒坐著是 None。不問 enabled：原位本來就不看宴客開關。"""
        from . import actions  # noqa: PLC0415

        return actions.scene(ctx)

    # core_world（全部拆包第 25 批「世界層掛鉤」）
    _world: tuple[WorldHook, ...] | None = None

    def world(self) -> tuple[WorldHook, ...]:
        """世界層 step 的 feast 那一格（時間到了的宴散席；原本 world.advance_world_state 直接叫 feasts.settle）：不問 enabled。
        建一次就留著，在叫的那一下才照模組屬性找 rules.world_step（monkeypatch 照樣有效）。
        core_world2（全部拆包第 40 批）：世界層 life 的 feast 那一格（設宴；原本 figure_life.tick 每一輪每一位對話人物直接叫 feasts.maybe_open）。"""
        if self._world is None:
            from . import rules  # noqa: PLC0415

            self._world = (
                WorldHook("step", "feast", lambda *args: rules.world_step(*args)),
                WorldHook("life", "feast", lambda *args: rules.maybe_open(*args)),  # core_world2
            )
        return self._world

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415  只在殼建鎖外工作時才 import（同 routes 掛鉤）

        return routes.outlock(shell)


FEATURE = FeastFeature()
