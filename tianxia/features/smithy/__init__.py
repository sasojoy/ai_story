"""鐵匠鋪（帶地盤福利的城鎮裡的一間店：架上買、修、淬煉、換上、拆解，一步一步打造與店面直接開爐，打造的隱藏配方與鐵匠順口，神器原品定名與以器配招，
素材頁的收購與升階，爐火的看火候）。功能包，開發規範手冊 3.2；全部拆包第 41 批搬進來（引擎那一半；網頁那一半 web/ 第 3 階才切）。
README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- smithing.py：打造與淬煉的規則（原 tianxia/smithing.py；那個名字留成指到這裡的別名）
- shelf_actions.py：架上的選單與選單上按下去的一下（原本 Game 上的 8 個方法）
- forge_actions.py：開爐一次、店面打造頁的預覽、直接開爐、看火候（4 個）
- trade_actions.py：素材頁的收購與升階（5 個）
- gear_actions.py：裝備庫那一列的修與淬煉（3 個）
- divine_actions.py：神器原品定名、以器配招（2 個；沒有模型）
- clue.py：鐵匠順口（1 個）
- routes.py：/api/smith_line（原本寫在 server.py）
- bots.py：假人的分數（原本 bot_policy.score 的 smith 那一段與 _smith_want）

接縫掛鉤：choose（smith:*）、verbs（act:smith 進店與紀錄標題）、routes、content、bot_pick。店面登記（Shop）不登記、走 MENU_ORDER（第 56 批選單收接縫定案，計畫第四節：「此地還能做」的入口順序、
選單順序、_shop_open 與收店的 here 兩個意思）：menus() 登記選單、入口、_shop_open、出發收店、動身被擋那幾格；sync.close、stale.mid 的收店是 seams()（第 55 批）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, MenuHook, Outcome, SeamHook, Verb


class SmithyFeature(Feature):
    name = "smithy"
    prefix = "smith"  # smith:buy:<種類>、smith:repair、smith:forge-go:…、smith:page:<頁>、smith:back 等；入口 act:smith 是核心的前綴
    content = ("forge_secrets.json", "tier4_named.json")  # content.py 照舊讀（打造的隱藏配方與神器譜、四階名器名字表）
    # 鐵匠鋪開著沒、停在哪一頁、一步一步的單子、鐵匠這一季講過神器的規矩沒有（smith_rule 是這一次進門要講的那一句）：換季全部跟著新角色重來
    # 店面共用的 shop_line／shop_line_seed／shop_hold／shop_clue（七間店共用，核心）與 furnace_day／furnace_ready（銀兩出口包）不在這裡
    bot_always = ("smith:page:",)  # 切頁一直按得下去、不花體力：整季機器人不按（原本寫在 bot.py 的排除清單，拿掉，只剩這裡）
    player_fields = ("picking_smith", "smith_page", "smith_draft", "smith_rule", "smith_rules_told")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """武器或防具開著（跟 equipment.smith_open 同一個條件，不看第一季開關），或此刻還坐在鐵匠鋪裡：開關在坐著的時候被關掉（沒經過 sync 收店）
        照樣按得到離開、假人照樣只按它——搬包之前 choose 的 smith 那一支、bot_policy.score 的那一段都不看開關。"""
        c = ctx.content.config
        return c.weapons.enabled or c.armor.enabled or ctx.state.player.picking_smith

    def choose(self, ctx, kind, arg):
        """smith:*（鐵匠鋪第二層選單上的每一顆）：標題照 smithing.title（打造的每一步「打造」、淬煉「淬煉」，其餘「鐵匠鋪」；原 Game._action_title 的 smith 那一支），
        動作照原 Game._smith（做完擲一次鐵匠順口）。choose 後半「打造那幾步併成一則」、切頁不寫紀錄仍在核心原位讀 smithing 的三個名字。"""
        if kind != self.prefix:
            return None
        from . import shelf_actions, smithing  # noqa: PLC0415

        return Outcome(title=smithing.title(arg), run=lambda: shelf_actions.smith(ctx, arg))

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)

    # ── 接縫掛鉤（全部拆包第 11 批：原本在 Game 原位直接寫的那兩行；不問 enabled，原位本來就不看開關）──

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:smith 的主人（act 子動詞）：按下去走進鐵匠鋪（shelf_actions.enter：不花體力、單子從頭開始、停在第一個開著的那一頁；原本 Game._act 中段那幾行）、
        紀錄標題「鐵匠鋪・此地」（原本 Game._action_title 那張表的 smith）。進店那一顆（此地還能做）是 here/smithy 那一格（第 56 批；計畫 1.9）。"""
        if self._verbs is None:
            from tianxia import weapons  # noqa: PLC0415

            from . import shelf_actions  # noqa: PLC0415

            self._verbs = (Verb("smith", run=lambda ctx, prepared: shelf_actions.enter(ctx),
                                title=lambda ctx: f"{weapons.SMITH}・{ctx.content.locations[ctx.state.player.location].name}"),)
        return self._verbs

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的兩格（順序在 SEAM_ORDER；不問 enabled）：sync 收店（shelf_actions.sync_close）、清失效參照收店（shelf_actions.drop_stale）。"""
        if self._seams is None:
            from . import shelf_actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.close", "smithy", lambda ctx: shelf_actions.sync_close(ctx)),
                SeamHook("stale.mid", "smithy", lambda ctx: shelf_actions.drop_stale(ctx)),
            )
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單與動身的格（順序在 MENU_ORDER；不問 enabled）：鐵匠鋪不進店面登記 Shop（計畫第四節：here 有兩個意思：_shop_open 是「單子沒開著且開門」、收店是「開門」；出發不看坐不坐著都要清）：坐著接管整個選單、不算閒著、店面那一頁、動身收起來、動身被擋；此地那一顆。"""
        if self._menus is None:
            from tianxia import equipment  # noqa: PLC0415
            from . import shelf_actions  # noqa: PLC0415

            self._menus = (
                MenuHook("take", "smithy", lambda ctx: shelf_actions.smith_options(ctx) if ctx.state.player.picking_smith else None),
                MenuHook("here", "smithy", lambda ctx, loc, cost, odds: shelf_actions.here_cell(ctx, loc, cost, odds)),
                MenuHook("idle", "smithy", lambda ctx: ctx.state.player.picking_smith),
                MenuHook("open", "smithy", lambda ctx: shelf_actions.open_cell(ctx)),
                MenuHook("depart", "smithy", lambda ctx: equipment.close_smith(ctx.state.player)),
                MenuHook("block", "smithy", lambda state, content: shelf_actions.travel_block(state, content)),
            )
        return self._menus


FEATURE = SmithyFeature()
