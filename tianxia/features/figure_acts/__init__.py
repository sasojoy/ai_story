"""大勢人物的行動（功能包；開發規範手冊 3.2）：挑戰本人（閉門不見、勝算、對手那一路、打一場、打贏的一串、僵持）、護衛犒軍探望（aid:）、
助他一臂或壞他的事（plan:）、月旦評三段式的 A、C 兩段、管理者救回人物。全部拆包第 31 批搬進來（計畫 docs/superpowers/plans/2026-11-04-大勢人物包-第1批.md）。
README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

選項前綴 `aid:`（`aid:guard:<人物>`、`aid:rally:<人物>`、`aid:visit:<人物>`）與 `plan:`（`plan:help:<站>`、`plan:block:<站>`）：choose 接掛鉤（標題一起給）。
挑戰本人（`act:challenge:<人物>`）接 act 子動詞（verbs，帶後綴走 tail_*，第 57 批：按下去、標題、這一下打哪一路）；選單是 `MENU_ORDER["here"]` 的 challenge 那一格，選單末段
`MENU_ORDER["plays"]` 護衛在包選項之前、盤算在之後，夾著 `options` 掛鉤：這一包登記 `plays/aid`、`plays/plan` 那兩格（第 56 批）。
enabled 一直是 True（沒有自己的總開關：護衛看 Config.figure_aid、盤算看 Config.plans、挑戰本人看 figures.challenge_on，各在動作裡驗）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, HowtoHook, MenuHook, Outcome, SeamHook, StatusHook, Verb, WorldHook, slot_some


class FigureActsFeature(Feature):
    name = "figure_acts"
    web = ("figure_acts.js", "figure_acts.css")  # 盤算卡與此地舊事（全部拆包第 67 批從 main.js、style.css 切出來）
    prefix = ("aid", "plan")  # aid:guard／rally／visit:<人物>、plan:help／block:<站>
    bot_always = ("aid:",)  # 整季機器人：護衛、犒軍、探望不按（原本寫在 bot.py 的排除清單；plan: 照舊按得到）
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：閉門不見到幾時、這一季打贏每位人物幾次、聲威哪天扣過、三階與四階的帳、領過盤算結果的站。換季全部跟著新角色重來
    player_fields = (
        "snubbed_until", "figure_wins", "figure_dented", "figure_rare_drops", "tier3_drops", "tier4_wins", "tier4_challenge_drops", "plans_paid",
    )
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True

    def choose(self, ctx, kind, arg):
        """護衛、犒軍、探望（aid:）與盤算（plan:）；標題在動作之前拿（原本 Game._action_title 的 aid、plan 兩格）。"""
        if kind == "aid":
            from . import aid_actions  # noqa: PLC0415

            return Outcome(title=aid_actions.title(ctx, arg), run=lambda: aid_actions.act(ctx, arg))
        if kind == "plan":
            from . import plan_actions  # noqa: PLC0415

            return Outcome(title=plan_actions.title(ctx, arg), run=lambda: plan_actions.act(ctx, arg))
        return None

    # core_world（全部拆包第 25 批「世界層掛鉤」）
    _world: tuple[WorldHook, ...] | None = None

    def world(self) -> tuple[WorldHook, ...]:
        """世界層 step 的 yuedan 那一格（月旦評；原本 world.advance_world_state 直接叫 yuedan.tick）：不問 enabled。建一次就留著，
        在叫的那一下才照模組屬性找 yuedan.world_step（monkeypatch 照樣有效）。"""
        if self._world is None:
            from . import yuedan  # noqa: PLC0415

            self._world = (WorldHook("step", "yuedan", lambda *args: yuedan.world_step(*args)),)
        return self._world

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的兩格（順序在 SEAM_ORDER；不問 enabled）：護衛下線時擋下的挑戰回來補名望與心得（aid_actions.deliver_guard_credits：夾在首創名望回饋與 deliver_notices 之間）；
        讀檔清閉門不見的人（challenge.drop_stale）。"""
        if self._seams is None:
            from . import aid_actions, challenge  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.deliver", "guard", lambda ctx: aid_actions.deliver_guard_credits(ctx)),
                SeamHook("stale.late", "figure_acts", lambda ctx: challenge.drop_stale(ctx)),
            )
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單的格（順序在 MENU_ORDER；不問 enabled）：此地的挑戰本人；體力玩法那一串裡的護衛（包選項之前）、盤算（包選項之後）。"""
        if self._menus is None:
            from . import aid_actions, challenge, plan_actions  # noqa: PLC0415

            self._menus = (
                MenuHook("here", "challenge", lambda ctx, loc, cost, odds: challenge.options(ctx, odds)),
                MenuHook("plays", "aid", lambda ctx: aid_actions.options(ctx)),
                MenuHook("plays", "plan", lambda ctx: plan_actions.options(ctx)),
            )
        return self._menus

    # core_seams（全部拆包第 57 批「分派與標題收接縫」）
    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """挑戰本人 act:challenge:<人物>（原本 Game._act、_action_title、_fight_squad 原位；不問 enabled）：按下去、紀錄標題、這一下打哪一路（難度照他此刻的聲威與江湖水漲；人物表上沒有他不打）。
        按下去與打哪一路經 ctx 叫（scripts/measure_challenge.py 換掉 Game._challenge；服務清單 # core_seams）。"""
        if self._verbs is None:
            from tianxia import figures  # noqa: PLC0415  共用規則層（人物表 figures，第 40 批收進）

            from . import bots  # noqa: PLC0415

            self._verbs = (Verb(
                "challenge",
                tail_run=lambda ctx, prepared, tail: ctx._challenge(tail),
                tail_title=lambda ctx, tail: f"挑戰・{figures.name_of(ctx.content, tail)}",
                tail_squad=lambda ctx, tail: ctx._figure_squad(tail) if tail in ctx.content.figures else None,
                tail_bot=lambda ctx, profile, tail: bots.challenge(ctx, tail),
            ),)
        return self._verbs

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的challenge 那一格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (HowtoHook("challenge", lambda content, season, page: words.challenge_section(content, season)),)

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import plan_actions  # noqa: PLC0415

            self._status_slots = (
                # 世界活起來：全服開著的盤算裡最切身的一件（江湖頁行動列底下一張卡）；沒有開著的就沒有這個鍵
                StatusHook("main", "plan", lambda ctx, frame: slot_some("plan", plan_actions.plan_view(ctx))),
                # 世界活起來：此地舊事（場景卡底下最近的幾筆世界記事）；沒有就沒有這個鍵
                StatusHook("main", "place_deeds", lambda ctx, frame: slot_some("place_deeds", plan_actions.place_deeds_view(ctx))),
            )
        return self._status_slots


FEATURE = FigureActsFeature()
