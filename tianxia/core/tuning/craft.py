"""意境合成改版的數字（Config.craft；設計稿 https://claude.ai/artifact/G4m44hK3At7x2bmqoAbceu ，Joy 2026-11-10「好」，五件照推薦）。
不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。開關關著（預設）一個字都不變；開著也要等下一次開季蓋章
（WorldState.craft_v2，world_state.stamp_season）才生效，正在跑的季照舊。規則在共用層 tianxia/fusion.py 的「合成改版」那一段。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CraftTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    heat_need: int = Field(default=6, ge=1)  # 火候到這個數就帶真意：兩份層數相加＋上品 1＋地利 1
    near_chance: float = Field(default=0.25, ge=0, le=1)  # 火候差一（heat_need − 1）時自足帶出真意的機會
    bonus_chance: float = Field(default=0.10, ge=0, le=1)  # 每爐多帶一個一重一般功效的機會（還有空位時）
    # 化入：凡、佳、珍各給幾點意蘊，攢滿 yun_per_layer 點本體加一重
    yun_points: dict[str, int] = Field(default_factory=lambda: {"凡": 1, "佳": 2, "珍": 3})
    yun_per_layer: int = Field(default=3, ge=1)
    calm_hours: float = Field(default=6.0, ge=0)  # 秘訣「出關之後」：出關多少遊戲小時之內
    hint_at: int = Field(default=15, ge=1)  # 同一個配方熟到這個數，秘訣給一句提示
