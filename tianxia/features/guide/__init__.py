"""新手引導（功能包；開發規範手冊 3.2）：草廬之後的引導框、碰到才說的提示、新手目標、開局第一分鐘、入伍段。全部拆包第 22 批（引導一）
搬進來；玩法說明（howto）是第 59 批（引導二）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- rules.py：說書人的步驟與任務卡（原 tianxia/guide.py；那個名字留成指到這裡的別名）
- hints.py：碰到才說（原 tianxia/hints.py）；newbie.py：新手目標（原 tianxia/newbie.py）；opening.py：開局第一分鐘（原 tianxia/opening.py）；
  enlist.py：入伍段（原 tianxia/enlist.py）——舊名都留成別名
- actions.py：原本 Game 上的 31 個方法（Game 留 24 個一行委派）與核心原位叫的 12 個服務的本體
- checks.py：內容檢查（碰到才說那一塊，原本在 content.validate）

這一包沒有選項前綴：它的動作走 routes.py 的 main_actions（殼的 MAIN_ACTIONS，第 68 批；hints_off、skip_tutorial、view_map、view_orders、view_tab、guide_ack、
newbie_drifter）與 /api/prologue，選單上的那幾顆是別人的（act:rest 是核心 act: 的子動詞、開局三選一是事件的 choice:、投靠是 faction:）。
所以 options、menu、choose、bot_pick 都是預設的；enabled 一直是 True（引導、提示、新手目標、開局各有自己的開關，包本身沒有總開關）。
"""
from __future__ import annotations

from tianxia.core.features import DefectHook, Feature, StepHook


class GuideFeature(Feature):
    name = "guide"
    prefix = None  # 沒有自己的選項（見模組說明）
    content = ("tutorial.json", "hints.json", "opening.json")  # content.py 照舊讀（第 62 批起照它載）；檔名照舊
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

    def main_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.main_actions(shell)


FEATURE = GuideFeature()
