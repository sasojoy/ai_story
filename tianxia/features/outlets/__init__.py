"""銀兩出口與捐軍備（大本營的軍需官那一串：捐素材；21 天季的「打點」那一間店：捐銀兩、名師指點、買破境丹、看火候、打點門路與帳簿）。
功能包，開發規範手冊 3.2；全部拆包第 43 批搬進來（引擎那一半）；網頁的畫法 donatePicks、dadianHtml 等在 web/outlets.js（第 65 批）。README.md 寫這一包做什麼、
認領的欄位、還留在原位的接縫。

- donate_actions.py：捐軍備（原本 Game 上的 9 個方法，Game 留一行委派）
- silver_actions.py：銀兩出口（原本 Game 上的 8 個方法，Game 留一行委派）
- bots.py：假人的分數（原本 bot_policy.score 的 dadian、donate 兩段）

兩間店（軍需官那一串、「打點」那一間）接第 11 批的店面登記（shops）：坐在店裡的選單、哪一間開著、動身與此地不開了收店；進店那兩顆
（「此地還能做」裡的捐軍備、打點）留在 Game 原位，因為它們排在療傷之後（順序算行為），Shop.entry 回 None。act:donate、act:dadian 與銀兩出口
四樣（silver_donate、mentor、furnace、buy_legend）接 act 子動詞（verbs）；bribe:<人物> 帶後綴接不了 Verb，留在核心 _act 叫委派。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome, Shop, StatusHook, Verb


class OutletsFeature(Feature):
    name = "outlets"
    web = ("outlets.js",)  # 軍需帳與打點帳簿的畫法（全部拆包第 65 批從 app.js 切出來）；點擊分派的 case 照舊在 app.js（殼）。css 第 67 批才切
    prefix = ("donate", "dadian")  # donate:room、donate:<素材>:<個數>、donate:back（軍需官那一串）；dadian:back（打點那一間店）；入口 act:donate、act:dadian 是核心的前綴
    bot_always = ("donate:", "dadian:")  # 坐在店裡一直按得下去：整季機器人不按（bot.py 的排除清單原本也寫了這兩個，拿掉，只剩這裡）
    # 軍需官那一串與打點那一間店開著沒、今天捐了多少（素材、銀兩）、名師指點與看火候請了沒用、這一季買了幾顆破境丹、今天打點過誰：
    # 換季全部跟著新角色重來（軍備存量 World.armaments 是全服帳，由 donate_actions.credit 寫、核心 status_data 經 armament_view 讀）
    player_fields = ("picking_donate", "picking_dadian", "donate_day", "donated_today", "silver_donate_day", "silver_donated",
                     "mentor_day", "mentor_ready", "furnace_day", "furnace_ready", "legend_silver_bought", "bribed")
    carried = ("donate_day", "donated_today")  # 換季不能多捐一輪（Game._reset_player_for_new_season 照帶，同出陣的 sortie_day；不看開關）

    def enabled(self, ctx) -> bool:
        """捐軍備開著（Config.economy.donate）、銀兩出口開著（silver.on），或此刻還坐在店裡：開關在坐著的時候被關掉（沒經過 sync 收店）
        照樣按得到離開、假人照樣只按它——搬包之前 choose 的 donate、dadian 兩支、bot_policy.score 的那兩段都不看開關。"""
        from tianxia import silver  # noqa: PLC0415

        p = ctx.state.player
        return ctx.content.config.economy.donate or silver.on(ctx.content, ctx.state.world) or p.picking_donate or p.picking_dadian

    def choose(self, ctx, kind, arg):
        """donate:*（軍需官那一串：收起、捐一種）、dadian:*（打點那一間店的離開）；標題照招牌與此地（原 Game._action_title 的 donate、dadian 兩支）。"""
        if kind not in ("donate", "dadian"):
            return None
        from tianxia import economy, silver  # noqa: PLC0415

        from . import donate_actions, silver_actions  # noqa: PLC0415

        here = ctx.content.locations[ctx.state.player.location].name
        if kind == "donate":
            return Outcome(title=f"{economy.DONATE_TITLE}・{here}", run=lambda: donate_actions.donate_choice(ctx, arg))

        def leave() -> list[str]:  # 打點那一間店的「離開」
            silver_actions.close_dadian(ctx)
            return [silver.SHOP_CLOSED]

        return Outcome(title=f"{silver.SHOP}・{here}", run=leave)

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    # ── 接縫掛鉤（第 11 批）──

    _shops: tuple[Shop, ...] | None = None

    def shops(self) -> tuple[Shop, ...]:
        """店面登記：軍需官那一串（坐著 picking_donate；這裡開著＝人在自家大本營；收起 economy.close_donate）與「打點」那一間店（坐著 picking_dadian；
        這裡開著＝銀兩出口這裡還有得做；選單是這裡做得了的幾樣加離開）。進店那兩顆（entry）回 None：「此地還能做」裡捐軍備與打點排在療傷之後，
        入口留在 Game._everyday_options 原位（經 Game 的 _donate_option、_silver_options 委派；順序算行為）。建一次就留著，
        每一格在叫的那一下才照模組屬性找函式（monkeypatch 照樣有效）。"""
        if self._shops is None:
            from tianxia import economy, silver  # noqa: PLC0415
            from tianxia.core.option import Option  # noqa: PLC0415

            from . import donate_actions, silver_actions  # noqa: PLC0415

            self._shops = (
                Shop(key="donate", inside=lambda ctx: ctx.state.player.picking_donate, here=lambda ctx: ctx._at_own_base(),
                     close=lambda ctx: economy.close_donate(ctx.state), menu=lambda ctx: donate_actions.donate_options(ctx),
                     entry=lambda ctx: None),
                Shop(key="dadian", inside=lambda ctx: ctx.state.player.picking_dadian, here=lambda ctx: bool(silver_actions.silver_options(ctx)),
                     close=lambda ctx: silver_actions.close_dadian(ctx),
                     menu=lambda ctx: silver_actions.silver_options(ctx) + [Option(id="dadian:back", label=silver.SHOP_BACK)],
                     entry=lambda ctx: None),
            )
        return self._shops

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act 子動詞：donate（打開軍需官那一串，不花體力）、dadian（打開打點那一間店，不花體力）與銀兩出口四樣（silver_donate、mentor、furnace、
        buy_legend；打點那一間店開著時掮客換一句）。標題只接兩間店的招牌；四樣的標題與 bribe:<人物> 的標題留在核心 _action_title 原位。"""
        if self._verbs is None:
            from tianxia import economy, silver  # noqa: PLC0415

            from . import silver_actions  # noqa: PLC0415

            def here(ctx) -> str:
                return ctx.content.locations[ctx.state.player.location].name

            def open_donate(ctx, prepared):  # 大本營捐軍備：打開軍需官那一串，不花體力
                ctx.state.player.picking_donate, ctx.state.player.shop_clue = True, ""
                ctx._shop_say("enter")  # 軍需帳上軍需官那一句（店面同一套）
                return [economy.DONATE_OPEN.format(faction=ctx.content.scenario.faction_name(ctx.state.player.faction, ""))]

            def open_dadian(ctx, prepared):  # 打點：打開那一間店，不花體力
                p = ctx.state.player
                p.picking_dadian, p.shop_clue = True, ""
                ctx._shop_say("enter")
                return [silver.SHOP_ENTERED]

            def silver_verb(what: str) -> Verb:
                def run(ctx, prepared):
                    msgs = silver_actions.silver_act(ctx, what)  # 銀兩出口（21 天季，正式季整合 6.5）：都不花體力
                    if ctx.state.player.picking_dadian:
                        ctx._shop_say("done")  # 打點那一間店裡記了一筆：掮客換一句
                    return msgs

                return Verb(what, run=run)

            self._verbs = (
                Verb("donate", run=open_donate, title=lambda ctx: f"{economy.DONATE_TITLE}・{here(ctx)}"),
                Verb("dadian", run=open_dadian, title=lambda ctx: f"{silver.SHOP}・{here(ctx)}"),
                *(silver_verb(what) for what in ("silver_donate", "mentor", "furnace", "buy_legend")),
            )
        return self._verbs

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import donate_actions  # noqa: PLC0415

            self._status_slots = (
                StatusHook("status", "armament", lambda ctx, frame: {"armament": donate_actions.armament_view(ctx)}),
            )
        return self._status_slots


FEATURE = OutletsFeature()
