"""條款的數字（Config.terms；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TermsTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 開著：登入後沒同意過現行版的帳號要按同意（第一次一定要按；改版的 grace_days 天內跳改版頁、過了視為接受）。
    # 關著：/terms、/privacy 兩頁照樣看得到，只是不問同意。
    enabled: bool = False
    # 改版的考慮期（天）：定型化契約應記載事項十七「通知到達後十五日內未表示反對，視為接受」
    grace_days: int = Field(default=15, ge=1)
