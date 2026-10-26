"""減法季批 2（探索一顆、三道閘、屬性五段）的數字（減法季整合設計 4.1、4.2、4.5；主機側實作計畫第三節 Task 2-1）。

批 0（雲端側）的 `Config.jianfa`（`models.JianfaRules`）繼承這個模型（`class JianfaRules(JianfaNumbers)`，接線那一批）：
設定檔照舊寫在 `"jianfa": {...}` 底下，純規則（`explore_one`、`growth`）收 `content.config.jianfa`（duck-typed 的 cfg），
純規則的測試照舊直接建這個模型。開關與子開關在 `JianfaRules`，判斷一律走 `rules.jianfa(content, world, "<子開關>")`。

欄位名照計畫 Task 2-1，兩個跟子開關撞名的改了名：六張表叫 `explore_tables`（子開關叫 `explore_one`；計畫寫 `Config.explore_one`）、
境界的等級叫 `milestone_levels`（計畫的數字與子開關都叫 `stat_milestones`）。`stat_rates` 的四個鍵照計畫，做成 `StatRates`（JSON 的寫法一樣，
多寫一個鍵會擋）。
數字都是【預設】，出處寫在每一欄旁邊。這裡不 import `models`：`models.py` 引用這裡（`JianfaRules` 繼承它、`Location.explore_mix`），反過來會循環。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ExploreKind = Literal["town", "temple", "ford", "wild", "hill", "camp"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_100(table, what: str) -> None:
    total = table.event + table.encounter + table.material + table.insight
    if total != 100:
        raise ValueError(f"{what}四欄加起來要是 100（現在 {total}）")


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
        _check_100(self, f"探索表 {self.kind} ")
        return self


class ExploreMix(_Strict):
    """一個地點自己的四欄（設計 4.1「`locations.json` 可用 `explore_mix` 覆寫」；`Location.explore_mix`）：寫了就照它抽，
    不照標籤對到的那一張表的四欄；這一處算哪一種地點（城裡的地痞、自家營寨的比劃）照舊看標籤（`explore_one.kind_of`）。
    危險度與懸賞照樣往上加減。四欄加起來 100。"""

    event: int = Field(ge=0)
    encounter: int = Field(ge=0)
    material: int = Field(ge=0)
    insight: int = Field(ge=0)

    @model_validator(mode="after")
    def _adds_up_to_100(self) -> ExploreMix:
        _check_100(self, "地點的 explore_mix ")
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


class StatRates(_Strict):
    """每一點屬性的效果（設計 4.5「每點加倍」【預設】：先這樣跑一季再調）。開著時取代 Config 的同名四個數字（括號裡是現在的值）；
    接線時 team.stat_bonus／dodge_chance、悟性的修練與感悟、博聞的持有都改讀這裡（計畫 Task 2-5）。"""

    bonus_per_point: float = Field(default=0.06, ge=0)  # Config.stat_bonus_per_point（0.03）
    dodge_per_point: float = Field(default=0.04, ge=0, le=1)  # Config.dodge_per_point（0.02）
    sense_rate_per_wis: int = Field(default=6, ge=0)  # Config.sense_rate_per_wis（3）
    holding_per_lore_point: int = Field(default=4, ge=0)  # Config.holding_per_lore_point（2）


class JianfaNumbers(_Strict):
    """減法季批 2 的數字（批 0 之後併進 `JianfaRules`；開關與蓋章在那裡，這裡只有數字）。"""

    # ── 探索一顆（設計 4.1）──
    # 出門一趟的體力【定】（設計的 outing_stamina）。企劃者 2026-10-26：一趟一件事、體力 15（原本 18）。
    # 一趟只抽一件事（遭遇、事件、素材、感悟其中一件；2d，企劃者 2026-10-26「只抽一件事情」），所以沒有「一趟幾拍」這個數字了
    explore_stamina: int = Field(default=15, ge=0)
    danger_shift: int = Field(default=10, ge=0)  # 危險度每多一星（一星是表上的數字）：遭遇 +N、事件 −N【預設】
    beat_floor: int = Field(default=5, ge=0)  # 危險度移過的那兩欄夾在 beat_floor～beat_cap【預設】
    beat_cap: int = Field(default=80, ge=1)
    explore_tables: list[ExploreOneTable] = Field(default_factory=_default_tables, min_length=1)  # 六張表，照順序比對
    # 城類地點自己沒有對手（此刻站的、不是自家的隊伍）時，遭遇那一拍換成這幾路（第一路；PM 2026-10-25 第 3 件：自己有隊伍的城照原本的隊伍）：
    # 不推線、不算討伐、戰利（銀兩、心得、掉的素材）乘 town_loot_scale【PM】
    town_foes: list[str] = Field(default_factory=lambda: ["dipi"], min_length=1)
    town_loot_scale: float = Field(default=0.5, ge=0, le=1)
    # 自家營寨的遭遇是跟同袍比劃（不打、不掉東西）：給 _sortie_host 那一路心得、經驗的幾成（再乘三道閘的倍數）【暫】
    # （PM 2026-10-26：全額太多；同跟自己人操練的 Config.drill_reward_share 的量級）。仍算仗（growth 的 camp_spar）：45 級以後照樣升得上去
    camp_spar_share: float = Field(default=0.3, ge=0, le=1)
    # ── 遭遇的三道閘（設計 4.2；企劃者 2026-10-24「15 次開始下降，最低 0.3」「45 之後只有交戰的情況給的經驗可以繼續升級」）──
    drill_full_per_day: int = Field(default=15, ge=0)  # 一天前幾場全額【定】
    drill_decay: float = Field(default=0.8, gt=0, le=1)  # 之後每場再乘這個（疊加）【預設】
    drill_floor: float = Field(default=0.3, ge=0, le=1)  # 最低到這裡【定】
    drill_outlevel_steps: tuple[float, ...] = Field(default=(0.5, 0.1), min_length=1)  # 對手低一檔、兩檔（以上）的倍數【定】
    drill_outlevel_band: int = Field(default=10, ge=1)  # 一檔多寬（等級與對手難度都照它切）【待量】
    drill_level_cap: int = Field(default=45, ge=1)  # 這一級以後只認打出來的經驗，其餘換心得【定】
    # ── 屬性五段加點、每點加倍（設計 4.5；企劃者 2026-10-24「先這樣改」「15 點有點少，改成 5 點」）──
    milestone_levels: list[int] = Field(default_factory=lambda: [10, 20, 30, 40, 50])  # 到這幾級各一次境界【定】（計畫寫 stat_milestones，跟子開關同名）
    stat_points_per_milestone: int = Field(default=5, ge=0)  # 每次幾點【定】
    stat_rates: StatRates = Field(default_factory=StatRates)  # 每點的效果【預設】
    # 江湖水漲的事件加難（rise.event_bump）乘這個【量過：0】：2026-10-25 measure_difficulty --tiers（season21，種子 1、2，solo 與 team，
    # 主機側計畫第三節 Task 2-6 的量表）第 30 級事件檢定平均 ×1 42～54%、×0.5 53～64%、×0 64～73%；判準「第 30 級不低於 70%」只有 0 摸得到
    event_bump_scale: float = Field(default=0.0, ge=0, le=1)

    @field_validator("milestone_levels")
    @classmethod
    def _milestones_climb(cls, levels: list[int]) -> list[int]:
        if any(lv < 1 for lv in levels) or any(b <= a for a, b in zip(levels, levels[1:])):
            raise ValueError(f"境界的等級要從 1 起、一級比一級高：{levels}")
        return levels

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
