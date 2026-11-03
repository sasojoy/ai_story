"""有所感與頓悟（功能包；開發規範手冊 3.2）：探索撞上有所感（選做法、擲中、畫一筆或順其自然）、自己畫字悟出的意境（看圖取名的三段式）、
特殊頓悟（心靈拷問、心境小試、心魔、取名）。全部拆包第 24 批搬進來。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class SenseFeature(Feature):
    name = "sense"
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


FEATURE = SenseFeature()
