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


class Convoy(BaseModel):
    """身上押著的糧車（護糧，計畫 T6）：送到 to_loc 才算數。"""

    order: str  # 哪一道護糧軍令（Order.id）
    grain: int  # 交出去的糧草份量
    from_loc: str
    to_loc: str


class Summons(BaseModel):
    """收到的召見（計畫 T5、晉升文件第一節）：沒有期限；到了 location、演完那一階的奇遇才晉升。
    figure 是發召見那一刻出面的人（江湖紀錄寫他）；到了現場照當下再挑一次（ranks.presenter）。"""

    rank: int
    figure: str | None = None
    location: str
    since: float = 0.0


ONBOARDING_VERSION = 2  # 新手引導的版本：2＝有序章的新引導（新手引導計畫一）。比它小的是舊存檔，讀檔時當作走過序章（設計 7.2）


class PlayerState(BaseModel):
    name: str
    location: str
    stats: dict[str, int]
    stamina: float
    flags: set[str] = Field(default_factory=set)
    sect: str | None = None
    faction: str | None = None  # 投靠的陣營 id（Scenario.factions）；None＝散人
    pending_faction: str | None = None  # 按了「投靠某陣營」、還在確認畫面上的陣營 id
    pending_defect: str | None = None  # 按了「叛投某陣營」、還在確認畫面上的陣營 id（計畫甲）
    defected: bool = False  # 這一季叛投過了（第一季設計 5.1：一季最多一次）；角色每季重來，新的一季自然是 False
    member: Member = Field(default_factory=Member)  # 玩家本人的角色表

    # ── 同伴（sanguo-companions 合併重寫：全服唯一，見 world_state.py）──
    team: list[str] = Field(default_factory=list)  # 目前帶在身邊出戰的同伴 id，最多 MAX_TEAM_COMPANIONS 人
    affinities: dict[str, int] = Field(default_factory=dict)  # 人物 id -> 0~100 好感度，跟有沒有招到他無關
    relationship_notes: dict[str, str] = Field(default_factory=dict)  # 人物 id -> 一句話關係現況
    # 上一季的交情（第一季設計第十四節；正式版辛）：人物 id → 最近一次有聊過的那一季的關係筆記。換季時把
    # relationship_notes 搬過來（這一季的從頭寫），沒聊過的人物保留更早的那一句。只給模型當背景，畫面不顯示
    past_notes: dict[str, str] = Field(default_factory=dict)
    # 人物 id → dialogue_history 裡這一季的對話從第幾則開始（換季時記下當時的長度）；模型只看這一季的對話
    history_start: dict[str, int] = Field(default_factory=dict)

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
    art_levels: dict[str, int] = Field(default_factory=dict)  # 每門學過的功法各自的「成」；改練時存進來／取出來
    # ── 武學與成長（設計第三、四節）──
    insights: list[str] = Field(default_factory=list)  # 悟得的意境 id，照悟得的先後
    stat_points: int = 0  # 升級得到、還沒分配的屬性點（武學與成長設計 6.2）
    art_quality: dict[str, str] = Field(default_factory=dict)  # 功法 id → 自己那一份的品質（沒記＝全服登記的品質）
    art_mastery: dict[str, int] = Field(default_factory=dict)  # 功法 id → 修練往下一品失敗了幾次（熟練度）
    naming: str | None = None  # 第一個修到絕學、等著取正式名字的功法 id
    legend_items: int = 0  # 破境丹（Config.legend_item_name）的數量：探索撿到，玩家在修練頁勾了、衝絕學那一次才服一枚；角色每季重來

    seen_events: set[str] = Field(default_factory=set)
    # （舊的 event_seen 看過次數已拿掉：joy #16 的輪替取代了 FB-058 的 0.5^次數 遞減。舊存檔裡還有這一欄也讀得進來——
    # PlayerState 沒禁止多餘的欄位，讀的時候直接略過，下次存檔就不見了）
    # 防重複（events.pick_event 照它抽、events.note_round 在 Game._present 真的端出事件時才記）：池子（「地點:行動」或「*:行動」）→ 這一輪看過的事件 id，照看到的先後；輪完清空。
    # 舊存檔沒這欄就是每個池子都還沒看過；角色每季重來，所以每季自然清空
    event_rounds: dict[str, list[str]] = Field(default_factory=dict)
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
    guide_done: list[str] = Field(default_factory=list)  # 最近一次行動完成引導的那幾行（✔ 與獎勵），對話框顯示；下一次行動清掉
    guide_skipped: bool = False  # 按過「略過新手引導」：之後（含換季、第一季多出的步驟）都不畫對話框；步驟照樣記著
    guide_outro: bool = False  # 引導剛走完、結語還沒按「知道了」（對話框顯示結語）；略過的、早就做完的是 False
    onboarding: int = 0  # 這個角色的引導是照哪一版記的（ONBOARDING_VERSION）；舊存檔沒有這個欄位＝0
    visited: set[str] = Field(default_factory=set)  # 去過的地點
    fortune: bool = False  # 本季的新立門戶福緣已經發生（或已經改送賀禮）
    # 新手福利（氣血回復加倍、新立門戶福緣）從哪一刻起算（第一季設計第十四節「從自己加入的那天起算」）：這個角色進這一季時的
    # 賽季時間（世界秒）。新角色與換季重來的角色先是 None，第一次同步補算完賽季之後才蓋上（Game._stamp_join）——建角的那一刻
    # 賽季可能已經好幾個鐘頭沒人補算，那時就蓋會把福利白白吃掉一段。舊存檔沒有這一欄讀成 0.0：從季初算，跟以前一樣。
    # 只有第一季的規則開著才讀（roster.since_join）
    joined_at: float | None = 0.0

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
    convoy: Convoy | None = None  # 押著的糧車（計畫 T6 護糧）；None＝沒有。角色每季重來，跟著清空
    # ── 晉升（計畫 T5）；角色每季重來 ──
    rank: int = 0  # 晉升過的階；0 是還沒晉升過（有陣營時算第 1 階，見 ranks.rank_of）
    summons: Summons | None = None  # 還沒去的召見
    followers: list[str] = Field(default_factory=list)  # 部下（followers.json 的模板 id）

    # ── 大勢人物（計畫 T4、軍令文件 4.5）：剛被你打敗的人物 id → 到哪個「現實」時間（秒，Game.now）之前不見你、也不跟你交手。
    # 看現實時間、不看賽季時鐘（管理者快轉不會讓他提早見你）；角色每季重來，跟著清空 ──
    snubbed_until: dict[str, float] = Field(default_factory=dict)

    # ── 伏筆（計畫 T7、伏筆文件）；角色每季重來，跟著新角色清空（不在跨季保留的清單上）──
    fragments: dict[str, list[int]] = Field(default_factory=dict)  # 鏈 id → 聽過的片段（fragments 的索引）
    clue_items: dict[str, int] = Field(default_factory=dict)  # 伏筆專用物品 id → 數量
    fs_counters: dict[str, int] = Field(default_factory=dict)  # 隱藏計數：guanyin（官銀）、two_buyers（豪強兩頭賣糧的起點）
    fs_done: list[str] = Field(default_factory=list)  # 做完的鏈 id；多趟的鏈每做完一趟另記「鏈 id:第幾趟」（從 0 起）
    fs_cooldown_until: dict[str, float] = Field(default_factory=dict)  # 鏈 id → 答錯之後要等到哪個世界秒才能再做
    fs_asking: str | None = None  # 正在答最後一步的題的那條鏈；None＝沒在答（選單照常）
    fs_asked: int = 0  # 答到第幾題（0＝question，1 起是 then 的追問）

    # ── 機緣（正式版乙一、機緣文件）；角色每季重來，叛投時 opportunities.clear 清掉 ──
    opp_done: list[str] = Field(default_factory=list)  # 完成的機緣 id
    opp_counts: dict[str, int] = Field(default_factory=dict)  # 累積型：機緣 id → 記了幾次
    opp_items: dict[str, str] = Field(default_factory=dict)  # 機緣 id → 拿到、還沒交的東西（名字）
    opp_fronts: dict[str, str] = Field(default_factory=dict)  # 機緣 id → 那件東西要送去哪條戰線
    opp_clues: list[str] = Field(default_factory=list)  # 聽過線索的機緣 id
    # 失敗過、同一回（或同一曆日）不能再試的記號。鍵：天時地利型與推理型的指認是機緣 id（值是時段鍵／曆日）；拼圖的一樣東西是
    # 「機緣 id:東西 key」；密謀的一處是「plot:密謀 id:處的 key」（值都是曆日）
    opp_tried: dict[str, int] = Field(default_factory=dict)
    rank2_days: dict[int, int] = Field(default_factory=dict)  # 曆日 → 那天做了幾次第 2 階行動；只留今天
    # ── 機緣・乙二（拼圖、推理與集體密謀）；同樣每季重來、叛投時 opportunities.clear 清掉（opp_settled 例外，見 clear）──
    opp_pieces: dict[str, list[str]] = Field(default_factory=dict)  # 拼圖型：機緣 id → 已經拿到的東西的 key
    patron: str | None = None  # 靠山（晉升奇遇 4.2）：yuan、cao、self；計畫丙升第 3 階時寫入，叛投清掉
    opp_settled: list[int] = Field(default_factory=list)  # 結算過的集體密謀 id（只結算一次；換季跟著新角色清空）


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


class Plot(BaseModel):
    """一場集體密謀（機緣文件 1.1；正式版乙二）：全服共用，參與者各自回來時才結算（opportunities.settle）。
    一場密謀只有自己陣營的人看得到、做得了；一季結束整個賽季跟著換新，所以只增不減到季末（一人一次牽頭一場、
    每場最多 plot_days 個曆日，量不大）。"""

    # 這一季的密謀編號。選項 id（opp:join:<id>、opp:part:<id>）會原樣送到前端，所以不能是全服連號——連號的空缺會洩漏別的
    # 陣營發起過幾場、大約什麼時候（審查 I-1）。改由陣營、機緣、發起人與發起時刻（遊戲時間）的雜湊決定（opportunities.plot_id），
    # 一季之內不重複；從編號看不出別的陣營的任何事。opp_settled 也存這個編號
    id: int
    opp: str  # 機緣 id
    faction: str
    leader: str  # 發起人的名號
    # 寫在陣營軍情與響應選項上的名字：陣營內一律具名（企劃者 2026-10-06：只有地方傳聞匿名，同叛投與軍令的軍情），所以就是
    # 名號、不是顯示名（匿名的「某位少俠」會讓兩個匿名發起人的軍情與選項一模一樣，審查 I-2）
    shown: str
    members: list[str] = Field(default_factory=list)
    parts: dict[str, str] = Field(default_factory=dict)  # 那一處的 key → 誰做的
    deadline: float  # 世界秒
    status: Literal["open", "done", "failed"] = "open"


class Lock(BaseModel):
    """關鍵伏筆的鎖定（伏筆文件 2.4；T7 寫入，T2 結算時讀）。"""

    side: str  # 陣營 id
    name: str  # 名號（真名：時間軸的 locked_by、losers 與 T9 的稱號用它）
    time: float
    shown: str | None = None  # 公告與江湖史寫的名字：None＝寫名號（現在一律不記）；這一版之前匿名鎖定的是「某位少俠」，照舊


class FigureState(BaseModel):
    """大勢人物當下的樣子（計畫 T4；T2 先放最小版，時刻表結果改它）。"""

    prestige: int = 60
    status: Literal["active", "away", "retired", "crippled", "jailed"] = "active"  # 在場／未出場／退場／重創／下獄
    front: str | None = None  # 在推哪條戰線
    location: str = ""


class Order(BaseModel):
    """一道軍令（計畫 T6）：每週一發、期限到下週一。陣營的進度＝progress 加總；湊滿 quota 那一刻達成、套一次效果。
    text 是發的那一刻填好插槽的發布文字（主將之後換人也不改）。applied 是達成時實際推了戰況幾點（守城收回對方攻城的
    一半時讀它）。上週沒達成的在下週一清掉；達成的留到季末（守城看「敵方上週達成攻城」、整季模擬數軍令都讀它）。"""

    id: str
    template: str  # 種類（OrderTemplate.kind）；同一個陣營每種只有一筆模板
    faction: str
    week: int
    front: str | None = None  # 戰線（打擊是目標人物發令時所在的戰線）
    location: str | None = None  # 截糧的 {地點}、護糧的 {起點}、打擊時人物的所在
    start: str | None = None  # 護糧的 {起點}
    end: str | None = None  # 護糧的 {終點}
    figure: str | None = None  # 打擊的 {人物}
    quota: int
    text: str
    progress: dict[str, int] = Field(default_factory=dict)  # 名號 → 做了幾次
    shown: dict[str, str] = Field(default_factory=dict)  # 名號 → 軍情寫的名字（現在一律是名號；這一版之前匿名的記成「某位少俠」）
    done: bool = False
    done_time: float | None = None
    applied: int = 0


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
    ending_id: str = ""  # 收季時的結局 id（Ending.id）；舊存檔是空的
    # 第一季的結算畫面（計畫 T9）：收季那一刻的戰況（顯示中的每條線）與各陣營出力前五（名號, 貢獻；排行榜不能匿名）
    final_trends: dict[str, int] = Field(default_factory=dict)
    final_rankings: dict[str, list[tuple[str, int]]] = Field(default_factory=dict)
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
    third_party: dict[str, list[str]] = Field(default_factory=dict)  # 大事 id → 做完豪強伏筆的名號（真名）
    # 大事 id → {名號: 公告寫的名字}：這一版之前做完時匿名的豪強（「某位少俠」）；現在不再記，沒記的照名號寫
    third_party_shown: dict[str, dict[str, str]] = Field(default_factory=dict)
    event_mods: dict[str, float] = Field(default_factory=dict)  # 大事 id → 一般伏筆、軍令的成功率修正（合計夾在 ±0.20）
    event_bonus: dict[str, float] = Field(default_factory=dict)  # 大事 id → 時刻表結果帶來的修正（例：波才北上，不夾）
    schedule: dict[str, float] = Field(default_factory=dict)  # 決戰 id 與 "finale" → 世界秒；開季時填預設、管理者可改
    hooked_week: int = 0  # 週初的掛鉤（world.WEEK_HOOKS）已經跑到第幾週；0＝還沒跑過
    # ── 時刻表決戰開集結（計畫 T8）：季的事在 mutate 裡只記號，mutate 外面才開（world.open_waiting_showdown）──
    showdowns_waiting: list[str] = Field(default_factory=list)  # 時間到了、還沒開成的決戰 id，照時間先後（另一場還在打就等）
    showdowns_opened: dict[str, str] = Field(default_factory=dict)  # 開過集結的決戰 id → 開的那一筆 BattleDef；開過就不再開
    figures: dict[str, FigureState] = Field(default_factory=dict)  # 大勢人物 id → 聲威、狀態、所在（T4 開季時種）
    orders: list[Order] = Field(default_factory=list)  # 陣營軍令（計畫 T6）：這一週的，加上之前達成的
    plots: list[Plot] = Field(default_factory=list)  # 集體密謀（正式版乙二）：發起的、做完的、作罷的都留著到季末（編號是雜湊，見 Plot.id）
    # 升第 2 階的每日彙整（計畫 T5）：「曆日:陣營:階」→ 名號（陣營軍情一律具名）；過了那個曆日由季的事發成一則陣營軍情（傳聞只能新增，不能改）
    promoted_today: dict[str, list[str]] = Field(default_factory=dict)
    # ── 推力規則（計畫 T3）──
    trend_accum: dict[str, float] = Field(default_factory=dict)  # 不足一點的推力（全服共用，滿一點才真的推；正負會抵銷）：大勢線 id、"geju"、"fig:<人物 id>"（大勢人物每天的推動）、"prestige:<人物 id>"（挑戰打贏扣聲威不足一點的部分）
    active_pushers: dict[str, dict[str, float]] = Field(default_factory=dict)  # 陣營 id → 名號 → 最後一次推大勢的世界秒（人數緩衝用，過期的順手清掉）


class Fighter(BaseModel):
    name: str
    level: int


class LevelUps(BaseModel):
    """一場打完升級的人（FB-074）：「剛剛」的戰鬥卡片拿它畫一行簡短的「升到第 N 級」（battlelog.levelup_line），
    戰報頁與江湖紀錄照舊寫完整的句子。誰升到第幾級是結構化存下來的，不從句子的字裡讀回來。"""

    you: int | None = None  # 本人最後升到第幾級；本人沒升級是 None
    points: int = 0  # 本人升級之後還沒配的屬性點總數（那一刻的；畫卡片時改用現在的，見 levelup_line）
    mates: list[tuple[str, int]] = Field(default_factory=list)  # 升級的同伴（名字，最後升到第幾級），照隊伍順序
    lines: list[str] = Field(default_factory=list)  # 這一場寫進 notes 的升級句子原文（卡片不再重複，戰報頁照舊寫）


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
    rounds: list[str] = Field(default_factory=list)  # 回合演出，一回合一行（武學與成長設計 8.2）；決戰與舊戰報是空的
    # 大場面模型寫的過程（武學與成長設計 8.3）：照結果挑佔上風或落下風那一版；有就取代範本句子的回合（rounds 照樣算好）。
    # 叫 narration 不叫 story：battlelog 的 story_text／_story_block 已經是「結果」那一段（計畫三 G11）
    narration: str = ""
    guarded: bool = False  # 護命把落敗改判成僵持（武學與成長設計 13.4）；那一句演出寫在 notes 裡（跟 DODGE_NOTE 一樣，結果那一段）
    # 功效的演出句（13.6，content/trait_lines.json）：一句一行、前面標〔功效名〕，只在功效真的改到結果時才有（engine.Game._trait_lines）。
    # 放在「過程」裡回合（或大場面模型那一段）的前與後
    trait_before: list[str] = Field(default_factory=list)  # 開打前：先手、穩、破甲、險、連環、借力
    trait_after: list[str] = Field(default_factory=list)  # 受傷、結果出來、戰鬥外：化勁、厚、不動、乘勝、吸取、悟招、回春、輕身
    levelups: LevelUps | None = None  # 這一場有人升級才有（FB-074）；舊戰報沒有，卡片照 notes 原文


class JournalEntry(BaseModel):
    """江湖紀錄的一則：玩家的一次行動，整理成給畫面看的樣子（原始訊息仍照舊寫在 GameState.log）。"""

    time: float  # 行動時的遊戲時間；舊存檔轉來的紀錄沒有時間，記為 journal.LEGACY_TIME
    title: str  # 例如「前往 揚州城」「遊歷・揚州城郊」「酒樓鬥毆・上前勸架」
    tag: str = ""  # 簡短的結果，例如「遇上【酒樓鬥毆】」「擊退劫道山賊（4 回合）」「韓鐵出手・失敗」
    lines: list[str] = Field(default_factory=list)  # 敘事文字
    changes: list[str] = Field(default_factory=list)  # 數值變化，例如「銀兩 -5」「心得 +12」
    battle_id: int | None = None  # 這次行動打的那一場（BattleRecord.id）
    # 這次行動順便完成的新手引導（「✔ 引導完成」、獎勵、說書人的下一步）：江湖紀錄的列表照舊畫，「剛剛」卡片不畫——
    # 說書人的話改在行動列上方的對話框（引導重做設計 8.1）
    guide: list[str] = Field(default_factory=list)


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
    # 上次同步時的賽季時間（世界秒）：「你不在的時候」從這一刻之後算（Game._deliver_away）。None＝還沒記過（舊存檔、
    # 換季重來的角色），那一次從這一季開頭算
    last_world: float | None = None


def new_game_state(content: Content, name: str) -> GameState:
    """同伴全服唯一（設計文件四.4），開局不再自動塞給玩家任何一位——每個新玩家都是孤身
    一人起步，招募是要在遊戲裡真的去搶的行動，不是開局贈品（不然「唯一」第一時間就矛盾：
    每個新玩家都自動擁有同一位歷史人物是不可能的）。

    開局送 `Config.starter_skills` 的兩門基礎武學（第一成），新角色與每季重來的角色都一樣
    （武學與成長設計 3.3；自創武學已經作廢，沒有空欄位要自己取名）。"""
    from .rules import seed_trends  # rules → state：在函式裡 import，避免循環

    cfg = content.config
    player = PlayerState(
        name=name,
        location=content.scenario.start_location,
        stats=dict(cfg.start_stats),
        stamina=float(cfg.stamina_max),
        tutorial_step=0,
        # 有序章的內容才蓋新引導的章（新手引導計畫一）：沒有序章時步數還是舊編號，先蓋章會讓序章上線後的舊存檔跳過換算
        onboarding=ONBOARDING_VERSION if content.tutorial.location is not None else 0,
        member=Member(),
        joined_at=None,  # 第一次同步補算完賽季才蓋（Game._stamp_join）
    )
    for skill_id in cfg.starter_skills:  # 開局送的基礎內功、基礎武學（武學與成長設計 3.3）
        slot = "neigong_id" if content.skills[skill_id].kind == "內功" else "wugong_id"
        setattr(player.member, slot, skill_id)
    world = WorldState(storyline=content.scenario.storylines[0].id)
    seed_trends(world, content)
    return GameState(player=player, world=world)
