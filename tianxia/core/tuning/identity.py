"""帳號綁定的數字（Config.identity；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IdentityTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
