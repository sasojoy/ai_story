"""條款的數字（Config.terms；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TermsTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 開著：登入後沒同意過現行版的帳號要按同意（第一次一定要按；換版號之後照 update_must）。
    # 關著：/terms、/privacy 兩頁照樣看得到，只是不問同意。
    enabled: bool = False
    # 改版的考慮期（天；update_must 關著才用）：定型化契約應記載事項十七「通知到達後十五日內未表示反對，視為接受」
    grace_days: int = Field(default=15, ge=1)
    # 換版號之後同意過舊版的人要不要按過同意才能進（第 243 批；企劃者 2026-11-21「改成強制按同意」）。
    # 設 false 回到考慮期的做法：grace_days 天內問（可以稍後再看）、過了視為接受。
    update_must: bool = True
