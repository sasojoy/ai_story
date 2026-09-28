"""執行期狀態：玩家、世界、戰鬥。全部是可直接序列化成 JSON 的 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .models import Content

EQUIP_SLOTS = ("內功", "外功", "外功", "輕功")


class SkillProgress(BaseModel):
    level: int = 1
    exp: int = 0


class PlayerState(BaseModel):
    name: str
    location: str
    stats: dict[str, int]
    stamina: float
    flags: set[str] = Field(default_factory=set)
    sect: str | None = None
    skills: dict[str, SkillProgress] = Field(default_factory=dict)
    equipped: list[str | None] = Field(default_factory=lambda: [None] * len(EQUIP_SLOTS))
    seen_events: set[str] = Field(default_factory=set)
    anonymous: bool = False
    busy_until: float | None = None  # 閉關結束的遊戲時間
    seclusion_start: float = 0.0
    seclusion_skill: str | None = None
    tutorial_step: int = 0  # 等於引導步數時代表引導結束
    visited: set[str] = Field(default_factory=set)  # 去過的地點


class Rumor(BaseModel):
    time: float
    text: str


class WorldState(BaseModel):
    time: float = 0.0  # 賽季開始後經過的遊戲秒數
    trends: dict[str, int] = Field(default_factory=dict)
    revealed: set[str] = Field(default_factory=set)
    flags: set[str] = Field(default_factory=set)
    flag_times: dict[str, float] = Field(default_factory=dict)  # 世界旗標第一次成立的遊戲時間
    fired_thresholds: set[str] = Field(default_factory=set)
    rumors: list[Rumor] = Field(default_factory=list)
    chronicle: list[Rumor] = Field(default_factory=list)
    sim_accum: float = 0.0  # 累積但還不滿一小時的時間，給虛擬玩家用
    ended: bool = False
    ending_title: str = ""
    ending_text: str = ""
    storyline: str = ""  # 目前主線 id
    act: int = 0  # 目前第幾幕（從 0 起算）


class BattleState(BaseModel):
    enemy_id: str
    event_id: str
    choice_index: int
    player_hp: int
    player_hp_max: int
    enemy_hp: int
    round: int = 0
    ultimate_used: bool = False


class GameState(BaseModel):
    player: PlayerState
    world: WorldState
    pending_event: str | None = None
    battle: BattleState | None = None
    log: list[str] = Field(default_factory=list)
    last_real: float | None = None  # 上次同步的現實時間（time.time()）


def new_game_state(content: Content, name: str) -> GameState:
    cfg = content.config
    trends = content.scenario.trends
    player = PlayerState(
        name=name,
        location=content.scenario.start_location,
        stats=dict(cfg.start_stats),
        stamina=float(cfg.stamina_max),
        tutorial_step=0,
    )
    world = WorldState(
        trends={t.id: t.start for t in trends},
        revealed={t.id for t in trends if not t.hidden},
        storyline=content.scenario.storylines[0].id,
    )
    return GameState(player=player, world=world)
