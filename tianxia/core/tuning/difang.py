"""地方大事的數字（Config.difang；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。
數字全是草案（玩家一起玩設計稿第一節「正式的數字之後用極限假人量」）。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DifangTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False  # 總開關（預設關；week7、season21 也還沒開）。不蓋開季章：季中打開，下一次有人同步就開這一週的
    # 三幕各要多少：照這個大區上一件出過力的人數 × per_head，不低於 need_min（設計稿「目標量照在那一區活動的人數定，有下限」）
    need_min: list[int] = Field(default_factory=lambda: [12, 6, 12])
    per_head: list[float] = Field(default_factory=lambda: [3.0, 1.0, 2.0])
    need_max: list[int] = Field(default_factory=lambda: [90, 40, 80])
    # 第二幕：挑一個做法，照那一項屬性擲（成了算 way_hit 份、沒成算 way_miss 份；一人一次）
    way_base: float = 0.45  # 屬性 0 的成功率
    way_per_point: float = 0.03  # 每一點屬性多幾成
    way_cap: float = 0.9
    way_hit: int = 2
    way_miss: int = 1
    # 第三幕：一天上去一次；一下的份量 1 + 戰力 ÷ blow_power（夾在 blow_max）
    blow_power: float = 400.0
    blow_max: int = 3
    # 收場：湊滿了每個出過力的人一份此地素材（第 material_tier 階）與名望；出力最多的 top_names 個名字寫進江湖史
    material_tier: int = 2
    fame_done: int = 3
    fame_failed: int = 1  # 沒湊滿也記一點（「不是白費」）
    top_names: int = 3
