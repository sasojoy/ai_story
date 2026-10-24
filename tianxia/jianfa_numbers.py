"""減法季批 2（探索一顆、三道閘、屬性五段）的數字（減法季整合設計 4.1、4.2、4.5；主機側實作計畫第三節 Task 2-1）。

批 0（雲端側）的 `Config.jianfa`（`JianfaRules`）與開季的章還沒到，這一批先把純規則做起來：數字放在這個獨立的模型裡，
純規則（`explore_one`、`growth`）吃它（duck-typed 的 cfg），測試直接建它。批 0 到了之後把這些欄位併進 `JianfaRules`
（`class JianfaRules(JianfaNumbers)`，或照抄欄位與驗證），純規則改傳 `content.config.jianfa`，函式本身不必改。

欄位名照計畫 Task 2-1，跟子開關撞名的改了名：六張表叫 `explore_tables`（子開關叫 `explore_one`；計畫寫 `Config.explore_one`）。
數字都是【預設】，出處寫在每一欄旁邊。這裡不 import `models`：`models.py` 之後要引用這裡（`JianfaRules` 繼承或掛它），反過來會循環。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ExploreKind = Literal["town", "temple", "ford", "wild", "hill", "camp"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExploreOneTable(_Strict):
    """一種地點的探索表（設計 4.1）：出門一趟，每一拍照這四欄的比重抽一類（事件、遭遇、素材、感悟）。

    地點的標籤（`Location.tags`）跟 tags 有交集就算這一種；`JianfaNumbers.explore_tables` 照順序比對、第一個對得上的就是。
    四欄加起來 100（設計的表是百分比；危險度與懸賞再往上加減，見 `explore_one.weights`）。"""

    kind: ExploreKind
    tags: list[str] = Field(min_length=1)
    event: int = Field(ge=0)
    encounter: int = Field(ge=0)
    material: int = Field(ge=0)
    insight: int = Field(ge=0)

    @model_validator(mode="after")
    def _adds_up_to_100(self) -> ExploreOneTable:
        total = self.event + self.encounter + self.material + self.insight
        if total != 100:
            raise ValueError(f"探索表 {self.kind} 四欄加起來要是 100（現在 {total}）")
        return self


def _default_tables() -> list[ExploreOneTable]:
    """設計 4.1 的六張表（事件／遭遇／素材／感悟）。

    順序就是比對的順序：營排第一（鉅鹿道壇「祭壇、營寨」、廣宗「城池、營寨」兩張都對得上，設計寫「營（營寨、道壇）」，
    同現行 `Config.explore_mix` 營在前）；標籤一個都對不上的歸最後一張（野，同 `explore_mix` 最後那筆「其餘」是野外的比例）。
    酒肆、醫館、馬市是店面標籤，不歸表。跟現行 `explore_mix` 的差：塢堡從營搬到城，寺院、書院、莊院、里巷、結社從城搬到寺與城。"""
    return [
        ExploreOneTable(kind="camp", tags=["營寨"], event=15, encounter=60, material=15, insight=10),
        ExploreOneTable(kind="town", tags=["城鎮", "官署", "塢堡", "城池", "里巷"], event=60, encounter=15, material=15, insight=10),
        ExploreOneTable(
            kind="temple", tags=["寺院", "書院", "莊院", "結社", "草廬", "祭壇"], event=50, encounter=5, material=15, insight=30,
        ),
        ExploreOneTable(kind="ford", tags=["河畔", "渡口"], event=30, encounter=30, material=30, insight=10),
        ExploreOneTable(kind="hill", tags=["山林", "洞窟", "山寨"], event=10, encounter=30, material=40, insight=20),
        ExploreOneTable(kind="wild", tags=["野外", "官道", "古戰場"], event=15, encounter=55, material=20, insight=10),
    ]


class JianfaNumbers(_Strict):
    """減法季批 2 的數字（批 0 之後併進 `JianfaRules`；開關與蓋章在那裡，這裡只有數字）。"""

    # ── 探索一顆（設計 4.1）──
    explore_stamina: int = Field(default=18, ge=0)  # 出門一趟的體力【預設】（設計的 outing_stamina）
    beats: int = Field(default=3, ge=1)  # 一趟幾拍【預設】（設計的 outing_beats）
    danger_shift: int = Field(default=10, ge=0)  # 危險度每多一星（一星是表上的數字）：遭遇 +N、事件 −N【預設】
    beat_floor: int = Field(default=5, ge=0)  # 危險度移過的那兩欄夾在 beat_floor～beat_cap【預設】
    beat_cap: int = Field(default=80, ge=1)
    bounty_encounter_bonus: int = Field(default=30, ge=0)  # 接了這裡的討伐懸賞：遭遇那一欄 +N，夾在 beat_cap【定】
    explore_tables: list[ExploreOneTable] = Field(default_factory=_default_tables, min_length=1)  # 六張表，照順序比對

    @field_validator("explore_tables")
    @classmethod
    def _one_table_per_kind_and_tag(cls, tables: list[ExploreOneTable]) -> list[ExploreOneTable]:
        """每一種地點只有一張表、每一個標籤只落在一張表（設計 4.1；計畫 Task 2-1 的驗證）。"""
        kinds = [t.kind for t in tables]
        if twice := sorted({k for k in kinds if kinds.count(k) > 1}):
            raise ValueError(f"探索表的種類重複：{'、'.join(twice)}")
        tags = [tag for t in tables for tag in t.tags]
        if twice := sorted({tag for tag in tags if tags.count(tag) > 1}):
            raise ValueError(f"標籤落在兩張探索表：{'、'.join(twice)}")
        return tables

    @model_validator(mode="after")
    def _floor_below_cap(self) -> JianfaNumbers:
        if self.beat_floor > self.beat_cap:
            raise ValueError("beat_floor 不能比 beat_cap 大")
        return self
