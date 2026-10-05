"""內容資料模型：content/ 底下所有 JSON 設定的結構定義。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler, field_validator
from pydantic_core import core_schema

STATS = ("str", "agi", "con", "wis", "silver", "good", "evil", "fame", "xinde")
ActionKind = Literal["explore", "train", "socialize"]
TravelMode = Literal["walk", "hurry", "dash"]  # 步行／趕路／疾行（地圖擴充設計 3.2）
# sanguo-companions 合併：同伴不再分天地玄黃品階，改成「龍頭人物」（劇情鎖定，不可招募，
# 見設計文件四.4）跟「可招募」兩種，決定要不要出現在招募流程裡。
CompanionKind = Literal["locked", "recruitable"]
MartialKind = Literal["內功", "武學"]
Attribute = Literal["陰", "陽", "剛", "柔", "快", "慢", "虛", "實"]  # 見 tianxia/martial_arts.py
Quality = Literal["下品", "中品", "上品", "絕學"]  # 見 tianxia/martial_arts.py 的 QUALITIES
Lean = Literal["正", "邪", "無"]  # 武學與成長設計 7.3


class _Strict(BaseModel):
    """內容檔的欄位拼錯時直接報錯，而不是被默默忽略。"""
    model_config = ConfigDict(extra="forbid")


class Condition(_Strict):
    """所有欄位都是「且」的關係（any_of 內部是「或」）；空的欄位不檢查。"""

    min_stats: dict[str, int] = Field(default_factory=dict)
    max_stats: dict[str, int] = Field(default_factory=dict)
    flags_all: list[str] = Field(default_factory=list)
    flags_none: list[str] = Field(default_factory=list)
    sects: list[str] = Field(default_factory=list)
    no_sect: bool = False
    skills_all: list[str] = Field(default_factory=list)
    skills_none: list[str] = Field(default_factory=list)
    trend_min: dict[str, int] = Field(default_factory=dict)
    trend_max: dict[str, int] = Field(default_factory=dict)
    world_flags_all: list[str] = Field(default_factory=list)
    world_flags_none: list[str] = Field(default_factory=list)
    day_min: int | None = None
    day_max: int | None = None
    revealed_all: list[str] = Field(default_factory=list)
    revealed_none: list[str] = Field(default_factory=list)
    flag_age_hours: dict[str, int] = Field(default_factory=dict)  # 世界旗標成立後至少經過幾小時
    members_none: list[str] = Field(default_factory=list)  # 這些人物都還沒入門（結識事件用它排除已入門的人）
    # 地方痕跡（「地點 id:痕跡名」→ 次數，全服共用、每季清空）：至少／至多幾次。數字在載入時乘上
    # Config.mark_threshold_scale（無條件進位，見 content.load_content），所以這裡寫的是「開發期小伺服器」的門檻
    marks_min: dict[str, int] = Field(default_factory=dict)
    marks_max: dict[str, int] = Field(default_factory=dict)
    # ── 伏筆的準備事件、片段事件用（計畫 T7）；預設都是不限 ──
    factions: list[str] = Field(default_factory=list)  # 玩家的陣營在裡面才成立；空的＝不限（散人也行）
    # 季曆（calendar）的時刻：第一季開關關著（或這一季開季時沒開）時，寫了這三個的條件一律不成立——beta 季沒有季曆
    night: bool | None = None  # calendar.is_night 要等於它（True＝只在夜裡，False＝只在白天）
    week_min: int | None = None  # calendar.point(...).week 至少／至多第幾週
    week_max: int | None = None
    clue_items: dict[str, int] = Field(default_factory=dict)  # 伏筆專用物品至少幾個（原數字，不照伺服器規模換算）
    any_of: list[Condition] = Field(default_factory=list)  # 非空時，至少一個子條件成立


Condition.model_rebuild()


FRONT_KEY = "front"  # Effect.trend／Location.train_trend 的特殊鍵：效果發生地所在大區的戰線（rules.resolve_trend）


class Effect(_Strict):
    text: str = ""
    stats: dict[str, int] = Field(default_factory=dict)
    stamina: int = 0
    flags_add: list[str] = Field(default_factory=list)
    flags_remove: list[str] = Field(default_factory=list)
    learn_skills: list[str] = Field(default_factory=list)
    trend: dict[str, int] = Field(default_factory=dict)
    world_flags_add: list[str] = Field(default_factory=list)
    rumor: str = ""  # {name} 會換成玩家名號（匿名時為「某位少俠」）
    chronicle: str = ""  # 寫入江湖史，同樣支援 {name}
    join_sect: str | None = None
    leave_sect: bool = False
    next_event: str | None = None
    recruit: str | None = None  # 結識某人（同伴 id）：入門；已入門時改給心得（見 roster.recruit）
    materials: dict[str, int] = Field(default_factory=dict)  # 給煉製素材（素材 id -> 數量）；手寫劇情是天品素材的主要來源
    # 在地方上留下痕跡（「地點 id:痕跡名」→ 1～3，只能加）：全服共用、每季清空；同一個人對同一個痕跡一天只算一次
    marks: dict[str, int] = Field(default_factory=dict)
    # 伏筆（計畫 T7）的準備事件用；第一季開關關著時兩個都不發生（不給也不寫任何字）
    clue_items: dict[str, int] = Field(default_factory=dict)  # 伏筆專用物品（foreshadows.json 的 items）：正數給、負數收走
    fs_counters: dict[str, int] = Field(default_factory=dict)  # 伏筆的隱藏計數（例：豪強兩頭賣糧的起點 two_buyers）：加多少，不寫字
    # ── 晉升（計畫 T5）：只寫在晉升奇遇的選項上（content.validate 檢查）──
    promote: int | None = None  # 演完晉升到第幾階（清掉召見、接結尾那一句、記進當天的彙整）
    followers: list[str] = Field(default_factory=list)  # 給的部下（followers.json 的模板 id）
    affinity: dict[str, int] = Field(default_factory=dict)  # 人物 id → 情誼增減（夾在 0～100，訊息「皇甫嵩情誼 +10」）


class Material(_Strict):
    """煉製用的素材：一個屬性 × 一個階（見 docs/superpowers/specs/2026-10-01-無限煉製-design.md §三）。

    階只影響「煉出來的東西有多好」（素材的階位移品質的機率分佈），不影響屬性。
    """

    id: str
    name: str
    attribute: Attribute
    tier: int = Field(ge=1, le=3)  # 1 凡品、2 靈品、3 天品
    description: str = ""


class CraftNames(_Strict):
    """煉製時 LLM 不可用（或產出的名字過不了過濾）的決定性組名字表，見無限煉製設計 §5.6。

    用配方鍵的雜湊挑 prefix × suffix，所以同一個配方永遠組出同一個名字——離線也能玩，
    而且 `tests/test_real_content.py` 整季模擬（LLM 被 mock）走的就是這條路。
    """

    prefixes: list[str]
    wugong: list[str]  # 武學的字尾
    neigong: list[str]  # 內功的字尾


class Drop(_Strict):
    """一筆掉落：打贏這支隊伍時有 chance 的機率掉 count 個這種素材。

    敵方隊伍沒寫 drops 時走 materials.py 的預設掉落表（依難度），內容不必每隻都填。
    """

    material: str
    chance: float = Field(default=1.0, ge=0.0, le=1.0)
    count: int = Field(default=1, ge=1)


class Check(_Strict):
    stat: str
    difficulty: int
    by: Literal["team", "self"] = "team"  # team：隊伍派屬性最高的人出手；self：只看本人


class Choice(_Strict):
    text: str
    condition: Condition = Field(default_factory=Condition)
    check: Check | None = None
    combat: str | None = None  # 敵方隊伍 id：選了就自動開打
    effect: Effect = Field(default_factory=Effect)  # 檢定成功／戰鬥勝利（或無檢定時）
    fail_effect: Effect = Field(default_factory=Effect)  # 檢定失敗／戰鬥落敗


FREE_TEXT_MAX = 20  # 隨口應對最多幾個字（跟決戰的放手一搏一樣）


class FreeTextChoice(_Strict):
    """隨口應對（探索的多人與LLM玩法 §8.1）：事件多一個自己寫一句話的選項。LLM 只評估成功率，
    引擎再按 stat 修正、夾在 5%～85% 之後擲骰：成功套 effect，失敗套 fail_effect。"""

    prompt: str  # 選單上的標籤，例如「自己想辦法……」
    stat: Literal["str", "agi", "con", "wis"]
    by: Literal["team", "self"] = "team"  # 跟 Check.by 一樣：team 派隊伍中這項屬性最高的人，self 只看本人
    effect: Effect = Field(default_factory=Effect)
    fail_effect: Effect = Field(default_factory=Effect)


class Event(_Strict):
    id: str
    title: str
    text: str
    actions: list[ActionKind] = Field(default_factory=lambda: ["explore"])  # 空清單＝只能由 next_event 串接
    locations: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    weight: float = 1.0
    once: bool = False
    qiyu: bool = False
    fortune: bool = False  # 新立門戶福緣：不會被隨機抽到，由 engine 在交友時觸發（actions 必須是空的）
    condition: Condition = Field(default_factory=Condition)
    choices: list[Choice] = Field(min_length=1)
    free_text: FreeTextChoice | None = None


RoadKind = Literal["官道", "路", "山路"]
ROADS: tuple[RoadKind, ...] = ("官道", "路", "山路")  # 路的種類（地圖擴充設計 3.1）；沒標的是一般的「路」


class _ConnectionSpec(_Strict):
    """內容檔裡寫成物件的一條路：{"to": 地點 id, "road": 路的種類}。"""

    to: str
    road: RoadKind = "路"


class Connection(str):
    """一條路（Location.connections 的一筆）：字串本身就是目的地的地點 id，另外帶路的種類 road。

    做成 str 的子類別，是為了讓既有把 connections 當成地點 id 清單用的程式（大地圖、視野、假人、
    內容檢查）一行都不用改；要路的種類讀 .road，要純字串的地點 id 讀 .to。內容檔裡寫成字串（一般路）
    或 {"to": 地點 id, "road": "官道"|"路"|"山路"}（地圖擴充設計 3.1），寫回去也是同一個樣子。
    注意：不支援產生 JSON schema（Location.model_json_schema() 會報錯）；目前沒有任何地方用到。"""

    road: RoadKind

    def __new__(cls, to: str, road: RoadKind = "路") -> Connection:
        obj = super().__new__(cls, to)
        obj.road = road
        return obj

    @property
    def to(self) -> str:
        return str(self)

    def __repr__(self) -> str:
        return f"Connection({self.to!r}, {self.road!r})"

    def __reduce__(self):
        return (type(self), (self.to, self.road))

    @classmethod
    def _parse(cls, value: Any) -> Connection:
        if isinstance(value, Connection):
            return value
        if isinstance(value, str):
            return cls(value)
        if isinstance(value, dict):
            spec = _ConnectionSpec(**value)  # 欄位拼錯、路的種類寫錯時這裡就報錯
            return cls(spec.to, spec.road)
        raise ValueError('連線要寫成地點 id，或 {"to": 地點 id, "road": 路的種類}')

    @staticmethod
    def _dump(value: str) -> str | dict[str, str]:
        road = getattr(value, "road", "路")  # 程式或測試直接塞進清單的一般字串也當一般路
        return str(value) if road == "路" else {"to": str(value), "road": road}

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._parse, serialization=core_schema.plain_serializer_function_ser_schema(cls._dump),
        )


class LocationText(_Strict):
    """地點描寫的一個版本：這個世界旗標成立時改用 text（例：宛城第 3 週起依版本換，計畫 T8）。"""

    world_flag: str
    text: str


class Location(_Strict):
    id: str
    name: str
    description: str
    desc_when: list[LocationText] = Field(default_factory=list)  # 照順序第一個成立的世界旗標勝出；都不成立時用 description
    connections: list[Connection]  # 相鄰的地點，每一筆是一條路（見 Connection）
    x: int
    y: int
    tags: list[str] = Field(default_factory=list)
    danger: int = Field(default=1, ge=1, le=3)
    important: bool = False
    enemies: list[str] = Field(default_factory=list)
    train_trend: dict[str, int] = Field(default_factory=dict)  # 遊歷打贏／操練推大勢的量；正負是散人的方向，有陣營目標的人照自己的目標推（Game._train_push）
    materials: list[str] = Field(default_factory=list)  # 在這裡探索可能撿到的素材；留空則給隨機的一階素材
    insights: list[str] = Field(default_factory=list)  # 探索「悟意境」那一支悟得到的意境 id（武學與成長設計附錄 C）
    unlock_flag: str | None = None  # 設定後，需該世界旗標成立才能前往

    def describe(self, world_flags: set[str]) -> str:
        """此刻的描寫：desc_when 裡第一個旗標成立的那一版，都不成立時是 description。"""
        return next((d.text for d in self.desc_when if d.world_flag in world_flags), self.description)

    def road_to(self, dest: str) -> RoadKind:
        """到相鄰地點 dest 的路的種類；清單裡是一般字串（測試直接塞的）或沒連到 dest 時當一般路。"""
        for conn in self.connections:
            if conn == dest:
                return getattr(conn, "road", "路")
        return "路"


class RoadSight(_Strict):
    """路上見聞的一則（路上設計第五節）：每抵達一站有機會寫進自己的江湖紀錄的一兩句話。純敘事，沒有選項。
    內容在 content/road_sights.json，載入時 content.validate 檢查組合夠不夠、收穫有沒有超標、是不是繁體。"""

    id: str
    text: str  # 一兩句；「聽說……」直接寫在這裡。收穫照慣例自動接在後面（「銀兩 +5」），文字裡不用寫
    roads: list[RoadKind] = Field(default_factory=list)  # 適用的路的種類；空的＝哪種路都可以
    regions: list[str] = Field(default_factory=list)  # 適用的大區（照剛抵達的那一站算）；空的＝哪個大區都可以
    # 小收穫，最多一種，也可以沒有：stats 只能是 silver（≤10）或 xinde（≤5），materials 只能是一階 1 個。
    # 不發全服傳聞（每人每站都可能觸發，發到傳聞板會洗版），Effect.text 也留空。
    effect: Effect = Field(default_factory=Effect)


class LearnRule(_Strict):
    """基礎武學在哪裡學、誰肯教（武學與成長設計附錄 B）：武館與江湖人看名望、收銀兩；
    陣營營地只教投靠了那個陣營的人；門派只教那個門派的弟子。"""

    at: str  # 地點 id
    fame: int = 0
    silver: int = 0
    faction: str | None = None
    sect: str | None = None


class SkillDef(_Strict):
    """內容手寫的武學/內功：本命武學（歷史人物的固定武學，品質是絕學，見 martial_arts.historical_art）、
    部下用的通用武學（企劃者 2026-10-05 定上品，計畫 T5）與基礎武學（下品，開局送或在各地學，
    武學與成長設計附錄 B）。合成出來的武學不進這份內容檔，存在全服（world.get_skill）。
    """

    id: str
    name: str
    kind: MartialKind
    attribute: Attribute
    desc: str = ""
    quality: Quality = "絕學"
    learn: LearnRule | None = None  # 在各地學得到的基礎武學才填；開局送的看 Config.starter_skills


class InsightGrant(_Strict):
    """靠名聲悟得的意境（浩然、血煞，設計 7.2）：這項名聲第一次到門檻就悟得。"""

    stat: Literal["good", "evil"]
    at: int


class InsightDef(_Strict):
    """內容手寫的意境（武學與成長設計附錄 A）：四個基本意境靠探索悟得；浩然、血煞靠名聲。
    合併出來的意境不在這裡，存在全服（world.get_insight）。"""

    id: str
    name: str
    attribute: Attribute
    lean: Lean = "無"
    desc: str = ""
    grant: InsightGrant | None = None


class Sect(_Strict):
    id: str
    name: str
    location: str
    alignment: Literal["正", "邪", "中"]
    desc: str = ""


class CharacterDef(_Strict):
    """人物（同伴或敵人）。stats 是第 1 級的屬性，growth 是每升一級增加的量，仍給 Check
    系統（辦事/修行類事件選項的屬性判定）使用，跟遭遇/劇情戰的判定（encounter.py）無關。"""

    id: str
    name: str
    background: str = ""  # 出身
    situation: str = ""  # 此時處境
    personality: str = ""  # 性格基礎模板，companion_agent.py 的 system prompt 錨點
    kind: CompanionKind | None = None  # 同伴才填：locked（龍頭人物，不可招募）／recruitable；敵人不填
    stats: dict[str, float]
    growth: dict[str, float] = Field(default_factory=dict)
    sect: str | None = None
    desc: str = ""
    starting_wugong: str | None = None  # 本命武學 id（指向 SkillDef，kind 必須是「武學」）
    starting_neigong: str | None = None  # 本命內功 id（指向 SkillDef，kind 必須是「內功」）
    deep_interaction: bool = False  # 是否走 companion_agent.py 的即時 LLM 對話（見設計文件四.3）
    recruit_at: str | None = None  # 可招募的同伴在哪個地點找得到他（龍頭人物不填，用 talk_at）
    talk_at: str | None = None  # kind=locked 的龍頭人物在哪個地點可以深度對話（不可招募，見上一輪「還要改進」5）
    affinity_tag_deltas: dict[str, int] | None = None  # 覆寫 companion_agent.AFFINITY_TAG_DELTAS 的個別項目；None／缺的 tag 用預設值
    audience_fame: int = 0  # 求見門檻：名望要到多少才見得到他（透過他的「結識」劇情事件認識的人不受限制）


class Squad(_Strict):
    """遭遇/劇情戰的對手：一個抽象的難度值＋屬性，不是完整的人物陣容（見 encounter.py 的單次判定）。"""

    id: str
    name: str
    difficulty: float
    attribute: Attribute | None = None
    reward_silver: int = 0
    reward_xinde: int = 0
    exp: int = 0
    drops: list[Drop] = Field(default_factory=list)  # 留空則走 materials.py 依難度的預設掉落表
    faction: str | None = None  # 這支隊伍屬於哪個陣營（Scenario.factions 的 id）；自己陣營的人遇到時改成操練、不開打
    desc: str = ""  # 一句描述（運糧隊這類有特別來歷的對手才寫；遇上時接在戰鬥那一行後面，濃縮版內容表 3.3）


class Trend(_Strict):
    id: str
    name: str
    desc: str = ""
    start: int = Field(default=0, ge=0, le=100)
    hidden: bool = False
    # 衍生線（第一季濃縮版的黃巾聲勢）：來源線 id → 權重，加起來是 1。開關（Config.season_one）開著時它的值一律是
    # 來源線的加權和（rules.recompute_trends），不能直接推；開關關著時它是一般的線，照 start 起算
    derived: dict[str, float] = Field(default_factory=dict)
    season_one: bool = False  # 第一季濃縮版才有的線（三條戰線、豪強割據）：開關關著時不顯示、不推（rules.trend_shown）


class Threshold(_Strict):
    id: str
    trend: str
    op: Literal[">=", "<="]
    value: int
    text: str
    world_flags_add: list[str] = Field(default_factory=list)
    ends_season: bool = False
    starts_battle: str | None = None  # 指向 Content.battles 的 id：觸發時開一場全服即時戰鬥，不是立刻套用效果
    location: str | None = None  # 發生地：傳聞記在這裡，大地圖劇情層標 ✦；None＝不在特定地點


class SimRumor(_Strict):
    """虛擬玩家的一則傳聞，連同它發生的地點（傳聞裡寫明了在哪裡時用）。"""

    text: str
    location: str


class SimPlayer(_Strict):
    name: str
    actions_per_day: float
    trend: dict[str, int] = Field(default_factory=dict)
    requires_revealed: str | None = None  # 這條隱藏線浮現之前不會行動
    # 傳聞：寫成字串的記在第一個常出沒處；寫成 {"text", "location"} 的記在它寫的地點
    rumors: list[str | SimRumor] = Field(default_factory=list)
    rumor_chance: float = 0.3
    condition: Condition = Field(default_factory=Condition)
    haunts: list[str] = Field(default_factory=list)  # 常出沒的地點（固定不動）


StanceSide = Literal["guan", "huang", "haoqiang"]  # 三方態勢（rules.stances，第一季設計 4.4）


class Ending(_Strict):
    id: str
    title: str
    text: str  # 結局的一句；第一季接在季末公告的開頭後面（時刻表結算第 12 週）
    storyline: str | None = None  # 只在這條主線下成立；None＝任何主線
    hint: str = ""  # 顯示在任務區塊：怎麼達成這個結局
    condition: Condition = Field(default_factory=Condition)
    # ── 第一季濃縮版（計畫 T9）：只在 rules.season_one 成立時算；beta 季只看沒標的那幾筆。同一季清單的最後一筆是保底 ──
    season_one: bool = False
    stance_min: dict[StanceSide, int] = Field(default_factory=dict)  # 態勢至少（決定性勝利：季中一到就收季）
    stance_max: dict[StanceSide, int] = Field(default_factory=dict)  # 態勢至多（同上）
    stance_top: StanceSide | None = None  # 季末比態勢：這一方最高（平手時照清單順序，排前面的先成立）


class MapLabel(_Strict):
    text: str
    x: int
    y: int


HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"


class MapRegion(_Strict):
    """地圖上的一塊大區（例如江北、金陵一帶），以多邊形著色；地點依座標落在哪一區自動歸屬（見 atlas.region_of）。"""

    id: str
    name: str
    trends: list[str] = Field(default_factory=list)  # 對應的大勢線：大地圖局勢層依它上色
    front: str | None = None  # 這一區的戰況算在哪條戰線（第一季濃縮版）；洛陽這類沒有戰況的大區是 None
    points: list[list[int]]
    fill: str = Field(pattern=HEX_COLOR)
    text_fill: str = Field(pattern=HEX_COLOR)
    label_x: int
    label_y: int


class MapRiver(_Strict):
    """一條河（輿圖美術設計第四節）：points 從上游寫到下游，畫的時候照這個方向由 width[0] 漸寬到 width[1]。
    舊格式（每條河只是一串 [x, y] 點）照樣讀，當成藍色、寬 4→8（見 MapLayout._legacy_rivers）。"""

    name: str = ""  # 只給寫內容的人看；河名照舊寫在 MapLayout.labels
    points: list[list[int]]
    width: tuple[float, float] = (4, 8)  # 上游寬、下游寬
    color: Literal["blue", "yellow"] = "blue"  # yellow 只給黃河


TerrainKind = Literal["mountains", "hills", "forest"]  # 山脈、丘陵、林地


class Terrain(_Strict):
    """輿圖上的一片地形（輿圖美術設計第四節，純裝飾：不改路程也不改視野）。山脈、丘陵沿 spine（山腳線）排山頭，
    size 是山頭高度；林地在 points 圍成的多邊形裡排樹叢。山頭與樹自己讓開地點、路與河（mapart.terrain）。"""

    kind: TerrainKind
    name: str = ""  # 選填：畫成淡綠小字
    spine: list[list[int]] = Field(default_factory=list)  # 山脈、丘陵用
    size: int = 0  # 山脈、丘陵用，8～40
    points: list[list[int]] = Field(default_factory=list)  # 林地用


class MapLayout(_Strict):
    width: int = 680
    height: int = 420
    background: str = Field(default="#E9E2CC", pattern=HEX_COLOR)  # 紙色（輿圖美術設計 2.1）
    regions: list[MapRegion] = Field(default_factory=list)
    rivers: list[MapRiver] = Field(default_factory=list)
    terrain: list[Terrain] = Field(default_factory=list)
    compass: tuple[int, int] | None = None  # 指北針的位置；不寫就不畫
    labels: list[MapLabel] = Field(default_factory=list)
    mini_window: tuple[int, int] = (270, 180)  # 小地圖以所在地為中心截多寬、多高（地圖單位）；地圖畫得越疏，要截得越大才看得到一兩站路

    @field_validator("rivers", mode="before")
    @classmethod
    def _legacy_rivers(cls, rivers: Any) -> Any:
        """舊格式的河是一串 [x, y] 點（純陣列）：包成 {"points": ...}，其餘照預設（藍色、寬 4→8）。"""
        if isinstance(rivers, list):
            return [{"points": river} if isinstance(river, list) else river for river in rivers]
        return rivers


class WorldEvent(_Strict):
    """以任意條件觸發、只觸發一次的世界事件。"""

    id: str
    condition: Condition
    text: str
    world_flags_add: list[str] = Field(default_factory=list)
    ends_season: bool = False
    starts_battle: str | None = None  # 同 Threshold.starts_battle
    location: str | None = None  # 發生地，同 Threshold.location


class Act(_Strict):
    id: str
    title: str
    text: str
    goal: str
    advance_when: Condition | None = None  # 最後一幕為 None
    places: list[str] = Field(default_factory=list)  # 這一幕的目標地點：大地圖劇情層標 ★


class Storyline(_Strict):
    id: str
    name: str
    intro: str = ""
    acts: list[Act] = Field(min_length=1)
    replaces_when: Condition | None = None  # 支線主線：條件成立時取代主線


class Milestone(_Strict):
    id: str
    text: str
    condition: Condition


class TutorialGoal(_Strict):
    """每一項都要符合才算完成；空的（或 False 的）欄位不檢查。"""

    action: Literal["explore", "socialize", "move", "view_map", "recruit", "practice", "order"] | None = None  # order：替軍令記到一次（計畫 T6）
    locations: list[str] = Field(default_factory=list)
    condition: Condition = Field(default_factory=Condition)
    has_wugong: bool = False  # 身上要有一門武學才算（沒有武學威力是 0，出城只有挨打的份）


class TutorialStep(_Strict):
    id: str
    text: str
    done_when: TutorialGoal
    reward: Effect = Field(default_factory=Effect)
    season_one: bool = False  # 只在第一季濃縮版才有的步驟（開關開著、這一季也蓋了章，計畫 T6）；一律排在最後（content.validate）


class Tutorial(_Strict):
    speaker: str = "老說書人"
    steps: list[TutorialStep] = Field(default_factory=list)
    outro: str = ""


class FactionDef(_Strict):
    """一季的玩家陣營（第一季設計第五節）：在 join_at 的地點可以投靠；拜入 sects 裡的門派也算投靠這個陣營。
    goals 是這個陣營想把各條大勢線往哪推（伺服器假人照它打分數）。"""

    id: str
    name: str
    join_at: list[str] = Field(default_factory=list)
    sects: list[str] = Field(default_factory=list)
    goals: dict[str, int] = Field(default_factory=dict)  # 大勢線 id → 1 推高／-1 壓低；伺服器假人照這個行動


class SeasonOneOff(_Strict):
    """第一季不觸發的 beta 內容（控制者與地圖擴充 T4 說好的格式，2026-10-04）：只在 rules.season_one 成立時生效
    （開關開著、這一季開季時也蓋了「開」的章）；開關關著時 beta 那一季照舊。四種各自是那一種內容的 id。
    - thresholds：大勢門檻不觸發（管理者也觸發不了）；
    - storylines：主線不推進，「主線與目標」不顯示那條主線；
    - battles：大勢門檻的 starts_battle 不開，管理者「立刻開戰」的選單不列；
    - events：探索的事件抽選跳過（T4 做；這裡只定欄位，id 一樣在載入時檢查）；
    - milestones：「主線與目標」的個人目標不列（做不到的 beta 目標，例如擊敗波才、平定黃巾）。"""

    thresholds: list[str] = Field(default_factory=list)
    storylines: list[str] = Field(default_factory=list)
    battles: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)


class Scenario(_Strict):
    id: str
    name: str
    intro: str
    era_note: str = ""  # 給對話模型的時代背景：這一季是哪一年、各人物此時的身分、哪些事還沒發生（避免扯到之後的年代）
    start_location: str
    factions: list[FactionDef] = Field(default_factory=list)  # 空的＝這個劇本不分陣營，全服決戰維持集結時選邊
    trends: list[Trend]
    thresholds: list[Threshold] = Field(default_factory=list)
    sim_players: list[SimPlayer] = Field(default_factory=list)
    world_events: list[WorldEvent] = Field(default_factory=list)
    storylines: list[Storyline] = Field(min_length=1)
    endings: list[Ending]
    milestones: list[Milestone] = Field(default_factory=list)
    jade_seal_flag: str | None = None  # 這個世界旗標代表玩家親手取得了這一季的玉璽碎片（設計文件九），記進跨季持久紀錄
    season_one_off: SeasonOneOff = Field(default_factory=SeasonOneOff)  # 第一季不觸發的 beta 門檻、主線、決戰、事件


ExploreBranch = Literal["insight", "wild", "event"]
EXPLORE_BRANCHES: tuple[ExploreBranch, ...] = ("insight", "wild", "event")  # 探索三選一的三支：悟意境、野怪、事件


class ExploreMix(_Strict):
    """一種地點類型探索時三支的比例（探索三選一設計第三節）。

    地點有 tags 裡任何一個標籤就算這一類；Config.explore_mix 照順序比對、第一個符合的就是。
    tags 空的那一筆是「其餘」，必須放最後。weights 沒寫的那一支當 0。"""

    kind: str
    tags: list[str] = Field(default_factory=list)
    weights: dict[ExploreBranch, float]

    @field_validator("weights")
    @classmethod
    def _weights_add_up(cls, weights: dict[str, float]) -> dict[str, float]:
        if any(w < 0 for w in weights.values()):
            raise ValueError("探索比例不能是負的")
        if sum(weights.values()) <= 0:
            raise ValueError("探索比例三支加起來要大於 0")
        return weights


def _default_explore_mix() -> list[ExploreMix]:
    return [
        ExploreMix(kind="camp", tags=["營寨", "祭壇", "塢堡"], weights={"insight": 15, "wild": 35, "event": 50}),
        ExploreMix(
            kind="town", tags=["城鎮", "官署", "城池", "寺院", "書院", "莊院", "里巷", "結社"],
            weights={"insight": 15, "wild": 0, "event": 85},
        ),
        ExploreMix(kind="wild", tags=[], weights={"insight": 40, "wild": 35, "event": 25}),
    ]


# T2 之前開的季沒有蓋章，那些季都是用預設設定開的，所以長度就是這個預設值（FB-037）。
# 不是「現在載入的設定」：週末設定的 2.5 天只管有蓋章的新季。
DEFAULT_SEASON_DAYS = 14


class Config(_Strict):
    stamina_max: int = 150
    stamina_regen_seconds: float = 180  # 自然回復：每幾秒（遊戲時間）回 1 點體力（地圖擴充設計第二節：每 3 分鐘 1 點）
    rest_regen_multiplier: float = Field(default=2, ge=1)  # 打坐中體力回復是平常的幾倍
    # 地方痕跡的門檻倍數（Condition.marks_min/max 的數字乘上它、無條件進位）：開發期 1，正式伺服器依人數調大
    mark_threshold_scale: float = Field(default=1.0, gt=0)
    # 地圖座標 1 單位＝步行幾分鐘：現行內容（40 個地點的地圖）取 0.04，也就是 25 個單位約 1 分鐘；這裡的預設值只是沒寫時的退路
    travel_minutes_per_unit: float = Field(default=0.0375, gt=0)
    road_factor: dict[RoadKind, float] = Field(
        default_factory=lambda: {"官道": 0.8, "路": 1.0, "山路": 1.5}
    )  # 路程＝距離 × 路的種類係數 × travel_minutes_per_unit（地圖擴充設計 3.1）
    hurry_stamina_per_minute: float = Field(default=1, ge=0)  # 趕路：每分鐘路程扣幾點體力（時間減半）
    dash_stamina_per_minute: float = Field(default=2, ge=0)  # 疾行：每分鐘路程扣幾點體力（立刻到）
    # 路上小事（路上設計第四節）：收入要明顯低於在站上做事，不然一直趕路會變成最賺的玩法
    road_think_xinde: int = Field(default=3, ge=0)  # 邊走邊想：心得（一次遊歷大約 12～20）
    road_rumor_pool: int = Field(default=5, ge=1)  # 沿途打聽：從這一帶最近幾則傳聞裡挑一則
    road_gather_chance: float = Field(default=0.4, ge=0, le=1)  # 路邊採集：撿到一樣一階素材的機率
    road_sight_chance: float = Field(default=0.3, ge=0, le=1)  # 路上見聞：每抵達一站有幾成機會看見一則（路上設計第五節）
    road_sight_recent: int = Field(default=5, ge=0)  # 路上見聞：最近看過的幾則先排除，池子不夠才重複
    road_reward_daily_cap: int = Field(default=6, ge=0)  # 路上小事、見聞的收穫每個遊戲日各前幾次才有
    ollama_url: str = "http://localhost:11434"  # companion_agent.py 深度對話用；連不上時那輪對話取消
    ollama_model: str = "qwen2.5:14b"
    ollama_timeout: int = 120
    # 2026-10-03 實測（gemma4:26b）：有思考模式的模型要關掉思考，不然每輪多等好幾秒；None 表示不送這個欄位
    ollama_think: bool | None = None
    ollama_keep_alive: str = "30m"  # 模型閒置多久後卸載；大模型重新載入要十幾秒
    # 重複懲罰：太重時模型會改用英文字避開已經用過的中文字（gemma4 實測），換模型時一起調
    ollama_repeat_penalty: float = 1.18
    ollama_presence_penalty: float = 0.3
    ollama_frequency_penalty: float = 0.3
    action_cost: dict[str, int] = Field(
        default_factory=lambda: {"explore": 10, "train": 10, "socialize": 5}
    )
    time_scale: float = 1.0
    season_days: float = DEFAULT_SEASON_DAYS
    # 第一季濃縮版的規則（預設關，beta 那一季照舊）：季曆、時刻表、三條戰線都掛在這個開關後面。
    # 做到一半的 main 也會換上試玩伺服器，開關關著才不會把正在跑的那一季弄壞；
    # 全部做完、開測前由 PM 跟季長（season_days 改 2.5）一起打開（計畫 2026-10-04-第一季濃縮版）
    season_one: bool = False
    # 三條戰線與豪強割據（計畫 2026-10-04-T1；開關關著時沒人讀它們）
    geju_chaos_per_day: float = Field(default=1.0, ge=0)  # 每有一條戰線在亂局，豪強割據每曆日漲幾點
    # 割據漲速依人數等比例調整（企劃者 2026-10-05，測試階段）：漲速再乘 min(1, 這一季投靠名冊人數 ÷ geju_full_players)。
    # 湊滿這個人數就是設計的速度；人少的季（週末只有兩個人、沒人玩）割據照人數比例慢下來，不會第 5 週就衝到 100 提早收季。只管漲，不管回落
    geju_full_players: int = Field(default=15, gt=0)
    geju_calm_per_day: float = Field(default=1.0, ge=0)  # 三條戰線都穩下來時，豪強割據每曆日回落幾點（不能是負的，否則「回落」變成漲）
    chaos_low: int = 35  # 亂局：戰況在 chaos_low～chaos_high 之間（含兩端，第一季設計 4.2；low 不能大於 high，content.validate 檢查）
    chaos_high: int = 65
    season_weeks: int = Field(default=12, ge=1)  # 季曆：一季壓成幾週（計畫第六節：季曆秒＝世界秒 × 週數 × 7 ÷ season_days）
    # 決定性勝利（黃巾聲勢 ≥85、≤15，割據 ≥85）季曆第幾週起才提前收季；之前到了門檻也不收，季末照常比（企劃者 2026-10-05，計畫 T9）
    decisive_from_week: int = Field(default=10, ge=1)
    # 時刻表的人物結局扣多少聲威（時刻表結算文件第一節）：只有這三種用詞會扣；退場、重創是聲威歸零，下獄、到任不動聲威
    fate_prestige: dict[Literal["重挫", "聲威大減", "受挫"], int] = Field(
        default_factory=lambda: {"重挫": -30, "聲威大減": -30, "受挫": -15}
    )
    # 大勢人物（計畫 T4、總計畫第五節；掛在 season_one 後面，開關關著時沒人讀）
    figure_reaction_lean: int = Field(default=15, ge=0)  # 戰線偏向對方這麼多時，人物推得更勤（反應規則，第一季設計 8.2）
    figure_reaction_mult: float = Field(default=2.0, ge=1)  # 推得更勤的倍數
    figure_defeat_prestige: int = Field(default=5, ge=0)  # 挑戰本人打贏一次扣幾點聲威（照陣營人數緩衝）
    figure_defeat_affinity: int = Field(default=5, ge=0)  # 打贏的人跟他的情誼扣多少（軍令文件 4.5）
    snub_hours: float = Field(default=2, ge=0)  # 打贏之後幾個「現實」小時內他不見你、也不跟你交手（軍令文件 4.5）
    figure_difficulty_floor: float = Field(default=0.5, ge=0, le=1)  # 挑戰本人的難度：聲威 0 時是隊伍難度的幾成（100 時原值，中間線性）
    # 推力規則（第一季設計第七節、計畫 T3；掛在 season_one 後面，開關關著時推大勢跟以前一樣）
    daily_push_cap: float = Field(default=10, gt=0)  # 每人每曆日、每條線推得動多少（人數緩衝之後的量）
    over_cap_contrib_ratio: float = Field(default=0.2, ge=0, le=1)  # 超過每日上限的部分，貢獻只記幾成
    contrib_per_push: int = Field(default=10, ge=0)  # 推 1 點大勢記幾點貢獻（不打人數緩衝的折）
    active_window_days: float = Field(default=1, gt=0)  # 陣營人數緩衝的「活躍」時窗：幾個曆日內推過大勢的成員才算
    # 糧草（計畫 T6；這一版沒有軍備物資，糧草＝背包裡的慢屬性素材，濃縮版內容表 4.0）：凡、靈、天一個各算幾份
    grain_values: list[int] = Field(default_factory=lambda: [1, 3, 9])
    # ── 軍令（計畫 T6、軍令文件第二節、濃縮版內容表第三節；掛在 season_one 後面）──
    orders_per_week: int = Field(default=3, ge=0)  # 每個陣營每週同時有幾道（豪強這一版只有打擊一種，最多一道）
    order_quota_min: int = Field(default=4, ge=1)  # 陣營總額度最少幾次（軍令文件寫 5；週末兩人時太滿，總計畫待決 3 先用 4）
    convoy_ambush_chance: float = Field(default=0.2, ge=0, le=1)  # 糧車送到終點前先撞上敵方截糧隊的機率
    convoy_grain: int = Field(default=4, ge=1)  # 接一車糧要交出幾份糧草（軍令文件 3.4：份量 ≥ 4）
    duty_stamina: int = Field(default=10, ge=0)  # 第 1 階守勢行動（巡哨、傳道、保境安民）的體力
    rank2_contrib: int = Field(default=300, ge=0)  # 升第 2 階的貢獻門檻（計畫 T5、第五節：推 30 點大勢）
    # ── 伏筆（計畫 T7、伏筆文件 2.8）──
    # 需求量照 server_max_players 換算：人數上限「未滿」第一個數時用第二個數當係數，照順序找第一個符合的；
    # 都不符合（1000 人以上）就是 1。片段的機率反過來除以它（foreshadow.scale、foreshadow.need）
    foreshadow_tiers: list[tuple[int, float]] = Field(default_factory=lambda: [(10, 0.2), (100, 0.3), (1000, 0.6)])
    foreshadow_contrib: int = Field(default=50, ge=0)  # 最後一步答對記多少貢獻（五點推力的量；先完成、搶輸、同陣營後到都照記）
    guanyin_chance: float = Field(default=0.3, ge=0, le=1)  # 黃巾遊歷打贏官軍的隊伍時拿到一錠官銀的機率（濃縮版內容表 4.0）
    train_stat_chance: float = 0.3
    train_event_chance: float = 0.3
    qiyu_weight_multiplier: float = 1.5
    starter_skills: list[str] = Field(default_factory=list)
    start_stats: dict[str, int] = Field(
        default_factory=lambda: {
            "str": 5, "agi": 5, "con": 5, "wis": 5,
            "silver": 50, "good": 0, "evil": 0, "fame": 0, "xinde": 0,
        }
    )
    stat_names: dict[str, str] = Field(
        default_factory=lambda: {
            "str": "臂力", "agi": "身法", "con": "根骨", "wis": "悟性",
            "silver": "銀兩", "good": "善名", "evil": "惡名", "fame": "名望", "xinde": "心得",
        }
    )
    vision_base: int = 2  # 從所在地沿道路看得見幾步
    vision_fame: int = 10  # 名望達到這個值，視野 +1
    max_log: int = 200
    player_growth: dict[str, float] = Field(
        default_factory=lambda: {"str": 0.3, "agi": 0.3, "con": 0.3, "wis": 0.3}
    )
    neili_base: float = 300
    neili_per_con: float = 40
    neili_per_level: float = 20
    neili_regen_hours: float = 2  # 氣血從零回滿所需時間
    newbie_days: float = 3  # 每季前幾天氣血回復加倍
    seclusion_xinde_per_hour: int = 15
    xinde_cost_factor: int = 20  # 舊構想欄位，沒有任何地方讀它；練成的價錢看 practice_xinde_per_level（武學與成長設計 4.2）
    xinde_hint_threshold: int = 50  # 心得擱到這個量、而且還有功夫沒練滿時，主畫面提示玩家去門下練功
    # ── 探索三選一（探索三選一設計）──
    # 這裡有還能遇上的奇遇（一次性或奇遇事件）時，探索先滾這個機率，中了就是奇遇、不走三選一。
    # 照整季模擬換算（設計第二節，企劃者 2026-10-03 改）：一個玩家一季在奇遇池非空的地點探索 E 次，
    # 隨機機器人 120 季（p＝0.025 時）的中位數 E＝26.5，p ≤ 1 − 0.5^(1/26.5) ≈ 0.0258，取 0.025。
    # 設好之後量到：每人每季碰到奇遇那一步 0.58 次，至少一次的約四成六。正式內容的值寫在 content/config.json。
    rare_explore_chance: float = Field(default=0.025, ge=0, le=1)
    explore_mix: list[ExploreMix] = Field(default_factory=_default_explore_mix)  # 地點類型 -> 悟意境／野怪／事件的比例
    wild_neili_loss_factor: float = Field(default=0.5, ge=0, le=1)  # 探索撞上的野怪扣氣血是遊歷的幾倍（內傷照同一個比例）
    craft_xinde_base: int = 5  # 煉製成本 = base × 素材數 + per_tier × 階總和（見無限煉製設計 §5.5）
    craft_xinde_per_tier: int = 3
    level_exp: int = 10  # 第 n 級升 n+1 級需要 level_exp × n
    # 原本是 100，但實測一季打 19~26 場只升到第 2~3 級（升到第 10 級要 4500 經驗），
    # 而氣血設計 §1.4 的平衡量測點在第 5／10／15 級——連第 5 級都到不了。降到 10 之後
    # 一季大約升到第 10 級，等級的兩條線（氣血上限、檢定屬性）才有量級可談。
    max_level: int = 30
    # ── 練功（sanguo-companions 合併重寫，見設計文件六.2）──
    practice_injury_chance: float = 0.15  # 每次練功累積受傷（內傷）的機率
    # 遭遇戰按結果扣氣血，扣掉的量是上限的幾成（氣血設計 §1.3：打完要付代價，不是免費收入）
    encounter_neili_loss: dict[str, float] = Field(
        default_factory=lambda: {"大勝": 0.05, "險勝": 0.15, "僵持": 0.20, "落敗": 0.30}
    )
    injury_share: float = 0.2  # 損失的氣血有幾成變成內傷（其餘是輕傷，自己會回）
    practice_injury_amount: float = 15.0  # 受傷時扣的氣血（累積為內傷，需療傷才能回到滿上限）
    heal_neili_per_silver: float = 2.0  # 療傷：每幾點內傷算一兩銀子（氣血設計 §二：預設每 2 點 1 兩，無條件進位）
    # ── 武學與成長（設計第四節；全部【預設】，整季模擬校準見計畫一 Task 14）──
    practice_xinde_per_level: int = 1  # 練成：第 N 成升 N+1 成花 N × 這個數的心得
    fuse_xinde: int = 5  # 合成（武學＋意境）一次
    merge_xinde: int = 5  # 合併（意境＋意境）一次
    cultivate_stamina: int = 10  # 修練一次的體力
    # 修練升到這一品：第一次的機率、每失敗一次加多少（%）；加到 100 就必成（設計 3.5）
    cultivate_odds: dict[str, tuple[int, int]] = Field(
        default_factory=lambda: {"中品": (20, 10), "上品": (10, 6), "絕學": (4, 3)}
    )
    melt_refund_ratio: float = Field(default=0.8, ge=0, le=1)  # 熔一門武學退回練成花的心得的幾成
    melt_quality_bonus: dict[str, int] = Field(
        default_factory=lambda: {"下品": 0, "中品": 5, "上品": 15, "絕學": 40}
    )
    melt_insight_xinde: int = 10  # 熔一個意境換的心得
    duplicate_insight_xinde: int = 10  # 已經會的意境又悟到一次換的心得
    holding_cap_base: int = 50  # 武學與意境合計最多幾個
    holding_cap_levels: int = 5  # 每升幾級……
    holding_cap_step: int = 5  # ……多幾格
    # ── 同伴招募（sanguo-companions 合併重寫，取代舊的收徒/招賢，見設計文件四.4）──
    recruit_stamina: int = 15  # 嘗試招募一次的體力
    recruit_base_chance: float = 0.35  # 基礎成功率，情誼會再往上加（見 roster.py）
    recruit_affinity_bonus: float = 0.5  # 情誼每 100 點，成功率加多少（乘上目前好感度/100）
    duel_chance_on_fail: float = 0.4  # 招募失敗時，額外觸發對方要求決鬥的機率
    duel_fail_silver_loss: int = 15  # 決鬥吃虧：賠的銀兩（原本只有「你惹上了一場決鬥」的文字，沒有任何實際代價）
    recruit_consolation_xinde: int = 30  # 劇情事件想結識的人已經被別人招走時，改給的心得
    fortune_day_min: int = 2  # 新立門戶福緣：第幾天起交友必定先觸發
    fortune_day_max: int = 7  # 新立門戶福緣：第幾天結束還沒發生就直接送上門
    # ── 賽季生命週期（第一季設計第十四節）──
    admins: list[str] = Field(default_factory=list)  # 管理者的名號；暫時用名號認人，線上架構會換成帳號權限
    auto_open_first_season: bool = False  # True＝全服第一次開局就直接開季（測試內容用）；正式內容由管理者開季
    affinity_carry_ratio: float = 0.1  # 換季重來時，每位人物的好感度乘上這個數、無條件捨去後帶進下一季（第一季設計第十四節：最多從 10 起步）
    # ── 伺服器規模（伺服器假人設計第八節第 5 項；第一季設計 5.4、十二）──
    server_max_players: int = 30  # 伺服器人數上限；第四階席次、之後的軍令陣營額度照它等比例換算
    rank4_seat_ratio: float = 0.008  # 每陣營第四階席次＝上限 × 這個比例（四捨五入，最少 1 席）
    talk_stamina: int = 2  # 跟大勢人物對話，每一輪扣的體力
    talk_turns_per_day: int = 3  # 同一位大勢人物，每個遊戲日最多聊幾輪（只算玩家選的 talk:N）
    # ── 伺服器假人（伺服器假人設計第四、六節）──
    bots_min_per_faction: int = 5  # 每個陣營（真人＋假人）至少幾人，不足由假人程式補
    bot_strength: float = 0.6  # 假人挑最高分選項的機率（0＝全隨機，1＝永遠挑最高分）；積極 +0.2、懶散 -0.2
    bot_tick_seconds: float = 20  # 假人程式多久巡一輪（現實秒數）
    bot_fill_seconds: float = 3600  # 同一個陣營兩次補人至少隔幾秒（現實時間），看起來像玩家陸續湧入

    @field_validator("explore_mix")
    @classmethod
    def _rest_comes_last(cls, mixes: list[ExploreMix]) -> list[ExploreMix]:
        """照順序比對、tags 空的是「其餘」：它必須是最後一筆，而且只能有一筆（放前面會蓋掉後面的類型）。"""
        if not mixes or mixes[-1].tags:
            raise ValueError("explore_mix 最後一筆必須是 tags 空的「其餘」")
        if any(not mix.tags for mix in mixes[:-1]):
            raise ValueError("explore_mix 裡 tags 空的「其餘」只能放最後")
        return mixes

    def explore_mix_of(self, tags: list[str]) -> ExploreMix:
        """這組地點標籤算哪一類：照 explore_mix 的順序，第一個有共同標籤的；都沒有就是最後那筆「其餘」。"""
        have = set(tags)
        for mix in self.explore_mix:
            if have & set(mix.tags):
                return mix
        return self.explore_mix[-1]


class BattleFaction(_Strict):
    id: str
    name: str


class BattleActionEffect(_Strict):
    """一個行動分類（tag）選了之後的確定性效果——跟全專案一貫的原則一樣（好感度 tag
    查表、同伴反應強度覆寫），戰局推動跟氣血損耗都是這裡查表決定，LLM 只管潤色敘事，
    不負責算任何數字。"""

    trend_delta: int = 0  # 推動戰局 trend 的量（正負方向看 BattleDef 怎麼定義雙方）
    neili_damage: float = 0  # 這個行動的基礎氣血損耗
    mitigated_by_power: bool = False  # True 時依選擇者自身武學威力算一個抵銷比例（有實力的人魯莽也扛得住一些）


class BattleOption(_Strict):
    text: str  # free_text=True 時這是提示語（顯示在輸入框旁），不是按鈕文字
    tag: str  # 對照 BattleDef.action_tags 的 key——即使是 free_text，機制效果還是查這張表，
    # 不會因為玩家打了什麼字而改變數值（跟全專案一貫原則一樣：不信任 LLM 自己算數字）；
    # 玩家自己打的字只會被餵給 LLM 當敘事潤色的素材（見 battle_instance.py::resolve_round）。
    faction: str | None = None  # 限定某一方才能選；None＝雙方都能選
    free_text: bool = False  # True 時這個「選項」不是按鈕，是一個最多 20 字的自訂行動輸入框
    # （設計討論：「魯莽」這類選項本來就該是玩家自己想出的招，不是從固定清單挑一個）


class BattleAct(_Strict):
    """決戰的一幕。換幕照回合數走（BattleDef.rounds_per_act），不看戰局，所以幕本身沒有換幕條件
    （戰鬥系統設計 3.2；劇情線的幕 Act.advance_when 是另一回事）。"""

    id: str
    title: str
    text: str
    goal: str
    options: list[BattleOption] = Field(min_length=1)


class BattleOutcome(_Strict):
    faction: str
    trend_min: int | None = None
    trend_max: int | None = None
    title: str
    text: str
    world_flags_add: list[str] = Field(default_factory=list)  # 結果套用到共用賽季的世界旗標
    trend_delta: dict[str, int] = Field(default_factory=dict)  # 結果套用到共用賽季的大勢推動（trend id -> 增減量）


class FreeTextGamble(_Strict):
    """自訂行動（放手一搏）的機制（設計討論：「我就是希望看到玩家的奇葩操作對戰局產生
    影響」）：LLM 評估這個行動聽起來有多可能成功（success_rate，0~100），系統拿這個
    機率真的擲骰——賭贏了吃大戰果，賭輸了付大代價，幅度都跟著 LLM 評出的風險程度
    （100 - success_rate）走，不是固定一個數字，所以同樣是「放手一搏」，打「直取敵將
    首級」（成功率低）贏了戰果驚人、輸了代價慘重；打相對保守的描述（成功率高）輸贏
    幅度都小很多。LLM 只負責評機率這一件事（已實測 qwen2.5:14b 對這種單純的機率評估
    排序穩定、同一行動重複問也不會亂跳），擲骰跟換算成數值完全是系統做的，不信任 LLM
    自己決定「這次到底成不成功」或「成功了該加多少」。"""

    success_trend_base: int = 5  # 成功時，戰局推動的基礎量
    success_trend_per_risk: float = 0.3  # 成功時，風險每 1 點再加多少戰局推動
    success_neili_damage: float = 10  # 成功時的氣血損耗（固定小額，賭贏了代價不高）
    failure_trend_per_risk: float = 0.1  # 失敗時，戰局往對方倒退的量（乘上風險，取負）
    failure_neili_base: float = 20  # 失敗時的基礎氣血損耗
    failure_neili_per_risk: float = 3.0  # 失敗時，風險每 1 點再加多少氣血損耗


class BattleDef(_Strict):
    """全服共用的即時多人戰鬥骨架（例如「黃巾決戰」）：集結選陣營→逐幕逐回合（框架給
    選項，查表推動戰局/扣氣血；每幕固定幾回合）→打完最後一回合、或戰局一面倒時，看戰局
    數值判定最終勝負。不是自由發展的 LLM 劇情，
    是固定骨架裡的有限變因（設計討論：「有一個基本框架，玩家可以根據自身影響一些要素，
    但是大框架還是會進行下去」）。

    factions 的第一個是戰局 trend 的正向方（trend 越高對他們越有利，越低對第二個陣營
    越有利）——固定選項靠 action_tags 自己決定方向；free_text 的賭局型行動（見
    FreeTextGamble）沒有個別的 tag 效果可以決定方向，統一照這個順序推算。"""

    id: str
    name: str
    region: str | None = None  # 決戰所在的大區（MapRegion.id）：人要在這個大區、不在路上才能加入（地圖擴充設計第六節）；
    # None＝不限地點，只有測試用的戰鬥這樣寫——地圖有大區時內容檢查要求一定要寫
    factions: list[BattleFaction] = Field(min_length=2)
    trend_name: str = "戰局"
    trend_start: int = 50
    acts: list[BattleAct] = Field(min_length=1)
    rounds_per_act: int = Field(default=3, ge=1)  # 每幕打幾回合（戰鬥系統設計 3.2）：第 rounds_per_act 回合結算完換下一幕，
    # 整場 rounds_per_act × 幕數 回合，最後一回合結算完看戰局定結果
    decisive_margin: int = Field(default=40, ge=1)  # 戰局偏離中線 50 到這麼多（|trend − 50| ≥ 這個值，battle_instance.CENTER）
    # 就當回合收場、不再換幕（壓倒性提前收場：40 時是 90／10；看中線、不看這一場的起點，戰鬥系統 5.3）
    action_tags: dict[str, BattleActionEffect]
    free_text_gamble: FreeTextGamble | None = None  # 有 free_text 選項時必填
    outcomes: list[BattleOutcome] = Field(min_length=1)  # 時刻表決戰只留一筆保底：實際的結果與效果走時刻表
    muster_seconds: float = 600  # 集結期：開放選陣營的時間，逾時系統自動分配
    round_seconds: float = 120  # 每回合等待所有參戰者選擇的時間，逾時系統代選保守行動
    # ── 時刻表決戰（第一季三場大戲，計畫 T8）：時間到了照 WorldState.schedule 開集結，收場用 battle_instance.decide_result
    # 判誰贏、大勝或險勝，交給 timetable.resolve 結算；beta 那場（黃巾決戰）這四欄都是 None ──
    timetable_event: str | None = None  # 時刻表上的哪一件決戰（TimetableEvent.id）
    version: str | None = None  # 那件大事分版本時（宛城甲、乙）這一筆是哪一版；到時間照 version_from 的結果開對的那一筆
    defender: Literal["guan", "huang"] | None = None  # 守方：戰局剛好停在 50 算守方守住（戰鬥系統 4.2）
    front: str | None = None  # 起點讀哪條戰線（戰線 id）：集結開始時讀一次戰況 v，起點＝50 ＋（50 − v）÷ 2（戰鬥系統 5.3）


FigureFate = Literal["退場", "重創", "重挫", "聲威大減", "受挫", "下獄", "到任"]  # 用詞照時刻表結算文件第一節
TimetableKind = Literal["fixed", "roll", "showdown", "finale"]  # 固定發生／照戰況擲骰／全服決戰／季末


class FigureChange(_Strict):
    """時刻表結果對一位大勢人物的效果（計畫 T2 先定義，T4 補完接手規則）。"""

    fate: FigureFate | None = None
    prestige: int = 0  # fate 之外另加減的聲威
    front: str | None = None  # 重挫轉往、到任接手的戰線（大區 id）；重挫時 None＝退出戰線
    location: str | None = None  # 轉往、到任的地點
    only_if: dict[str, str] = Field(default_factory=dict)  # 人物 id → 那位人物當下必須在的戰線；條件不合整筆略過
    note: str = ""  # 這筆真的套用時接在公告後面的一句（例：朱儁到任南陽）


class FigureDef(_Strict):
    """一位大勢人物（content/figures.json，計畫 T4、濃縮版內容表 1.1）：開季時照這裡種進 WorldState.figures。"""

    id: str
    character: str | None = None  # 對話用的人物（characters.json）；輕量接位者（彭脫、韓忠）是 None，不開放對話
    name: str
    faction: str  # 陣營 id（Scenario.factions）
    front: str | None = None  # 開季時推哪條戰線（戰線 id）；None＝在地圖上、能見能打，只是不推（何進、趙弘、董卓）
    location: str  # 開季時在哪個地點
    destiny: bool = False  # 天命人物：聲威歸零是重創，不是退場
    start_prestige: int = Field(default=60, ge=0, le=100)
    actions_per_day: float = Field(default=1.0, ge=0)  # 每曆日推幾次（季曆）
    push: int = Field(default=1, ge=0)  # 每次推幾點
    successor: str | None = None  # 空出戰線時由誰接（人物表的 id）
    squad: str  # 挑戰本人時的對手（squads.json）；難度是聲威 100 時的值
    active_from_week: int = Field(default=1, ge=1)  # 第幾週起才推（官軍三將與孫堅是第 2 週「朝廷出兵」之後）
    start_status: Literal["active", "away"] = "active"  # 輕量接位者開季時還沒出場，接手時才出現
    challenge_off_front: bool = False  # 沒有戰線也能挑戰（何進）；其他人戰線空著時不受挑戰（PM 2026-10-05 定）


class TimetableOutcome(_Strict):
    """一件大事的一種結果：結算文件第五節一列的「公告」「江湖史」「效果」。"""

    text: str  # 沒人鎖定時的公告（接在 TimetableEvent.preface 後面）
    locked_text: dict[str, str] = Field(default_factory=dict)  # 鎖定方 → 具名公告（整句，含開頭；{name} 是鎖定者，伏筆文件）
    loser_text: dict[str, str] = Field(default_factory=dict)  # 鎖定方 → 搶輸那一方的一句（{loser} 是搶輸的人）
    note: str = ""  # 不論有沒有人鎖定都接在公告後面的一句（例：長社黃巾大勝的「波才北上」）
    chronicle: str = ""  # 江湖史一行
    trends: dict[str, int] = Field(default_factory=dict)  # 戰況移動，往黃巾為正
    figures: dict[str, FigureChange] = Field(default_factory=dict)  # 人物 id、「@commander:<戰線>:<guan|huang>」或「@人物:<人物 id>」
    chance_mods: dict[str, float] = Field(default_factory=dict)  # 之後那件大事的成功率修正（寫進 event_bonus，不佔 ±0.20 上限）
    world_flags_add: list[str] = Field(default_factory=list)
    third_party_text: str | None = None  # 這個結果專用的豪強那一句，蓋過 TimetableEvent.third_party_text（盧植下獄分兩版）


class TimetableEvent(_Strict):
    """時刻表上的一件大事（content/timetable.json，照時刻表結算文件第五節逐件轉）。

    outcomes 的鍵：固定的是 "fixed"；擲骰的是 "成"／"不成"；決戰的是 "guan:大勝" 這類；有版本時前面加 "甲:"。"""

    id: str
    week: int = Field(ge=1)
    day: float = Field(default=0, ge=0, lt=7)  # 那一週的第幾曆日發生；0＝週一凌晨
    front: str | None = None  # 戰線（大區 id）；None＝不在戰線上（例：洛陽的盧植下獄）
    title: str
    kind: TimetableKind
    roll_side: Literal["guan", "huang"] | None = None  # 擲骰的「成」對哪一方有利；成功率就是這一方的機率
    base_chance: float | None = Field(default=None, ge=0, le=1)  # 沒有戰線時的基礎成功率
    preface: str = ""  # 沒人鎖定時公告共用的開頭（例：長社的「史書上，……」）
    version_from: str | None = None  # 看哪一件大事的結果決定版本（例：宛城看第 3 週）
    versions: dict[str, str] = Field(default_factory=dict)  # 那件的結果鍵 → 版本（例：{"成": "甲", "不成": "乙"}）
    skip_if_out: str | None = None  # 這位人物已經退場（或重創）就跳過，不公告
    outcomes: dict[str, TimetableOutcome] = Field(default_factory=dict)
    lock_result: dict[str, str] = Field(default_factory=dict)  # 鎖定方 → 結果鍵（不含版本）；決戰不寫，由 T8 給鍵
    third_party_text: str | None = None  # 豪強做完伏筆時接在公告後面的一句（{name} 是豪強那邊的人）
    third_party_trends: dict[str, int] = Field(default_factory=dict)  # 豪強每個名字各套一次的效果
    # 江湖史具名（計畫 T7、伏筆文件 2.4）：有人鎖定、結果是他那一方的具名公告時，江湖史用這一方的這一行（{name} 是鎖定者）；
    # 這一方沒寫就在原本那一行後面接「（{name}改寫）」
    locked_chronicle: dict[str, str] = Field(default_factory=dict)
    # 豪強做完伏筆時另外記的一行江湖史（例：「{name} 取得新野」；多人用「、」接），不論誰贏都記
    third_party_chronicle: str | None = None
    # ── 季末大事（kind＝finale，計畫 T9；別的種類不能寫）──
    early_preface: str = ""  # 季中就收季（決定性勝利、管理者提早收季）時取代 preface 的開頭
    out_lines: dict[str, str] = Field(default_factory=dict)  # 人物 id → 那位人物退場或重創時接在最後的一句（董卓兵敗）
    ending_chronicle: str = ""  # 江湖史那一行，{結局} 換成結局標題


FsKind = Literal["天時地利", "推理", "反直覺抉擇", "拼圖", "累積", "情誼", "集體密謀"]  # 第一季設計 11.3 的類型（只是標記）
FsSource = Literal["action", "event", "talk"]  # 片段從哪裡聽到：在那個大區花體力的行動／那則事件／跟那位人物對話


class FsItem(_Strict):
    """伏筆專用物品（伏筆文件第八節）：名字固定，不進煉製、不進軍備；存在 PlayerState.clue_items，換季清空。"""

    id: str
    name: str


class FsFragment(_Strict):
    """一則線索片段（伏筆文件 2.2）。只發給做得了這條鏈的陣營成員；同一個人每則只聽一次。

    text 可以寫 {風向}、{偽裝}（天機，foreshadow.tianji_answer）；versions 是有版本的大事（宛城甲、乙）的分版文字，
    鍵是版本（timetable 的 versions 的值），那件大事還沒定版本時用史書那一版（第一個）。"""

    region: str  # 大區 id（map.json 的 regions）；action 照它抽，talk 在這個大區的行動裡讓求見不到那位人物的人偷聽，event 只是標記
    source: FsSource
    text: str
    versions: dict[str, str] = Field(default_factory=dict)
    event: str | None = None  # source=event：哪一則事件（事件觸發時給，foreshadow.hear_from_event）
    character: str | None = None  # source=talk：人物 id；在不在那裡照對話（_deep_interaction_target／talk_at）
    stand_in: str | None = None  # source=talk：主角色退場、重創或下獄時改由他出面（例：盧植下獄後董卓）
    topic: str = ""  # source=talk：對話選單上的標籤（例：「問起破敵之策」）
    affinity_min: int = Field(default=0, ge=0)  # source=talk：跟出面那位人物的情誼門檻（基準量，照 foreshadow.need 換算）


class FsCheck(_Strict):
    """最後一步的屬性檢定（只看本人，伏筆是個人做的）：答完題、要交出東西之前擲。"""

    stat: Literal["str", "agi", "con", "wis"]
    dc: int


class FsRequires(_Strict):
    """最後一步的條件積木（伏筆文件 2.2：片段是知識不是門票，只檢查這些）。數字是 1000 人以上那一檔的基準量，
    檢查時照 foreshadow.need 換算（無條件進位、最少 1；寫 0 就是不要）。"""

    clue_items: dict[str, int] = Field(default_factory=dict)  # 物品 id → 數量；答對時交出（扣掉換算後的量）
    grain: int = 0  # 糧草份量（materials.grain_of）；答對時交出
    donations: dict[str, int] = Field(default_factory=dict)  # 「據點 id:糧草」→ 至少捐過多少（PlayerState.donations）；不扣
    affinity: dict[str, int] = Field(default_factory=dict)  # 人物 id → 情誼至少多少；不扣
    counters: dict[str, int] = Field(default_factory=dict)  # 隱藏計數（PlayerState.fs_counters）→ 至少多少；不扣
    check: FsCheck | None = None  # 檢定（不是門檻：照樣顯示可以做，答完題才擲；失敗照 wrong 處理）
    any_of: list[FsRequires] = Field(default_factory=list)  # 非空時至少一組成立（例：乾葦證物，或波才情誼 30）；答對時交出第一組成立的


FsRequires.model_rebuild()


class FsWrong(_Strict):
    """答錯（或檢定失敗）的懲罰；之後可以再來。全部空的就是「沒有損失」。"""

    text: str = ""
    lose_items: list[str] = Field(default_factory=list)  # 這幾樣物品全部收走
    lose_all: bool = False  # 這一步條件裡寫到的物品全部作廢（含 any_of 的每一組）
    lose_grain: bool = False  # 這一步要交的糧草沒收（份量照條件換算）
    affinity: dict[str, int] = Field(default_factory=dict)  # 人物 id → 情誼增減（例：波才 -5）
    cooldown_days: float = Field(default=0, ge=0)  # 幾個曆日之內不能再做這條鏈


class FsOption(_Strict):
    id: str  # 答案用 tianji:<key> 時要是那個天機的候選（例：東、南、西、北）
    text: str
    wrong: FsWrong | None = None  # 選了這個（而且答錯）時用它，蓋過那一步的 wrong


class FsAsk(_Strict):
    """一道題：question 是場景上的問句，options 是選單；answer 是正解的選項 id，或 tianji:<key>（天機決定，伏筆文件 2.9）。"""

    question: str
    options: list[FsOption] = Field(min_length=1)
    answer: str


class FsStep(_Strict):
    """最後一步的一趟（在一個地點做完的事）。單趟的鏈把這些欄位直接寫在 final 上；兩頭賣糧要兩趟，寫成 final.steps。

    question 沒寫：按下選單上的 label 就直接做（例：交糧、點糧）。question 寫了：先問題，答對再接 then 的追問
    （例：孫堅的第二問），全對才擲檢定、交東西、完成。"""

    location: str | None = None  # 在哪個地點做（steps 的每一趟、或單趟的 final 都要寫）
    label: str = ""  # 選單上的字（例：「束苣乘城」「交糧」）
    requires: FsRequires = Field(default_factory=FsRequires)
    unready: str = ""  # 條件不夠時選單上按不下去寫的那句（例：「官軍縮在城裡，我還怕他放火？」）；沒寫就是「東西還沒備齊」
    question: str = ""
    options: list[FsOption] = Field(default_factory=list)
    answer: str | None = None
    then: list[FsAsk] = Field(default_factory=list)
    wrong: FsWrong = Field(default_factory=FsWrong)  # 答錯（選項沒有自己的 wrong 時）與檢定失敗
    success_text: str = ""  # 多趟時：這一趟做完的那句；整條還沒完成就只有這句，最後完成的這一趟則接在 final.success_text 前面（單趟的看 final.success_text）


class FsFinal(FsStep):
    """最後一步（伏筆文件 2.3）：時間窗、夜裡、戰況，加上一趟（直接寫在這裡）或好幾趟（steps）。"""

    window_days: float = Field(default=7, gt=0)  # 時間窗：大事前幾個曆日內（timetable.when 往前算）
    window: Literal["before_event", "during_muster"] = "before_event"  # during_muster：決戰排定的時間到了、還沒收場（新野）
    night: bool = False  # 要在季曆的夜裡（子時到寅時，calendar.is_night）
    front_rule: Literal["side"] = "side"  # 戰況：官軍 ≤ 60、黃巾 ≥ 40、其他（豪強）35～65
    steps: list[FsStep] = Field(default_factory=list)  # 兩趟以上時寫這裡，final 自己的 location 留空；final.requires 每一趟都要
    success_text: str = ""  # 整條完成時看到的敘事（不論先完成還是搶輸都一樣）；可以寫 {風向}、{偽裝}、{人物}
    success_versions: dict[str, str] = Field(default_factory=dict)  # 有版本的大事：版本 → 完成的敘事
    figure: str | None = None  # {人物}：這位人物在那條戰線上（figures.on_front）時寫他的名字，否則寫 stand_in
    stand_in: str | None = None


class FsInvalidIf(_Strict):
    figure_out: str | None = None  # 這位人物退場或重創（figures.is_out）後，整條鏈失效：片段、選項都不再出現


class FsChain(_Strict):
    """一條關鍵伏筆鏈（伏筆文件第二～六節，濃縮版內容表第四節）。"""

    id: str
    event: str  # 時刻表大事 id（content/timetable.json）
    side: str  # 誰能做：劇本的陣營 id（guan、huang 會鎖定那件大事；其他陣營是第三方，寫進 third_party）
    kind: FsKind
    front: str | None = None  # 戰況看哪條線；沒寫就看那件大事的戰線（盧植下獄、張角病逝要寫 jizhou）
    fragments: list[FsFragment] = Field(default_factory=list)
    final: FsFinal
    invalid_if: FsInvalidIf = Field(default_factory=FsInvalidIf)


class FsGuanyin(_Strict):
    """官銀（濃縮版內容表 4.0）：side 的人在 regions 的大區遊歷打贏 squad_faction 的隊伍時，有 Config.guanyin_chance
    的機率 fs_counters["guanyin"] +1，寫 text 這一句。只在某條鏈的條件讀 guanyin 時才擲。"""

    side: str = "huang"
    squad_faction: str = "guan"
    regions: list[str] = Field(default_factory=list)
    text: str


class Foreshadows(_Strict):
    """content/foreshadows.json（計畫 T7）。檔案不存在或是空的就是這個空的預設值：什麼都不發生。"""

    items: list[FsItem] = Field(default_factory=list)
    chains: list[FsChain] = Field(default_factory=list)
    guanyin: FsGuanyin | None = None


OrderKind = Literal["siege", "defend", "intercept", "escort", "strike"]  # 攻城、守城、截糧、護糧、打擊大勢人物
PersonalKind = Literal["win", "duty", "convoy", "challenge"]  # 遊歷打贏、守勢行動、糧車送到、挑戰打贏


class OrderWhen(_Strict):
    """什麼時候發（濃縮版內容表 3.1）；寫了的每一項都要成立（or_enemy_siege 只放寬 losing_by）。
    front_min／front_max：那條戰線的戰況在這個區間（含兩端）；打擊是看目標人物所在戰線。
    losing_by：戰線偏向對方超過多少（官軍：戰況 ≥ 50＋n；黃巾：≤ 50－n）。
    or_enemy_siege：或者敵方上週在這條戰線達成了攻城（守城）。
    event_within_weeks：這條戰線的下一件時刻表大事在幾週內（季曆）。
    always：每週固定一道（豪強的打擊）。"""

    front_min: int | None = None
    front_max: int | None = None
    losing_by: int | None = None
    or_enemy_siege: bool = False
    event_within_weeks: float | None = None
    always: bool = False


class OrderEffect(_Strict):
    """達成時的效果（濃縮版內容表 3.1）。trend：戰況往己方偏幾點；守城的 trend 只在敵方這週還沒達成攻城時才給，
    已經達成就改成把對方攻城的效果收回一半（halve_enemy_siege）。event_mod：那條戰線下一件時刻表大事己方 +多少。
    figure_prestige：打擊的人物聲威再扣多少（負數）。"""

    trend: int = 0
    event_mod: float = 0.0
    figure_prestige: int = 0
    halve_enemy_siege: bool = False


class OrderTemplate(_Strict):
    """一種軍令對一個陣營（濃縮版內容表 3.1 的一列）。文字的插槽：{戰線}{地點}{起點}{終點}{主將}{人物}{號令}。"""

    kind: OrderKind
    side: str  # 陣營 id
    priority: int  # 數字小的先發
    when: OrderWhen = Field(default_factory=OrderWhen)
    text: str  # 發布文字
    personal: PersonalKind  # 個人部分怎樣算一次（跟 kind 是固定的對應，content.validate 檢查）
    quota_base: int = Field(ge=1)  # 陣營總額度（3000 人的量）
    effect: OrderEffect = Field(default_factory=OrderEffect)
    faction_rumor: str  # 達成時的陣營軍情（後面接「出力最多：…」）
    leak_rumor: str  # 達成時在那一帶外洩的地方傳聞（不寫名字）


class OrderSlots(_Strict):
    """一條戰線、一個陣營的地點插槽（濃縮版內容表 3.2）。"""

    intercept: str  # 截糧的 {地點}：在這裡與相鄰站遊歷可能遇上敵方糧隊
    escort: tuple[str, str]  # 護糧的 {起點}、{終點}（終點是己方據點）


class Duty(_Strict):
    """第 1 階守勢行動（濃縮版內容表 2.6）：選單上的名字與一句敘事（{地點} 換成所在地點）。"""

    name: str
    text: str


class OrderCaller(_Strict):
    """黃巾發令的人（{號令}）：照順序第一個沒退場的（figure 是 None 的那一筆是最後的退路）。"""

    figure: str | None = None
    text: str


class OrdersContent(_Strict):
    """content/orders.json（計畫 T6）。不存在時是空的：沒有軍令、沒有守勢行動。"""

    templates: list[OrderTemplate] = Field(default_factory=list)
    slots: dict[str, dict[str, OrderSlots]] = Field(default_factory=dict)  # 戰線 id → 陣營 id → 插槽
    duties: dict[str, Duty] = Field(default_factory=dict)  # 陣營 id → 守勢行動
    commander_fallback: dict[str, str] = Field(default_factory=dict)  # 陣營 id → 沒有主將時 {主將} 寫的泛稱
    callers: list[OrderCaller] = Field(default_factory=list)  # {號令}
    convoy_squads: dict[str, str] = Field(default_factory=dict)  # 陣營 id → 自己的運糧隊（截糧打的是對方的）


class PromotionDef(_Strict):
    """一階的晉升（濃縮版內容表 2.1、2.2；計畫 T5）。figure 是出面的大勢人物（豪強的馬商不是人物，空著），不在時由
    successor 出面、演 event_handoff。location 是地點 id，或 "nearest_base"（豪強：離自己最近的投靠點）。
    召見文字放這裡（{據點} 換成地點名）；結尾那一句（closing）接在選項的反應後面。"""

    faction: str
    rank: int = Field(ge=2)
    figure: str | None = None
    successor: str | None = None
    location: str
    event_main: str
    event_handoff: str | None = None
    summons_text: str
    summons_handoff: str | None = None
    closing: str


class FollowerDef(_Strict):
    """部下的模板（濃縮版內容表 2.4）：原創的無名稱呼；不能對話、不能散功，只算威力（計畫 T5）。"""

    id: str
    faction: str
    name: str
    stats: dict[str, int] = Field(default_factory=dict)
    wugong: str  # skills.json 的武學
    wugong_level: int = Field(ge=1, le=10)


class Content(_Strict):
    config: Config
    scenario: Scenario
    locations: dict[str, Location]
    events: dict[str, Event]
    skills: dict[str, SkillDef]
    insights: dict[str, InsightDef] = Field(default_factory=dict)  # 意境（content/insights.json，武學與成長設計附錄 A）
    materials: dict[str, Material]
    craft_names: CraftNames
    banned_names: list[str]  # 煉製命名的禁用詞（原創原則：不用金庸等作品的專有名詞）
    sects: dict[str, Sect]
    characters: dict[str, CharacterDef]
    squads: dict[str, Squad]
    battles: dict[str, BattleDef] = Field(default_factory=dict)  # 內容尚未撰寫，先留介面（見設計討論，骨架做完再回頭寫黃巾決戰）
    road_sights: dict[str, RoadSight] = Field(default_factory=dict)  # 路上見聞（content/road_sights.json，路上設計第五節）
    timetable: list[TimetableEvent] = Field(default_factory=list)  # 第一季的時刻表（content/timetable.json，計畫 T2）
    figures: dict[str, FigureDef] = Field(default_factory=dict)  # 大勢人物（content/figures.json，計畫 T4）；沒有這個檔就是空的
    foreshadows: Foreshadows = Field(default_factory=Foreshadows)  # 關鍵伏筆（content/foreshadows.json，計畫 T7）
    orders: OrdersContent = Field(default_factory=OrdersContent)  # 陣營軍令（content/orders.json，計畫 T6）
    promotions: list[PromotionDef] = Field(default_factory=list)  # 晉升（content/promotions.json，計畫 T5）
    followers: dict[str, FollowerDef] = Field(default_factory=dict)  # 部下模板（content/followers.json，計畫 T5）
    map: MapLayout
    tutorial: Tutorial
