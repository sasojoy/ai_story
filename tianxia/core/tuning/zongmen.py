"""門派的數字（Config.zongmen；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。
設計稿 v6（Joy 2026-11-08「不錯，按照設計稿動工」）；數字是初稿，照平衡檢查清單量過再定。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ZongmenTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # 師門武譜（第二批）
    offer_seconds: float = 3 * 86400  # 獻上來的一式等同門試練多久（現實秒），過了沒湊滿就退回
    need_min: int = 2  # 至少要幾個同門試練過才入譜（不含獻的人）
    need_max: int = 5  # 最多要幾個（門人再多也不超過）
    trial_xinde: int = 10  # 試練一次花的心得
    learn_xinde: int = 40  # 學一式花的心得
    pending_per_giver: int = 1  # 一個人同時最多有幾式在等試練
