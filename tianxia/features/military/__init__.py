"""軍情（功能包；開發規範手冊 3.2）：軍令卡與押糧（接下糧車、走到終點交軍令）、第 2 階行動、第 3／4 階行動（煽動起事、修築塢堡、趁亂占據郡縣）、
第 4 階席次的抄帳、管理者重發軍令／輪替席次／發召見。全部拆包第 33 批搬進來（計畫 docs/superpowers/plans/2026-11-05-軍情包-第1批.md）。
README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

第 34 批「軍情二」加進來：機緣（opp_rules.py，原本的 tianxia/opportunities.py）與伏筆（fs_rules.py，原本的 tianxia/foreshadow.py）的規則、
動作（opp_actions.py、fs_actions.py）、假人分數（bots.py）。選項前綴 opp:、fs: 接 choose 掛鉤；效果三格與叛投兩格由這一包登記；核心與共用規則層讀的只讀那一半
留在 tianxia/core/omen_base.py（查詢服務）。下面「沒有選項前綴」那一段只講第 33 批搬進來的那幾樣（act: 開頭的）。

包名不叫 `orders`：`tianxia/orders.py`（軍令的規則）、`ranks.py`、`seats.py` 這一批不搬（共用規則層，第 40 批收進），包裡照 `registry.SHARED` import。

沒有選項前綴：`act:rank2`、`act:convoy`、`act:summons`、`act:rank:<行動>` 都是核心 `_act` 的 act 子動詞（行動列），選單那三段、按下去、抄帳、管理者的鈕都在核心原位叫
Game 上的一行委派（理由在 tests/core/test_feature_boundaries.py 的 `# military` 那一段）；掛鉤只有叛投那一刻的格（defection：clear 位置的 convoy，第 32 批）；沒有路由（server.py 的 `orders`、`convoy` 兩個鍵與管理者三顆鈕照舊叫 Game）。
假人分數（`act:rank2`、`act:convoy`、`act:summons`）留在 bot_policy.score 的 act 分支原位。
"""
from __future__ import annotations

from tianxia.core.features import BusHook, DefectHook, EffectHook, Feature, Outcome, SeamHook, StepHook


class MilitaryFeature(Feature):
    name = "military"
    # 第 34 批：機緣 opp:<…>（交東西、嘗試、拼圖、呈交、指認、請命、響應、各做一處）與伏筆 fs:<鏈>、fs:<鏈>:<選項>、fs:leave
    prefix = ("opp", "fs")
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：押著的糧車、第 2 階今天做了幾次、第 3／4 階這週做了幾次（第 33 批）；
    # 伏筆 7 個（聽過的片段、拿到的物品、計數、做完的鏈、冷卻、正在答的鏈與已答的題）與機緣 8 個（做完的、次數、拿到的東西、各處的戰線、
    # 聽過的線索、試過的時段、拼圖湊了哪幾樣、結算過的密謀）（第 34 批）。換季全部跟著新角色重來
    player_fields = (
        "convoy", "rank2_days", "rank_action_weeks",
        "fragments", "clue_items", "fs_counters", "fs_done", "fs_cooldown_until", "fs_asking", "fs_asked",
        "opp_done", "opp_counts", "opp_items", "opp_fronts", "opp_clues", "opp_tried", "opp_pieces", "opp_settled",
    )
    carried: tuple[str, ...] = ()
    # 第 2 階晉升奇遇與晉升表（第 33 批）、機緣、伏筆與準備事件（第 34 批；總表附錄甲）；content.py 照舊讀（第 62 批起照它載）；檔名照舊
    content = ("promotions.json", "events/promotion.json", "opportunities.json", "foreshadows.json", "events/foreshadow_fragments.json", "events/foreshadow_prep.json")

    def enabled(self, ctx) -> bool:
        return True

    def on_drop_stale(self, ctx) -> None:
        """內容改版後拿掉的伏筆鏈與物品：撿到的物品、聽過的片段、正在答的鏈清掉（原本接在 _drop_stale_references 的 snubbed_until 之前，現在接在最後；
        中間到 features_core.on_drop_stale 沒有任何一行讀 clue_items、fragments、fs_asking、fs_asked）。"""
        p = ctx.state.player
        chains = {ch.id for ch in ctx.content.foreshadows.chains}
        items = {item.id for item in ctx.content.foreshadows.items}
        p.clue_items = {k: v for k, v in p.clue_items.items() if k in items and v > 0}
        p.fragments = {k: v for k, v in p.fragments.items() if k in chains}
        if p.fs_asking is not None and p.fs_asking not in chains:
            p.fs_asking, p.fs_asked = None, 0

    def choose(self, ctx, kind, arg):
        """opp:<…> 與 fs:<…>（原本 Game.choose 的 `elif kind == "opp"`、`"fs"` 兩支，夾在 road 與 invite 中間；前後沒有別支會吃掉這兩個 kind）。
        標題照原本 Game._action_title 的那兩支（機緣 opp_rules.title；伏筆「作罷」或「<這一趟>・<所在>」），動作之前先拿。"""
        if kind == "opp":
            from . import opp_rules  # noqa: PLC0415

            return Outcome(
                title=opp_rules.title(ctx.state, ctx.content, arg),
                run=lambda: opp_rules.act(ctx.state, ctx.content, ctx.world, arg, ctx.rng),
            )
        if kind == "fs":
            from . import fs_actions  # noqa: PLC0415

            here = ctx.content.locations[ctx.state.player.location].name
            title = "作罷" if arg == "leave" else f"{fs_actions.trip_label(ctx, arg.partition(':')[0])}・{here}"
            return Outcome(title=title, run=lambda: fs_actions.foreshadow(ctx, arg))
        return None

    def bot_pick(self, ctx, option):
        """假人看到 opp:、fs: 的選項怎麼按：都不按（原本 bot_policy.score 的 `if kind == "opp": return None`；fs: 原本走到 score 最後一行的 None）。"""
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    # core_effects（全部拆包第 32 批「效果與叛投掛鉤」）
    _defection: tuple[DefectHook, ...] | None = None
    _effects: tuple[EffectHook, ...] | None = None

    def defection(self) -> tuple[DefectHook, ...]:
        """叛投：clear 位置的 convoy 那一格（押著的糧車；原本 defection.clear_progress 直接寫 p.convoy）與 opportunities 那一格（機緣的進度，
        第 34 批；原本是核心代叫表 defection._CLEAR_CORE 的一格），leave 位置的 plots 那一格（還開著的密謀全部退出；原本 defection._LEAVE_CORE）：
        不問 enabled。那兩張核心代叫表第 35 批陣營成包時拿掉了（progress 那一格改由陣營包登記）。
        建一次就留著，在叫的那一下才照模組屬性找 convoy_actions.defect_clear、opp_rules.clear、opp_rules.leave_plots（monkeypatch 照樣有效）。"""
        if self._defection is None:
            from . import convoy_actions, opp_rules  # noqa: PLC0415

            self._defection = (
                DefectHook("clear", "convoy", lambda p: convoy_actions.defect_clear(p)),
                DefectHook("clear", "opportunities", lambda p: opp_rules.clear(p)),
                DefectHook("leave", "plots", lambda state: opp_rules.leave_plots(state)),
            )
        return self._defection

    def effects(self) -> tuple[EffectHook, ...]:
        """效果的三格（第 34 批；原本 rules._EFFECT_CORE 的 grain、fs_fragments、foreshadow）：捐糧、直接給伏筆片段、伏筆物品與計數。不問 enabled。
        建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）。格的位置照 EFFECT_ORDER。"""
        if self._effects is None:
            from . import fs_rules  # noqa: PLC0415

            self._effects = (
                EffectHook("grain", lambda r: fs_rules.effect_grain(r)),
                EffectHook("fs_fragments", lambda r: fs_rules.effect_fragments(r)),
                EffectHook("foreshadow", lambda r: fs_rules.effect_clues(r)),
            )
        return self._effects

    # core_eventbus（全部拆包第 26 批「事件機制」）
    _bus: tuple[BusHook, ...] | None = None

    def bus(self) -> tuple[BusHook, ...]:
        """事件 arrive 的 convoy 那一格（抵達一站：糧車到了終點就交糧；原本 Game._arrive 經 _convoy_arrives 委派直接叫；現在發布點在移動包 departure.arrive）：排在懸賞護送之前
        （BUS_ORDER）。不問 enabled（押糧的判斷都在 convoy_arrives 裡）。建一次就留著，在叫的那一下才照模組屬性找 convoy_actions.convoy_arrives。"""
        if self._bus is None:
            from . import convoy_actions  # noqa: PLC0415

            self._bus = (BusHook("arrive", "convoy", lambda ctx, loc_id: convoy_actions.convoy_arrives(ctx, loc_id)),)
        return self._bus

    # core_step（全部拆包第 36 批「你這一步」）
    _steps: tuple[StepHook, ...] | None = None

    def steps(self) -> tuple[StepHook, ...]:
        """「你這一步」的 order 與 foreshadow 兩格（原本 weekcard._steps 的軍令、伏筆那兩段與 step._target、_then 的那兩支）：位置在 STEP_ORDER。
        不問 enabled（軍令看殼傳進來的 orders_view、伏筆看 next_step，判斷都在被叫的函式裡）。讀伏筆就是 foreshadow 那一格，核心不再讀。
        建一次就留著，在叫的那一下才照模組屬性找 order_actions.step_items／step_place、fs_actions.step_items／step_place（monkeypatch 照樣有效）。"""
        if self._steps is None:
            from . import fs_actions, order_actions  # noqa: PLC0415

            self._steps = (
                StepHook("order", lambda ctx, status, orders: order_actions.step_items(ctx, orders), ref="order",
                         place=lambda ctx, ref: order_actions.step_place(ctx, ref)),
                StepHook("foreshadow", lambda ctx, status, orders: fs_actions.step_items(ctx), ref="foreshadow",
                         place=lambda ctx, ref: fs_actions.step_place(ctx, ref)),
            )
        return self._steps

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """sync.deliver 的兩格（順序在 SEAM_ORDER；不問 enabled）：密謀結算（opp_actions.deliver_plots）、席次抄帳與補缺（seat_actions.deliver_seat，排在抵達與密謀之後，test_seats 守）。"""
        if self._seams is None:
            from . import opp_actions, seat_actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.deliver", "plots", lambda ctx: opp_actions.deliver_plots(ctx)),
                SeamHook("sync.deliver", "seat", lambda ctx: seat_actions.deliver_seat(ctx)),
            )
        return self._seams


FEATURE = MilitaryFeature()
