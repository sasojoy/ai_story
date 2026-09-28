"""內容資料模型：content/ 底下所有 JSON 設定的結構定義。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

STATS = ("str", "agi", "con", "wis", "silver", "good", "evil", "fame")
Style = Literal["剛", "柔", "快", "巧", "無"]
Slot = Literal["內功", "外功", "輕功"]
ActionKind = Literal["explore", "train", "socialize"]


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


class Check(_Strict):
    stat: str
    difficulty: int


class Choice(_Strict):
    text: str
    condition: Condition = Field(default_factory=Condition)
    check: Check | None = None
    combat: str | None = None  # 敵人 id：選了就進入關鍵戰鬥
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
    move_cost: int = 5
    important: bool = False
    enemies: list[str] = Field(default_factory=list)
    train_trend: dict[str, int] = Field(default_factory=dict)
    unlock_flag: str | None = None  # 設定後，需該世界旗標成立才能前往


class Skill(_Strict):
    id: str
    name: str
    slot: Slot
    style: Style = "無"
    power: int
    sect: str | None = None
    desc: str = ""


class Sect(_Strict):
    id: str
    name: str
    location: str
    alignment: Literal["正", "邪", "中"]
    desc: str = ""
    starter_skills: list[str] = Field(default_factory=list)


class Enemy(_Strict):
    id: str
    name: str
    desc: str = ""
    hp: int
    atk: int
    dfn: int
    spd: int
    style: Style = "無"
    reward_silver: int = 0


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


class SimPlayer(_Strict):
    name: str
    actions_per_day: float
    trend: dict[str, int] = Field(default_factory=dict)
    requires_revealed: str | None = None  # 這條隱藏線浮現之前不會行動
    rumors: list[str] = Field(default_factory=list)
    rumor_chance: float = 0.3
    condition: Condition = Field(default_factory=Condition)


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


class MapLayout(_Strict):
    width: int = 680
    height: int = 420
    rivers: list[list[list[int]]] = Field(default_factory=list)  # 每條河是一串 [x, y] 點
    labels: list[MapLabel] = Field(default_factory=list)


class WorldEvent(_Strict):
    """以任意條件觸發、只觸發一次的世界事件。"""

    id: str
    condition: Condition
    text: str
    world_flags_add: list[str] = Field(default_factory=list)
    ends_season: bool = False


class Act(_Strict):
    id: str
    title: str
    text: str
    goal: str
    advance_when: Condition | None = None  # 最後一幕為 None


class Storyline(_Strict):
    id: str
    name: str
    intro: str = ""
    acts: list[Act] = Field(min_length=1)
    replaces_when: Condition | None = None  # 支線主線：條件成立時取代主線


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


class Config(_Strict):
    stamina_max: int = 150
    stamina_regen_seconds: float = 300
    action_cost: dict[str, int] = Field(
        default_factory=lambda: {"explore": 10, "train": 10, "socialize": 5}
    )
    time_scale: float = 1.0
    season_days: float = 14
    seclusion_exp_per_hour: int = 20
    skill_exp_per_level: int = 100
    train_skill_exp: int = 10
    train_stat_chance: float = 0.3
    train_event_chance: float = 0.3
    qiyu_weight_multiplier: float = 1.5
    starter_skills: list[str] = Field(default_factory=list)
    start_stats: dict[str, int] = Field(
        default_factory=lambda: {
            "str": 5, "agi": 5, "con": 5, "wis": 5,
            "silver": 50, "good": 0, "evil": 0, "fame": 0,
        }
    )
    stat_names: dict[str, str] = Field(
        default_factory=lambda: {
            "str": "臂力", "agi": "身法", "con": "根骨", "wis": "悟性",
            "silver": "銀兩", "good": "善名", "evil": "惡名", "fame": "名望",
        }
    )
    max_log: int = 200


class Content(_Strict):
    config: Config
    scenario: Scenario
    locations: dict[str, Location]
    events: dict[str, Event]
    skills: dict[str, Skill]
    sects: dict[str, Sect]
    enemies: dict[str, Enemy]
    map: MapLayout
