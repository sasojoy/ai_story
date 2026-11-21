"""異聞的數字（Config.yiwen；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。

全部是草案【草】（設計 docs/superpowers/specs/2026-11-20-異聞-design.md 第十三節；企劃者 2026-11-21「看過了，十題都照建議做」），等量過再定。
時間一律是季鐘（rules.season_clock：world.time / time_scale，這一季開季以來真的在跑的現實秒；總計畫「對不上的」第 1 條）；
只有全服每天的名額照台灣日（ctx._pill_day）。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class YiwenTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False  # 總開關；開季蓋章 WorldState.yiwen_on（rules.on 兩個都要）
    season_cap: int = 30  # 一季最多幾則（＝開場句數）【定：一季 30 則】
    discover_chance: float = 0.0002  # 【草】一段探索不用道具撞見新的一則的機率（設計 7.3）
    free_daily_cap: int = 1  # 【草】全服每天不用道具的發掘最多幾則（台灣日）
    free_per_player: int = 1  # 【草】一個人一季不用道具最多發掘幾則
    seek_per_player: int = 3  # 【草】一個人一季尋異符最多用得上幾張（異聞三）
    discover_until_day: float = 18  # 開季之後季鐘的第幾天以後不再發掘（企劃者 11/21「維持第 18 天」）；重走開到季末
    rewalk_chance: float = 0.07  # 【草】在有異聞的地點探索一段，撞見一則自己還沒走完的機率
    pending_hours: float = 24  # 【草】撞見之後放著多久照已寫的公開（或名額放回）；世界那一格掃（異聞四）
    typed_max: int = 30  # 【草】自己說最多幾字（異聞二）
    typed_tries: int = 3  # 【草】一步自己說被擋幾次之後只能按現成的（異聞二）
    luck_good: float = 0.6  # 【草】一步擲到「順」的機率（引擎擲）
    step_budget_seconds: float = 60  # 【草】一步從開單到寫成的總預算（異聞二）
    step_min_write_seconds: float = 15  # 【草】審字之後剩下的不到這麼多就不寫幕（異聞二）
    typed_staff_extra: list[str] = Field(default_factory=lambda: ["公告", "天下大勢"])  # 自己說另外擋的身分字（name_base.staff_like 沒涵蓋的；總計畫「對不上的」第 3 條）
    scene_chars: int = 60  # 【草】一段的字數（提示寫的；檢查放到 72）
    option_chars: int = 14  # 【草】一個做法的字數（檢查放到 16）
    ledger_chars: int = 22  # 【草】帳一條的字數
    retry: int = 1  # 【草】程式檢查沒過重問幾次
    fallback_max_per_path: int = 1  # 【草】一條路最多幾幕是替身，超過那一條不算數
    branch_cap: int = 5  # 【草】一則最多開幾條岔路（異聞三）
    free_branches: int = 2  # 一則頭幾條岔路不用道具【定：頭兩條】（異聞三）
    verdict_hours: float = 72  # 發掘之後多久定論【定：三天】（異聞四）
    omen_min_steps: int = 5  # 【草】定論那條路至少幾個足跡才給兆頭（異聞四）
    omen_margin: int = 2  # 【草】兩軍足跡差幾個以上才給邊（異聞四）
    omen_push: int = 3  # 【草】兆頭推那一條戰線幾點（異聞四）
    unreadable_reports: int = 3  # 【草】「讀不通」至少幾個人按（異聞四）
    unreadable_share: float = 0.2  # 【草】而且至少佔看過的人幾成（異聞四）
    abuse_hide_reports: int = 3  # 【草】幾個人檢舉同一處先遮起來（異聞四）
    mute_days_default: float = 7  # 【草】管理者禁寫預設幾天（異聞四）
    per_scene: dict[str, str] = Field(default_factory=lambda: {"silver": "medium", "xinde": "medium"})  # 【草】寫成一幕的獎勵等級
    per_replay: dict[str, str] = Field(default_factory=lambda: {"silver": "small", "xinde": "small"})  # 【草】重放一幕
    finish_first: dict[str, str] = Field(default_factory=lambda: {"silver": "rich", "xinde": "rich"})  # 【草】發掘者走完三步
    finish: dict[str, str] = Field(default_factory=lambda: {"silver": "medium", "xinde": "medium"})  # 【草】後來的人走完三步
    luck_material_tier: int = 1  # 【草】寫成的那一幕是「順」多給一個這一階的此地素材
    discover_fame: int = 5  # 【草】發掘者走完三步的名望
    verdict_fame: int = 5  # 【草】定論那條路的主人的名望（異聞四）
