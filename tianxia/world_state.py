"""全服狀態：所有玩家共讀共寫的一份資料（設計文件四.3／四.4／六.2）——資料模型與存取介面。

存的東西：
- **自創武學命名登記與煉製配方**：武學名稱同一季全服不能重名；配方的結果全服共享，第一個煉出來的人定義它。
- **同伴性情漂移**：歷史人物的「當下性情」是全服玩家共同形塑的；這裡只存 tag 累積計數與語意化後的一句話
  （把計數轉成一句話是 companion_agent.py 的事）。
- **同伴進度與招募狀態**：每位歷史人物全服唯一（設計文件四.4），等級／武學是人物本身的屬性，不是某個玩家
  存檔裡的副本；玩家存檔只留「我對這位人物的好感度」。
- **共享賽季**（大勢、門檻、主線、結局）、投靠名冊、全服決戰，以及跨季的傳國玉璽碎片。

怎麼存不在這個模組：`WorldStateStore` 是介面（線上架構設計第二、三節）。第 1 期的實作是
`sqlite_world.SqliteWorldStore`：每個會寫的方法自己是一筆交易，呼叫端在 action_lock() 裡時併進那一筆。
第 2 期的世界主迴圈會換成「記憶體裡一份＋每個動作寫進資料庫」，介面不變。
"""
from __future__ import annotations

import random
from collections.abc import Callable, Collection
from contextlib import AbstractContextManager
from typing import Any, Literal, NamedTuple, Protocol

from pydantic import BaseModel, Field, model_serializer, model_validator

from .battle_instance import BattleInstance, BattleRoundRecord, SiegeInfo
from .martial_arts import Insight, MartialArt
from .models import DEFAULT_SEASON_DAYS, BattleDef, Content
from .state import GearFind, Rumor, SignatureClaim, WeaponRecipe, WorldState
from .tactics import Bout, BoutSide

SeasonPhase = Literal["preparing", "running", "resting"]  # 籌備（管理者還沒開季）／進行中／休季（這一季已結束）

JADE_SEAL_FRAGMENT_COUNT = 7  # 設計文件九.2：七塊碎片＝跨季長線，不是單季目標


class JadeSealFragment(BaseModel):
    """跨季持久記錄的一塊傳國玉璽碎片（設計文件九）：找到後永遠留在這裡，不會因為任何
    玩家開新季、甚至之後換到別的季別劇本而被清掉——這正是「跨季」的字面意思。"""

    number: int  # 第幾塊（1~JADE_SEAL_FRAGMENT_COUNT），依找到的先後順序
    finder: str  # 找到的玩家名號
    season_name: str  # 當時是哪一季主題劇本找到的（例如「黃巾之亂」）
    text: str  # 給玩家看的一句話紀錄（通常取自觸發事件的 chronicle 文字）


class CompanionProgress(BaseModel):
    """一位歷史人物（可招募的 7 位）目前的等級/武學/招募狀態，全服共用一份。"""

    level: int = 1
    exp: int = 0
    neili: float | None = None  # 氣血，None＝回滿（滿＝上限 − 內傷）
    injury: float = 0.0  # 內傷，同 state.Member.injury
    neigong_id: str | None = None
    neigong_level: int = 1
    wugong_id: str | None = None
    wugong_level: int = 1
    owner: str | None = None  # 目前招募他的玩家名號；None＝自由之身，誰都能嘗試招募
    # 傳功（Config.chuangong）傳給他的屬性點：{"str": 3, "con": 1}，加在內容的起始值與每級成長上面（team.member_stats）。
    # 跟等級、武學成數一樣記在他身上：放走、被別人招去都帶著走（傳過的功是他學到的），換季跟其他進度一起清空
    taught: dict[str, int] = Field(default_factory=dict)
    # 歷史武將同行 9.6：決戰收場、他從誰身邊回江湖（escorts.after_battle 記）；那個人自己的 Game 同步或按招募之前把情誼減半、拿掉自己的名號
    parted_from: list[str] = Field(default_factory=list)


class SealEvent(BaseModel):
    """全服登記的一筆（玉璽碎片設計 13.2）：全服流水號 seq；補送（Game._deliver_seal_results）與江湖史都讀它。"""

    seq: int
    season: int
    # 不要往這裡加新的種類（FB-695）：舊程式的 kind 也是這一串 Literal，多一種，退回舊程式時整列 world 讀不進來（伺服器與假人程式都
    # 起不來）。新的紀錄另開一欄、空的時候不寫（例 SealRegistry.uses）；tests/seal/test_seal.py 守這一串跟舊程式一樣
    kind: Literal["emerge", "stir", "keep", "take", "sink", "unsettled", "assign", "recall", "scatter", "mandate"]
    shard: str | None = None
    holder: str | None = None  # 這一筆之後的持有者（take 是挑戰者；sink、收回是 None）
    other: str | None = None  # 對手（take 的失主、keep 的挑戰者）
    record: int | None = None  # 決戰的戰報流水號（BattleInstance.record_id）
    where: str = ""  # 哪一場決戰的陣前（SealDuel.where）：補戰報寫地點
    result: str | None = None  # 單挑的結果（挑戰者的角度）；沒打成是 None
    fresh: bool = False  # 持有者是照新角色算的（只寫進他自己的戰報，5.9）
    proxied: list[str] = Field(default_factory=list)  # 被代打過的那一邊（challenger／holder；只寫進那個人自己的戰報）
    absent: list[str] = Field(default_factory=list)  # 整場一手都沒自己出、全由代打的那一邊（FB-174：「未及趕到」只寫給他們）；舊資料沒有＝空
    at: float | None = None  # 單挑收場那一刻（這一季的世界秒，FB-175）：兩份戰報與紀錄都照它蓋時刻；舊資料沒有＝補送那一刻
    lines: list[str] = Field(default_factory=list)  # 單挑每回合一句（挑戰者的角度），補戰報用
    edge: float | None = None  # 單挑收場時的氣勢（挑戰者的角度）：持有者那份戰報照它分大勝、險勝；舊資料沒有＝None
    round: int | None = None  # 這一筆是第幾輪的（seal.log 寫；舊資料沒有＝第 1 輪）：江湖史七格只列這一輪
    holders: dict[str, str] = Field(default_factory=dict)  # mandate：天命之爭定下來那一刻每一片在誰手上（合璽之人）
    text: str = ""  # 江湖史那一句（沒有是空的）


class SealUse(BaseModel):
    """起用獨門行動的一筆（玉璽碎片改版第 2、3 批，Game.seal_use）：有名號，只給管理者看（設定頁玉璽那一組的 uses），江湖史七格與
    補送都不讀。FB-695 起記在 SealRegistry.uses，不放進 history（舊程式的 SealEvent.kind 不認得 "use"）。"""

    seq: int  # 全服流水號（跟 history 共用一串；舊資料搬過來照原號）
    season: int
    shard: str
    holder: str  # 起用的人
    act: str  # 哪一種（models.SealActKind；寫成 str：以後多一種行動，退回這一版也讀得進來）
    what: str = ""  # 指定了什麼（seal_acts.what_text；頒詔、承露是空的）
    at: float | None = None  # 起用那一刻（這一季的世界秒）


def _uses_out_of_history(data: object) -> object:
    """FB-695 以前的新程式把起用記在 history（kind "use"：holder 是起用的人、result 是哪一種、where 是指定了什麼）：讀進來時搬到
    uses（同一號只留一筆，照流水號排），history 不留 use。沒有這種舊紀錄的原樣回傳（一個位元組都不動）。"""
    if not isinstance(data, dict):
        return data
    history = data.get("history")
    if not isinstance(history, list) or not any(isinstance(e, dict) and e.get("kind") == "use" for e in history):
        return data
    old = [e for e in history if isinstance(e, dict) and e.get("kind") == "use"]
    have = list(data.get("uses") or [])

    def seq_of(u) -> int:
        return u["seq"] if isinstance(u, dict) else u.seq

    seqs = {seq_of(u) for u in have}
    moved = [
        {"seq": e["seq"], "season": e["season"], "shard": e.get("shard") or "", "holder": e.get("holder") or "",
         "act": e.get("result") or "", "what": e.get("where") or "", "at": e.get("at")}
        for e in old if e.get("seq") not in seqs
    ]
    return {**data, "history": [e for e in history if not (isinstance(e, dict) and e.get("kind") == "use")],
            "uses": sorted([*have, *moved], key=seq_of)}


class SealShard(BaseModel):
    id: str
    state: Literal["hidden", "held", "sunk"] = "hidden"  # 未現世／有主／隱沒
    holder: str | None = None  # 名號；比對用 characters.name_key（seal.key）
    since_season: int | None = None  # 到手的季（新主保護）
    stirred_season: int | None = None  # 最近一次璽動的季（每片每季最多一次）
    emerged_round: int | None = None  # 這一輪現世過沒（天命的觸發看它，玉璽二）
    former: str | None = None  # 上一個從這一片被奪走的人（追璽）
    absent: int = 0  # 持有者連續幾季沒上線（換季時數，PM 庚；隱沒看它）
    # 獨門行動（玉璽碎片改版第 2 批）：次數記在碎片上、跟著碎片走（同一季被搶走，新主人只剩還沒用掉的次數）。
    # act_season 不是這一季就當這一季還沒用過（換季自然歸零）；act_last 是上一次起用的世界秒（那一季的）
    act_season: int | None = None
    act_uses: int = 0
    act_last: float | None = None


class SealCache(BaseModel):
    """領地爭奪的季，這一季藏在中立地的那一片（領地爭奪設計 3.9、4.8；seal.hide）。藏在哪一塊不公開：沒有任何畫面、API、江湖史讀它，
    只有探索撿碎片（Game._seal_find）與管理者的「現在藏一片」讀。季末沒撿到就在換季時清掉。"""

    season: int
    shard: str
    loc: str


class SealRegistry(BaseModel):
    """碎片歸屬的正本（玉璽碎片設計 7.4、13.2）：world 那一列的 JSON，不分季、跨季保存。"""

    shards: dict[str, SealShard] = Field(default_factory=dict)  # 內容的七片；登記沒有的由 seal.filled 補上
    round: int = 1
    seq: int = 0
    opened_real: float | None = None  # 這一季開季的現實時間（「這一季上線過」、隱沒）；None 一律當上線過
    salt: str = ""  # 亂數的密鹽（5.13）；伺服器與假人程式啟動時產生（測試與腳本是空的），不顯示、不進指紋
    emerge_season: int | None = None  # 這一季已經現世過（一季最多一片）
    force_emerge: str | None = None  # 管理者：下一場標 emerge 的決戰必定現世（"*" 照亂數挑，或指定哪一片）
    force_stir: str | None = None  # 管理者：下一場標了 seal 的決戰必定牽動這一片（略過 7%、新主保護與次數上限）
    last_showdown: int | None = None  # 這一季最近一場收場的時刻表決戰（戰報流水號）：管理者的強制開單挑只能掛在它上面
    last_showdown_dueled: bool = False  # 上面那一場已經開過單挑
    last_showdown_where: str = ""  # 上面那一場的名字（BattleDef.name）：管理者開的單挑公告照它寫
    mandate_season: int | None = None  # 最近一次蓋上天命之季的季別（seal.mandate_now 看它；WorldState.mandate 同時蓋）
    mandate_pending: bool = False  # 下一個能打天命之爭的季要蓋章（上一次延後、或管理者「下一季」）
    cache: SealCache | None = None  # 領地爭奪的季，這一季藏著的那一片（不公開；舊資料沒有＝None）
    history: list[SealEvent] = Field(default_factory=list)
    # 起用獨門行動的帳（FB-695；seal.log_use 寫）：另記一欄，舊程式的登記模型不認得、讀的時候略過（pydantic 預設），退回舊程式開得起來
    # （舊程式寫回時這一欄會丟掉）。空的時候不寫進 JSON（_drop_empty_uses）：沒人起用過的存檔跟以前一個位元組都不差
    uses: list[SealUse] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _move_uses(cls, data: object) -> object:
        return _uses_out_of_history(data)

    @model_serializer(mode="wrap")
    def _drop_empty_uses(self, handler):
        """uses 是空的時候不寫這個鍵（同 BattleInstance._drop_empty_front_note）。不用 Field(exclude_if=…)：那是 Pydantic 2.11 才有的，
        requirements.txt 寫 pydantic>=2.6，舊版會把它當多餘的參數略過，`"uses":[]` 照樣寫出來、存檔就跟以前不一樣。"""
        data = handler(self)
        if isinstance(data, dict) and "uses" in data and not data["uses"]:
            del data["uses"]
        return data


class DivineRegistry(BaseModel):
    """神器輪替與收集的全服登記（正式季整合 5.6、10.4；第 10 批，tianxia/divine.py）：world 那一列的 JSON，不分季、跨季保存（同玉璽碎片）。"""

    seen: list[str] = Field(default_factory=list)  # 這個伺服器現世過的神器配方 id（照第一次現世的先後）；空的＝還沒照這套規則開過季
    finds: dict[str, GearFind] = Field(default_factory=dict)  # 配方 id → 原品那一筆（主人、定名、全服仿品數、第幾季打出）；只算輪替季打的
    exhausted: int | None = None  # 新神器用完了的那一季（主控台與管理者的回話提醒）


class SealSide(BaseModel):
    """奪璽單挑的一方：身手全是快照（5.3），不回頭讀存檔。"""

    name: str
    faction: str | None = None
    power: float = 0.0
    scores: dict[str, float] = Field(default_factory=dict)  # 三招的份量（拿掉了騎兵與部下，要 PM 定的第 4 條）
    role: str = ""
    hp: float
    hp_cap: float
    last_seen: float | None = None  # 現實秒：最近一次自己推這場單挑（真人自己的請求才記、每 seen_write_seconds 秒最多寫一次；假人不記）
    present: bool = False  # 這一回合開始時判他在場沒（判成不在場，這一回合的鈕灰掉）
    fresh: bool = False  # 照新角色算的（只寫進他自己的戰報）
    gambles: int = 0  # 這一場放手一搏了幾次（Config.seal.gamble_cap）
    proxied: bool = False  # 這一場被代打過
    acted: int = 0  # 這一場自己出了幾手（含放手一搏；FB-174：一手都沒出才是「未及趕到」）
    kit: BoutSide | None = None  # 身上的本命戰法快照（不算坐騎與部下，同頭目戰）；沒有是 None


class SealDuel(BaseModel):
    """一場奪璽單挑（玉璽碎片設計第五節）：存在 SharedWorldState.seal_duels（全服、不在季裡，5.12）。氣勢一律是挑戰者的角度。"""

    id: str  # f"{決戰戰報流水號}:{碎片 id}"；管理者不掛決戰開的是 f"qa{seq}:{碎片 id}"
    shard: str
    record: int | None = None
    event_id: str | None = None
    where: str = ""  # 哪一場決戰的陣前（BattleDef.name；公告與戰報寫「在長社火攻陣前」）；管理者不掛決戰開的是空的
    tier: str = "旁觀"  # 持有者那一方打得怎樣（seal.tier_for）
    phase: Literal["muster", "active"] = "muster"  # 收場的不留在清單裡（記進 history）
    starts_real: float
    challenger: SealSide
    holder: SealSide
    edge: float = 50.0
    round: int = 0  # 已經結算了幾回合
    rounds: int = 5
    cap: float = 0.25  # cap × 局勢 × 護璽（開打時算好）
    pending: dict[str, str] = Field(default_factory=dict)  # 這一回合誰出了什麼：招，或 "text"（放手一搏）
    rates: dict[str, int] = Field(default_factory=dict)
    texts: dict[str, str] = Field(default_factory=dict)
    stories: dict[str, list[str]] = Field(default_factory=dict)  # 邊 → ［成功版, 失敗版］
    proxy_move: dict[str, str] = Field(default_factory=dict)  # 回合開始時替不在場的那一邊預擲的招
    tell: dict[str, str] = Field(default_factory=dict)  # 代打那一邊給對手看的架勢
    opened_real: float | None = None  # 這一回合開始的現實秒
    lines: list[str] = Field(default_factory=list)
    fixed: bool | None = None  # 管理者「定這一場結果」：再擲中（True）或不中（False）；None 照擲
    bout: Bout | None = None  # 兩邊的本命戰法（tactics.Bout，a 是挑戰者）；兩邊都沒有是 None


class SortieSide(BaseModel):
    """出陣約戰的一方（減法季整合設計 4.3；tianxia/sortie_duel.py）：封招那一刻的快照，結算時不回頭讀存檔。"""

    name: str
    side: str  # 替哪一軍打（allied.side_of：豪強是依附的那一軍）
    power: float = 0.0  # 封招那一刻的威力（呼叫端照 Game._spar_power 算好）
    moves: list[str] = Field(default_factory=list)  # 封好的三招（Config.sortie.moves）
    sealed_at: float = 0.0  # 現實秒：封招那一刻（補位的人是窗內隨機的一刻；卡與戰報都不寫）
    region: str | None = None  # 封招那一刻站在哪一個大區（atlas.region_of 的 id）
    allies: list[str] = Field(default_factory=list)  # 攻方才有：同去的同袍（集火由接線那一批照 conquest.focus_bonus 算）
    garrison: bool = False  # 守軍迎戰（這一邊連補位的人都沒有）


class SortieRound(BaseModel):
    """約戰的一回合（sortie_duel.resolve）：兩邊的招、相剋、攻方乘過相剋的威力、單次判定的結果（攻方的角度）、誰贏、兩邊扣的比例。"""

    attacker_move: str
    defender_move: str
    beat: int = 0  # tactics.counter（攻方剋守方 +1、被剋 −1；有人撤退是 0）
    power: float = 0.0
    tier: str = ""  # encounter.resolve_encounter 擲出來的（有人撤退的回合也擲，記下來但不用）
    winner: Literal["attacker", "defender", "draw"] = "draw"
    attacker_toll: float = 0.0  # 這一回合扣氣血上限的幾成
    defender_toll: float = 0.0


class SortieResult(BaseModel):
    """一場約戰的總帳（計畫寫的 DuelResult）：攻方贏、輸、僵持幾回合，結果（big／win／draw／lose，攻方的角度；守方那一份 defender_tier），
    三回合合計扣氣血上限的幾成。推（拉）多少、內傷、冷卻、戰報由接線那一批照它算。"""

    wins: int = 0
    losses: int = 0
    draws: int = 0
    tier: Literal["big", "win", "draw", "lose"] = "draw"
    defender_tier: Literal["big", "win", "draw", "lose"] = "draw"
    rounds: list[SortieRound] = Field(default_factory=list)
    attacker_toll: float = 0.0
    defender_toll: float = 0.0


class SortieDuel(BaseModel):
    """一張出陣約戰（減法季整合設計 4.3）：存在 SharedWorldState.sorties（全服；換季清掉）。時刻一律是現實秒（Game.now）。
    open（貼了、等人應戰）→ answered（對面有人應了）→ 窗滿 settled（結算了）；到時連守軍都沒有、或季已經結束是 void（沒打成）。"""

    id: str
    block: str  # 哪一塊（地點 id）
    region: str | None = None  # 那一塊在哪一個大區（限同一區才應得了戰）；地圖沒有大區是 None（不限）
    place: str = ""  # 地點的名字（卡上寫；貼的那一刻抄下來）
    region_name: str = ""  # 大區的名字（「在潁川汝南才應得了戰」）
    attacker: SortieSide
    defender: SortieSide | None = None
    garrison: SortieSide | None = None  # 貼的那一刻抄好的這一塊的駐軍：到時沒人應戰、補位也沒人時迎戰
    opened_at: float
    expires_at: float
    status: Literal["open", "answered", "settled", "void"] = "open"
    settled_at: float | None = None
    result: SortieResult | None = None
    report: dict[str, Any] = Field(default_factory=dict)  # 接線那一批放戰報流水號、送達了沒這類


class SealView(NamedTuple):
    """seal_state() 讀回來的一份（只讀 world 那一列的 JSON，不讀季）。"""

    registry: SealRegistry
    duels: list[SealDuel]
    season: int
    tianji: int
    paused: bool


class SharedWorldState(BaseModel):
    companion_tag_counts: dict[str, dict[str, int]] = Field(default_factory=dict)  # 人物 id -> {tag: 次數}
    companion_drift_note: dict[str, str] = Field(default_factory=dict)  # 人物 id -> 目前漂移後的一句話性情
    companion_drift_synthesized_at: dict[str, int] = Field(default_factory=dict)  # 人物 id -> 上次語意化時的 tag 總數
    companions: dict[str, CompanionProgress] = Field(default_factory=dict)  # 人物 id -> 進度/招募狀態
    event_flavor: dict[str, str] = Field(default_factory=dict)  # 江湖大事 id -> 全服共用的一次性潤色句（設計文件 8.2 第 4 點）
    jade_seal_fragments: list[JadeSealFragment] = Field(default_factory=list)  # 跨季持久（設計文件九.2）

    # ── 共享賽季（真正共享的大勢/門檻/主線/結局，取代原本每個玩家各自獨立的 WorldState）──
    # 上面那些欄位不跟著 season 整個換掉，但換季時同伴進度會照「跨季不滾雪球」清空，玉璽碎片等才是
    # 永遠留著；武學命名、煉製配方、投靠名冊每季各一份（存在各自的表裡，見 sqlite_world），換季自然是空的。
    # season 本身每次開新賽季會被整個換掉（見 next_season）。season_number 從 1 起算，
    # season_last_real 是這個賽季的共用時鐘上次對到現實時間的時間點（None＝還沒對過）。
    season: WorldState = Field(default_factory=WorldState)
    season_number: int = 1
    season_last_real: float | None = None
    season_opened: bool = False  # 這一季管理者開季了沒；False＝籌備中（見 season_phase）
    # 賽季時鐘暫停（線上架構設計第四節、8.3「公告停機時賽季時鐘暫停，季末跟著往後延」）：按「暫停」的現實時間；None＝沒有暫停。
    # 暫停中補算（catch_up_season）不推季的時間、對時點也不動；引擎（Game）不推決戰、選單只剩一顆灰的、不能快轉，
    # 管理者的動作只留「繼續」；伺服器擋住不走選單的動作（server._refuse_while_paused）、假人程式不出手；
    # 按「繼續」時對時點往後挪停的長度（resume_clock），進行中的決戰期限與排好的決戰也跟著挪，
    # 所以停的這一段不算進賽季。舊資料沒有這一欄＝沒有暫停
    paused_at: float | None = None
    tianji: int = 0  # 天機：每次換季 +1，自創武學「名字 → 數值」的配方跟著換（跨季不滾雪球第三條）
    # ── 玉璽碎片（玉璽碎片設計 7.4、5.12）：全服、不分季，跟 season 一樣存在 world 那一列的 JSON 裡 ──
    seal: SealRegistry = Field(default_factory=SealRegistry)
    divine: DivineRegistry = Field(default_factory=DivineRegistry)  # 神器輪替與收集（正式季整合 10.4）：全服、不分季
    seal_duels: list[SealDuel] = Field(default_factory=list)  # 還沒收場的奪璽單挑，第一場在打、其餘排隊（玉璽一一次最多一場）
    # ── 名帖的檢舉（tianxia/mingtie.py）：全服、不分季 ──
    mingtie_reports: dict[str, list[str]] = Field(default_factory=dict)  # 「名號鍵|版本」→ 檢舉的人（名號鍵）
    mingtie_removed: dict[str, int] = Field(default_factory=dict)  # 名號鍵 → 管理者撤下到第幾版（這一版以前的都不畫，名帖匣裡收著的也是）
    mingtie_cleared: list[str] = Field(default_factory=list)  # 管理者看過、放回去的（「名號鍵|版本」）：檢舉再多也照畫

    # ── 全服即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步）────────
    # 同一時間最多一場（先簡化成這樣；真的需要同時好幾場再擴充成 list/dict）。
    active_battle: BattleInstance | None = None
    # 攻城戰（領地爭奪第二批）：跟決戰、別的攻城戰同時打，另存一串。每一場跟決戰一樣是 battles 表的一列，world 那一列的 JSON 只記
    # 流水號（siege_records，存檔時照 sieges 寫）；資料庫結構不動。收場、季終收兵之後拿掉（ended_battles 照樣讀得到那一列）
    sieges: list[BattleInstance] = Field(default_factory=list)
    siege_records: list[int] = Field(default_factory=list)
    # 出陣約戰（減法季批 3b，tianxia/sortie_duel.py）：id → 那一張；還沒結算的與結算完還留著的（keep_hours）。全服、換季清掉（next_season）。
    # 空的時候 world 那一列的 JSON 不寫這個鍵（_drop_empty_sorties）：關著的季、沒人約過戰的存檔跟以前一個位元組都不差
    sorties: dict[str, SortieDuel] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def _drop_empty_sorties(self, handler):
        """sorties 是空的時候不寫這個鍵（同 SealRegistry._drop_empty_uses；不用 Field(exclude_if=…)：Pydantic 2.11 才有）。"""
        data = handler(self)
        if isinstance(data, dict) and "sorties" in data and not data["sorties"]:
            del data["sorties"]
        return data

    def season_phase(self) -> SeasonPhase:
        if not self.season.storyline or not self.season_opened:
            return "preparing"
        return "resting" if self.season.ended else "running"


def fresh_season(content: Content, now: float | None = None) -> WorldState:
    """照劇本種出一季全新的共用賽季（大勢起始值、公開的大勢線、第一條主線），並蓋上當下的章（stamp_season）。
    seed_first_season、next_season 都走這裡；籌備中的季在管理者開季時再蓋一次（open_season）。now 是開季那一刻（現實 epoch 秒），
    21 天季照它算季曆的錨點（stamp_season）；種季（籌備中）時不知道，不給。"""
    from .rules import seed_trends  # rules → world_state：在函式裡 import，避免循環

    season = WorldState(storyline=content.scenario.storylines[0].id)
    stamp_season(season, content, now=now)  # 先蓋章：種哪些大勢線看這一季的章（rules.seed_trends）
    seed_trends(season, content)
    return season


def stamp_season(season: WorldState, content: Content, now: float | None = None) -> None:
    """把當下的開關與季長蓋章在這一季上（計畫 T2「舊季不會被補算」）：之後換了設定，這一季照它自己的章走。
    開關開著時順便填決戰與季末的預設時間（管理者開季後可以改，T10）。只在季還沒開始時呼叫：種季、換季、開季。
    21 天季（Config.season21）另蓋季曆的錨點：now（開季那一刻的現實 epoch 秒）給了才算，不然是 0（第 1 週週一 00:00 就是開季那一刻）；
    要先蓋錨點再排決戰與季末（正式季整合設計 1.1）。"""
    from .figures import seed  # noqa: PLC0415  延後 import：figures → rules → world_state
    from .timetable import default_schedule  # noqa: PLC0415  延後 import：timetable → rules → world_state

    cfg = content.config
    season.season_one = cfg.season_one
    season.length_days = cfg.season_days
    from .calendar import anchor_offset  # noqa: PLC0415  延後 import：calendar → world_state
    season.season21 = cfg.season21
    season.precise_actions = cfg.precise_actions  # 一類一顆（正式季整合第二章、12.3 第 13 條）：照開季蓋章，正在跑的季不變
    season.cal_offset = anchor_offset(now, content) if cfg.season21 and now is not None else 0.0
    season.haoqiang_allied = cfg.season_one and cfg.haoqiang_allied  # 豪強分屬兩軍（企劃者 2026-10-15）：只在第一季的季（allied.on）
    season.jianfa_on = cfg.jianfa.enabled  # 減法季（Config.jianfa）：season21、week7 開，週末不開；正在跑的季不變（rules.jianfa）
    season.schedule = default_schedule(content, season) if cfg.season_one else {}  # 照剛蓋好的季長排
    # 素材與經濟（企劃者 2026-10-15）：神器配方的條數與線索分片從下一季開季起照這個章（正在跑的季沒有＝照舊）
    season.forge_divine_per_kind = cfg.forge_secrets.divine_per_kind
    season.forge_split_clues = cfg.forge_secrets.split_clues
    # 名聲（企劃者 2026-10-15）：門檻乘季長倍數從下一季開季起照這個章（正在跑的季沒有＝倍數 1，renown.scale）
    season.renown_scale = length_factor(season, content) if cfg.renown.titles and cfg.renown.scale else None
    # 名聲 5.1：正邪武學開著時綠林山寨開寨（它的 unlock_flag）；關著時不立，山寨不畫、去不了。正在跑的季由 world._open_greenwood 補
    from .renown import GREENWOOD_FLAG  # noqa: PLC0415  renown 只延後 import world_state，這裡也延後，兩邊都不在載入時牽動
    if cfg.renown.titles and cfg.renown.lessons:
        season.flags.add(GREENWOOD_FLAG)
        season.flag_times.setdefault(GREENWOOD_FLAG, season.time)
    else:
        season.flags.discard(GREENWOOD_FLAG)
        season.flag_times.pop(GREENWOOD_FLAG, None)
    season.figures = {}
    if cfg.season_one:  # 大勢人物照人物表種好（T4）：時刻表的 only_if、伏筆的出面人物從第一刻起就看得到每一位
        seed(season, content)


def season_length_days(season: WorldState, content: Content) -> float:
    """這一季有幾個遊戲日：照開季時蓋的章；T2 之前開的季沒有章，一律照它開季時的長度（DEFAULT_SEASON_DAYS，
    那些季都是用預設設定開的），不跟著現在載入的設定走——換成週末設定的 2.5 天也不會把它收掉（FB-037）。"""
    return season.length_days if season.length_days is not None else DEFAULT_SEASON_DAYS


def length_factor(season: WorldState, content: Content) -> float:
    """季長倍數（名聲設計 2.4；決戰道具 2.2 的「一份」用同一個數，rules 轉出去叫 rules.length_factor）：
    max(1, 這一季蓋章的季長 ÷ Config.drill_push_base_days)。週末季 1、7 天 2.8、14 天 5.6、30 天 12；就是 Game.season_scale 的倒數。"""
    days = season_length_days(season, content)
    base = content.config.drill_push_base_days
    return max(1.0, days / base) if base > 0 else 1.0


def jade_seal_summary(fragments: list[JadeSealFragment]) -> str:
    if not fragments:
        return "傳國玉璽的七塊碎片，至今尚無人尋獲過一塊。"
    lines = [f"傳國玉璽：{len(fragments)}/{JADE_SEAL_FRAGMENT_COUNT} 塊碎片已現世——"]
    lines += [f"　第 {f.number} 塊：{f.finder}（{f.season_name}）{f.text}" for f in fragments]
    return "\n".join(lines)


class WorldStateStore(Protocol):
    """全服狀態的存取介面。引擎只認這個介面，實作見 sqlite_world.SqliteWorldStore。

    交易：每個會寫的方法自己就是一筆交易（讀→改→寫回一起成功或一起撤回）；呼叫端在 action_lock()
    裡時，併進那一筆。「補算時間＋做動作＋存檔」整段一律包在 action_lock() 裡（server.py、假人程式）。"""

    def action_lock(self, timeout: float | None = None) -> AbstractContextManager[object]:
        """一個動作＝一筆交易（線上架構設計 3.1）。timeout=None 等到拿到為止（伺服器）；給秒數時等不到就丟
        TimeoutError（假人程式跳過這一輪，不卡住正在等 LLM 的真人）。出錯時整個動作一起撤回。可以巢狀。"""
        ...

    def read(self) -> SharedWorldState: ...

    def mutate(self, fn: Callable[[SharedWorldState], None]) -> SharedWorldState:
        """讀取→套用 fn(state)→寫回，同一筆交易，回傳套用後的狀態。fn 直接原地修改 state。
        fn 裡面不能再呼叫會寫入的 store 方法（mutate、mutate_season、mutate_battle、update_companion 等）：
        內層寫的會被外層最後的整份存檔蓋掉，實作遇到巢狀會直接丟 RuntimeError。交易本身（action_lock）可以巢狀，
        不可以的只有 mutate 這一類「整份讀、整份寫」的區段。"""
        ...

    # ── 武學命名登記與煉製配方（這一季）──
    def get_skill(self, name: str) -> MartialArt | None:
        """這一季登記過的自創或煉製功法（自創功法的 id 就是它的名字）；沒有就是 None。"""
        ...

    def is_skill_name_taken(self, name: str) -> bool: ...

    def is_character_name(self, name: str) -> bool:
        """name 是不是江湖上某個角色的名號（真人、假人一樣，不分大小寫、不管前後空白，同 characters.name_key）。
        給命名過濾用（FB-069：武學、意境不能取成角色的名號）；只回是或不是，不透露那個角色是不是假人。"""
        ...

    def claim_skill_name(self, art: MartialArt) -> bool:
        """把 art 登記成這一季的自創武學；名字已經有人用過就不登記。回傳有沒有登記成功（原子判斷，
        不會有兩個玩家同時取到同一個名字都成功）。"""
        ...

    def lookup_recipe(self, key: str) -> MartialArt | None:
        """這個配方這一季已經有人煉出來過嗎？有就回傳登記在案的那一門（全服看到同一個結果）。"""
        ...

    def recipe_keys(self) -> set[str]:
        """這一季已經有人煉出來的配方鍵。"""
        ...

    def claim_recipe(self, key: str, art: MartialArt) -> tuple[MartialArt | None, bool]:
        """登記配方與功法，回傳（這個配方的功法, 是不是首創），原子判斷。三種結果：
        - 配方已經有人登記 → 回傳登記在案的那一門與 False（配方的結果全服共享，無限煉製設計 §十二 第 1 點）。
        - 配方還沒人登記、art.name 也還沒被占用 → 登記，回傳 (art, True)。
        - 配方還沒人登記、但 art.name 已經被別人的自創功法或別的配方占用 → 回傳 (None, False)，
          呼叫端換一個名字再試（取名自創仍然是獨佔的）。"""
        ...

    # ── 改名、合併出來的意境、第一個練成絕學的人（武學與成長設計 3.2、3.6；這一季）──
    def rename_skill(self, skill_name: str, new_name: str) -> bool:
        """把這一季登記過的功法（skill_name 是它的 id）改叫 new_name：id 不變（身上、功法庫照舊指得到），
        只換顯示的名字；new_name 已經被任何功法、改過的名字或意境用掉時不改、回 False（原子判斷）。"""
        ...

    def renamed_skill_ids(self) -> set[str]:
        """這一季被改過名字的功法 id（絕學定名，FB-083）。一次查完：同步時拿來判斷手上的武學有沒有被改過，不必一門一門查。"""
        ...

    def get_insight(self, name: str) -> Insight | None:
        """這一季合併出來的意境；基本意境不在這裡（在 content.insights）。"""
        ...

    def lookup_insight_recipe(self, key: str) -> Insight | None: ...

    def claim_insight_recipe(self, key: str, insight: Insight) -> tuple[Insight | None, bool]:
        """跟 claim_recipe 同一套：配方有了回 (登記在案的, False)；名字被占用回 (None, False)；否則登記、回 (insight, True)。"""
        ...

    # ── 兵器配方（兵器設計 4.4；資料庫第 4 版的 gear_recipes；這一季）：打造隱藏配方第一批起不再新增，上線那一季讀舊名字用 ──
    def lookup_weapon_recipe(self, key: str) -> WeaponRecipe | None:
        """這個兵器配方這一季有沒有人打過；有就回登記在案的那一筆（全服看到同一個名字）。"""
        ...

    def claim_weapon_recipe(self, key: str, recipe: WeaponRecipe) -> tuple[WeaponRecipe | None, bool]:
        """跟 claim_recipe 同一套，原子判斷：配方有了 → (登記在案的, False)；名字被任何功法、改過的名字、意境、兵器配方用掉
        → (None, False)，呼叫端換名字再試；否則登記、回 (recipe, True)。"""
        ...

    # ── 隱藏配方的發現（打造隱藏配方設計 7.1；gear_recipes 裡鍵「鑄|配方 id」那幾列；這一季）──
    def lookup_gear_find(self, key: str, registry: bool | None = None) -> GearFind | None:
        """這條隱藏配方這一季有沒有人打出來過；有就回首位發現者那一筆。神器輪替（FB-402）：registry 是 None 時這一季蓋了輪替的章
        讀全服登記、沒蓋讀照季分的那一列；手上有那一件神器時照它的 Equipment.collected 傳（True 只讀登記、False 只讀那一列）。
        add_copy、name_divine 的 registry 同一個意思。"""
        ...

    def claim_gear_find(self, key: str, find: GearFind) -> tuple[GearFind, bool]:
        """原子判斷誰先：已經有了 → (登記在案的, False)；否則登記、回 (find, True)。名字欄寫鍵本身，不佔名字空間；
        鍵不是「鑄|」開頭丟 ValueError（別把兵器的組合鍵寫進來）。"""
        ...

    def add_copy(self, key: str, registry: bool | None = None) -> None:
        """這一季這條神器配方的仿品數 +1（打造隱藏配方設計 5.3、7.1；神器譜寫「仿品 N 把」）。沒有那一列就什麼都不做。"""
        ...

    def name_divine(self, key: str, owner: str, name: str, registry: bool | None = None) -> str | None:
        """神器原品定名（打造隱藏配方設計 5.2、7.1、7.3；鎖內原子，同 rename_skill）：這一季這條神器配方那一列的原品主人是 owner、還沒定名、
        名字沒被佔（_name_taken：武學、改過的名字、意境、gear_recipes），才把名字欄與 data 一起改掉（定的名字佔名字空間）。
        回 None＝定成了；不行回原因："gone"（沒有那一列、不是神器配方）、"owner"（不是主人）、"named"（已經定過）、"taken"（名字被佔）。"""
        ...

    def divine_records(self) -> list[tuple[int, GearFind]]:
        """神器譜（打造隱藏配方設計 5.5）：歷來每一季的神器原品——gear_recipes 裡「鑄|」開頭、神器配方、有原品主人的列，
        照季、再照鍵排，跨季讀（換季不刪）。回（季數, 那一列）。"""
        ...

    def signature_records(self) -> list[tuple[int, dict[str, SignatureClaim]]]:
        """神器譜裡的名將本命兵器（打造第三批）：歷來每一季的 WorldState.signature_arms，從 seasons 表照季讀（換季不刪，所以跨季）。
        回（季數, 人物 id → SignatureClaim）；那一季一把都沒給出去的不列。"""
        ...

    # ── 合到舊的（武學與成長設計 12.2；這一季）──
    def fused_arts(self) -> list[MartialArt]:
        """這一季靠合成登記的功法（origin 是 fused），照登記的先後；「合到舊的」從這裡找候選。"""
        ...

    def merged_insights(self) -> list[Insight]:
        """這一季合併出來的意境，照登記的先後；基本意境不在這裡。"""
        ...

    def season_firsts(self) -> dict[str, int]:
        """這一季每個人首創了幾樣（宗師榜，leaderboard.compute_boards）：名號（身分）→ 合成首創的武學＋首悟（合併出來）的意境件數。
        論武兩人共有的，兩個人各算一樣；合到舊的、師門配方不算（同江湖史的「合成首創」）。"""
        ...

    def link_recipe(self, key: str, skill_name: str, creator: str | None) -> tuple[MartialArt | None, bool]:
        """把配方指到這一季已經登記的一門功法（合到舊的），原子判斷：配方已經有人登記 → (登記在案的, False)；
        那門功法不存在 → (None, False)；否則記下這個配方 → (那一門, True)。功法本身不動，首創者照舊。
        skill_name 是登記的 id（資料表裡 skills.name 那一欄）：練成絕學改名之後顯示的名字就對不上了，所以呼叫端傳 art.id、不是 art.name。"""
        ...

    def link_insight_recipe(self, key: str, insight_name: str, creator: str | None) -> tuple[Insight | None, bool]:
        """跟 link_recipe 同一套，指到這一季合併出來的一個意境。insight_name 是登記的名字（insights.name 那一欄，跟 insight.id 一樣；意境不改名）。"""
        ...

    def claim_master(self, skill_name: str, player: str, shown: str | None = None) -> bool:
        """這門武學這一季第一個修到絕學的人：還沒有人就記成 player、回 True；已經有人回 False（原子判斷）。
        player 是名號（身分：取名權照它認）；shown 是寫給別人看的名號（引擎現在不給，一律寫名號；這一版之前匿名行走的人記成「某位少俠」），
        同一筆交易寫進那門武學的 master_shown（後到的人那一句、換季的江湖史照它寫）。"""
        ...

    def master_of(self, skill_name: str) -> str | None: ...

    # ── 感悟的首悟紀錄（悟意境設計 0.2b）──
    def claim_insight_first(self, key: str, name: str, creator: str, place: str, time: float = 0.0) -> bool:
        """這一季第一個在這裡、用這個做法、畫出這個屬性悟到的人：key 是「地點|做法屬性|畫出的屬性」（sensing.first_key）。
        還沒有人就記下（名字、名號、地名）、回 True；已經有人回 False（原子判斷，不看誰先送出模型請求）。
        記的是紀錄、不是定義：意境本身存在悟到的人自己的存檔裡，後面的人照樣自己悟、自己取名。換季寫進那一季的江湖史。"""
        ...

    def insight_first(self, key: str) -> tuple[str, str] | None:
        """這一季這個鍵的首悟紀錄：（意境名, 名號）；沒有人悟過是 None。"""
        ...

    # ── 玩家傳（資料庫第 5 版 biographies）：每個角色每季一篇，跨季保留 ──

    def save_annals(self, season: int, name: str, annals: list[dict], profile: dict) -> None:
        """換季前把這個角色那一季的行狀與身家存起來（Game._reset_player_for_new_season）。已經存過的那一季：傳還沒寫成就換成這一份，
        寫成了就不動（寫的是當時那份行狀）。"""
        ...

    def add_saved_annal(self, season: int, name: str, entry: dict) -> None:
        """那一季的行狀已經存起來之後才補到的一則（上一季收場的決戰，下一季才回來補）：接在存著的那份後面。那一季沒存過就不記。"""
        ...

    def biography(self, season: int, name: str) -> dict | None:
        """那一季這個角色的那一篇（欄位照 biographies 表；annals、profile 已經解開成 Python 的資料）；沒有是 None。"""
        ...

    def biographies_of(self, name: str) -> list[dict]:
        """這個角色歷季存著的每一篇（同 biography），照季別由新到舊。"""
        ...

    def store_biography(self, season: int, name: str, text: str, written_by: str, written_at: float, rewrite: bool) -> bool:
        """寫成的傳存進那一季那一篇（save_annals 要先存過）：rewrite 是 False 時只在還沒寫過時存（同時兩個請求只存先到的那一篇），
        是 True 時蓋掉舊的、重寫次數加一。存了回 True。"""
        ...

    def share_biography(self, season: int, name: str, public: bool, code: str) -> str | None:
        """公開或收回那一篇（寫成了才行）：公開時沒有分享代碼就用 code（呼叫端產生的亂碼），有了就沿用舊的（取消再公開網址不變）。
        回傳那一篇的分享代碼；那一篇不在或還沒寫成回 None。"""
        ...

    def biography_by_code(self, code: str) -> dict | None:
        """公開頁照分享代碼查（不用登入）：只回公開中、寫成了的那一篇；其餘一律 None。"""
        ...

    # ── 同伴性情漂移 ──
    def record_companion_tag(self, companion_id: str, tag: str) -> None: ...

    def get_companion_drift_note(self, companion_id: str) -> str: ...

    def set_companion_drift_note(self, companion_id: str, note: str) -> None: ...

    def tag_counts_since_last_drift(self, companion_id: str) -> int:
        """自上次語意化以來，全服玩家又新累積了幾次交友 tag（用總次數而非時間排程：誰的這次互動剛好跨過門檻就由誰觸發）。"""
        ...

    def record_drift_synthesis(self, companion_id: str, note: str) -> None:
        """語意化完成後，把新的一句話性情跟「這次是在累積到多少次時算的」一起寫回（同一筆交易裡讀當下總數）。"""
        ...

    # ── 江湖大事潤色（全服共用一次）──
    def get_event_flavor(self, fire_id: str) -> str: ...

    def set_event_flavor(self, fire_id: str, text: str) -> None:
        """只在這個江湖大事還沒有人潤色過（或先寫的那一句不合格，flavor.clean）時才寫入：全服永遠只看到同一份。"""
        ...

    # ── 傳國玉璽碎片（跨季）──
    def record_jade_seal_fragment(self, finder: str, season_name: str, text: str) -> JadeSealFragment | None:
        """記錄一塊新找到的碎片（編號在交易裡決定，不會重複或漏編）；七塊都找完之後回傳 None。"""
        ...

    def get_jade_seal_fragments(self) -> list[JadeSealFragment]: ...

    def tianji(self) -> int:
        """天機（同 read().tianji，只是不整份讀）。"""
        ...

    def jade_seal_summary(self) -> str: ...

    # ── 共享賽季 ──
    def get_season(self) -> WorldState:
        """目前這一季，連同這一季全部的傳聞與江湖史（給畫面看）。read()／mutate()／mutate_season()
        給出的賽季不讀傳聞與江湖史，兩個清單是空的，往裡面加的照樣會寫進去。"""
        ...

    def chronicle_before(self, season_number: int) -> list[tuple[int, list[Rumor]]]:
        """season_number 以前每一季的江湖史，新的一季在前（線上架構設計 3.2：江湖史跨季保留）。"""
        ...

    def past_season(self, number: int) -> WorldState | None:
        """第 number 季那一列（不含傳聞與江湖史）；沒有那一季是 None。換季時讀上一季收季那一刻存的四階（減法季批 3c，final_tiers）。"""
        ...

    def get_season_number(self) -> int: ...

    def mutate_season(self, fn: Callable[[WorldState], None]) -> WorldState:
        """讀取共用賽季→套用 fn(season)→寫回，同一筆交易。"""
        ...

    def save_season(self, season: WorldState) -> None:
        """寫回共用賽季：呼叫端（engine.py）把 state.world 指向 get_season() 讀回的那一份、就地修改過，這裡寫回。"""
        ...

    def season_phase(self) -> SeasonPhase: ...

    def seed_first_season(self, content: Content) -> WorldState:
        """全服第一次開局：照劇本種出第 1 季。預設停在籌備中等管理者開季；內容設定 auto_open_first_season
        時直接開季。已經種過就原封不動回傳。"""
        ...

    def open_season(self, content: Content, now: float) -> bool:
        """管理者開季：籌備中 → 進行中，賽季時鐘從 now 起算。還沒種、或已經開過，回傳 False。
        開季時照現在的設定重新蓋章（stamp_season）：第一次啟動忘了設 TIANXIA_PROFILE、種下的季蓋的是「關」，
        設好重開之後開季，這一季照新的設定跑。籌備中的季時間是 0、什麼都還沒跑，重蓋是安全的。"""
        ...

    def next_season(self, content: Content, now: float) -> bool:
        """管理者開下一季：只在休季時有效。換上全新的一季、賽季編號 +1、直接開季，賽季時鐘從 now 起算；
        同伴全部重獲自由、沒打完的決戰清掉，天機 +1；玉璽碎片不動。武學命名、煉製配方、投靠名冊每季各一份，
        新的一季自然是空的。舊的一季整份留著（線上架構設計 3.2），上一季的首創（合成首創、首悟意境、練成絕學）寫進那一季的江湖史。"""
        ...

    def catch_up_season(self, content: Content, now: float, rng: random.Random) -> list[str]:
        """被動的現實時間追趕：把共用賽季依「距離上次有人追趕過了多久現實時間」往前推進，世界的時間
        永遠只走一份。時鐘只會往前：拿比上次對過的還早的時間來追趕，不推進、也不把時鐘撥回去。
        賽季時鐘暫停中（paused_at）什麼都不做：不推進、對時點也不動（繼續時才一起往後挪，見 resume_clock）。"""
        ...

    # ── 賽季時鐘暫停（線上架構設計第四節、8.3）──
    def paused_at(self) -> float | None:
        """賽季時鐘從哪個現實時間起暫停；沒有暫停是 None。只讀一個欄位、很快：引擎每次排選單、推決戰都會問。"""
        ...

    def pause_clock(self, now: float) -> bool:
        """暫停賽季時鐘：只在進行中、還沒暫停時有效（記下 now、回 True）；籌備、休季、已經停著都什麼都不做、回 False。"""
        ...

    def resume_clock(self, content: Content, now: float) -> float | None:
        """讓賽季時鐘繼續走，回傳停了幾個現實秒；沒有暫停回 None。停的這一段不算進賽季：對時點（season_last_real）往後挪
        world.pause_skip 那麼多（第一季照整個曆時往下取整，其他照停的長度）——暫停前還沒補算的那一小段照算，季末與一般的大事
        跟著往後延。還沒收場的決戰，集結截止或這一回合開放的時間往後挪停的長度（battle_instance.shift_deadlines），
        剩下的時間跟暫停前一樣。排好、還沒開的決戰照原本的現實時間開（企劃者 2026-10-06 定 B3，world.keep_showdowns_on_time）；
        原本的時間落在暫停裡的記進 showdowns_waiting（B11）。
        繼續之後緊接著還要補算、開集結（不補算的話，決戰會在它前面的一般大事還沒結算時就開成）：呼叫端不要自己接這幾步，
        一律走 world.resume_season_clock。"""
        ...

    # ── 投靠名冊 ──
    def record_faction(self, name: str, faction_id: str) -> None:
        """記進投靠名冊；faction_id 是 allied.roll_key（豪強分屬兩軍時依附的豪強寫「haoqiang@guan」）。"""
        ...

    def faction_of(self, name: str) -> str | None:
        """這一季投靠名冊上這個名號算哪一方（豪強依附時是那一軍，allied.side_of_key）；還沒記過是 None。"""
        ...

    def roll_of(self, name: str) -> str | None:
        """名冊上記的鍵本身（allied.roll_key）；還沒記過是 None。Game._record_faction 比這個。"""
        ...

    def faction_counts(self) -> dict[str, int]:
        """這一季各陣營（身分）投靠了幾人（只列有人的陣營；豪強依附哪一軍都算豪強，allied.faction_totals）。"""
        ...

    def roll_counts(self) -> dict[str, int]:
        """這一季名冊照鍵數（allied.side_totals、gentry_totals 從這一份算）。"""
        ...

    def seal_state(self) -> SealView:
        """玉璽碎片的登記與奪璽單挑（加上季別、天機、暫停沒）：只讀 world 那一列，不讀季，每次輪詢都讀得起。"""
        ...

    def seal_duel_open(self) -> bool:
        """有沒有還沒收場的奪璽單挑（提前收季要等它，5.11）。在 mutate 裡也查得到（同 faction_counts）。"""
        ...

    def sortie_duels(self) -> dict[str, SortieDuel]:
        """出陣約戰（減法季批 3b）：只讀 world 那一列的 sorties，不讀季，每次輪詢都讀得起。"""
        ...

    def divine_state(self) -> DivineRegistry:
        """神器輪替的全服登記（現世過哪幾件、原品那一筆）：只讀 world 那一列，不讀季。"""
        ...

    def fingerprint_parts(self) -> tuple[SharedWorldState, int, int]:
        """（全服狀態，這一季最大的天下大事傳聞流水號，這一季江湖史的則數），同一個唯讀快照裡讀的；賽季裡的傳聞與江湖史
        不讀回每一列。推送的看守用（server.current_fingerprint）。"""
        ...

    # ── 全服即時多人戰鬥 ──
    def get_battle(self) -> BattleInstance | None: ...

    def mutate_battle(self, fn: Callable[[BattleInstance], None]) -> BattleInstance | None:
        """讀取目前這場戰鬥→套用 fn(battle)→寫回；沒有戰鬥時 fn 不會被呼叫，直接回傳 None。"""
        ...

    def start_battle(self, definition: BattleDef, now: float, trend_start: int | None = None) -> BattleInstance:
        """開一場新戰鬥；已經有一場還沒結束的戰鬥時，原封不動回傳那一場。trend_start 是這一場的起點（時刻表決戰照
        前線戰況算）；不給照 definition.trend_start（見 battle_instance.start_muster）。"""
        ...

    def clear_battle(self) -> None: ...

    # ── 攻城戰（領地爭奪第二批）：跟決戰同時打，另存一串 ──
    def get_sieges(self) -> list[BattleInstance]:
        """還在共用狀態裡的攻城戰（照開集結的先後；收場之後拿掉，見 drop_siege）。"""
        ...

    def mutate_siege(self, record_id: int, fn: Callable[[BattleInstance], None]) -> BattleInstance | None:
        """讀出流水號 record_id 那一場攻城→套用 fn→寫回；沒有那一場時 fn 不會被呼叫、回 None。"""
        ...

    def start_siege(self, definition: BattleDef, now: float, trend_start: int, info: SiegeInfo) -> BattleInstance:
        """開一場攻城戰的集結（start_muster，再記上 info）；回帶著流水號的那一場。"""
        ...

    def drop_siege(self, record_id: int) -> None:
        """把那一場攻城從共用狀態拿掉（收場、季終收兵之後）；battles 表那一列照留。"""
        ...

    def battle_rounds(self, record_id: int) -> list[BattleRoundRecord]:
        """這一場（BattleInstance.record_id）結算過的每一回合，照先後。BattleInstance.rounds 只放這次讀出來
        之後才結算、還沒寫進資料庫的回合，存檔後讀出來是空的；要看以前的回合查這裡。"""
        ...

    def ended_battles(self, after: int = 0, skip: Collection[int] = ()) -> list[tuple[int, BattleInstance]]:
        """收場的決戰（phase 是 ended）裡流水號（record_id）比 after 大的，不分季別、照先後，每一場連同它是第幾季
        打的：（季別, 戰鬥），戰鬥帶著 record_id。決戰的結果常常就把季收掉，所以參戰者休季、下一季才回來也要補得到
        （FB-027，見 Game._deliver_battle_results）。只讀。

        skip 是呼叫端已經處理過的流水號（攻城戰跟決戰、別的攻城戰同時打，先開的可能晚收場，領地爭奪第二批）：after 給的是往回讓幾場的
        下限，流水號在 skip 裡的不讀內容（先只查流水號，便宜）。下面「照開戰的先後收場」的理由只對決戰成立。
        after 是呼叫端已經處理過的最大流水號：決戰照開戰的先後收場，所以比它小的不會再有新收場的。理由——
        同一時間只有一場還沒收場（start_battle 在它收場或被清掉之前不另開），被清掉的（換季 next_season、季終
        clear_battle）不再指到、永遠不會收場，而新開的一場流水號一定比之前的都大（實作要保證這一點，SQLite 版是
        從不刪列的 INTEGER PRIMARY KEY）。所以一場收場時，它比之前收場的每一場都大。

        季終沒打完的決戰，Game 先用 mutate_battle 標成 ended 且 unfinished（沒有結果、不套用）再 clear_battle，
        所以它也列在這裡（FB-035）；用的人要看 BattleInstance.unfinished 分辨。它收場的那一刻仍是同時唯一還沒收場的那一場，
        流水號的先後前提不變。"""
        ...

    def ended_battle(self, record_id: int) -> BattleInstance | None:
        """一場收場的決戰（流水號 record_id），沒有或還沒收場是 None。戰報頁畫決戰的完整戰況照它（收場之後才補上的放手一搏劇情也在）。只讀。"""
        ...

    def season_ended_battles(self, season: int) -> list[BattleInstance]:
        """這一季收場的決戰，照先後（季終沒打完的也在，看 unfinished）。補回被洗掉的決戰戰報用（Game._restore_showdowns）。只讀。"""
        ...

    # ── 同伴進度與招募 ──
    def get_companion(self, companion_id: str) -> CompanionProgress:
        """讀目前進度；還沒有人動過這位人物時回傳一份預設值（不寫回）。"""
        ...

    def companions(self) -> dict[str, CompanionProgress]:
        """每一位人物的進度（同 read().companions，只是不整份讀；每次都是新的一份）。"""
        ...

    def try_recruit(self, companion_id: str, player_name: str, cap: int | None = None) -> bool:
        """把 owner 設成 player_name；已經有主的話失敗（設計文件四.4：唯一、可搶）。"""
        ...

    def release_companion(self, companion_id: str) -> None:
        """放走同伴：只清 owner，等級/武學等進度原封不動。"""
        ...

    def update_companion(
        self, companion_id: str, fn: Callable[[CompanionProgress], None],
    ) -> CompanionProgress: ...
