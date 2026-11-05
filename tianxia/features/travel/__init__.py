"""移動（一）：移動選單（步行、疾行）、路上三樣小事、路上見聞、喊停、折返、安排前往（功能包，開發規範手冊 3.2；全部拆包第 47 批）。
README.md 寫這一包做什麼、導覽與設計稿。

- menu.py：原本 Game 上的 _move_option、_back_way、_back_option、_road_task_options、set_move_mode（Game 留一行委派給選單、server、測試）
- road_actions.py：原本 Game 上的 _move、_road、_road_*、_road_sight（_road_sight、_road_reward_due、_count_road_reward 留委派，
  給 _arrivals 與第 48 批的 _share_road）
- go_actions.py：原本 Game 上的 _halt、travel、travel_refusal（travel、travel_refusal 留委派）
- bots.py：假人的分數（原本 bot_policy.score 的 move: 那一段）
- routes.py：POST /api/travel（原本 server.py 的 api_travel）

出發（_depart）與抵達（_arrive、_arrivals）、結伴同行、前往的補算是第 48 批（移動二），這一批都經 ctx 叫、位置不動。
"""
from __future__ import annotations

from tianxia import atlas  # 過渡：待搬（輿圖：路程、走法、折返的路）
from tianxia.core.features import Feature, Outcome, Verb
from tianxia.core.services import ROAD_TASKS


class TravelFeature(Feature):
    name = "travel"
    prefix = ("move", "road")  # move:<地點>[:<走法>]；road:back[:<走法>]、road:think／ask／gather
    bot_always = ("road:",)  # 路上小事按完還有、折返隨時能按：整季機器人不按（原本 bot.pick 的排除；move: 不在這裡，站著的時候它是正常的選項）
    player_fields = ("leg_actions", "recent_sights", "road_rewards_today")  # 這一段做過的路上小事、最近看過的見聞、今天拿過幾次路上收穫；換季照 _reset_player_for_new_season 重來
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """一律開著：choose 與 bot_pick 原位本來就不看開關；選單不走 Feature.options（見 menu.py）。搬包之前就是這樣，行為一個字不變。"""
        return True

    def choose(self, ctx, kind, arg):
        if kind == "move":
            from . import road_actions  # noqa: PLC0415

            return Outcome(title=f"前往 {ctx.content.locations[arg.partition(':')[0]].name}", run=lambda: road_actions.move(ctx, arg))
        if kind == "road":
            from . import menu, road_actions  # noqa: PLC0415

            what = arg.partition(":")[0]
            if what == "back":
                title = atlas.journey_title(ctx.content, menu.back_way(ctx).path)  # 折返：跟「前往」同一個標題，抵達時才併得進同一則
            else:
                title = ROAD_TASKS[what][0]
            return Outcome(title=title, run=lambda: road_actions.road(ctx, arg))
        return None

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option, ctx.state.player.bot)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:halt 那一格（act 子動詞，第 11 批）：按下去（go_actions.halt）與紀錄標題「喊停」（原本 Game._action_title 那張表的 halt 一格）。
        選單上的 act:halt 那一顆在路上那串裡（Game._options，順序算行為），不在這裡。建一次就留著，在叫的那一下才照模組屬性找函式。"""
        if self._verbs is None:
            from . import go_actions  # noqa: PLC0415

            self._verbs = (Verb("halt", run=lambda ctx, prepared: go_actions.halt(ctx), title=lambda ctx: "喊停"),)
        return self._verbs


FEATURE = TravelFeature()
