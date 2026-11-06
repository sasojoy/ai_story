"""一條線（功能包；開發規範手冊 3.2）：特殊事件與特殊頓悟的底座（企劃者 2026-10-26，設計稿「一條線」；長篇奇事 2026-10-27）。
一條線是一串段（事件、答題、打一場、等一件事做成），每一段走完照這條線自己記下的記號往下，結局一定寫進傳。全部拆包第 30 批搬進來。
README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- storyline.py：一條線自己的走法（選單、答題、打一場、結算、收尾、餘波；原 tianxia/storyline.py 的後半，舊名留成別名）。
  底座〔登記鉤子的字典、開線、換字、題目文字〕在共用規則層 tianxia/story_base.py（核心的 rules、事件檢定與探索包、有所感包也讀），storyline.py re-export 它的每個名字
- actions.py：原本 Game 上的 10 個方法（Game 留 10 個一行委派）與核心原位叫的 4 個（答題選單、「未了之事」那一顆、換季收線、標題）的本體

掛鉤：choose（只吃 story:）、scene（接縫掛鉤：眼前的答題）、effects（核心的效果格 story：一條線的一步，第 32 批）。enabled 一直是 True，線自己看 Config.jianfa.storylines。沒有路由（/api/do/story_seen 在殼的 MAIN_ACTIONS，照舊叫 Game）、
沒有假人分數（story: 原本在 bot_policy.score 就沒有處理，落到預設的 None）。
"""
from __future__ import annotations

from tianxia.core.features import EffectHook, Feature, Outcome, SeamHook


class StoryFeature(Feature):
    name = "story"
    prefix = "story"  # story:<線>、story:<線>:a<答案序號>、story:<線>:later
    # content/events/ 底下四個長篇奇事的段落事件檔（content.py 照舊讀；content/storylines.json 混著章回主線的線，不宣告：章回批再看）
    content = ("events/story_fuzhi.json", "events/story_maier.json", "events/story_wangyue.json", "events/story_wolong.json")
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：這一季開過的線與進度、答題停在哪一條、等著跳出來的卡、紀念物與跨季旗標。
    # 紀念物與跨季旗標換季跟著角色（Game._reset_player_for_new_season），其餘換季重來
    player_fields = ("storylines", "story_open", "story_cards", "keepsakes", "lasting")
    carried = ("keepsakes", "lasting")

    def enabled(self, ctx) -> bool:
        """一直開著：原本 choose 的 story: 那一支與標題、選單都不看任何開關（線自己看 Config.jianfa.storylines〔storyline.on〕；關著時選單上沒有 story: 的選項，
        按舊的 id 也走原本那條路）。灰掉的包不會接 choose，落到 else 當成事件選項炸掉，所以要一直是 True。"""
        return True

    def choose(self, ctx, kind, arg):
        """story:<線>（按「未了之事」那一顆、答題的答案、先擱著；原本 Game.choose 的 storyline.OPTION 那一支叫 Game._story_act）：標題照原本 Game._action_title
        的那一支（線的名字，動作之前先拿）。"""
        if kind != "story":
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.story_title(ctx, arg), run=lambda: actions.story_act(ctx, arg))

    def scene(self, ctx):
        """自己眼前的場景卡（接縫掛鉤，第 11 批；原本 Game._own_scene_text 有所感、取名之後的一支）：一條線的答題；沒有答題是 None。
        不問 enabled（原位本來就不看開關）。排在有所感包、宴客包之後（FEATURES 的順序），第一個不是 None 的算。"""
        from . import actions  # noqa: PLC0415

        return actions.scene(ctx)

    # core_effects（全部拆包第 32 批「效果與叛投掛鉤」）
    _effects: tuple[EffectHook, ...] | None = None

    def effects(self) -> tuple[EffectHook, ...]:
        """核心的效果格 story（一條線的一步；原本 rules.apply_effect 最後一段直接寫 storylines、keepsakes）：不問 enabled。
        建一次就留著，在叫的那一下才照模組屬性找 storyline.effect_step（monkeypatch 照樣有效）。"""
        if self._effects is None:
            from . import storyline  # noqa: PLC0415

            self._effects = (EffectHook("story", lambda r: storyline.effect_step(r)),)
        return self._effects

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的兩格（順序在 SEAM_ORDER；不問 enabled）：sync 走一步（actions.deliver_story：召見之後、席次之前）、換季照帶紀念物與跨季旗標（actions.carry_season）。"""
        if self._seams is None:
            from . import actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.deliver", "story", lambda ctx: actions.deliver_story(ctx)),
                SeamHook("season.carry", "story", lambda ctx, old, fresh: actions.carry_season(ctx, old, fresh)),
            )
        return self._seams


FEATURE = StoryFeature()
