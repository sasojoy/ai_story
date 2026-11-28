"""門派論劍的數字（Config.lunjian；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。
設計稿：門派論劍設計稿第三版（https://claude.ai/artifact/DVU9c63P9mfszr7VJsmTmL；Joy 2026-11-28「機制這樣可以 開始做」）。禮匣的機率是草案，做好後用假人量。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LunjianTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False  # 總開關（預設關；week7、season21 也還沒開）。不蓋開季章：季中打開，那一週起就能報名
    # 時刻：每週最後一天（季曆）晚上 draw_hour 點截止報名、抽籤，fight_hour 點開打；季末早於那一天時照季末往前推
    draw_hour: int = 20
    fight_hour: int = 21
    seats: int = 3  # 一門上台幾人（先鋒、中堅、大將）
    elder_share: float = 0.9  # 師兄的身手：這一週全服報名者威力的中間值 × 它
    # 賞：上台的人贏一場單挑一份第 material_tier 階素材（自己挑類）；門派贏了上台的本人各一個論劍禮匣（三場全勝換上等）
    material_tier: int = 4
    # 禮匣開出什麼：[種類, 數量, 權重]。種類 mat（四階素材，挑幾份）、legend（破境丹幾顆）、coin（送的那一種元寶，五銖上線後就是五銖）、
    # move（免費製作一次絕招動畫）
    box: list[list] = Field(default_factory=lambda: [["mat", 1, 40], ["legend", 1, 25], ["coin", 100, 20], ["coin", 300, 10], ["move", 1, 5]])
    top_box: list[list] = Field(default_factory=lambda: [["mat", 2, 30], ["legend", 1, 25], ["coin", 300, 25], ["move", 1, 20]])
    bot_sign_share: float = 0.6  # 拜了門的那幾位，照名號雜湊有這麼多會報名（每週重擲）
    # 打法第四版（Joy 2026-11-28「可以」：底子照擂台、戰策由模型判、引擎再夾；身手差兩成的人有三四成勝算）
    plan_chars: int = 30  # 戰策最多幾個字
    plan_cap: float = 5.0  # 戰策全佔上風（判讀 ±10）時推的起手氣勢，悟性在基準（5）時
    plan_cap_wis: float = 0.4  # 悟性每高過基準一點，上限多推這麼多（悟性 15 是 9）
    plan_tilt: float = 1.5  # 戰策寫了哪一路（強攻、固守、奇襲），分身出那一招的份量乘它
    judge_wait_hours: float = 0.25  # 開打之後等模型判讀最多幾個曆時，過了沒判到的照關鍵字判
    judge_round_seconds: float = 30.0  # 背景那一條多久看一次（現實秒）
    judge_budget_seconds: float = 60.0  # 一場單挑的判讀最多花多久（現實秒）
    crowd_chance: float = 0.3  # 一場單挑碰上場邊事件的機率（內容檔 crowd：一句話、推誰幾點氣勢）
