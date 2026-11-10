"""馬的來路的數字（Config.horses；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。

Joy 2026-11-10 在選擇卡上挑「奪馬＋馴野馬＋論功賜馬」：三條都要打或花代價才拿得到，不會讓別人掉馬。數字是【預設】，量過再調。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HorsesTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # ── 奪馬：打贏騎馬的那幾路（遊歷、出陣、探索野怪；事件 win），照機率牽走一匹良駒；名駒不從這裡來 ──
    seize_squads: dict[str, float] = Field(default_factory=lambda: {  # 隊伍 id → 這一路打贏牽走一匹的機率
        "guan_patrol": 0.08, "guishou": 0.08, "beijun_wuzu": 0.08, "liangzhou_cavalry": 0.12,
        "toumu": 0.08, "yan_mazei": 0.10, "nz_xiangma": 0.10, "nz_huqi": 0.12,
    })
    seize_cap: int = Field(default=2, ge=0)  # 一人一季最多奪幾匹
    # ── 馴野馬：北方幾處的野馬群；連三步（每步花體力與一個一階素材），第三步擲成敗 ──
    pastures: list[str] = Field(default_factory=lambda: ["juma_river", "yanshan_foot", "baima_ford"])  # 有野馬群的地點 id
    tame_steps: int = Field(default=3, ge=1)
    tame_stamina: int = Field(default=20, ge=0)  # 每一步的體力
    tame_chance: float = Field(default=0.5, ge=0, le=1)  # 最後一步馴成的機會；不成，野馬跑掉、前面幾步白做
    tame_cap: int = Field(default=1, ge=0)  # 一人一季最多馴成幾匹
    herd_per_week: int = Field(default=2, ge=0)  # 每一處每一週全服馴得走幾匹（被別人馴走就沒了）
    wild_steed_chance: float = Field(default=0.05, ge=0, le=1)  # 馴成時是名駒的機會
    wild_steed_cap: int = Field(default=3, ge=0)  # 全服一季最多馴出幾匹名駒
    wild_steed_quality: str = "中品"
    # ── 論功賜馬：全服決戰（不含攻城）得勝那一方，自己出手過、戰功前幾名 ──
    merit_steed_top: int = Field(default=1, ge=0)  # 第 1 名到第幾名賜名駒
    merit_horse_top: int = Field(default=3, ge=0)  # 再往下到第幾名賜良駒
    merit_horse_quality: str = "上品"
    merit_steed_quality: str = "中品"
