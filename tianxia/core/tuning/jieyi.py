"""結義的數字（Config.jieyi；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JieyiTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_members: int = Field(default=5, ge=2)  # 一組最多幾人（設計稿 v2 卷一）
    offer_seconds: float = Field(default=1800, gt=0)  # 邀請多久沒回就作廢（現實秒；同切磋的 invite_ttl_seconds）
    cooldown_seconds: float = Field(default=86400, ge=0)  # 割袍斷義之後多久不能再結義（現實秒）
    log_cap: int = Field(default=40, ge=1)  # 義譜最多留幾行（舊的先丟）
    feud_seconds: float = Field(default=86400, gt=0)  # 替兄出頭：兄弟被截殺之後多久內能報這一筆仇（現實秒；第一批，Joy 2026-11-09）
    # 假人收到結義邀請（同名帖的回法）：等多久才回、答應與婉拒的比例，其餘不理（等它作廢）【預設】
    bot_reply_seconds: float = Field(default=60, ge=0)
    bot_accept_share: float = Field(default=0.5, ge=0, le=1)
    bot_reject_share: float = Field(default=0.25, ge=0, le=1)
