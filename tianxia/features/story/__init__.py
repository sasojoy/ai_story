"""一條線（功能包；開發規範手冊 3.2）：特殊事件與特殊頓悟的底座（企劃者 2026-10-26，設計稿「一條線」；長篇奇事 2026-10-27）。
一條線是一串段（事件、答題、打一場、等一件事做成），每一段走完照這條線自己記下的記號往下，結局一定寫進傳。全部拆包第 30 批搬進來。
README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- storyline.py：一條線自己的走法（選單、答題、打一場、結算、收尾、餘波；原 tianxia/storyline.py 的後半，舊名留成別名）。
  底座〔登記鉤子的字典、開線、換字、題目文字〕在共用規則層 tianxia/story_base.py（核心的 rules、事件檢定與探索包、有所感包也讀），storyline.py re-export 它的每個名字
- actions.py：原本 Game 上的 10 個方法（Game 留 9 個一行委派）與核心原位叫的 4 個（答題選單、「未了之事」那一顆、換季收線、標題）的本體

掛鉤：choose（只吃 story:；enabled 一直是 True，線自己看 Config.jianfa.storylines）。沒有路由（/api/do/story_seen 在殼的 MAIN_ACTIONS，照舊叫 Game）、
沒有假人分數（story: 原本在 bot_policy.score 就沒有處理，落到預設的 None）。
"""
from __future__ import annotations

from tianxia.core.features import Feature


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


FEATURE = StoryFeature()
