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
    # 在路上改道、折返（路上設計 3.1）：新路程從路中間出發，第一段走的是 origin—path[0] 那條路剩下的部分。
    # 舊存檔沒有這兩欄＝從 location 出發的一般路程。
    origin: str | None = None  # 第一段那條路的另一頭；None＝從 location 出發
    share: float = 0.0  # 出發時 origin—path[0] 那條路已經走掉的幾成（第一段只走剩下的）

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
    # 路上小事（路上設計第四節）：這一段路上已經做過的（road: 選項的 id 後半，例如 think）。到了另一站就清空；
    # 掉頭回到剛離開的那一站不算換段，所以不跟著那一趟 Journey 走，記在玩家身上（不然折返一下就能重做）。
    leg_actions: set[str] = Field(default_factory=set)
    surveyed: set[str] = Field(default_factory=set)  # 留意地形摸清的地點：大地圖上跟去過一樣算記得（atlas.location_view）
    recent_sights: list[str] = Field(default_factory=list)  # 最近看過的路上見聞 id（舊的在前）；挑的時候先排除（路上設計第五節）
    # 路上收穫的每天上限（企劃者 2026-10-03 決定）："task"（邊走邊想、路邊採集）／"sight"（路上見聞）->
    # [第幾個遊戲日, 當天已拿幾次]，跟 talks_today 同一種寫法；記的是前幾天就當沒拿過
    road_rewards_today: dict[str, list[int]] = Field(default_factory=dict)
    tutorial_step: int = 0  # 等於引導步數時代表引導結束
    visited: set[str] = Field(default_factory=set)  # 去過的地點
    fortune: bool = False  # 本季的新立門戶福緣已經發生（或已經改送賀禮）

    # ── 共享賽季（跨玩家，見 world_state.py::SharedWorldState.season）────
    season_number: int = 1  # 這個玩家的角色屬於第幾季；跟共用賽季的編號對不上時，
    # Game._drop_stale_references() 會知道共用的賽季已經換過一輪，幫這個玩家的角色重開
    # 新的一季（關係現況/對話紀錄保留、好感度只帶一成，角色本身的等級/位置/隊伍重新開始，見設計討論）。
    bot: BotProfile | None = None  # 伺服器假人才有（伺服器假人設計第五節）；任何畫面都不能顯示或透露
    # 處理過的收場決戰（BattleInstance.record_id）：自己參戰、已經補進江湖紀錄與戰報的，以及看過不是自己參戰的
    # （FB-027，見 Game._deliver_battle_results）。跨季保留：決戰常常把季收掉，下一季才回來的人也要補、而且只補一次
    battle_results_seen: list[int] = Field(default_factory=list)
    # 這一季已經補進江湖紀錄的時刻表大事 id（FB-038，見 Game._deliver_big_events）。大事 id 每季都一樣，
    # 所以這份每季重來：換季時新角色自然是空的（跟 battle_results_seen 不同，不跨季保留）
    events_seen: list[str] = Field(default_factory=list)

    # ── 推力與貢獻帳（計畫 T3、第一季設計第七節）；角色每季重來，跟著新角色清空 ──
    contrib: int = 0  # 本季替目前陣營推大勢記下的貢獻（散人不記）
    contrib_weeks: dict[int, int] = Field(default_factory=dict)  # 季曆第幾週 → 那一週記的貢獻
    pushed: dict[str, float] = Field(default_factory=dict)  # 「曆日:大勢線 id」→ 當天這條線推得動多少（人數緩衝之後）；只留今天與昨天

    # ── 捐獻紀錄（計畫 T6，軍備文件 4.1）：「據點 id:糧草」→ 累積的份量。T7 的伏筆只讀它；寫入是 T6 護糧的事 ──
    donations: dict[str, int] = Field(default_factory=dict)


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


class TimelineResult(BaseModel):
    """一件大事結算的結果（時刻表，計畫 T2）。key 是結果鍵（"成"、"甲:guan:大勝"…；跳過的是 timetable.SKIPPED）。"""

    key: str
    time: float  # 結算的世界秒
    locked_by: str | None = None  # 鎖定者的名號（江湖史、結算畫面的稱號依據）；沒人鎖定是 None
    losers: list[str] = Field(default_factory=list)  # 搶輸的人
    text: str = ""  # 公告全文（不含「【江湖大事】」）；跳過的是空的


class Lock(BaseModel):
    """關鍵伏筆的鎖定（伏筆文件 2.4；T7 寫入，T2 結算時讀）。"""

    side: str  # 陣營 id
    name: str  # 名號
    time: float


class FigureState(BaseModel):
    """大勢人物當下的樣子（計畫 T4；T2 先放最小版，時刻表結果改它）。"""

    prestige: int = 60
    status: Literal["active", "away", "retired", "crippled", "jailed"] = "active"  # 在場／未出場／退場／重創／下獄
    front: str | None = None  # 在推哪條戰線
    location: str = ""


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
    # ── 開季時蓋的章（計畫 T2「舊季不會被補算」）：world_state.stamp_season 照當下的 Config 寫入——種季、換季時蓋，
    # 籌備中的季在管理者開季時再蓋一次（第一次啟動忘了設 TIANXIA_PROFILE 也救得回來）──
    # 開關打開時還在跑的舊季照它自己的章走：不跑季曆與時刻表，也不會因為設定的季長變短就一口氣收掉。
    season_one: bool = False  # 這一季開季時第一季濃縮版的規則是不是開著
    length_days: float | None = None  # 這一季的長度（遊戲日）；None＝T2 之前開的季，一律照 models.DEFAULT_SEASON_DAYS（FB-037）
    # ── 時刻表（計畫 T2；鎖定、搶輸、豪強、一般伏筆修正由 T7 寫入）──
    timeline: dict[str, TimelineResult] = Field(default_factory=dict)  # 大事 id → 結算結果（有就不再結算）
    locks: dict[str, Lock] = Field(default_factory=dict)  # 大事 id → 第一個做完關鍵伏筆的人
    lock_losers: dict[str, list[Lock]] = Field(default_factory=dict)  # 大事 id → 之後才做完的人
    third_party: dict[str, list[str]] = Field(default_factory=dict)  # 大事 id → 做完豪強伏筆的名號
    event_mods: dict[str, float] = Field(default_factory=dict)  # 大事 id → 一般伏筆、軍令的成功率修正（合計夾在 ±0.20）
    event_bonus: dict[str, float] = Field(default_factory=dict)  # 大事 id → 時刻表結果帶來的修正（例：波才北上，不夾）
    schedule: dict[str, float] = Field(default_factory=dict)  # 決戰 id 與 "finale" → 世界秒；開季時填預設、管理者可改
    hooked_week: int = 0  # 週初的掛鉤（world.WEEK_HOOKS）已經跑到第幾週；0＝還沒跑過
    figures: dict[str, FigureState] = Field(default_factory=dict)  # 大勢人物 id → 聲威、狀態、所在（T4 開季時種）
    # ── 推力規則（計畫 T3）──
    trend_accum: dict[str, float] = Field(default_factory=dict)  # 大勢線 id → 不足一點的推力（全服共用，滿一點才真的推；正負會抵銷）
    active_pushers: dict[str, dict[str, float]] = Field(default_factory=dict)  # 陣營 id → 名號 → 最後一次推大勢的世界秒（人數緩衝用，過期的順手清掉）


class Fighter(BaseModel):
    name: str
    level: int


class BattleRecord(BaseModel):
    """一場遭遇/劇情戰的紀錄（sanguo-companions 合併重寫：單次判定，取代舊的逐回合戰報，
    見 tianxia/encounter.py）。kind 是 showdown 的是全服決戰補送給參戰者的那一筆（FB-027）：沒有我方威力與
    對手難度（記 0），tier 是決戰的結果（例如「官軍大勝」），side 是自己站的那一邊，見 battlelog 的畫法。"""

    id: int  # 流水號，本季從 1 起算
    time: float  # 開打時的遊戲時間（決戰是收場時的）
    location: str  # 地點名稱（決戰是大區名；上一季打的前面加「第 N 季・」）
    kind: Literal["train", "event", "wild", "showdown"]  # 遊歷／劇情／探索撞上的野怪／全服決戰（舊戰報的 train 不遷移，照舊顯示「遊歷」）
    event: str = ""  # 劇情戰的事件標題；決戰是決戰的名稱
    opponent: str  # 敵方隊伍名稱；決戰是敵方陣營名
    ours: list[Fighter]  # 我方陣容，第一位是隊長；等級是開打時的等級（決戰不記，是空的）
    tier: str  # 大勝/險勝/僵持/落敗（encounter.EncounterResult.tier）；決戰是結果的標題
    our_power: float
    difficulty: float
    side: str = ""  # 決戰時自己站的陣營名；其他 kind 是空字串
    exp: int = 0  # 每人獲得的經驗
    xinde: int = 0
    silver: int = 0  # 正數為獲得、負數為失落
    materials: list[str] = Field(default_factory=list)  # 這一戰掉落的素材，已經是「精鐵砂 ×1」這樣的句子
    notes: list[str] = Field(default_factory=list)  # 敘事文字：選項效果、升級、拜師、傳聞等（不是數字，見 changes）
    changes: list[str] = Field(default_factory=list)  # 其他數值變化，如屬性、名望、善惡名（經驗／心得／銀兩已有專屬欄位）


class JournalEntry(BaseModel):
    """江湖紀錄的一則：玩家的一次行動，整理成給畫面看的樣子（原始訊息仍照舊寫在 GameState.log）。"""

    time: float  # 行動時的遊戲時間；舊存檔轉來的紀錄沒有時間，記為 journal.LEGACY_TIME
    title: str  # 例如「前往 揚州城」「遊歷・揚州城郊」「酒樓鬥毆・上前勸架」
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
