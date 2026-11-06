"""交友求見（功能包；開發規範手冊 3.2）：交友（act:socialize）、指名求見（act:call 打開名單、call:<人物>）、被打發、每位人物每個遊戲日談幾輪、結識奇遇（福緣）。
全部拆包第 21 批搬進來（計畫 docs/superpowers/plans/2026-11-04-交友求見包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

選項前綴 `call:`（`call:<人物 id>`、`call:back`）；`act:socialize`、`act:call` 兩格接 act 子動詞（verbs，第 57 批：按下去與紀錄標題，那一顆與底下那一行是 MENU_ORDER 的 here、notes 那兩格）。
`call:` 的 choose 接掛鉤（鎖外生成好的一輪 prepared 經 `ctx._talk_turn` 寄放，第 20 批人物對話寫的；標題在動作之前拿）；進鎖後的重驗 `_checked_prepared`
與做完之後的引導 `_note_action("socialize")` 仍在 `Game.choose` 原位（位置算行為）。enabled 一直是 True（沒有自己的總開關；一類一顆 precise、福緣 roster 各有自己的開關）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, HowtoHook, MenuHook, Outcome, SeamHook, Verb


class SocializeFeature(Feature):
    name = "socialize"
    prefix = "call"  # 指名求見：call:<人物>、call:back（假人只按返回，見 bots.py）
    content = (  # 交友事件（總表附錄甲）；content.py 照舊讀（第 62 批起照它載）；檔名照舊。recruit.json 招募的事件檔歸誰交 PM 定（計畫「交 PM 定的」第 1 條）
        "events/social_nanyang_yingchuan.json", "events/social_north.json", "events/social_runan.json",
    )
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：每位人物這個遊戲日談了幾輪、求見名單開著。換季全部跟著新角色重來
    player_fields = ("talks_today", "picking_audience")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True

    def on_drop_stale(self, ctx) -> None:
        """內容改版後這裡不再有兩位以上的人物：收起求見名單（原本在 _drop_stale_references 一串 picking_* 之間，現在接在最後；只差序章收尾挪人之後的地點）。"""
        from . import view  # noqa: PLC0415

        p = ctx.state.player
        if p.picking_audience and not view.audience_hall(ctx):
            p.picking_audience = False

    def choose(self, ctx, kind, arg):
        """指名求見（call:<人物>、call:back）；一開頭就收起名單，名望不夠被打發、夠了開口對話（動作在 actions.call）。"""
        if kind != "call":
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.call_title(ctx, arg), run=lambda: actions.call(ctx, arg, ctx._talk_turn))

    def bot_pick(self, ctx, option):
        """假人看到 call: 的選項怎麼按（原本 bot_policy.score 的 call 那一段）：只按返回。"""
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    def bot_idle(self, ctx, option):
        """整季機器人不按名望不夠的求見（原本 bot.pick 那一條；不問 enabled）。"""
        from . import bots  # noqa: PLC0415

        return bots.idle_call(ctx, option)

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """local 的 fortune 那一格（順序在 SEAM_ORDER；不問 enabled）：福緣到期自己送上門（actions.fortune_due），排在閉關收尾之後。"""
        if self._seams is None:
            from . import actions  # noqa: PLC0415

            self._seams = (SeamHook("local", "fortune", lambda ctx: actions.fortune_due(ctx)),)
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單與動身的格（順序在 MENU_ORDER；不問 enabled）：求見名單接管整個選單、不算閒著、動身被擋；此地的交友與求見、行動列底下那幾行。"""
        if self._menus is None:
            from . import menus  # noqa: PLC0415

            self._menus = (
                MenuHook("take", "audience", lambda ctx: menus.audience_options(ctx) if ctx.state.player.picking_audience else None),
                MenuHook("here", "social", lambda ctx, loc, cost, odds: menus.here_cell(ctx, loc, cost, odds)),
                MenuHook("notes", "socialize", lambda ctx, ids, loc: menus.action_notes(ctx, ids, loc)),
                MenuHook("idle", "audience", lambda ctx: ctx.state.player.picking_audience),
                MenuHook("block", "audience", lambda state, content: menus.travel_block(state, content)),
            )
        return self._menus

    # core_seams（全部拆包第 57 批「分派與標題收接縫」）
    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:call（打開求見名單，不花體力）與 act:socialize（扣體力、晉升奇遇或交友）：按下去與紀錄標題（原本 Game._act、_action_title 原位）；不問 enabled。"""
        if self._verbs is None:
            from . import actions, bots  # noqa: PLC0415

            def here(ctx) -> str:
                return ctx.content.locations[ctx.state.player.location].name

            self._verbs = (
                Verb("call", run=lambda ctx, prepared: actions.open_audience(ctx), title=lambda ctx: f"求見・{here(ctx)}", bot=lambda ctx, profile: None),
                Verb("socialize", run=lambda ctx, prepared: actions.press(ctx, prepared), title=lambda ctx: f"交友・{here(ctx)}",
                     bot=lambda ctx, profile: bots.act_socialize(ctx)),
            )
        return self._verbs

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的socialize 那一格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (HowtoHook("socialize", lambda content, season, page: words.socialize_section(content, season)),)


FEATURE = SocializeFeature()
