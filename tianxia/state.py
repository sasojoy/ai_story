"""執行期狀態：玩家、門下、世界。全部是可直接序列化成 JSON 的 Pydantic 模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import Content

PLAYER = "player"  # 門下資料裡代表玩家本人的 key


class Member(BaseModel):
    level: int = 1
    exp: int = 0
    neili: float | None = None  # None＝內力全滿
    innate_level: int = 1  # 同伴本命武學的成數（本人的本命記在 skills 裡）


class PlayerState(BaseModel):
    name: str
    location: str
    stats: dict[str, int]
    stamina: float
    flags: set[str] = Field(default_factory=set)
    sect: str | None = None
    skills: dict[str, int] = Field(default_factory=dict)  # 已習武學 → 成數
    members: dict[str, Member] = Field(default_factory=dict)  # 門下；PLAYER＝本人
    team: list[str] = Field(default_factory=list)  # 出戰隊伍，第一位是隊長
    loadouts: dict[str, list[str | None]] = Field(default_factory=dict)  # 每人兩格自選武學
    seen_events: set[str] = Field(default_factory=set)
    anonymous: bool = False
    busy_until: float | None = None  # 閉關結束的遊戲時間
    seclusion_start: float = 0.0
    tutorial_step: int = 0  # 等於引導步數時代表引導結束
    visited: set[str] = Field(default_factory=set)  # 去過的地點


class Rumor(BaseModel):
    time: float
    text: str
    location: str | None = None  # 發生地（地點 id）；江湖史、舊存檔與不在特定地點的傳聞為 None


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


class Fighter(BaseModel):
    name: str
    level: int


class Performance(BaseModel):
    """我方一人在這場的表現（只提供數據）。"""

    name: str
    damage: int  # 造成的傷害（戰報上的數字加總）
    controls: int  # 控制命中次數


class BattleRecord(BaseModel):
    """一場戰鬥（歷練或劇情戰）的紀錄。"""

    id: int  # 流水號，本季從 1 起算
    time: float  # 開打時的遊戲時間
    location: str  # 地點名稱
    kind: Literal["train", "event"]  # 歷練／劇情
    event: str = ""  # 劇情戰的事件標題
    opponent: str  # 敵方隊伍名稱
    ours: list[Fighter]  # 我方陣容，第一位是隊長；等級是開打時的等級
    theirs: list[Fighter]
    outcome: Literal["win", "draw", "lose"]
    rounds: int
    ending: str  # 結束原因（戰報最後一行）
    leader_ok: bool  # 我方隊長是否無恙
    moments: list[str] = Field(default_factory=list)  # 關鍵時刻，最多 3 則
    exp: int = 0  # 每人獲得的經驗
    xinde: int = 0
    silver: int = 0  # 正數為獲得、負數為失落
    notes: list[str] = Field(default_factory=list)  # 敘事文字：選項效果、升級、拜師、傳聞等（不是數字，見 changes）
    changes: list[str] = Field(default_factory=list)  # 其他數值變化，如屬性、名望、善惡名（經驗／心得／銀兩已有專屬欄位）
    report: list[str] = Field(default_factory=list)  # 完整逐回合戰報
    performance: list[Performance] = Field(default_factory=list)  # 我方每人表現，順序同 ours


class JournalEntry(BaseModel):
    """江湖紀錄的一則：玩家的一次行動，整理成給畫面看的樣子（原始訊息仍照舊寫在 GameState.log）。"""

    time: float  # 行動時的遊戲時間；舊存檔轉來的紀錄沒有時間，記為 journal.LEGACY_TIME
    title: str  # 例如「前往 揚州城」「歷練・揚州城郊」「酒樓鬥毆・上前勸架」
    tag: str = ""  # 簡短的結果，例如「遇上【酒樓鬥毆】」「擊退劫道山賊（4 回合）」「韓鐵出手・失敗」
    lines: list[str] = Field(default_factory=list)  # 敘事文字
    changes: list[str] = Field(default_factory=list)  # 數值變化，例如「銀兩 -5」「心得 +12」
    battle_id: int | None = None  # 這次行動打的那一場（BattleRecord.id）


class GameState(BaseModel):
    player: PlayerState
    world: WorldState
    pending_event: str | None = None
    battles: list[BattleRecord] = Field(default_factory=list)  # 最近的戰鬥紀錄，最新的在前
    battle_seq: int = 0  # 最近一場戰鬥的流水號
    battle_card: int | None = None  # 場景裡顯示卡片的那一場；下一次行動時清掉
    log: list[str] = Field(default_factory=list)  # 原始訊息，每次行動之間夾一個 journal.LOG_BREAK
    journal: list[JournalEntry] = Field(default_factory=list)  # 江湖紀錄，最新的在前，最多 journal.MAX_ENTRIES 則
    last_real: float | None = None  # 上次同步的現實時間（time.time()）


def new_game_state(content: Content, name: str) -> GameState:
    cfg = content.config
    trends = content.scenario.trends
    companions = list(cfg.start_companions)
    keys = [PLAYER] + companions
    player = PlayerState(
        name=name,
        location=content.scenario.start_location,
        stats=dict(cfg.start_stats),
        stamina=float(cfg.stamina_max),
        tutorial_step=0,
        members={key: Member() for key in keys},
        team=keys[:3],
        loadouts={key: [None, None] for key in keys},
    )
    world = WorldState(
        trends={t.id: t.start for t in trends},
        revealed={t.id for t in trends if not t.hidden},
        storyline=content.scenario.storylines[0].id,
    )
    return GameState(player=player, world=world)
