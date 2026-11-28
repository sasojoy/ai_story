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
