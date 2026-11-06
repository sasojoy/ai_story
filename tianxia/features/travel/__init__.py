"""移動（一）：移動選單（步行、疾行）、路上三樣小事、路上見聞、喊停、折返、安排前往（功能包，開發規範手冊 3.2；全部拆包第 47 批）。
README.md 寫這一包做什麼、導覽與設計稿。

- menu.py：原本 Game 上的 _move_option、_back_way、_back_option、_road_task_options、set_move_mode（Game 留一行委派給選單、server、測試）
- road_actions.py：原本 Game 上的 _move、_road、_road_*、_road_sight（第 48 批 _arrivals 搬進 departure.py，直接叫 sight；委派拿掉）
- go_actions.py：原本 Game 上的 _halt、travel、travel_refusal（travel、travel_refusal 留委派）
- departure.py：原本 Game 上的 _depart、_arrivals、_arrive、_journey_line（第 48 批；都留一行委派）
- party.py：原本 Game 上結伴同行的 _join、join_refusal、_party_expires、_party、party_view、leave_party、_part_ways、_lead、_partners、_share_road
  （_join、join_refusal、_party_expires、party_view 留委派）
- bots.py：假人的分數（原本 bot_policy.score 的 move: 那一段）
- routes.py：POST /api/travel、POST /api/party/leave（原本 server.py 的 api_travel、api_party_leave）

`_arrivals` 每次 sync、advance 都叫，迴圈中途的 _ambush_check → arrive → 騎乘飽足 → 路上見聞先後算行為；`arrive` 是事件 arrive 的發布點。
"""
from __future__ import annotations

from tianxia import atlas  # 共用規則層（輿圖：路程、走法、折返的路；第 50 批收進）
from tianxia.core.features import Feature, Outcome, Verb
from tianxia.core.services import ROAD_TASKS


class TravelFeature(Feature):
    name = "travel"
    prefix = ("move", "road")  # move:<地點>[:<走法>]；road:back[:<走法>]、road:think／ask／gather
    bot_always = ("road:",)  # 路上小事按完還有、折返隨時能按：整季機器人不按（原本 bot.pick 的排除；move: 不在這裡，站著的時候它是正常的選項）
    player_fields = ("leg_actions", "recent_sights", "road_rewards_today", "tagalong")  # 這一段做過的路上小事、最近看過的見聞、今天拿過幾次路上收穫、跟著誰結伴同行；換季照 _reset_player_for_new_season 重來
    content = ("road_sights.json",)  # 路上見聞（road_actions.sight 讀 content.road_sights）
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

        # 正式路徑上 `move:` 由 `bot_policy.score` 先問（第 47 批 PM 認定第 2 條），這裡留給直接叫掛鉤的測試
        return bots.score(ctx, option, ctx.state.player.bot)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:halt、act:part 兩格（act 子動詞，第 11 批、第 48 批）：按下去（go_actions.halt、party.part_ways）與紀錄標題「喊停」「分道揚鑣」
        （原本 Game._action_title 那張表的兩格）。選單上的 act:halt、act:part 那兩顆在路上那串裡（Game._options，順序算行為），不在這裡。
        建一次就留著，在叫的那一下才照模組屬性找函式。"""
        if self._verbs is None:
            from . import go_actions, party  # noqa: PLC0415

            self._verbs = (
                Verb("halt", run=lambda ctx, prepared: go_actions.halt(ctx), title=lambda ctx: "喊停"),
                Verb("part", run=lambda ctx, prepared: party.part_ways(ctx), title=lambda ctx: "分道揚鑣"),
            )
        return self._verbs


FEATURE = TravelFeature()
