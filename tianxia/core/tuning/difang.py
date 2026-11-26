"""地方大事的數字（Config.difang；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。
數字全是草案（玩家一起玩設計稿第一節「正式的數字之後用極限假人量」）。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DifangTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False  # 總開關（預設關；week7、season21 也還沒開）。不蓋開季章：季中打開，下一次有人同步就開這一週的
    # 三幕各要多少：照上一件（全服一件）出過力的人數 × per_head，不低於 need_min（設計稿「目標量照活動的人數定，有下限」）
    need_min: list[int] = Field(default_factory=lambda: [20, 20, 20])
    per_head: list[float] = Field(default_factory=lambda: [3.0, 3.0, 2.0])
    need_max: list[int] = Field(default_factory=lambda: [240, 240, 200])
    # 赴大事（第一、二幕；Joy 2026-11-26「改成特別活動」）：一次花的體力跟探索一次一樣（jianfa.explore_stamina），一天最多 daily_goes 次
    daily_goes: int = 3
    xinde_hit: int = 5  # 每赴一次的小獎：擲成了
    xinde_miss: int = 2  # 沒成、或不擲的做法
    # 事件的做法：寫了屬性的照那一項擲（成了算 way_hit 份、沒成算 way_miss 份）；不擲的穩穩算 way_miss 份
    way_base: float = 0.45  # 屬性 0 的成功率
    way_per_point: float = 0.03  # 每一點屬性多幾成
    way_cap: float = 0.9
    way_hit: int = 2
    way_miss: int = 1
    # 第三幕：一天上去一次、挑一個打法（照那一項屬性擲，成了多一份）；一下的份量 1 + 戰力 ÷ blow_power（夾在 blow_max）
    blow_power: float = 400.0
    blow_max: int = 3
    # 收場：湊滿了每個出過力的人自己挑一份第 material_tier 階的素材、名聲 fame_done、心得 xinde_done；
    # 出力前 top_more 名多一份同類的、戴「義士」；出力最多的 top_names 個名字寫進江湖史（Joy 2026-11-26 獎勵往上調一級）
    material_tier: int = 4
    fame_done: int = 3
    xinde_done: int = 20
    top_more: int = 10
    fame_failed: int = 1  # 沒湊滿也記一點（「不是白費」）
    top_names: int = 3
