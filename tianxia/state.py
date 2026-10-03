"""執行期狀態：玩家、門下、世界。全部是可直接序列化成 JSON 的 Pydantic 模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import Content, TravelMode

PLAYER = "player"  # 沿用舊名，指玩家本人；同伴不再用 key 存在 PlayerState 裡（見下）


class Member(BaseModel):
    """玩家本人的角色表：等級/氣血/內功/武學。同伴不再用這個模型——他們全服唯一，等級/
    武學是共用資料（見 world_state.py::CompanionProgress），不是某個玩家存檔裡的副本。"""

    level: int = 1
    exp: int = 0
    neili: float | None = None  # 氣血，None＝回滿（滿＝上限 − 內傷）
    injury: float = 0.0  # 內傷：氣血自己只回到「上限 − 內傷」，要療傷才能清掉（氣血設計 §1.3）

    # 每人最多學一門內功、一門武學（設計文件六.4），id 指向 tianxia/martial_arts.py 的
    # MartialArt，可能是內容裡的固定武學（本命武學）也可能是玩家自創、存在共用世界狀態
    # 裡的武學。
    neigong_id: str | None = None
    neigong_level: int = 1  # 熟練度，第一成～第十成
    wugong_id: str | None = None
    wugong_level: int = 1


MAX_TEAM_COMPANIONS = 4  # 設計文件四.4：每位玩家最多帶 4 個夥伴，只有一支隊伍，沒有多隊派遣

Personality = Literal["積極", "普通", "懶散"]


class BotProfile(BaseModel):
    """伺服器假人的內部資料（伺服器假人設計第五節）：只存在存檔裡，畫面上任何地方都不顯示。
    faction／season_number：這一季被叫醒、替哪個陣營效力；season_number 跟全服賽季編號
    對不上（或 faction 是 None）就是退隱中，不上線（見 server_bots.active）。"""

    personality: Personality
    seed: int  # 作息、趕來參戰的擲骰都從這裡算，同一個假人永遠一樣
    faction: str | None = None
    season_number: int = 0


class Journey(BaseModel):
    """在路上（地圖擴充設計 3.3）：出發時排好的路線與每一站的抵達時間。時間記在賽季時鐘上（WorldState.time
    的遊戲秒數，跟閉關的 busy_until 一樣），sync／advance 推進時鐘之後補算抵達。"""

    mode: TravelMode
    path: list[str]  # 出發時排好的路線（不含出發地），最後一個是終點
    arrive_at: list[float]  # 每一站的抵達時間，跟 path 一一對應
    reached: int = 0  # 已經抵達幾站
    stop_at: int | None = None  # 喊停：走到 path 的第幾站（索引）就停；None＝走到終點

    @property
    def last(self) -> int:
        """這一趟最後要抵達的那一站（path 的索引）。"""
        return len(self.path) - 1 if self.stop_at is None else self.stop_at


class PlayerState(BaseModel):
    name: str
    location: str
    stats: dict[str, int]
    stamina: float
    flags: set[str] = Field(default_factory=set)
    sect: str | None = None
    faction: str | None = None  # 投靠的陣營 id（Scenario.factions）；None＝散人
    pending_faction: str | None = None  # 按了「投靠某陣營」、還在確認畫面上的陣營 id
    member: Member = Field(default_factory=Member)  # 玩家本人的角色表

    # ── 同伴（sanguo-companions 合併重寫：全服唯一，見 world_state.py）──
    team: list[str] = Field(default_factory=list)  # 目前帶在身邊出戰的同伴 id，最多 MAX_TEAM_COMPANIONS 人
    affinities: dict[str, int] = Field(default_factory=dict)  # 人物 id -> 0~100 好感度，跟有沒有招到他無關
    relationship_notes: dict[str, str] = Field(default_factory=dict)  # 人物 id -> 一句話關係現況

    # ── 深度對話（companion_agent.py，見設計文件四.3）── 這些是「這個玩家跟這位人物」的
    # 私有對話狀態，不是全服共用的（性情漂移才是全服共用，見 world_state.py）。
    pending_companion: str | None = None  # 目前正在對話中的人物 id；非 None 時 options() 顯示對話選項
    dialogue_history: dict[str, list[dict[str, str]]] = Field(default_factory=dict)  # 人物 id -> 最近對話（role/content）
    used_dialogue_options: dict[str, list[str]] = Field(default_factory=dict)  # 人物 id -> 說過的話（避免重複）
    last_offered_dialogue: dict[str, list[list[str]]] = Field(default_factory=dict)  # 人物 id -> [選項文字清單, 對應tag清單]
    turns_since_consolidation: dict[str, int] = Field(default_factory=dict)  # 人物 id -> 距離上次記憶梳理幾輪
    talks_today: dict[str, list[int]] = Field(default_factory=dict)  # 人物 id -> [第幾個遊戲日, 當天已聊幾輪]
    picking_audience: bool = False  # 按了「求見」、正在挑要拜會哪一位人物（兩位以上大勢人物的地點）；舊存檔沒這欄就是沒在挑

    # ── 煉製素材（無限煉製第一刀，見 tianxia/materials.py）──
    materials: dict[str, int] = Field(default_factory=dict)  # 素材 id -> 數量；舊存檔沒這欄就是空背包
    arts: list[str] = Field(default_factory=list)  # 功法庫：煉出來但沒配上身的功法 id
    art_levels: dict[str, int] = Field(default_factory=dict)  # 每門學過的功法各自的熟練度；改練時存進來／取出來

    seen_events: set[str] = Field(default_factory=set)
    mark_days: dict[str, int] = Field(default_factory=dict)  # 地方痕跡：這個人上次替這個痕跡算進一次是第幾天（一天只算一次；角色每季重來，跟著清空）
    anonymous: bool = False
    busy_until: float | None = None  # 閉關結束的遊戲時間
    seclusion_start: float = 0.0
    resting_since: float | None = None  # 打坐坐下時的賽季時間（遊戲秒）；None＝沒在打坐（地圖擴充設計第二節，跟閉關同一種做法）
    journey: Journey | None = None  # 在路上；None＝人在某個地點（location）
    tutorial_step: int = 0  # 等於引導步數時代表引導結束
    visited: set[str] = Field(default_factory=set)  # 去過的地點
    fortune: bool = False  # 本季的新立門戶福緣已經發生（或已經改送賀禮）

    # ── 共享賽季（跨玩家，見 world_state.py::SharedWorldState.season）────
    season_number: int = 1  # 這個玩家的角色屬於第幾季；跟共用賽季的編號對不上時，
    # Game._drop_stale_references() 會知道共用的賽季已經換過一輪，幫這個玩家的角色重開
    # 新的一季（好感度/關係現況保留，角色本身的等級/位置/隊伍重新開始，見設計討論）。
    bot: BotProfile | None = None  # 伺服器假人才有（伺服器假人設計第五節）；任何畫面都不能顯示或透露


RumorLayer = Literal["world", "faction", "local", "personal"]  # 天下大事／陣營軍情／地方傳聞／個人線索（傳聞分層設計第二節）


class Rumor(BaseModel):
    """一則傳聞，或一則江湖史（江湖史只用到 id、time、text、location）。"""

    time: float
    text: str
    location: str | None = None  # 發生地（地點 id）；江湖史、舊存檔與不在特定地點的傳聞為 None
    id: int | None = None  # 資料庫的流水號；None＝還沒寫進資料庫（存的時候新增一列，見 sqlite_world）
    layer: RumorLayer = "world"
    faction: str | None = None  # 陣營軍情：哪個陣營的人看得到
    region: str | None = None  # 發生地所在的大區（atlas.region_of）；地方傳聞照它給人看
    character: str | None = None  # 個人線索：只有這個名號看得到
    named: bool = True  # 具名；觸發者選了匿名（「某位少俠」）時是 False


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
    act_reached: int = 0  # 本季到過的最遠一幕；主線改寫會把 act 歸零，隊伍數與統御上限看這個（見 roster.stage）
    marks: dict[str, int] = Field(default_factory=dict)  # 地方痕跡：「地點 id:痕跡名」→ 累積次數（全服共用，換季整個重來）
    pending_battle: str | None = None  # 背景推進跨過開戰門檻時記下要開的戰鬥 id；那時人在 mutate_season 的
    # callback 裡，不能再 mutate 開戰（巢狀的 mutate 內層寫的會被蓋掉，會丟錯），callback 結束後由
    # world.start_pending_battle 開戰並清掉


class Fighter(BaseModel):
    name: str
    level: int


class BattleRecord(BaseModel):
    """一場遭遇/劇情戰的紀錄（sanguo-companions 合併重寫：單次判定，取代舊的逐回合戰報，
    見 tianxia/encounter.py）。"""

    id: int  # 流水號，本季從 1 起算
    time: float  # 開打時的遊戲時間
    location: str  # 地點名稱
    kind: Literal["train", "event"]  # 歷練／劇情
    event: str = ""  # 劇情戰的事件標題
    opponent: str  # 敵方隊伍名稱
    ours: list[Fighter]  # 我方陣容，第一位是隊長；等級是開打時的等級
    tier: str  # 大勝/險勝/僵持/落敗（encounter.EncounterResult.tier）
    our_power: float
    difficulty: float
    exp: int = 0  # 每人獲得的經驗
    xinde: int = 0
    silver: int = 0  # 正數為獲得、負數為失落
    materials: list[str] = Field(default_factory=list)  # 這一戰掉落的素材，已經是「精鐵砂 ×1」這樣的句子
    notes: list[str] = Field(default_factory=list)  # 敘事文字：選項效果、升級、拜師、傳聞等（不是數字，見 changes）
    changes: list[str] = Field(default_factory=list)  # 其他數值變化，如屬性、名望、善惡名（經驗／心得／銀兩已有專屬欄位）


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
    # 共用賽季：只在記憶體裡，不進角色存檔（線上架構設計 3.1）。Game 建構與每次 sync 都把它指向全服狀態裡的
    # 那一份（Game._reconcile_season）；舊存檔裡夾帶的 world 讀得進來，但隨即被取代。
    world: WorldState = Field(default_factory=WorldState, exclude=True)
    pending_event: str | None = None
    battles: list[BattleRecord] = Field(default_factory=list)  # 最近的戰鬥紀錄，最新的在前
    battle_seq: int = 0  # 最近一場戰鬥的流水號
    battle_card: int | None = None  # 場景裡顯示卡片的那一場；下一次行動時清掉
    log: list[str] = Field(default_factory=list)  # 原始訊息，每次行動之間夾一個 journal.LOG_BREAK
    journal: list[JournalEntry] = Field(default_factory=list)  # 江湖紀錄，最新的在前，最多 journal.MAX_ENTRIES 則
    last_real: float | None = None  # 上次同步的現實時間（time.time()）


def new_game_state(content: Content, name: str) -> GameState:
    """同伴全服唯一（設計文件四.4），開局不再自動塞給玩家任何一位——每個新玩家都是孤身
    一人起步，招募是要在遊戲裡真的去搶的行動，不是開局贈品（不然「唯一」第一時間就矛盾：
    每個新玩家都自動擁有同一位歷史人物是不可能的）。"""
    cfg = content.config
    trends = content.scenario.trends
    player = PlayerState(
        name=name,
        location=content.scenario.start_location,
        stats=dict(cfg.start_stats),
        stamina=float(cfg.stamina_max),
        tutorial_step=0,
        member=Member(),
    )
    world = WorldState(
        trends={t.id: t.start for t in trends},
        revealed={t.id for t in trends if not t.hidden},
        storyline=content.scenario.storylines[0].id,
    )
    return GameState(player=player, world=world)
