"""內容資料模型：content/ 底下所有 JSON 設定的結構定義。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler
from pydantic_core import core_schema

STATS = ("str", "agi", "con", "wis", "silver", "good", "evil", "fame", "xinde")
ActionKind = Literal["explore", "train", "socialize"]
TravelMode = Literal["walk", "hurry", "dash"]  # 步行／趕路／疾行（地圖擴充設計 3.2）
# sanguo-companions 合併：同伴不再分天地玄黃品階，改成「龍頭人物」（劇情鎖定，不可招募，
# 見設計文件四.4）跟「可招募」兩種，決定要不要出現在招募流程裡。
CompanionKind = Literal["locked", "recruitable"]
MartialKind = Literal["內功", "武學"]
Attribute = Literal["陰", "陽", "剛", "柔", "快", "慢", "虛", "實"]  # 見 tianxia/martial_arts.py


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
    any_of: list[Condition] = Field(default_factory=list)  # 非空時，至少一個子條件成立


Condition.model_rebuild()


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
    fortune: bool = False  # 新立門戶福緣：不會被隨機抽到，由 engine 在交遊時觸發（actions 必須是空的）
    condition: Condition = Field(default_factory=Condition)
    choices: list[Choice] = Field(min_length=1)


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


class Location(_Strict):
    id: str
    name: str
    description: str
    connections: list[Connection]  # 相鄰的地點，每一筆是一條路（見 Connection）
    x: int
    y: int
    tags: list[str] = Field(default_factory=list)
    danger: int = Field(default=1, ge=1, le=3)
    important: bool = False
    enemies: list[str] = Field(default_factory=list)
    train_trend: dict[str, int] = Field(default_factory=dict)  # 歷練打贏／操練推大勢的量；正負是散人的方向，有陣營目標的人照自己的目標推（Game._train_push）
    materials: list[str] = Field(default_factory=list)  # 在這裡探索可能撿到的素材；留空則給隨機的一階素材
    unlock_flag: str | None = None  # 設定後，需該世界旗標成立才能前往

    def road_to(self, dest: str) -> RoadKind:
        """到相鄰地點 dest 的路的種類；清單裡是一般字串（測試直接塞的）或沒連到 dest 時當一般路。"""
        for conn in self.connections:
            if conn == dest:
                return getattr(conn, "road", "路")
        return "路"


class SkillDef(_Strict):
    """武學/內功的內容定義（sanguo-companions 合併重寫，取代 battle.py 時代的 Skill/SkillEffect）。

    只定義「本命武學」（歷史人物的固定武學，情誼滿門檻習得）——自創功法完全是玩家取名
    當下即時生成、存進共用世界狀態（見 martial_arts.py／world_state.py），不進這份內容檔。
    本命武學的品質固定是絕學（見 martial_arts.historical_art），這裡不必也不該填品質。
    """

    id: str
    name: str
    kind: MartialKind
    attribute: Attribute
    desc: str = ""


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


class Trend(_Strict):
    id: str
    name: str
    desc: str = ""
    start: int = Field(default=0, ge=0, le=100)
    hidden: bool = False


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


class Ending(_Strict):
    id: str
    title: str
    text: str
    storyline: str | None = None  # 只在這條主線下成立；None＝任何主線
    hint: str = ""  # 顯示在任務區塊：怎麼達成這個結局
    condition: Condition = Field(default_factory=Condition)


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
    points: list[list[int]]
    fill: str = Field(pattern=HEX_COLOR)
    text_fill: str = Field(pattern=HEX_COLOR)
    label_x: int
    label_y: int


class MapLayout(_Strict):
    width: int = 680
    height: int = 420
    background: str = Field(default="#F6F1E4", pattern=HEX_COLOR)
    regions: list[MapRegion] = Field(default_factory=list)
    rivers: list[list[list[int]]] = Field(default_factory=list)  # 每條河是一串 [x, y] 點
    labels: list[MapLabel] = Field(default_factory=list)
    mini_window: tuple[int, int] = (270, 180)  # 小地圖以所在地為中心截多寬、多高（地圖單位）；地圖畫得越疏，要截得越大才看得到一兩站路


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

    action: Literal["explore", "socialize", "move", "view_map", "recruit", "practice"] | None = None
    locations: list[str] = Field(default_factory=list)
    condition: Condition = Field(default_factory=Condition)
    has_wugong: bool = False  # 身上要有一門武學才算（沒有武學威力是 0，出城只有挨打的份）


class TutorialStep(_Strict):
    id: str
    text: str
    done_when: TutorialGoal
    reward: Effect = Field(default_factory=Effect)


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


class Config(_Strict):
    stamina_max: int = 150
    stamina_regen_seconds: float = 180  # 自然回復：每幾秒（遊戲時間）回 1 點體力（地圖擴充設計第二節：每 3 分鐘 1 點）
    rest_regen_multiplier: float = Field(default=2, ge=1)  # 打坐中體力回復是平常的幾倍
    # 地圖座標 1 單位＝步行幾分鐘：現行內容（40 個地點的地圖）取 0.04，也就是 25 個單位約 1 分鐘；這裡的預設值只是沒寫時的退路
    travel_minutes_per_unit: float = Field(default=0.0375, gt=0)
    road_factor: dict[RoadKind, float] = Field(
        default_factory=lambda: {"官道": 0.8, "路": 1.0, "山路": 1.5}
    )  # 路程＝距離 × 路的種類係數 × travel_minutes_per_unit（地圖擴充設計 3.1）
    hurry_stamina_per_minute: float = Field(default=1, ge=0)  # 趕路：每分鐘路程扣幾點體力（時間減半）
    dash_stamina_per_minute: float = Field(default=2, ge=0)  # 疾行：每分鐘路程扣幾點體力（立刻到）
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
    season_days: float = 14
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
    xinde_cost_factor: int = 20  # 第 n 成升到 n+1 成需要 factor × n（構想欄位，目前練功免費、沒有任何地方讀它）
    xinde_hint_threshold: int = 50  # 心得擱到這個量、而且還有功夫沒練滿時，主畫面提示玩家去門下練功
    explore_material_chance: float = 0.3  # 探索時撿到一個素材的機率（見無限煉製設計 §4.2）
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
    # ── 同伴招募（sanguo-companions 合併重寫，取代舊的收徒/招賢，見設計文件四.4）──
    recruit_stamina: int = 15  # 嘗試招募一次的體力
    recruit_base_chance: float = 0.35  # 基礎成功率，情誼會再往上加（見 roster.py）
    recruit_affinity_bonus: float = 0.5  # 情誼每 100 點，成功率加多少（乘上目前好感度/100）
    duel_chance_on_fail: float = 0.4  # 招募失敗時，額外觸發對方要求決鬥的機率
    duel_fail_silver_loss: int = 15  # 決鬥吃虧：賠的銀兩（原本只有「你惹上了一場決鬥」的文字，沒有任何實際代價）
    recruit_consolation_xinde: int = 30  # 劇情事件想結識的人已經被別人招走時，改給的心得
    fortune_day_min: int = 2  # 新立門戶福緣：第幾天起交遊必定先觸發
    fortune_day_max: int = 7  # 新立門戶福緣：第幾天結束還沒發生就直接送上門
    # ── 賽季生命週期（第一季設計第十四節）──
    admins: list[str] = Field(default_factory=list)  # 管理者的名號；暫時用名號認人，線上架構會換成帳號權限
    auto_open_first_season: bool = False  # True＝全服第一次開局就直接開季（測試內容用）；正式內容由管理者開季
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


class BattleAdvanceWhen(_Strict):
    """跟 Condition 不一樣——戰鬥幕只看戰局 trend，不該看哪個玩家的個人屬性/旗標
    （一場戰鬥是所有參戰者共同經歷的，不該因為某個人的狀態而對其他人判斷出不同結果）。
    trend_min/trend_max 是「夾在區間內」（AND，例如「停留在中段膠著」）；trend_outside
    是「偏離中性值夠多」（OR，雙向都算——戰局往任一方明顯傾斜就該進入下一幕，不是只有
    某一方拉開差距才算，兩種只會擇一使用）。"""

    trend_min: int | None = None
    trend_max: int | None = None
    trend_outside: int | None = None  # |trend - BattleDef.trend_start| >= 這個值就算成立


class BattleAct(_Strict):
    id: str
    title: str
    text: str
    goal: str
    options: list[BattleOption] = Field(min_length=1)
    advance_when: BattleAdvanceWhen | None = None  # None＝最後一幕


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
    選項，查表推動戰局/扣氣血）→決戰幕的戰局數值判定最終勝負。不是自由發展的 LLM 劇情，
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
    action_tags: dict[str, BattleActionEffect]
    free_text_gamble: FreeTextGamble | None = None  # 有 free_text 選項時必填
    outcomes: list[BattleOutcome] = Field(min_length=1)
    muster_seconds: float = 600  # 集結期：開放選陣營的時間，逾時系統自動分配
    round_seconds: float = 120  # 每回合等待所有參戰者選擇的時間，逾時系統代選保守行動


class Content(_Strict):
    config: Config
    scenario: Scenario
    locations: dict[str, Location]
    events: dict[str, Event]
    skills: dict[str, SkillDef]
    materials: dict[str, Material]
    craft_names: CraftNames
    banned_names: list[str]  # 煉製命名的禁用詞（原創原則：不用金庸等作品的專有名詞）
    sects: dict[str, Sect]
    characters: dict[str, CharacterDef]
    squads: dict[str, Squad]
    battles: dict[str, BattleDef] = Field(default_factory=dict)  # 內容尚未撰寫，先留介面（見設計討論，骨架做完再回頭寫黃巾決戰）
    map: MapLayout
    tutorial: Tutorial
