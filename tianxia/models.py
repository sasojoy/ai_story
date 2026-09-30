"""內容資料模型：content/ 底下所有 JSON 設定的結構定義。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

STATS = ("str", "agi", "con", "wis", "silver", "good", "evil", "fame", "xinde")
Style = Literal["剛", "柔", "快", "巧", "無"]
ActionKind = Literal["explore", "train", "socialize"]
Tier = Literal["天", "地", "玄", "黃", "敵"]
COMPANION_TIERS = ("天", "地", "玄", "黃")  # 同伴的品階，由高到低；「敵」只給敵人
Grade = Literal["S", "A", "B", "C"]
Source = Literal["開局", "收徒", "交遊", "福緣", "奇遇", "招降", "招賢"]  # 同伴的取得管道
EffectKind = Literal["damage", "heal", "buff", "debuff", "control", "dodge", "reduce"]


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


class SkillEffect(_Strict):
    """武學效果。base 是第 1 成的數值，top 是第 10 成的數值（省略＝不隨成數變化）。"""

    kind: EffectKind
    base: float
    top: float | None = None
    target: Literal["enemy", "enemies", "self", "ally_lowest", "allies"] = "enemy"
    stat: Literal["atk", "dfn", "spd"] | None = None
    control: Literal["點穴", "卸兵", "封脈"] | None = None
    rounds: int = 1


class Skill(_Strict):
    id: str
    name: str
    kind: Literal["心法", "絕招", "連招"]
    style: Style = "無"
    quality: Literal["下", "中", "上"] = "中"
    sect: str | None = None
    chance_base: float = 0.0
    chance_top: float | None = None
    prep: int = 0
    effects: list[SkillEffect] = Field(min_length=1)
    desc: str = ""


class Sect(_Strict):
    id: str
    name: str
    location: str
    alignment: Literal["正", "邪", "中"]
    desc: str = ""
    starter_skills: list[str] = Field(default_factory=list)


class CharacterDef(_Strict):
    """人物（同伴或敵人）。stats 是第 1 級的屬性，growth 是每升一級增加的量。"""

    id: str
    name: str
    tier: Tier
    style: Style = "無"
    stats: dict[str, float]
    growth: dict[str, float] = Field(default_factory=dict)
    aptitude: dict[str, Grade] = Field(default_factory=dict)  # 剛柔快巧；未列出＝B
    innate: str | None = None
    sect: str | None = None
    desc: str = ""
    command: int | None = None  # 統御；同伴必填，敵人不填
    sources: list[Source] = Field(default_factory=list)  # 取得管道；同伴必填，敵人不填
    recruit_at: list[str] = Field(default_factory=list)  # 只在這些地點收得到徒；空＝任何城鎮或門派
    trait: str | None = None  # 天品的特性：一門效果固定的心法，不佔武學欄、不能升級或散功


def in_gacha_pool(ch: CharacterDef) -> bool:
    """招賢的卡池：同伴品階、取得管道有「招賢」。tianxia/gacha.py 抽人與載入時的卡池檢查（content.py）都用這一個判斷。"""
    return ch.tier in COMPANION_TIERS and "招賢" in ch.sources


class SquadMember(_Strict):
    character: str
    level: int = Field(default=1, ge=1)


class Surrender(_Strict):
    """打贏敵方隊伍後可能投效的人（同伴 id）；chance 省略時用 config.surrender_chance。"""

    character: str
    chance: float | None = Field(default=None, ge=0, le=1)


class Squad(_Strict):
    """敵方隊伍；第一名成員是隊長。"""

    id: str
    name: str
    members: list[SquadMember] = Field(min_length=1, max_length=3)
    reward_silver: int = 0
    reward_xinde: int = 0
    exp: int = 0
    surrender: Surrender | None = None  # 打贏後可能投效的人


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

    action: Literal["explore", "train", "socialize", "move", "view_map"] | None = None
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


class Config(_Strict):
    stamina_max: int = 150
    stamina_regen_seconds: float = 300
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
    player_innate: str | None = None  # 本人的本命武學（1a 為固定武學，1b 改為骨架＋詞條）
    player_style: Style = "無"
    player_aptitude: dict[str, Grade] = Field(default_factory=dict)
    player_growth: dict[str, float] = Field(
        default_factory=lambda: {"str": 0.3, "agi": 0.3, "con": 0.3, "wis": 0.3}
    )
    start_companions: list[str] = Field(default_factory=list)  # 出身給的同伴；前兩名與本人組隊
    battle_rounds: int = 8
    battle_atk_factor: float = 12.0
    battle_def_factor: float = 5.0
    neili_base: float = 300
    neili_per_con: float = 40
    neili_per_level: float = 20
    neili_regen_hours: float = 2  # 內力從零回滿所需時間
    newbie_days: float = 3  # 每季前幾天內力回復加倍
    seclusion_xinde_per_hour: int = 15
    xinde_cost_factor: int = 20  # 第 n 成升到 n+1 成需要 factor × n
    dispel_refund: float = 0.8
    level_exp: int = 100  # 第 n 級升 n+1 級需要 level_exp × n
    max_level: int = 30
    vision_skills: list[str] = Field(default_factory=list)  # 練到 vision_skill_level 時視野 +1
    vision_skill_level: int = 5
    # ── 名冊與編隊（1c）──
    team_counts: list[int] = Field(default_factory=lambda: [2, 3, 4])  # 開放的隊伍數：第一幕、第二幕、第三幕起
    command_caps: list[int] = Field(default_factory=lambda: [15, 18, 20])  # 每隊總統御上限，同上
    player_command: int = 5  # 你本人的統御
    apprentice_silver: int = 40  # 收徒：每次的銀兩
    apprentice_stamina: int = 5  # 收徒：每次的體力
    apprentice_per_day: int = 2  # 收徒：每個遊戲日最多幾次
    apprentice_tags: list[str] = Field(default_factory=lambda: ["城鎮", "門派"])  # 有這些標籤的地點才能收徒
    apprentice_weights: dict[str, float] = Field(default_factory=lambda: {"黃": 75, "玄": 25})  # 收徒抽到各品階的比重
    surrender_chance: float = 0.25  # 招降：敵方隊伍沒寫 chance 時的機率
    fortune_day_min: int = 2  # 新立門戶福緣：第幾天起交遊必定先觸發
    fortune_day_max: int = 7  # 新立門戶福緣：第幾天結束還沒發生就直接送上門
    # 劇情事件結識到已入門的人、招賢抽到重複的人時改給的心得（暫定・另談；招賢的另受付費心得護欄限制）
    duplicate_xinde: dict[str, int] = Field(default_factory=lambda: {"黃": 10, "玄": 20, "地": 50, "天": 100})
    # ── 招賢（1c-3）：價格、重複換算與付費心得護欄是「暫定・另談」的數字（見 provisional），只是讓功能能跑 ──
    gacha_single: int = 100  # 單抽要幾元寶（暫定・另談）
    gacha_ten: int = 1000  # 十連要幾元寶（暫定・另談）
    gacha_rates: dict[str, float] = Field(  # 各品階的機率（%，加起來 100），同品階的人平均分配
        default_factory=lambda: {"天": 3, "地": 12, "玄": 35, "黃": 50}
    )
    gacha_pity: int = 40  # 保底：連續這麼多抽沒出天品，這一抽必得天品
    gacha_ten_floor: str = "地"  # 十連至少一名這個品階以上（和天品保底分開算）
    gacha_xinde_cap: int = 300  # 付費心得護欄：本季招賢換到的心得最多這麼多（暫定・另談）
    gacha_xinde_half: int = 150  # 付費心得護欄：本季招賢心得超過這個數之後，重複只給一半（暫定・另談）
    gacha_silver: dict[str, int] = Field(  # 付費心得護欄：本季招賢心得滿了之後，重複改給的銀兩（暫定・另談）
        default_factory=lambda: {"黃": 10, "玄": 20, "地": 50, "天": 100}
    )
    test_yuanbao: int = 1000  # 設定分頁「測試：領取元寶」每按一次給多少元寶
    # 標為「暫定・另談」的設定名稱：JSON 不能寫註解，寫在這裡；載入時檢查名稱存在，不影響任何數字
    provisional: list[str] = Field(default_factory=list)


class Content(_Strict):
    config: Config
    scenario: Scenario
    locations: dict[str, Location]
    events: dict[str, Event]
    skills: dict[str, Skill]
    sects: dict[str, Sect]
    characters: dict[str, CharacterDef]
    squads: dict[str, Squad]
    map: MapLayout
    tutorial: Tutorial
