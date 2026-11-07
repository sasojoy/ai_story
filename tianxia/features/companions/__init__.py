"""人物情誼（功能包；開發規範手冊 3.2）：同伴招募與名下、人物心意、託付與勸降、來信與委託、人物頁。全部拆包第 19 批（人物情誼一）搬進來；
人物對話與 NPC 智能（companion_agent、parley，`talk:`、`parley:`）是第 20 批搬進來的（talk_actions、parley_actions、bots.py）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

選項前綴 `errand:`（託付：交信、探營、勸降）、`talk:`（跟人物談著的選項：上一輪給的、自己說、商量打法、條件的接與不接、還債、請他兌現、伏筆與機緣的話題、告辭）、
`parley:`（帶路的路上跟他說一句）；招募接 act 子動詞（`act:recruit`、`act:recruit:<id>` 同一個 Verb，第 57 批）。`talk:`、`parley:road` 的 choose 第 20 批審查接上掛鉤
（鎖外生成好的一輪 prepared 與驗過的那句話經 `ctx._talk_turn`、`ctx._talk_said` 寄放，同勸降的 `_persuade_said`）；進鎖後的重驗 `_checked_prepared` 與字數 `say_max` 仍在 choose 前段。enabled 一直是 True
（招募 Config.companions、書信 Config.figure_life.letters、心意與託付 Config.jianfa 各有自己的開關，包本身沒有總開關）。
"""
from __future__ import annotations

from tianxia.core.features import DefectHook, Feature, HowtoHook, MenuHook, Outcome, SeamHook, StatusHook, StepHook, Verb, slot_some


class CompanionsFeature(Feature):
    name = "companions"
    web = ("companions.js", "companions.css")  # 託付的勸降那一句（全部拆包第 66 批從 app.js 切出來）；書信、點人物、對話、往來紀錄與樣子（全部拆包第 67 批從 main.js、style.css 切出來）
    prefix = ("errand", "talk", "parley")  # 託付（errand:<動詞>:<id>）；整季機器人不按（要寫字、不收託付）；人物對話 talk:*、帶路的路上 parley:road（假人只按告辭，見 bots.py）
    # 整季機器人不收託付，萬一有也不按（勸降要寫字；原本 bot.pick 的排除清單）；對話的片段與機緣的話題（原本 bot.FORESHADOW_OPTIONS，第 60 批）：這一版假人不做伏筆也不做機緣
    bot_always = ("errand:", "talk:clue:", "talk:opp:")
    content = ("events/stances.json",)  # 人物心意開的事件（總表附錄甲）；content.py 照它到這一包的 content/ 載；檔名照舊
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）。換季全部跟著新角色重來；parted_done（同伴回江湖的減半記號）第 7 批決戰包認領了，第 7 批 PM 認定第 4 條留到這一包再看：
    # 寫它的 settle_partings 還在決戰包，這一批照留
    player_fields = (
        "stance_notes", "errands", "letters", "letter_day", "letter_seq", "cheers",
        # 第 20 批（審查補認領）：人物對話（companion_agent）的私有狀態與 NPC 智能 2.0（parley）這一季的帳；talks_today、picking_audience 留給第 21 批（交友求見）
        "pending_companion", "dialogue_history", "used_dialogue_options", "last_offered_dialogue", "turns_since_consolidation",
        "talk_memos", "talk_prev", "parley_days", "parley_terms", "parley_owed", "parley_backing", "parley_debts", "parley_records",
        "parley_escort", "parley_road_leg",
    )
    # 對話紀錄、說過的話、梳理的輪數換季照帶（Game._reset_player_for_new_season；history_start 是它從 dialogue_history 的長度算的，不另認領）
    carried: tuple[str, ...] = ("dialogue_history", "used_dialogue_options", "turns_since_consolidation")

    def enabled(self, ctx) -> bool:
        return True

    def choose(self, ctx, kind, arg):
        """託付（交信、探營、勸降的 C 段）；勸降按下去只叫出輸入框那一下在建紀錄之前，是 MENU_ORDER["quick"] 的 errand 那一格（第 57 批）。"""
        if kind == "talk" or (kind == "parley" and arg == "road"):
            # 談話（talk:<N>、say、leave、clue、opp、terms……）與帶路的路上說一句（parley:road；第 20 批審查接上掛鉤）：鎖外生成好的一輪與驗過的
            # 那句話經 ctx._talk_turn、ctx._talk_said 寄放（Game.choose 前段驗完擺好，同勸降的 _persuade_said）；標題在動作之前拿
            from . import talk_actions  # noqa: PLC0415

            if kind == "talk":
                return Outcome(title=talk_actions.talk_title(ctx), run=lambda: talk_actions.talk(ctx, arg, ctx._talk_turn, ctx._talk_said))
            return Outcome(title=talk_actions.road_title(ctx), run=lambda: talk_actions.road_say(ctx, ctx._talk_turn, ctx._talk_said))
        if kind != "errand":
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.errand_title(ctx, arg), run=lambda: actions.errand_act(ctx, arg))

    def bot_pick(self, ctx, option):
        """假人看到 talk:、parley: 的選項怎麼按（原本 bot_policy.score 的 talk 那一段）；errand: 整季機器人不收、伺服器假人在 take_turn 打分數之前就濾掉，沒有分數（None）。"""
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    def bot_idle(self, ctx, option):
        """整季機器人不按對話的「自己說」「商量打法」、帶路的路上說一句（要寫一句話，機器人寫不出有意義的做法；原本 bot.pick 比相等的 TEXT_TALKS，第 60 批；不問 enabled）。"""
        from tianxia.core.services import TEXT_TALKS  # noqa: PLC0415

        return option.id in TEXT_TALKS

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    # core_effects（全部拆包第 32 批「效果與叛投掛鉤」）
    _defection: tuple[DefectHook, ...] | None = None

    def defection(self) -> tuple[DefectHook, ...]:
        """叛投 after 位置的 parley 那一格（NPC 智能 2.1：接了又叛投，欠著的都算食言；原本 Game._defect_step 經 Game._parley_forsake 委派叫）：
        排在同伴回江湖（leave_behind）之後。不問 enabled。建一次就留著，在叫的那一下才照模組屬性找 parley_actions.forsake_all。"""
        if self._defection is None:
            from . import parley_actions  # noqa: PLC0415

            self._defection = (DefectHook("after", "parley", lambda ctx, side: parley_actions.forsake_all(ctx)),)
        return self._defection

    # core_step（全部拆包第 36 批「你這一步」）
    _steps: tuple[StepHook, ...] | None = None

    def steps(self) -> tuple[StepHook, ...]:
        """「你這一步」的 errand 那一格（身上還在辦的人物託付；原本 weekcard._steps 第一行直接叫 errands.step_items）：排在最前面（STEP_ORDER）。
        自己帶好 id 與 target、不掛 _ref，所以沒有 ref、place（step.finish 看到有 target 就照留）。不問 enabled（託付關著是 errands.on 判的，回空的）。
        建一次就留著，在叫的那一下才照模組屬性找 errands.step_items（monkeypatch 照樣有效）。"""
        if self._steps is None:
            from . import errands  # noqa: PLC0415

            self._steps = (StepHook("errand", lambda ctx, status, orders: errands.step_items(ctx.state, ctx.content)),)
        return self._steps

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的四格（順序在 SEAM_ORDER；不問 enabled）：sync 記心意的行狀（actions.stance_annals）、書信那一格（actions.deliver_mail，時間讀 ctx.now：sync 開頭設的）；
        讀檔清招募確認；換季照帶對話歷史。"""
        if self._seams is None:
            from . import actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.deliver", "stances", lambda ctx: actions.stance_annals(ctx)),
                SeamHook("sync.deliver", "mail", lambda ctx: actions.deliver_mail(ctx, ctx.now)),
                SeamHook("stale.early", "companions", lambda ctx: actions.drop_stale(ctx)),
                SeamHook("season.carry", "companions", lambda ctx, old, fresh: actions.carry_season(ctx, old, fresh)),
            )
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單與動身的格（順序在 MENU_ORDER；不問 enabled）：談著接管整個選單、動身被擋；他帶你走的路上每到一站說一句；此地的招募、託付；勸降只叫出輸入框（quick，第 57 批：
        回 None 照舊往下走 choose 掛鉤，送信、探營是 errand: 的正常路）。"""
        if self._menus is None:
            from . import actions, parley_actions, talk_actions  # noqa: PLC0415

            self._menus = (
                MenuHook("take", "talk", lambda ctx: talk_actions.talk_options(ctx) if ctx.state.player.pending_companion else None),
                MenuHook("road", "parley", lambda ctx, j: parley_actions.road_cell(ctx, j)),
                MenuHook("here", "recruit", lambda ctx, loc, cost, odds: actions.recruit_options(ctx)),
                MenuHook("here", "errand", lambda ctx, loc, cost, odds: actions.errand_options(ctx)),
                MenuHook("block", "talk", lambda state, content: talk_actions.travel_block(state, content)),
                MenuHook("quick", "errand", lambda ctx, kind, arg, option_id: actions.errand_ask(ctx, arg) if kind == "errand" else None),
            )
        return self._menus

    # core_seams（全部拆包第 57 批「分派與標題收接縫」）
    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """招募：act:recruit（舊招募：這裡那一位）與 act:recruit:<人物>（招這一位），按下去與紀錄標題（原本 Game._act、_action_title 原位）；不問 enabled（原位不看開關）。
        不認得的人物標題回 None，照舊掉到核心的「提前出關」。兩個分頁搶人的 FB-363 那一句回 Refused（只在 engine），留在 Game.choose 前段。"""
        if self._verbs is None:
            from . import actions  # noqa: PLC0415

            def here(ctx) -> str:
                return ctx.content.locations[ctx.state.player.location].name

            self._verbs = (Verb(
                "recruit", run=lambda ctx, prepared: actions.recruit(ctx), title=lambda ctx: f"招募・{here(ctx)}",
                tail_run=lambda ctx, prepared, tail: actions.recruit_one(ctx, tail),
                tail_title=lambda ctx, tail: f"招募・{ctx.content.characters[tail].name}" if tail in ctx.content.characters else None,
                tail_bot=lambda ctx, profile, tail: None, tail_bot_skip=True,  # 招募歷史武將（歷史武將同行第七節）：假人不招。act:recruit 不寫 bot：照舊 ACT_SCORES 的 0.0
            ),)
        return self._verbs

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的bond 那一格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (HowtoHook("bond", lambda content, season, page: words.bond_section(content, season, page.recruitable)),)

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import actions, talk_actions  # noqa: PLC0415

            self._status_slots = (
                # 「自己說」最多幾個字（NPC 智能 2.0 開著時比較長，網頁的輸入框照它）
                StatusHook("main", "say_max", lambda ctx, frame: {"say_max": talk_actions.say_max(ctx)}),
                StatusHook("main", "companions", lambda ctx, frame: talk_actions.main_slot(ctx, frame)),
                # 書信（大勢人物擴充第二批）：江湖頁「剛剛」上面一張小卡；沒有沒看過的信就沒有這個鍵
                StatusHook("main", "letter", lambda ctx, frame: slot_some("letter", actions.letter_view(ctx))),
            )
        return self._status_slots

    def main_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.main_actions(shell)

    def menxia_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.menxia_actions(shell)

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415  只在殼建鎖外工作時才 import（同 routes 掛鉤）

        return routes.outlock(shell)


FEATURE = CompanionsFeature()
