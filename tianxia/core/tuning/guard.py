"""親衛隊長的數字（Config.guard；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。
設計稿 https://claude.ai/artifact/7Sra7sBo7njyH34B2Nr7Su（Joy 2026-11-09「其他都按照建議」）；數字都是【草】，做完拿假人量過再定。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# 性向九種（設計稿第二節）：模型只能從這裡挑；出師時照分數挑出路（第二批）
TAGS = ("勇", "謀", "俠", "巧", "耕", "市", "暗", "準", "仁")


class GuardTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    meet_level: int = Field(default=10, ge=1)  # 幾級撞見那個孩子（7 天季同）
    study_level: int = Field(default=20, ge=1)  # 幾級送去求學（第二批；7 天季 15）
    qing_cap: int = Field(default=20, ge=1)  # 情分上下限
    step_cap: int = Field(default=3, ge=1)  # 一件事最多動多少情分（模型評 −2～+2，固定事件寫死的也夾這個）
    tags: list[str] = Field(default_factory=lambda: list(TAGS))
    tag_cap: int = Field(default=2, ge=1)  # 一個做法最多加幾種性向
    # 心性五檔（設計稿第二節）：情分 ≥ 這幾個門檻由高到低；都不到是恨極
    bands: list[tuple[int, str]] = Field(default_factory=lambda: [(12, "恩深"), (4, "敬重"), (-3, "淡然"), (-11, "怨懟")])
    hate_band: str = "恨極"
    home_per_day: int = Field(default=1, ge=0)  # 每天保底幾件家裡的事（7 天季照 week7_home_per_day）
    week7_home_per_day: int = Field(default=2, ge=0)
    road_chance: float = Field(default=0.35, ge=0, le=1)  # 帶他出門、花了體力的那一下冒出一件的機會
    road_per_day: int = Field(default=3, ge=0)  # 一天最多冒出幾件
    log_cap: int = Field(default=60, ge=1)  # 紀事最多留幾行（舊的先丟；給模型的是最後 prompt_memos 行）
    prompt_memos: int = Field(default=10, ge=1)
    wait_seconds: float = Field(default=600, gt=0)  # 等模型生事件等多久（世界秒）就換固定事件
    budget_seconds: float = Field(default=40, gt=0)  # 生一件事、評一句自己寫的，模型的時間預算
    say_max: int = Field(default=60, ge=1)  # 自己寫的那一句最多幾個字
