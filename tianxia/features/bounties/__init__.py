"""懸賞榜（討伐、打探、護送、求兵、通緝、人物託付與求援）。功能包，開發規範手冊 3.2；全部拆包第 45 批搬進來（引擎那一半；網頁那一半 web/ 第 3 階才切）。
包名 bounties 跟設定 Config.bounties、季上的 WorldState.bounties 同字，不是同一件事：這裡是功能包，另兩個是舊的名字。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- rules.py：懸賞榜的規則（原 tianxia/bounties.py；那個名字留成指到這裡的別名）。別人讀的那一半在核心 core/bounty_base.py，rules re-export 同一批
- wanted.py：通緝掛上玩家卡（原 tianxia/wanted.py，別名；載入這一包時登記進核心的 cards.ACTIONS）
- actions.py：懸賞榜第二、三層的選單與選單上按下去的一下、打開榜、掛通緝、截殺打贏的發布點、退押金與作廢、系統通緝（原本 Game 上的 4 個方法與 _act、sync、own_turn_checks 裡那幾行）
- step_actions.py：「你這一步」的委託與懸賞兩格（原本 step._STEP_CORE）
- bots.py：假人的分數（原本 bot_policy.score 的 bounty 那一段）

接縫掛鉤：choose（bounty:*）、verbs（act:bounties 打開榜與紀錄標題）、bot_pick、bus（六種事件交差）、world（step、week、day、start 掛單）、steps（commission、bounty）、defection（stranded）。
店面登記（Shop）不登記、走 MENU_ORDER（第 56 批選單收接縫定案，計畫第四節：入口排在鐵匠鋪、馬市前面；drop_shops 會在 sync.close 多收一次）：menus() 登記選單、入口、_shop_open、出發收店、動身被擋那幾格。
"""
from __future__ import annotations

from tianxia.core.features import BusHook, DefectHook, Feature, MenuHook, Outcome, SeamHook, StepHook, Verb, WorldHook

from . import wanted as _wanted_card  # noqa: F401  通緝登記進玩家卡的動作表（core/cards.py 的 ACTIONS）；載入這一包就登記（原本 engine.py 頂端 import 它；scripts/test_for.py 認這個寫法）


class BountiesFeature(Feature):
    name = "bounties"
    prefix = "bounty"  # bounty:take:<id>、drop、pick、give:<id>:<東西>、unpick、back；灰掉的 more、none、empty 按不下去；入口 act:bounties 是核心的前綴
    # 榜開著沒、第三層指著哪一張：換季跟著新角色重來。bounties_done 是交差的總數（寫在 rules._complete；新手目標、行狀、傳承讀）
    # 店面共用的 shop_line／shop_clue／shop_hold（七間店共用，核心）不在這裡；Bounty 類別與 WorldState.bounties、rallies、bounty_seq、bounty_week、bounty_day 的定義在核心 state.py
    player_fields = ("picking_bounty", "bounty_pick", "bounties_done")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """懸賞榜開著（bounty_base.active：設定開著、劇本有陣營、這一季還沒收），或此刻還坐在榜前：季收了、開關被關掉（還沒經過 sync 收店）照樣按得到「返回」、
        假人照樣按得到——搬包之前 choose 的 bounty 那一支、bot_policy.score 的那一段都不看開關。"""
        from tianxia.core import bounty_base  # noqa: PLC0415

        return bounty_base.active(ctx.state, ctx.content) or ctx.state.player.picking_bounty

    def choose(self, ctx, kind, arg):
        """bounty:*（懸賞榜第二、三層選單上的每一顆）：標題「懸賞榜」（原 Game._action_title 的 bounty 那一支），動作照原 Game._bounty。
        FB-162 被搶的那一句（選單上沒有的 bounty: 回為什麼不成）、翻頁不寫紀錄仍在 Game.choose 原位，在這個掛鉤之前與之後。"""
        if kind != self.prefix:
            return None
        from tianxia.core import bounty_base  # noqa: PLC0415

        from . import actions  # noqa: PLC0415

        return Outcome(title=bounty_base.BOARD, run=lambda: actions.bounty(ctx, arg))

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)

    # ── 接縫掛鉤（不問 enabled，原位本來就不看開關；判斷都在被叫的函式裡）──

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:bounties 的主人（act 子動詞）：按下去打開榜（actions.enter：不花體力、從第二層開始、榜吏那一句；原本 Game._act 中段那幾行）、
        紀錄標題「懸賞榜・此地」（原本 Game._action_title 那張表的 bounties）。進榜那一顆（此地還能做）是 here/bounties 那一格（第 56 批）。"""
        if self._verbs is None:
            from tianxia.core import bounty_base  # noqa: PLC0415

            from . import actions  # noqa: PLC0415

            self._verbs = (Verb("bounties", run=lambda ctx, prepared: actions.enter(ctx),
                                title=lambda ctx: f"{bounty_base.BOARD}・{ctx.content.locations[ctx.state.player.location].name}"),)
        return self._verbs

    _bus: tuple[BusHook, ...] | None = None

    def bus(self) -> tuple[BusHook, ...]:
        """事件的六格（原本 engine._BUS_CORE 的 win、outing、explore、arrive、raid_win 五格，加第 45 批開的 aid）：交差。位置在 BUS_ORDER（arrive 排在 convoy 後面、outing 排在 seal 前面）。
        outing 與 explore 都是 on_explore（打探）。建一次就留著，在叫的那一下才照模組屬性找 rules.on_*（monkeypatch 照樣有效）。"""
        if self._bus is None:
            from . import rules  # noqa: PLC0415

            self._bus = (
                BusHook("win", "bounties", lambda ctx, loc_id, squad_id: rules.on_win(ctx, loc_id, squad_id)),
                BusHook("outing", "bounties", lambda ctx, loc_id: rules.on_explore(ctx, loc_id)),
                BusHook("explore", "bounties", lambda ctx, loc_id: rules.on_explore(ctx, loc_id)),
                BusHook("arrive", "bounties", lambda ctx, loc_id: rules.on_arrive(ctx, loc_id)),
                BusHook("raid_win", "bounties", lambda ctx, target: rules.on_raid_win(ctx, target)),
                BusHook("aid", "bounties", lambda ctx, cid: rules.on_aid(ctx, cid)),
            )
        return self._bus

    _world: tuple[WorldHook, ...] | None = None

    def world(self) -> tuple[WorldHook, ...]:
        """世界層的四格（原本 world._STEP_CORE、_WEEK_CORE、_DAY_CORE、_START_CORE 的 bounties）：規則關著的季跨週掛單（step_tick）、週初（issue）、每天（issue_day）、開季（tick）。
        格的位置照 WORLD_ORDER、簽名照原樣。建一次就留著，在叫的那一下才照模組屬性找。"""
        if self._world is None:
            from . import rules  # noqa: PLC0415

            self._world = (
                WorldHook("step", "bounties", lambda vehicle, content, store, step: rules.step_tick(vehicle, content, store, step)),
                WorldHook("week", "bounties", lambda state, content, rng: rules.issue(state, content, state.world.hooked_week, rng)),
                WorldHook("day", "bounties", lambda state, content, rng: rules.issue_day(state, content, state.world.hooked_day, rng)),
                WorldHook("start", "bounties", lambda state, content, rng: rules.tick(state, content)),
            )
        return self._world

    _steps: tuple[StepHook, ...] | None = None

    def steps(self) -> tuple[StepHook, ...]:
        """「你這一步」的 commission 與 bounty 兩格（原本 step._STEP_CORE）：位置在 STEP_ORDER。commission 的 ref 是 "errand"（格名與 ref 分開記，STEP_ORDER 底下那張表）。
        建一次就留著，在叫的那一下才照模組屬性找。"""
        if self._steps is None:
            from . import step_actions  # noqa: PLC0415

            self._steps = (
                StepHook("commission", lambda ctx, status, orders: step_actions.commission_items(status), ref="errand",
                         place=lambda ctx, ref: step_actions.bounty_place(ctx, ref)),
                StepHook("bounty", lambda ctx, status, orders: step_actions.bounty_items(status), ref="bounty",
                         place=lambda ctx, ref: step_actions.bounty_place(ctx, ref)),
            )
        return self._steps

    _defection: tuple[DefectHook, ...] | None = None

    def defection(self) -> tuple[DefectHook, ...]:
        """叛投 stranded 那一格（原本陣營包 defection._STRANDED_CORE）：手上舊陣營掛的懸賞作廢、每張一句（FB-151）；改的是共用的季，Game.choose 結尾統一存。"""
        if self._defection is None:
            from tianxia.core import bounty_base  # noqa: PLC0415

            self._defection = (DefectHook("stranded", "bounties", lambda s, c, side: bounty_base.drop_stranded(s, c, side)),)
        return self._defection

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的三格（順序在 SEAM_ORDER；不問 enabled：on_sync、on_own_turn 問的不是這個位置）：sync 退押金與作廢（actions.deliver）、本人這一輪暫停那一道之後的系統通緝（actions.post_auto）、
        清失效參照收懸賞榜（actions.drop_stale）。"""
        if self._seams is None:
            from . import actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.deliver", "bounties", lambda ctx: actions.deliver(ctx)),
                SeamHook("own_turn", "bounties", lambda ctx: actions.post_auto(ctx)),
                SeamHook("stale.mid", "bounties", lambda ctx: actions.drop_stale(ctx)),
            )
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單與動身的格（順序在 MENU_ORDER；不問 enabled）：懸賞榜不進店面登記 Shop（計畫第四節：入口排在鐵匠鋪、馬市前面，_shops 照 FEATURES 排在最後；drop_shops 會多收一次）：榜開著接管整個選單、不算閒著、店面那一頁、動身收起來、動身被擋；此地那一顆。"""
        if self._menus is None:
            from tianxia.core import bounty_base  # noqa: PLC0415
            from . import actions  # noqa: PLC0415

            self._menus = (
                MenuHook("take", "bounties", lambda ctx: actions.options(ctx) if ctx.state.player.picking_bounty else None),
                MenuHook("here", "bounties", lambda ctx, loc, cost, odds: actions.here_cell(ctx, loc, cost, odds)),
                MenuHook("idle", "bounties", lambda ctx: ctx.state.player.picking_bounty),
                MenuHook("open", "bounties", lambda ctx: actions.open_cell(ctx)),
                MenuHook("depart", "bounties", lambda ctx: bounty_base.close_board(ctx.state.player)),
                MenuHook("block", "bounties", lambda state, content: actions.travel_block(state, content)),
            )
        return self._menus


FEATURE = BountiesFeature()
