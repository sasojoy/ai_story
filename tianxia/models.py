"""內容資料模型：content/ 底下所有 JSON 設定的結構定義。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

STATS = ("str", "agi", "con", "wis", "silver", "good", "evil", "fame", "xinde")
ActionKind = Literal["explore", "train", "socialize"]
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


class Location(_Strict):
    id: str
    name: str
    description: str
    connections: list[str]
    x: int
    y: int
    tags: list[str] = Field(default_factory=list)
    danger: int = Field(default=1, ge=1, le=3)
    move_cost: int = Field(default=5, ge=0)
    important: bool = False
    enemies: list[str] = Field(default_factory=list)
    train_trend: dict[str, int] = Field(default_factory=dict)
    unlock_flag: str | None = None  # 設定後，需該世界旗標成立才能前往


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


class Squad(_Strict):
    """遭遇/劇情戰的對手：一個抽象的難度值＋屬性，不是完整的人物陣容（見 encounter.py 的單次判定）。"""

    id: str
    name: str
    difficulty: float
    attribute: Attribute | None = None
    reward_silver: int = 0
    reward_xinde: int = 0
    exp: int = 0


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


class WorldEvent(_Strict):
    """以任意條件觸發、只觸發一次的世界事件。"""

    id: str
    condition: Condition
    text: str
    world_flags_add: list[str] = Field(default_factory=list)
    ends_season: bool = False
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
    """三項都要符合才算完成；空的欄位不檢查。"""

    action: Literal["explore", "socialize", "move", "view_map", "recruit", "practice"] | None = None
    locations: list[str] = Field(default_factory=list)
    condition: Condition = Field(default_factory=Condition)


class TutorialStep(_Strict):
    id: str
    text: str
    done_when: TutorialGoal
    reward: Effect = Field(default_factory=Effect)


class Tutorial(_Strict):
    speaker: str = "老說書人"
    steps: list[TutorialStep] = Field(default_factory=list)
    outro: str = ""


class Scenario(_Strict):
    id: str
    name: str
    intro: str
    start_location: str
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
    stamina_regen_seconds: float = 300
    ollama_url: str = "http://localhost:11434"  # companion_agent.py 深度對話用；連不上時優雅退回保底反應
    ollama_model: str = "qwen2.5:14b"
    ollama_timeout: int = 120
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
    xinde_cost_factor: int = 20  # 第 n 成升到 n+1 成需要 factor × n
    level_exp: int = 100  # 第 n 級升 n+1 級需要 level_exp × n
    max_level: int = 30
    # ── 練功（sanguo-companions 合併重寫，見設計文件六.2）──
    practice_injury_chance: float = 0.15  # 每次練功累積受傷（內傷）的機率
    practice_injury_amount: float = 15.0  # 受傷時扣的氣血（累積為內傷，需療傷才能回到滿上限）
    heal_silver_per_injury: int = 2  # 療傷：每點內傷要幾兩銀子（無條件進位）
    # ── 同伴招募（sanguo-companions 合併重寫，取代舊的收徒/招賢，見設計文件四.4）──
    recruit_stamina: int = 15  # 嘗試招募一次的體力
    recruit_base_chance: float = 0.35  # 基礎成功率，情誼會再往上加（見 roster.py）
    recruit_affinity_bonus: float = 0.5  # 情誼每 100 點，成功率加多少（乘上目前好感度/100）
    duel_chance_on_fail: float = 0.4  # 招募失敗時，額外觸發對方要求決鬥的機率
    recruit_consolation_xinde: int = 30  # 劇情事件想結識的人已經被別人招走時，改給的心得
    fortune_day_min: int = 2  # 新立門戶福緣：第幾天起交遊必定先觸發
    fortune_day_max: int = 7  # 新立門戶福緣：第幾天結束還沒發生就直接送上門


class Content(_Strict):
    config: Config
    scenario: Scenario
    locations: dict[str, Location]
    events: dict[str, Event]
    skills: dict[str, SkillDef]
    sects: dict[str, Sect]
    characters: dict[str, CharacterDef]
    squads: dict[str, Squad]
    map: MapLayout
    tutorial: Tutorial
