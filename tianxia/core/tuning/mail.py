"""帖友書信的數字（Config.mail；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。
設計稿 https://claude.ai/artifact/FhMZSwH6aqNsrnNAwHBznn（Joy 2026-11-07「信能寫聯絡方式、網址嗎？不擋，其他按照建議」）。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MailTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False  # 緊急開關：關了信匣與「寫信」都不見，信不刪（小檔照留）
    max_chars: int = Field(default=200, ge=10)  # 一封最多幾個字
    per_day: int = Field(default=10, ge=1)  # 一天寄幾封（回體丹那一套的 00:00 換日）
    unanswered: int = Field(default=3, ge=1)  # 對方沒回之前，同一個人最多連寄幾封
    keep_per_pair: int = Field(default=200, ge=10)  # 一對帖友在主檔留最近幾封（多的丟最舊的）
    mute_days: tuple[int, ...] = (1, 3, 7)  # 管理者停他寄信可以挑的天數
