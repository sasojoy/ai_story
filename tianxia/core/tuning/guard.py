"""親衛隊長的數字（Config.guard；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。
設計稿 https://claude.ai/artifact/7Sra7sBo7njyH34B2Nr7Su（Joy 2026-11-09「其他都按照建議」）；數字都是【草】，做完拿假人量過再定。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# 性向九種（設計稿第二節）：模型只能從這裡挑；出師時照分數挑出路（第二批）
TAGS = ("勇", "謀", "俠", "巧", "耕", "市", "暗", "準", "仁")

# 求學的七處去處（設計稿第一節「求學」）：id → 要花的銀兩、推的性向、動的情分（丟著不管的往下）。名字與信在 features/guard/texts.py
SCHOOLS = {
    "shuyuan": {"silver": 200, "tags": {"謀": 3, "仁": 1}, "qing": 1},
    "wuguan": {"silver": 150, "tags": {"勇": 3, "俠": 1}, "qing": 1},
    "junying": {"silver": 100, "tags": {"勇": 2, "準": 2}, "qing": 0},
    "tiepu": {"silver": 80, "tags": {"巧": 3, "耕": 1}, "qing": 0},
    "yiguan": {"silver": 150, "tags": {"仁": 3, "巧": 1}, "qing": 1},
    "gensui": {"silver": 0, "tags": {"俠": 1, "市": 1, "準": 1}, "qing": 2},
    "buguan": {"silver": 0, "tags": {"市": 2, "暗": 2}, "qing": -3},
}

# 每天教他什麼（成長期一天一次；設計稿 GzVzRd… 第三節）：id → 推的性向、動的情分。「讓他自己玩」的性向照心性挑（恩深、敬重、淡然往俠，怨懟、恨極往暗），寫在 features/guard/rules.py
LESSONS = {
    "read": {"tags": ["謀"], "qing": 0}, "fist": {"tags": ["勇"], "qing": 0}, "work": {"tags": ["巧", "耕"], "qing": 0},
    "errand": {"tags": ["市"], "qing": 0}, "herb": {"tags": ["仁"], "qing": 0}, "hunt": {"tags": ["準"], "qing": 0},
    "play": {"tags": [], "qing": 1}, "free": {"tags": [], "qing": 0},
}

# 出路十種（設計稿第三節）：名字 → 看哪幾種性向（取平均）。出師時照分數挑前三交給模型；專長是第三批
PATHS = (
    ("將軍", ("勇", "謀")), ("謀士", ("謀",)), ("遊俠", ("俠", "勇")), ("鐵匠", ("巧",)), ("農夫", ("耕",)),
    ("乞丐", ("市",)), ("殺手", ("暗",)), ("弓箭手", ("準",)), ("醫者", ("仁",)), ("斥候", ("市", "準")),
)


class GuardTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    meet_level: int = Field(default=10, ge=1)  # 幾級撞見那個孩子（7 天季同）
    # 成長期三段（初來、相熟、長成；Joy 2026-11-10「沒有跟他互動幾次就要把她送出去求學」「我們收留他的時候已經12-13歲」→ 設計稿
    # https://claude.ai/artifact/GzVzRdBgshFJpvYsNd8E91「好」）：看一起過的日子與經歷的事，不看等級。每一段兩樣都到了才來那一段的大事；三段走完他開口想去求學
    phase_days: int = Field(default=3, ge=0)  # 每一段要一起過幾天（換日才算一天；7 天季照 week7_phase_days）
    week7_phase_days: int = Field(default=1, ge=0)
    phase_events: int = Field(default=8, ge=0)  # 每一段要一起經歷幾件事（家裡、路上的事答了、每天教他的那一下都算；7 天季照 week7_phase_events）
    week7_phase_events: int = Field(default=4, ge=0)
    lessons: dict[str, dict] = Field(default_factory=lambda: {k: {"tags": list(v["tags"]), "qing": v["qing"]} for k, v in LESSONS.items()})
    study_days: float = Field(default=3, gt=0)  # 求學幾天（季曆的天；7 天季照 week7_study_days）
    week7_study_days: float = Field(default=1, gt=0)
    letters: int = Field(default=2, ge=0)  # 求學期間寫幾封信回來（平均排在求學那幾天裡）
    schools: dict[str, dict] = Field(default_factory=lambda: {k: {"silver": v["silver"], "tags": dict(v["tags"]), "qing": v["qing"]} for k, v in SCHOOLS.items()})
    paths: list[tuple[str, tuple[str, ...]]] = Field(default_factory=lambda: list(PATHS))
    path_options: int = Field(default=3, ge=1)  # 出師時交給模型挑的出路有幾條
    bio_max: int = Field(default=300, ge=50)  # 生平最多幾個字
    settle_budget_seconds: float = Field(default=60, gt=0)  # 出師結算（稱號、生平、立誓那一段）模型的時間預算
    # 第三批：投效之後（設計稿第四節）
    hurt_ratio: float = Field(default=0.3, gt=0, le=1)  # 做完一件事氣血掉到上限的幾成以下、而且比做之前少：他說一句（一天一次）
    band_steps_per_season: int = Field(default=1, ge=0)  # 投效之後心性一季最多換幾檔（恨可以被焐回來、恩也會寒心，只是很慢）
    # 專長（設計稿第三節；Joy 2026-11-09「好」先合時全 0）。第四批（Joy 2026-11-10「全部做完一起上」）照 scripts/measure_guard.py 量過填：
    # 人人養得到，一格不超過玉璽碎片（威力 ×1.10、閃避 +0.03）的一半。week7 30 級、六種配法 × 七套身手、每格 400 場：
    # 弓箭手 +3 個百分點；殺手、謀士 ×1.05 截殺設伏勝率平均 +6 個百分點（碎片 +13）；醫者少扣 5%～10% 的氣血；其餘照單位換算。出路 → {鍵: 值}；鍵與原位對照在 core/guard_base.py
    perks: dict[str, dict[str, float]] = Field(default_factory=lambda: {
        "將軍": {"big_fight": 3.0}, "謀士": {"ambush": 0.05}, "遊俠": {"bounty_pct": 0.1}, "鐵匠": {"forge_points": 4.0},
        "農夫": {"stamina_day": 24.0}, "乞丐": {"tavern_asks": 1.0}, "殺手": {"raid": 0.05}, "弓箭手": {"fight_pp": 3.0},
        "醫者": {"toll_cut": 0.05}, "斥候": {"explore_legend": 0.25},
    })
    # 心性的加成（設計稿第四節）：恩深、敬重有機會替你擋一下（落敗閃成僵持）；怨懟、恨極不擋刀（Joy 2026-11-09 照推薦）。碎片金角 +0.03
    band_perks: dict[str, dict[str, float]] = Field(default_factory=lambda: {"恩深": {"dodge": 0.02}, "敬重": {"dodge": 0.01}})
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
