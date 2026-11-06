"""體力玩法：設伏劫道、屯糧練兵（後期體力玩法第一批，Joy 2026-10-16；功能包，開發規範手冊 3.2；全部拆包第 39 批，小包併批）。
README.md 寫這一包做什麼、導覽與設計稿。

- ambush_rules.py、works_rules.py：純規則（原 tianxia/ambush.py、tianxia/works.py；那兩個名字留成指到這裡的別名）
- ambush_actions.py：原本 Game 上的 _ambush_*（Game 留一行委派給 sync、_arrivals 與測試）
- works_actions.py：原本 Game 上的 _works_act
- actions.py：原本 Game._stamina_play_options 的前半（設伏／收伏、屯糧兩段選項；Game 留接縫，後半護衛、功能包選項、盤算照舊）
- bots.py：假人的分數（原本 bot_policy.score 的 ambush／works 那一段）
"""
from __future__ import annotations

from tianxia.core.features import Feature, HowtoHook, Outcome, WorldHook


class StaminaPlaysFeature(Feature):
    name = "stamina_plays"
    prefix = ("ambush", "works")  # ambush:set:<地點>、ambush:lift；works:stockpile
    bot_always = ("ambush:", "works:")  # 體力夠就一直按得下去、收伏一直按得下去：整季機器人不按（原本 bot.pick 的排除）
    player_fields = ("ambush",)  # 守著的那一處（AmbushPost）；換季照 _reset_player_for_new_season 重來
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """一律開著：choose 與 bot_pick 原位本來就不看開關（設伏看 Config.ambush、屯糧看 Config.stockpile，判斷在 set_problem、stock_spot 裡，
        關著照舊回「此刻無法這麼做」）；選項不走 Feature.options（見 actions.py）。搬包之前就是這樣，行為一個字不變。"""
        return True

    def choose(self, ctx, kind, arg):
        if kind == "ambush":
            from . import ambush_actions, ambush_rules  # noqa: PLC0415

            title = "收伏" if arg == "lift" else f"{ambush_rules.TITLE}・{ctx.content.locations[ctx.state.player.location].name}"
            return Outcome(title=title, run=lambda: ambush_actions.act(ctx, arg))
        if kind == "works":
            from . import works_actions, works_rules  # noqa: PLC0415

            title = f"{works_rules.STOCK_TITLE}・{ctx.content.locations[ctx.state.player.location].name}"
            return Outcome(title=title, run=lambda: works_actions.act(ctx, arg))
        return None

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    # core_world（全部拆包第 25 批「世界層掛鉤」）
    _world: tuple[WorldHook, ...] | None = None

    def world(self) -> tuple[WorldHook, ...]:
        """世界層 muster 的 works 那一格（時刻表決戰剛開集結：兩軍屯的量換成起點的偏移；原本 world._muster_works 函式裡 import 舊名 works 叫
        on_muster）：不問 enabled（原位不看包的開關，判斷在 on_muster 裡）。位置在 WORLD_ORDER 的「起點」之後、「玉璽」之前，一個字不動。
        建一次就留著，在叫的那一下才照模組屬性找 works_rules.on_muster（monkeypatch 照樣有效）。簽名 (store, content, definition, start, now)，
        on_muster 只要前三個。"""
        if self._world is None:
            from . import works_rules  # noqa: PLC0415

            self._world = (WorldHook("muster", "works", lambda store, content, definition, start, now: works_rules.on_muster(store, content, definition)),)
        return self._world

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的ambush 那一格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (HowtoHook("ambush", lambda content, season, page: words.ambush_lines(content)),)


FEATURE = StaminaPlaysFeature()
