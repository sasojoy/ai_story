"""江湖錄的數字（Config.codex；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CodexTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    tracker: bool = False  # 江湖頁狀態列下一行的「進行中」（Joy 2026-11-13 設計稿 v2 選甲）：要 enabled 也開著
