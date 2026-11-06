"""有所感與頓悟（功能包；開發規範手冊 3.2）：探索撞上有所感（選做法、擲中、畫一筆或順其自然）、自己畫字悟出的意境（看圖取名的三段式）、
特殊頓悟（心靈拷問、心境小試、心魔、取名）。全部拆包第 24 批搬進來。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- sensing.py：有所感的規則（原 tianxia/sensing.py）；epiphany.py：特殊頓悟（原 tianxia/epiphany.py：import 的時候登記一條線的鉤子）；
  glyph.py：讀筆畫（原 tianxia/glyph.py）；insight_llm.py：看圖取名的 B 段（原 tianxia/insight_llm.py）——舊名都留成別名
- actions.py：原本 Game 上的 10 個方法（Game 留 8 個一行委派）與核心原位、探索包、引導包叫的 7 個服務的本體
- routes.py：/api/sense、/api/sense_read、/api/sense_warm（原本寫在 server.py；殼照 FEATURES 掛）

掛鉤：choose（只吃 sense:；dunwu: 要帶自己寫的名字，留在 Game.choose 原位叫委派）、scene（接縫掛鉤：有所感的卡、取名那一張）、routes。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome


class SenseFeature(Feature):
    name = "sense"
    web = ("sense.js",)  # 有所感的畫布、悟來的那一筆、神品意境取名（全部拆包第 66 批從 app.js 切出來）
    # sense:<做法>、sense:draw、sense:let（有所感）；dunwu:think、dunwu:<候選>、dunwu:own（特殊頓悟取名）。Feature.prefix 收 tuple（第 11 批）
    prefix = ("sense", "dunwu")
    content = ("insight_scenes.json",)  # content.py 照舊讀、content.check_insight_scenes 照舊驗（核心沒有 import 這一包）；檔名照舊
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：有所感那一份與流水號、選錯的帳；特殊頓悟這一季的次數與保底、等著取名的那一個。
    # 換季全部跟著新角色重來（Game._reset_player_for_new_season 本來就不帶）。私有意境 own_insights／own_serial 是共用規則層 insights 的（合成也寫）
    player_fields = ("sensing", "sense_serial", "sense_misses", "epiphanies", "epiphany_dry", "god_naming")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """一直開著：有所感沒有總開關（有沒有場景看內容 content/insight_scenes.json），特殊頓悟看自己的 Config.epiphany——
        搬包之前 choose 的 sense、dunwu 兩支與選單、場景都不看任何一包的開關。"""
        return True

    def choose(self, ctx, kind, arg):
        """sense:<做法>、sense:let（原本 Game.choose 的 sense 那一支叫 Game._sense；「畫下來」sense:draw 在建紀錄之前就回了）：標題照
        原本 Game._action_title 的 sense 那一支（「有所感・場景」，動作之前先拿）。dunwu: 不接（自己寫的名字在 Game.choose 的 text，
        掛鉤不帶），留在原位叫 Game._epiphany_name。"""
        if kind != "sense":
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.sense_title(ctx), run=lambda: actions.sense(ctx, arg))

    def scene(self, ctx):
        """自己眼前的場景卡（接縫掛鉤，第 11 批；原本 Game._own_scene_text 宴客那一行之後的兩支）：有所感的卡、特殊頓悟取名那一張；
        都不是是 None。不問 enabled（原位本來就不看開關）。"""
        from . import actions  # noqa: PLC0415

        return actions.scene(ctx)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)


FEATURE = SenseFeature()
