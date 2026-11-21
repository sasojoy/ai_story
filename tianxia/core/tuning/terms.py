"""條款的數字（Config.terms；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TermsTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 開著：登入後沒同意過任何一版的帳號要按同意（第一次一定要按）；同意過舊版的照 update_must（預設考慮期）。
    # 關著：/terms、/privacy 兩頁照樣看得到，只是不問同意。
    enabled: bool = False
    # 改版的考慮期（天；update_must 關著〔預設〕才用）：使用條款第九條、定型化契約應記載事項十七「通知到達後十五日內未表示反對，視為接受」
    grace_days: int = Field(default=15, ge=1)
    # 換版號之後同意過舊版的人要不要按過同意才能進（第 243 批開的開關，第 246 批預設改回關）。
    # 關著（預設）：published 起 grace_days 天內看到可以「稍後再看」的改版頁、過了視為接受——跟使用條款第九條與定型化契約應記載事項一致。
    # 設 true：每個人都得按過新版的同意才進得去。企劃者 2026-11-21 凌晨選過「改成強制按同意」，下午改選「這次用 15 天考慮期」；
    # 強制留給以後大改的版，開之前先問法律專業。
    update_must: bool = False
