"""慢慢長出來的數字（Config.unfold；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UnfoldTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    gift: int = Field(100, ge=0)  # 見面禮：新角色辦完第一件託付，萬寶閣掌櫃送幾個元寶（Joy 2026-11-25 選 100）；0 不送
    # 江湖頁的打點、馬市兩塊招牌：銀兩第一次到這麼多才長出來（江湖頁重排第六批量的：打點門路最便宜 30 兩、駑馬 100 兩；草案，待 joy 定）
    sign_silver_dadian: int = Field(50, ge=0)
    sign_silver_market: int = Field(100, ge=0)
    # 帶著做一次（Joy 2026-11-26「照建議」）：小事卡按了「改天」，過了這麼多小時再碰到同一個時機才再出一次；第二次再改天就不出了
    later_hours: float = Field(12, ge=0)
    # 舊角色（開關打開以前就在玩的人）也帶：還沒碰過那個系統的才出（關掉＝只帶新角色）
    old_chars: bool = True
