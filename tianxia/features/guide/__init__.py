"""新手引導（功能包；開發規範手冊 3.2）：草廬之後的引導框、碰到才說的提示、新手目標、開局第一分鐘、入伍段。全部拆包第 22 批（引導一）
搬進來；玩法說明（howto）是第 59 批（引導二）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- rules.py：說書人的步驟與任務卡（原 tianxia/guide.py；那個名字留成指到這裡的別名）
- hints.py：碰到才說（原 tianxia/hints.py）；newbie.py：新手目標（原 tianxia/newbie.py）；opening.py：開局第一分鐘（原 tianxia/opening.py）；
  enlist.py：入伍段（原 tianxia/enlist.py）——舊名都留成別名
- actions.py：原本 Game 上的 31 個方法（Game 留 24 個一行委派）與核心原位叫的 12 個服務的本體
- checks.py：內容檢查（碰到才說那一塊，原本在 content.validate）
- howto.py：玩法說明的底與組裝（第 59 批：原 tianxia/howto.py 拆進 17 包，各節在各包的 howto.py，順序在核心 HOWTO_ORDER）；routes.py：/api/howto

這一包沒有選項前綴：它的動作走 server 的 MAIN_ACTIONS（hints_off、skip_tutorial、view_map、view_orders、view_tab、guide_ack、
newbie_drifter）與 /api/prologue，選單上的那幾顆是別人的（開局三選一是事件的 choice:、投靠是 faction:）；序章教體力那一步的 act:rest 接 act 子動詞（verbs，第 57 批）。
所以 options、menu、choose、bot_pick 都是預設的；enabled 一直是 True（引導、提示、新手目標、開局各有自己的開關，包本身沒有總開關）。
"""
from __future__ import annotations

from tianxia.core.features import DefectHook, Feature, HowtoHook, SeamHook, StepHook, Verb


class GuideFeature(Feature):
    name = "guide"
    prefix = None  # 沒有自己的選項（見模組說明）
    # content.py 照它到這一包的 content/ 載；檔名照舊。events/opening.json、events/prologue.json 是開局與序章的事件池（全部拆包第 63 批），
    # 跟 opening.json（開局第一分鐘）是不同的檔
    content = ("tutorial.json", "hints.json", "opening.json", "events/opening.json", "events/prologue.json")
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）。換季照帶的四格（說過的提示、不再提示、新手目標的兩本帳）照舊在 Game._reset_player_for_new_season
    # 原位帶（不看包的開關）；做完的引導步數、略過、入伍段走完是「做到才帶」（tutorial_step、guide_skipped、enlist_step），契約測試的換季那一條
    # 擺不出這種條件，不列在這裡（README 照列）
    player_fields = ("guide_done", "guide_outro", "enlist_end", "enlist_since", "hint_queue", "hints_seen", "hints_off", "newbie_marks",
                     "newbie_done")
    carried = ("hints_seen", "hints_off", "newbie_marks", "newbie_done")

    def enabled(self, ctx) -> bool:
        return True

    def check_content(self, content, need) -> None:
        """碰到才說（hints.json）的檢查：原本在 content.validate 裡、句子照抄（核心的 content.py 不能 import 包）。"""
        from . import checks  # noqa: PLC0415

        checks.check_hints(content, need)

    # core_effects（全部拆包第 32 批「效果與叛投掛鉤」）
    _defection: tuple[DefectHook, ...] | None = None

    def defection(self) -> tuple[DefectHook, ...]:
        """叛投 clear 位置的 hints 那一格（舊陣營引薦人排著的提示作廢；原本 defection.clear_progress 直接寫 p.hint_queue）：不問 enabled。
        建一次就留著，在叫的那一下才照模組屬性找 hints.defect_clear（monkeypatch 照樣有效）。"""
        if self._defection is None:
            from . import hints  # noqa: PLC0415

            self._defection = (DefectHook("clear", "hints", lambda p: hints.defect_clear(p)),)
        return self._defection

    # core_step（全部拆包第 36 批「你這一步」）
    _steps: tuple[StepHook, ...] | None = None

    def steps(self) -> tuple[StepHook, ...]:
        """「你這一步」的 newbie 那一格（新手目標；原本 weekcard._steps 讀 status["newbie"] 那一段與 step._target 的新手目標那一支）：位置在
        STEP_ORDER。不問 enabled（新手期過了 status 裡就沒有 newbie）。建一次就留著，在叫的那一下才照模組屬性找 actions.newbie_step_items／
        newbie_step_place（monkeypatch 照樣有效）。"""
        if self._steps is None:
            from . import actions  # noqa: PLC0415

            self._steps = (StepHook("newbie", lambda ctx, status, orders: actions.newbie_step_items(ctx, status), ref="newbie",
                                    place=lambda ctx, ref: actions.newbie_step_place(ctx, ref)),)
        return self._steps

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的四格（順序在 SEAM_ORDER；不問 enabled）：sync 引薦人的結語（actions.deliver_enlist）、碰到才說（經 ctx._check_hints：test_hints 換掉 Game 上的名字才打得到）；
        清失效參照最前面蓋老手（actions.mark_veteran：要在換季之前，換季會把陣營清掉）；換季照帶（actions.carry_season）。"""
        if self._seams is None:
            from . import actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.deliver", "enlist", lambda ctx: actions.deliver_enlist(ctx)),
                SeamHook("sync.deliver", "hints", lambda ctx: ctx._check_hints()),
                SeamHook("stale.first", "guide", lambda ctx: actions.mark_veteran(ctx)),
                SeamHook("season.carry", "guide", lambda ctx, old, fresh: actions.carry_season(ctx, old, fresh)),
            )
        return self._seams

    # core_seams（全部拆包第 57 批「分派與標題收接縫」）
    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:rest（序章教體力那一步的調息）：按下去與紀錄標題（原本 Game._act、_action_title 原位）；不問 enabled。那一顆是核心 MENU_ORDER["here"] 的 rest 那一格。"""
        if self._verbs is None:
            from . import actions  # noqa: PLC0415

            self._verbs = (Verb("rest", run=lambda ctx, prepared: actions.rest(ctx),
                                title=lambda ctx: f"調息・{ctx.content.locations[ctx.state.player.location].name}", bot_skip=True),)
        return self._verbs

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的六格（season、act_head、growth、stamina、fame、bag）：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (
            HowtoHook("season", lambda content, season, page: words.season_section(content, season, page.rule)),
            HowtoHook("act_head", lambda content, season, page: words.act_head()),
            HowtoHook("growth", lambda content, season, page: words.jianfa_growth_lines(content, season)),
            HowtoHook("stamina", lambda content, season, page: words.stamina_section(content, season)),
            HowtoHook("fame", lambda content, season, page: words.fame_section(content, season)),
            HowtoHook("bag", lambda content, season, page: words.bag_section()),
        )


FEATURE = GuideFeature()
