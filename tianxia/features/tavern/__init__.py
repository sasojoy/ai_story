"""酒肆（帶「酒肆」標籤的城鎮裡的一間：打聽、題壁、請酒、藏行跡、反查、買殺手、問酒家、鄰桌閒談）。功能包，開發規範手冊 3.2；
主動搬六包第 10 批搬進來（引擎那一半；網頁那一半 app.js、style.css 第 3 階才切）。README.md 寫這一包做什麼、導覽與設計稿、
認領的欄位、還留在原位的接縫。

- rules.py：純規則（原 tianxia/tavern.py；那個名字留成指到這裡的別名）
- ask.py：問酒家照問句找事實（原 tianxia/tavern_ask.py；同上）
- actions.py：原本 Game 上酒肆的 43 個方法（Game 留一行委派）
- bots.py：假人的分數（原本 bot_policy.score 的 tavern 那一段）

選單接管那一格（坐在酒肆裡）、act:tavern 入口、sync 的下線殺手與三個 deliver、choose 最後那一下殺手檢查，第 10 批留在 Game 原位
直接叫這一包（位置算行為，批次表第二節）；全部拆包第 11 批換成接縫掛鉤，掛在原本那一行（店面登記 shops、act 子動詞 verbs、
on_away、deliver_notices、after_action，下面）。這一包另接 tavern:* 的 choose（互斥前綴）與假人分數。
"""
from __future__ import annotations

from tianxia.core.features import Feature, MenuHook, Outcome, Shop, Verb


class TavernFeature(Feature):
    name = "tavern"
    prefix = "tavern"  # tavern:news、tavern:treat、tavern:hide、tavern:trace、tavern:board、tavern:back；入口 act:tavern 是核心的前綴
    bot_always = ("tavern:",)  # 坐在酒肆裡一直按得下去：整季機器人不按（bot.py 的排除清單原本也寫了一個，第 11 批拿掉那一個，只剩這裡）
    # 酒肆開著沒、酒家最近幾則回話、聽過的傳聞、查到過的名號、哪一天請過酒、收到的風聲、藏行跡到幾時、託酒家留意的人、
    # 保鏢跟到幾時、剛被殺手得手的護身：換季全部跟著新角色重來（季上的牆、風聲、請酒、殺手單、閒談照季存）
    player_fields = ("picking_tavern", "tavern_notes", "tavern_heard", "tavern_known", "tavern_treat_day", "whispers", "hidden_until",
                     "tavern_watches", "tavern_guard_until", "tavern_shield_until")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """酒肆開著（Config.tavern.enabled、內容有帶「酒肆」標籤的地點），或此刻還坐在酒肆裡：開關在坐著的時候被關掉（沒經過 sync
        收店）照樣按得到「出酒肆」、假人照樣只按它——搬包之前 choose 的 tavern 那一支、bot_policy.score 的那一段都不看開關。"""
        from . import rules  # noqa: PLC0415

        return rules.on(ctx.content) or ctx.state.player.picking_tavern

    def choose(self, ctx, kind, arg):
        """tavern:* 那幾顆（選單接管那一格給的，只在坐在酒肆裡時有）：標題照招牌與動作（原 Game._action_title 的 tavern 那一支），
        動作照原 Game._tavern_choice（出酒肆、看牆上的懸賞榜、其餘照店面那一頁的動作）。"""
        if kind != self.prefix:
            return None
        from . import actions, rules  # noqa: PLC0415

        return Outcome(title=rules.title_of(ctx.state, ctx.content, arg), run=lambda: actions.tavern_choice(ctx, arg))

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    # ── 接縫掛鉤（全部拆包第 11 批：原本在 Game 原位直接叫這一包的那幾行；不問 enabled，原位本來就不看酒肆開關）──

    _shops: tuple[Shop, ...] | None = None

    def shops(self) -> tuple[Shop, ...]:
        """店面登記：酒肆是第一間搬成包的店（原本 Game 上七間店共用的那幾處，酒肆那幾行照抄；都排在舊的六間後面）——坐在酒肆裡
        （picking_tavern）選單整個是酒肆那一串（actions.tavern_options）；此地還能做裡「酒肆」那一顆（開著、這裡帶酒肆標籤，只是打開酒肆，
        不花體力）；店面那一頁的 key 是 tavern（坐著、這裡也還開著）；動身、此地不開了收起來（rules.close：掌櫃那一句一併清）。
        建一次就留著（契約測試照同一個物件認），每一格在叫的那一下才照模組屬性找 actions、rules 的函式（monkeypatch 照樣有效）。"""
        if self._shops is None:
            from tianxia.core.option import Option  # noqa: PLC0415

            from . import actions, rules  # noqa: PLC0415

            def entry(ctx):
                return Option(id="act:tavern", label=rules.TAVERN) if rules.on(ctx.content) and rules.here(ctx.state, ctx.content) else None

            self._shops = (Shop(
                key="tavern", inside=lambda ctx: ctx.state.player.picking_tavern, here=lambda ctx: rules.here(ctx.state, ctx.content),
                close=lambda ctx: rules.close(ctx.state), menu=lambda ctx: actions.tavern_options(ctx), entry=entry,
            ),)
        return self._shops

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:tavern 的主人（act 子動詞，第 11 批）：按下去打開酒肆（actions.tavern_enter：開著、人在酒肆、閒著才進得去，不花體力；
        原本 Game._act 中段那一行）、紀錄標題是招牌（actions.tavern_sign；原本 Game._action_title 那張表的 tavern）。兩樣都不問 enabled
        （原位不看開關；這一包的 tests/test_tavern_package.py 直接叫 _action_title("act", "tavern")）。進店那一顆在店面登記（Shop.entry）。"""
        if self._verbs is None:
            from . import actions  # noqa: PLC0415

            self._verbs = (Verb("tavern", run=lambda ctx, prepared: actions.tavern_enter(ctx), title=lambda ctx: actions.tavern_sign(ctx)),)
        return self._verbs

    def on_away(self, ctx, away_from) -> None:
        """下線那一段殺手找上門（原本 Game.sync 補算完本人下線那一段之後的那幾行，照抄）：離線夠久（Config.tavern.hit_offline_minutes）
        才擲；站在城外下線的人才會被找到（tavern_hit_check 自己看）；得手了改了共用賽季，存回。戰報與紀錄自己寫，不併進江湖大事。"""
        from . import actions  # noqa: PLC0415

        if away_from is not None and ctx.now - away_from >= ctx.content.config.tavern.hit_offline_minutes * 60:
            if actions.tavern_hit_check(ctx, away_from):
                ctx._save_season()

    def deliver_notices(self, ctx) -> None:
        """別人捎來的（原本 Game.sync 護衛補帳之後的那三行，照原順序）：有人在酒肆打聽你（風聲）、自己雇的殺手得手失手或到期退錢、
        託酒家留意的人有了準信或到期。三個都不看酒肆開關（關著照送、照退）。"""
        from . import actions  # noqa: PLC0415

        actions.deliver_whispers(ctx)
        actions.deliver_hits(ctx)
        actions.deliver_watches(ctx)

    def after_action(self, ctx) -> list[str]:
        """本人做完一件事（原本 Game.choose 最後、記下陣營之後、存回季之前那一行）：有人雇了殺手找你，你剛在城外做完一件事（設計第六節）。"""
        from . import actions  # noqa: PLC0415

        return actions.tavern_hit_check(ctx)

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單與動身的格（順序在 MENU_ORDER；不問 enabled）：坐在酒肆裡不算閒著；動身被擋。"""
        if self._menus is None:
            from . import actions  # noqa: PLC0415

            self._menus = (
                MenuHook("idle", "tavern", lambda ctx: ctx.state.player.picking_tavern),
                MenuHook("block", "tavern", lambda state, content: actions.travel_block(state, content)),
            )
        return self._menus


FEATURE = TavernFeature()
