"""裝備（修練頁的換上、拆解〔含批量〕、餵馬，馬市的買餵換上，寄放補送，名將贈禮，名將本命兵器，神器譜）。功能包，開發規範手冊 3.2；
全部拆包第 42 批搬進來（引擎那一半）；網頁的畫法在 web/gear.js（第 65 批）。包名 gear 跟測試資料夾 tests/gear/、內容欄位 Content.gear（content/gear.json 讀進來的
GearBook）同字，不是同一件事：這裡是功能包，另兩個是舊的名字。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- signature_arms.py：名將本命兵器的規則（原 tianxia/signature_arms.py；那個名字留成指到這裡的別名）
- market_actions.py：馬市的第二層選單、選單上的選擇、進門（原本 Game 上的 2 個方法與 _act 的 act:market 三行）
- bench_actions.py：修練頁的換上、餵馬、拆解、批量拆解（4 個）
- gift_actions.py：寄放補送、名將贈禮、此刻在身邊的人物、贈禮另起的紀錄、本命兵器（5 個）
- views.py：修練頁裝備那一塊、見聞榜單的神器譜（2 個）
- bots.py：假人的分數（原本 bot_policy.score 的 market 那兩行）

接縫掛鉤：choose（market:*）、verbs（act:market 進門與紀錄標題）、content、bot_pick。沒有 APIRouter（/api/menxia 的四個動作在 routes.py 的 menxia_actions，全部拆包第 68 批；/api/boards、/api/board_card 留在殼，叫 Game 的委派）。
店面登記（Shop）不登記、走 MENU_ORDER（第 56 批選單收接縫定案，計畫第四節；同鐵匠鋪：入口順序 懸賞榜 → 鐵匠鋪 → 馬市是行為）：menus() 登記選單、入口、_shop_open、出發收店、動身被擋那幾格。
checks.py：內容驗證（第二輪第 100 批從 content.py 搬來；改了另外跑 tests/core/test_content.py，test_for 改包帶不到）
"""
from __future__ import annotations

from tianxia.core.features import Feature, MenuHook, Outcome, SeamHook, Verb
from tianxia.core.features import ContentSlot


class GearFeature(Feature):
    name = "gear"
    web = ("gear.js",)  # 裝備格與馬市的畫法（全部拆包第 65 批從 app.js 切出來）。樣子在 shop.css（第 86 批切出來）
    prefix = "market"  # market:buy、market:feed、market:wield:<id>、market:back；入口 act:market 是核心的前綴
    content = ("gear.json",)  # content.py 照它到這一包的 content/ 載（check_gear、check_signature_arms 在 checks.py，content.validate 原位經 check_at 叫，不接 check_content）
    player_fields = ("picking_market",)  # 馬市第二層選單開著沒：換季跟著新角色重來。held_gear 核心與共用層也讀、figure_wins 是大勢人物包的，不認領
    carried: tuple[str, ...] = ()

    # core_content（第二輪第 100 批）：位置固定的內容驗證，先後在 content.validate 那幾行，格在核心 CONTENT_SLOTS；在叫的那一下才照模組屬性找
    def content_slots(self) -> tuple[ContentSlot, ...]:
        from . import checks  # noqa: PLC0415

        return (
            ContentSlot("gear", lambda *a: checks.check_gear(*a)),
            ContentSlot("signature_arms", lambda *a: checks.check_signature_arms(*a)),
        )

    def scratch(self) -> dict:
        """寄放在 Game 上的旗標（第二輪第 92 批；原本在 Game.__init__：核心建 Game 時照 registry.DECLARED 擺上去〔features.scratch_init〕，不進存檔）。"""
        return {
            "_affinity_before": None,  # choose()、隨口應對進行中：這一下之前的情誼（_people_here 認這一下加了誰的情誼）
        }

    def enabled(self, ctx) -> bool:
        """兵器、防具、坐騎、寶物四欄各看自己的 enabled（不看第一季開關；裝備四欄設計 2.6），或此刻還坐在馬市裡：開關在坐著的時候被關掉（沒經過 sync 收店）
        照樣按得到離開、假人照樣只按它——搬包之前 choose 的 market 那一支、bot_policy.score 的那一段都不看開關。"""
        c = ctx.content.config
        return c.weapons.enabled or c.armor.enabled or c.mounts.enabled or c.treasures.enabled or ctx.state.player.picking_market

    def choose(self, ctx, kind, arg):
        """market:*（馬市第二層選單上的每一顆）：標題「馬市」（原 Game._action_title 的 market 那一支），動作照原 Game._market。
        FB-195（選單上沒有或灰掉的 market: 回為什麼不成）仍在 Game.choose 原位，在這個掛鉤之前。"""
        if kind != self.prefix:
            return None
        from tianxia import mounts  # noqa: PLC0415

        from . import market_actions  # noqa: PLC0415

        return Outcome(title=mounts.MARKET, run=lambda: market_actions.market(ctx, arg))

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)

    # ── 接縫掛鉤（全部拆包第 11 批；不問 enabled，原位本來就不看開關）──

    def shop_view(self, ctx, shop) -> dict | None:
        """店面那一頁（core/features.shop_page 問；一間店只有一包認，開頭先認店、不看 ctx；第二輪第 93 批）：馬市。組法在 shop_view.page。"""
        if shop != "market":
            return None
        from . import shop_view as page  # noqa: PLC0415

        return page.page(ctx)

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:market 的主人（act 子動詞）：按下去走進馬市（market_actions.enter：不花體力、馬販那一句；原本 Game._act 中段那幾行）、
        紀錄標題「馬市・此地」（原本 Game._action_title 那張表的 market）。進店那一顆（此地還能做）是 here/gear 那一格（第 56 批；計畫 1.9）。"""
        if self._verbs is None:
            from tianxia import mounts  # noqa: PLC0415

            from . import bots, market_actions  # noqa: PLC0415

            self._verbs = (Verb("market", run=lambda ctx, prepared: market_actions.enter(ctx),
                                title=lambda ctx: f"{mounts.MARKET}・{ctx.content.locations[ctx.state.player.location].name}",
                                bot=lambda ctx, profile: bots.enter(ctx), bot_skip=True),)
        return self._verbs

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的四格（順序在 SEAM_ORDER；不問 enabled）：sync、清失效參照收馬市（market_actions.close_gone）；sync、advance 補寄放的東西
        （gift_actions.deliver_held_gear，位置固定在 _deliver_big_events 之後：on_sync 只問開著的包、advance 沒有 on_sync）。"""
        if self._seams is None:
            from . import gift_actions, market_actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.close", "gear", lambda ctx: market_actions.close_gone(ctx)),
                SeamHook("stale.mid", "gear", lambda ctx: market_actions.close_gone(ctx)),
                SeamHook("sync.deliver", "held_gear", lambda ctx: gift_actions.deliver_held_gear(ctx)),
                SeamHook("advance.held", "held_gear", lambda ctx: gift_actions.deliver_held_gear(ctx)),
            )
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單與動身的格（順序在 MENU_ORDER；不問 enabled）：馬市不進店面登記 Shop（計畫第四節：_shops 照 FEATURES，酒肆、銀兩出口會排到它前面；出發不看坐不坐著都要清）：坐著接管整個選單、不算閒著、店面那一頁、動身收起來、動身被擋；此地那一顆。"""
        if self._menus is None:
            from tianxia import mounts  # noqa: PLC0415
            from . import market_actions  # noqa: PLC0415

            self._menus = (
                MenuHook("take", "gear", lambda ctx: market_actions.market_options(ctx) if ctx.state.player.picking_market else None),
                MenuHook("here", "gear", lambda ctx, loc, cost, odds: market_actions.here_cell(ctx, loc, cost, odds)),
                MenuHook("idle", "gear", lambda ctx: ctx.state.player.picking_market),
                MenuHook("open", "gear", lambda ctx: market_actions.open_cell(ctx)),
                MenuHook("depart", "gear", lambda ctx: mounts.close_market(ctx.state.player)),
                MenuHook("block", "gear", lambda state, content: market_actions.travel_block(state, content)),
                MenuHook("stale", "market", lambda ctx, option, option_id: market_actions.stale_cell(ctx, option, option_id)),
            )
        return self._menus

    def menxia_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.menxia_actions(shell)


FEATURE = GearFeature()
