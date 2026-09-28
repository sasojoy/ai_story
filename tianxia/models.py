"""內容資料模型：content/ 底下所有 JSON 設定的結構定義。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

STATS = ("str", "agi", "con", "wis", "silver", "good", "evil", "fame")
Style = Literal["剛", "柔", "快", "巧", "無"]
Slot = Literal["內功", "外功", "輕功"]
ActionKind = Literal["explore", "train", "socialize"]


class Condition(BaseModel):
    """所有欄位都是「且」的關係；空的欄位不檢查。"""

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


class Effect(BaseModel):
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


class Check(BaseModel):
    stat: str
    difficulty: int


class Choice(BaseModel):
    text: str
    condition: Condition = Field(default_factory=Condition)
    check: Check | None = None
    combat: str | None = None  # 敵人 id：選了就進入關鍵戰鬥
    effect: Effect = Field(default_factory=Effect)  # 檢定成功／戰鬥勝利（或無檢定時）
    fail_effect: Effect = Field(default_factory=Effect)  # 檢定失敗／戰鬥落敗


class Event(BaseModel):
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


class Location(BaseModel):
    id: str
    name: str
    description: str
    connections: list[str]
    tags: list[str] = Field(default_factory=list)
    danger: int = Field(default=1, ge=1, le=3)
    move_cost: int = 5
    important: bool = False
    enemies: list[str] = Field(default_factory=list)
    train_trend: dict[str, int] = Field(default_factory=dict)
    unlock_flag: str | None = None  # 設定後，需該世界旗標成立才能前往


class Skill(BaseModel):
    id: str
    name: str
    slot: Slot
    style: Style = "無"
    power: int
    sect: str | None = None
    desc: str = ""


class Sect(BaseModel):
    id: str
    name: str
    location: str
    alignment: Literal["正", "邪", "中"]
    desc: str = ""
    starter_skills: list[str] = Field(default_factory=list)


class Enemy(BaseModel):
    id: str
    name: str
    desc: str = ""
    hp: int
    atk: int
    dfn: int
    spd: int
    style: Style = "無"
    reward_silver: int = 0


class Trend(BaseModel):
    id: str
    name: str
    desc: str = ""
    start: int = Field(default=0, ge=0, le=100)
    hidden: bool = False


class Threshold(BaseModel):
    id: str
    trend: str
    op: Literal[">=", "<="]
    value: int
    text: str
    world_flags_add: list[str] = Field(default_factory=list)
    ends_season: bool = False


class SimPlayer(BaseModel):
    name: str
    actions_per_day: float
    trend: dict[str, int] = Field(default_factory=dict)
    requires_revealed: str | None = None  # 這條隱藏線浮現之前不會行動
    rumors: list[str] = Field(default_factory=list)
    rumor_chance: float = 0.3


class Ending(BaseModel):
    id: str
    title: str
    text: str
    condition: Condition = Field(default_factory=Condition)


class Scenario(BaseModel):
    id: str
    name: str
    intro: str
    start_location: str
    trends: list[Trend]
    thresholds: list[Threshold] = Field(default_factory=list)
    sim_players: list[SimPlayer] = Field(default_factory=list)
    endings: list[Ending]


class Config(BaseModel):
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


class Content(BaseModel):
    config: Config
    scenario: Scenario
    locations: dict[str, Location]
    events: dict[str, Event]
    skills: dict[str, Skill]
    sects: dict[str, Sect]
    enemies: dict[str, Enemy]
