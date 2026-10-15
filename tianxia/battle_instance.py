"""全服共用的即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步→打完最後一回合、或戰局一面倒時
判定勝負；每幕固定幾回合，見戰鬥系統設計 3.2 與 resolve_round）。

固定選項（強攻／固守／奇襲，三招互剋，戰鬥系統 3.4）的推力與氣血損耗是 Config.battle 的數字加上每個人加入時快照的
份量算出來的確定性結果，不信任 LLM 自己算數字；
自訂行動（放手一搏，見 BattleOption.free_text／FreeTextGamble）則是 LLM 評估一個成功率
（這件事 LLM 做得到、也實測過排序穩定），系統拿這個機率真的擲骰、用寫死的公式換算
成戰局推動/氣血損耗——玩家的奇葩操作因此真的會影響戰局（賭贏大賺、賭輸慘賠），但
「最後是不是成功」跟「成功該加多少」都是系統的亂數/公式決定，LLM 從頭到尾不會直接
吐出任何被拿去套用的數字，只吐一個被擲骰消費掉的機率。回合的敘事是系統判定的句子（誰佔了上風、為什麼，
見 round_line／round_causes），不叫模型潤色：結算在行動鎖裡，鎖內等模型會讓全服跟著等（試玩回饋 2026-10-08）。

這裡是純粹的資料模型跟引擎函式，不碰共用儲存的存讀鎖（那是 world_state.py::
get_battle/mutate_battle/start_battle 的事）、不碰網頁介面（那是 engine.py/server.py 的事）。
回合「鎖步」的意思是：每個參戰者各自送出一個行動，全員都送出（或逾時被系統代選）才會
真正結算那一回合，由誰送出最後一個行動就由誰的這次呼叫觸發結算，不需要背景常駐程式。
"""
from __future__ import annotations

import math
import random
import re
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

from . import encounter, gender, tactics, zh
from .models import (
    BEATS, MOVES, BattleAct, BattleDef, BattleOption, BattleOutcome, BattleTuning, FreeTextGamble, TacticTuning,
)
from .ollama_client import OllamaClient

Phase = Literal["muster", "active", "ended"]

UNFINISHED_TITLE = "未分勝負"  # 季終收兵的決戰：結果標題與江湖紀錄標題的尾巴（FB-035）
UNFINISHED_TEXT = "季終了，這場決戰沒打完就各自收兵，不算勝負。"

CENTER = 50  # 戰局的中線：提前收場看偏離它多少（戰鬥系統 5.3），時刻表決戰的勝負也以它為界（4.1、4.2）
BIG_WIN_MARGIN = 15  # 時刻表決戰：戰局偏離中線達到這麼多是大勝，否則險勝（戰鬥系統 4.1【預設】）

# 戰線動了多少的說法（Joy 2026-10-10 轉玩家反饋：「那個推進多少我都不知道是啥意思」）：句子裡不寫數字，照大小分三段
# （同 front_lines.BANDS 的想法；決戰一回合的變動比戰況大，所以門檻不同）。數字只畫在戰局條上（gauge）。
SHOVE_BANDS: tuple[tuple[int, str], ...] = ((10, "一大截"), (4, "一截"), (1, "一點"))


def shove_size(delta: int) -> str:
    """變動（看絕對值）是「一點」「一截」還是「一大截」。"""
    size = abs(delta)
    return next((word for low, word in SHOVE_BANDS if size >= low), SHOVE_BANDS[-1][1])


def shove(side: str, delta: int) -> str:
    """「替官軍把戰線推前了一截」／「讓官軍的戰線退了一點」；delta 是這一邊這一下推了多少（負是倒退）。"""
    if delta >= 0:
        return f"替{side}把戰線推前了{shove_size(delta)}"
    return f"讓{side}的戰線退了{shove_size(delta)}"

DEFAULT_FREE_TEXT_SUCCESS_RATE = 40  # LLM 評估失敗/無 client 時的保底值——明顯偏低（放手一搏預設不利），
# 不是 50/50，呼應「不會全程 LLM 自由發展」的框架精神：評不出來就當作風險自負，不讓機制因為評估失敗而意外變得穩賺不賠。


GAMBLES_KEPT = 6  # 每個參戰者記幾次放手一搏給行狀（per_act 不限之後，九回合的仗最多九次，行狀只留最近六次）


class GambleMoment(BaseModel):
    """一次放手一搏（收場時挑「最有戲」的那一次寫進傳聞，試玩回饋 2026-10-08）。"""

    name: str
    faction: str
    text: str
    story: str = ""  # 播出來的那一版劇情；模型沒寫是空的
    rate: int  # 評估的成功率（加職位之前，傳聞照玩家看到的那個數）
    won: bool
    target: str = ""  # 點名的那個人（find_target）；沒點名是空的（玩家傳的行狀寫；舊資料沒有）
    round: int = 0  # 整場的第幾回合（回合結算後補劇情時認這一筆，apply_tales）；舊資料沒有是 0


class GambleTale(BaseModel):
    """一次放手一搏等著補劇情（Joy 2026-10-13「應該要做到能承受」：評分只回成功率，劇情等回合結算後一整回合批給模型一次寫）。
    結算當下先播固定句 fixed；寫好了把場景記錄裡的 fixed 換成「劇情（numbers）」（apply_tales）。數字照引擎算的，模型不碰。"""

    round: int  # 整場的第幾回合（1 起算）
    act_index: int  # 那一回合是第幾幕：劇情照這一幕的情境寫
    name: str
    faction: str  # 陣營 id
    text: str  # 玩家寫的那一句
    won: bool
    target: str = ""  # 點名的那個人；沒點名是空的
    sex: str = "男"  # 送出的人的性別（gender）：模型寫劇情時的稱呼
    fixed: str  # 先播的固定句（場景記錄裡要換掉的那一段）
    numbers: str  # 換上劇情時括號裡的數字（引擎算的）


class BattleParticipant(BaseModel):
    name: str
    faction: str
    neili: float  # 這場戰鬥專屬的氣血池，從角色當下的氣血上限抓一份快照，跟角色本身的
    # Member.neili（存檔裡的，練功/療傷用的那個）完全分開——戰鬥的傷害不會回頭影響角色
    # 平常的氣血，這是刻意的設計邊界（見設計討論沒有明講時的預設假設，之後如果想要「這場
    # 戰鬥真的會傷到我的角色」，再回頭改這裡）。
    neili_cap: float
    power: float = 0.0  # 加入時快照的武學威力（給 mitigated_by_power 用，見 resolve_round）——
    # 戰局結算只看共用戰鬥狀態本身，不會、也不能回頭去讀別的玩家自己存檔裡的角色資料，
    # 所以威力要在加入當下、由那個玩家自己的 Game 執行個體算好存進來。
    scores: dict[str, float] = Field(default_factory=dict)  # 加入時快照的每招份量（move_scores，還沒乘氣血狀態）；
    # 舊資料沒有＝每招 0（戰鬥系統 3.4）：份量 0、照常扣血與出局，不當機（resolve_round 讀 scores.get(招, 0.0)）
    last_result: str = ""  # 這個人上一回合出的招與剋制（「固守（剋制 ×1.3）」），畫面用；上一回合沒出固定招（放手一搏、
    # 離開大區、倒下、沒出手）是空的——resolve_round 一開頭先清掉所有人的
    eliminated: bool = False
    away: bool = False  # 離開了決戰的大區（人在區外，或這一趟路正要走出大區）：這回合不出手，回到大區才再出手（地圖擴充設計第六節）。
    # 由那個玩家自己的 Game 在出發、抵達時寫進來（見 Game._sync_battle_presence）；戰局結算不會、也不能去讀別人的存檔
    is_bot: bool = False
    # 參戰者自己的戰報要寫的（FB-027，見 Game._deliver_battle_results）；舊資料沒有這兩欄就是預設值
    acted_rounds: int = 0  # 自己送出行動、而且結算了的回合數：玩家按的、假人自己選的都算，逾時被系統代選的不算（見 resolve_round）
    fell_round: int | None = None  # 在整場的第幾回合倒下；沒倒下是 None
    attribute: str = ""  # 加入時身上武學的屬性（隊伍多樣性，一門打不遍）；只有第一季開著時才快照，空的不算一路
    role: str = ""  # 加入時依本人最突出的屬性給的職位（屬性的鍵，role_for；名字在 BattleTuning.roles）；空的是沒有職位
    # 以下是 Joy 2026-10-10 決戰試玩回饋加的（舊資料沒有這幾欄就是預設值）
    gambled_act: int = -1  # 最近一次放手一搏是在第幾幕（BattleTuning.gamble_per_act：一幕最多搏幾次）
    gambles_this_act: int = 0  # 那一幕搏了幾次
    pinned_round: int = 0  # 被險招牽制住、只能固守的那一回合（整場的第幾回合，1 起算）；0 是沒有
    led_rounds: int = 0  # 帶頭出固定招、而且那一回合自己這一邊佔了上風的回合數（戰報寫）
    targeted_by: list[str] = Field(default_factory=list)  # 放手一搏點名過他的人（照先後、不重複）
    hurt_taken: float = 0.0  # 被別人打掉的氣血（點名的放手一搏、對面強攻的集火）
    hurt_dealt: float = 0.0  # 自己的放手一搏打掉被點名的人多少氣血
    # 個人戰功（Joy 2026-10-10，merit）：舊資料沒有這幾欄就是 0
    gambles_won: int = 0  # 放手一搏成了幾次
    hits_landed: int = 0  # 點名的放手一搏真的打掉對方氣血幾次
    stood_marked: int = 0  # 被點名或被集火打掉氣血、回合結束還站著的回合數
    # 掛機（Joy 2026-10-10：「掛機的人很影響節奏，是不是有掛機懲罰」）：連續幾回合是逾時被代選的（自己送出就歸零）。
    # 1 以上就是掛機：下一回合起不等他（其他人送齊就結算，他照舊被代選固守）。固守的份量與戰功照常算、也不撤下陣
    # （Joy：「固守就別打折了 他進戰場已經很有心 戰功正常算」）
    idle_streak: int = 0
    held_rounds: int = 0  # 逾時被系統代為出手（固守）的回合數：不算自己出手（acted_rounds），戰功照一樣算
    # 以下是裝備二（坐騎）加的（舊資料沒有這兩欄就是預設值）
    mount: str = ""  # 加入時騎的馬名（裝備四欄 5.9：決戰畫面、戰報寫）；沒騎馬是空的
    cavalry: float = 0.0  # 加入時的騎兵加成（強攻、奇襲的份量已經乘過，這裡只給畫面寫幾成）
    # 部下上陣（PM 2026-10-12）：舊資料沒有這兩欄就是沒帶部下
    troops: str = ""  # 加入時帶的部下（team.troop_names：「兩名持矛鄉勇」）；沒帶是空的
    # 每一回合自己出了什麼（整場的第幾回合 → 「強攻」「固守（逾時代選）」「放手一搏「…」，成了」）：收場時寫進自己的戰報（Joy 2026-10-14
    # 「決戰能不能把完整戰報在戰報那邊可以展開」）；舊資料沒有是空的
    moves: dict[int, str] = Field(default_factory=dict)
    # 本命戰法（本命戰法第二批）：加入那一刻本人身上帶的戰法與這一場的條件（team.self_side，算坐騎與部下）、打到一半的狀態；
    # 沒有本命戰法、舊資料是 None
    kit: tactics.BoutSide | None = None
    gambles: list[GambleMoment] = Field(default_factory=list)  # 這個人這一場的每一次放手一搏（玩家傳的行狀寫，最多 GAMBLES_KEPT 次）；舊資料沒有
    troop_bonus: float = 0.0  # 部下讓強攻、奇襲多的份量（份量已經乘過，這裡只給畫面寫幾成）
    # 玉璽碎片（玉璽碎片設計 4.6）：加入那一刻的快照，挑挑戰者只讀它；舊資料沒有＝False
    turncoat: bool = False  # 這一季叛投過（PlayerState.defected）
    newbie: bool = False  # 還在新手期（roster.newbie）


# 跟按鈕一樣的字（battles.json 三幕的放手一搏按鈕）：只照按鈕抄一遍的不算寫了什麼（長社火攻那一場「最令人印象深刻的一幕」
# 頒給了只寫「放手一搏」四個字的人，PM 2026-10-15）
GAMBLE_WORDS = ("放手一搏", "孤注一擲", "背水一戰")
# 去掉標點與空白之後少於這麼多字的也不算寫了什麼（「衝」「殺啊」「上！」）
HOLLOW_BELOW = 4
_NOT_WORDS = re.compile(r"[\W_]+")


def hollow(text: str) -> bool:
    """這一搏沒寫什麼內容：去掉標點與空白後跟按鈕一樣（GAMBLE_WORDS），或少於 HOLLOW_BELOW 個字。"""
    bare = _NOT_WORDS.sub("", text)
    return len(bare) < HOLLOW_BELOW or bare in GAMBLE_WORDS


def more_dramatic(new: GambleMoment, old: GambleMoment | None) -> bool:
    """哪一次放手一搏最有戲：有寫內容的勝過沒寫內容的（hollow；全部都沒寫內容就照下面挑）；成了的勝過沒成的；
    同樣成了，成功率越低越有戲；同樣沒成，也是越荒唐（成功率越低）越有戲；一樣有戲時留先發生的那一次。只看規則，不叫模型。"""
    if old is None:
        return True
    return (not hollow(new.text), new.won, -new.rate) > (not hollow(old.text), old.won, -old.rate)


def one_miss_left(p: BattleParticipant, gamble: FreeTextGamble) -> bool:
    """氣血池撐不過一次最壞的失手（成功率 0 的失手扣的量，同 resolve_round）：再失手一次就倒下。"""
    worst = p.neili_cap * min(1.0, gamble.failure_neili_share_base + 100 * gamble.failure_neili_share_per_risk)
    return p.neili <= worst


class BattleRound(BaseModel):
    pending_actions: dict[str, str] = Field(default_factory=dict)  # 玩家名號 -> tag
    custom_texts: dict[str, str] = Field(default_factory=dict)  # 玩家名號 -> 自訂行動文字（free_text 選項才有）
    success_rates: dict[str, int] = Field(default_factory=dict)  # 玩家名號 -> LLM 評估的成功率（0~100，
    # free_text 選項才有；在送出的當下就評好存起來，不是結算時才問——resolve_round 不能
    # 呼叫 LLM，見模組說明。這個欄位有值就代表這個人這回合是賭局型行動，沒有值就是出固定的三招，
    # resolve_round 靠這個區分兩條路徑）。
    opened_real: float = 0.0  # 這回合開放選擇的時間點，逾時代選判斷用
    stories: dict[str, list[str]] = Field(default_factory=dict)  # 名號 ->［成功版, 失敗版］放手一搏的劇情（評成功率的同一次
    # 模型呼叫寫的，試玩回饋 2026-10-08）；擲骰後播對應的那一版，空字串或沒有就用固定句
    auto_picked: list[str] = Field(default_factory=list)  # 這回合逾時、由系統代選行動的人（fill_timed_out_actions
    # 記下）：resolve_round 不把他們這回合算成自己出手（BattleParticipant.acted_rounds）
    sexes: dict[str, str] = Field(default_factory=dict)  # 名號 → 放手一搏的人的性別（回合結算後補劇情用，GambleTale.sex）


class BattleRoundRecord(BaseModel):
    """結算過的一回合（線上架構設計 3.1：戰鬥回合一筆一筆加）。只寫不讀回：寫進資料庫之後，下次讀出來的
    BattleInstance.rounds 是空的；要看以前的回合用 WorldStateStore.battle_rounds。"""

    id: int | None = None  # 資料庫的流水號；None＝還沒寫進資料庫
    act_index: int  # 結算前是第幾幕
    round_number: int = 0  # 這是整場的第幾回合（1 起算）；0＝回合上限之前的舊紀錄
    resolved_real: float  # 結算的現實時間
    actions: dict[str, str] = Field(default_factory=dict)  # 名號 -> tag
    custom_texts: dict[str, str] = Field(default_factory=dict)  # 名號 -> 自訂行動文字
    success_rates: dict[str, int] = Field(default_factory=dict)  # 名號 -> LLM 評估的成功率
    messages: list[str] = Field(default_factory=list)  # 系統判定的結算訊息
    narration: str = ""  # 以前 LLM 潤色的敘事（2026-10-08 起回合不再叫模型，新的回合是空字串；舊資料留著）
    trend_after: int  # 結算後的戰局


class RoundSwing(BaseModel):
    """一回合戰局往哪邊走、為什麼（round_causes 寫的那幾句）：收場時挑出關鍵的回合寫成敗因（outcome_reason）。
    存在 BattleInstance 裡（不像 rounds 寫進資料庫就讀不回來），一場最多 total_rounds 筆。"""

    round: int  # 整場的第幾回合（1 起算）
    delta: int  # 這一回合戰局變了多少（正是往第一方，負是往第二方）
    causes: str = ""  # 這一回合的原因，「；」分開
    fixed: int = 0  # 其中三招交鋒推的（同 delta 的正負；其餘是放手一搏）；舊資料沒有是 0


class BattleInstance(BaseModel):
    battle_id: str
    phase: Phase = "muster"
    muster_deadline_real: float = 0.0
    participants: dict[str, BattleParticipant] = Field(default_factory=dict)
    trend: int = 50
    trend_start: int | None = None  # 開打時的戰局（時刻表決戰照戰況算，不一定是 50）；舊資料沒有是 None
    seal_lean: dict[str, int] = Field(default_factory=dict)  # 天命之爭開集結那一刻各方握幾片（玉璽碎片設計 8.3；起點已經照兩軍的數偏過）
    act_index: int = 0
    round_number: int = 0  # 已經結算了幾回合（換幕與最後一回合都照這個數，見 resolve_round）
    round: BattleRound = Field(default_factory=BattleRound)
    last_mix: dict[str, dict[str, float]] = Field(default_factory=dict)  # 陣營 → 上一回合各招的比例（只算出固定招的人；
    # 那一邊沒人出固定招是空的），畫面寫「對面上一回合」（戰鬥系統 3.4）；舊資料沒有就是空的
    narrative_log: list[str] = Field(default_factory=list)
    outcome_title: str | None = None
    outcome_text: str | None = None
    tales: list[GambleTale] = Field(default_factory=list)  # 等著補劇情的放手一搏（伺服器一回合批一次給模型寫，apply_tales 補完拿掉）
    highlight: GambleMoment | None = None  # 這一場到目前最有戲的放手一搏（more_dramatic）；收場時寫進傳聞，成功的人加名望
    outcome_side: str = ""  # 贏的那一方（陣營 id）；保底的「膠著」、沒分勝負、舊資料是空的（軍餉的獲勝加給看它）
    outcome_margin: str = ""  # 「大勝」或「險勝」；outcome_side 是空的時候也是空的
    outcome_reason: str = ""  # 勝負的關鍵（outcome_reason 寫的那一句）：收場訊息、參戰者的戰報都放；舊資料、沒分勝負是空的
    swings: list[RoundSwing] = Field(default_factory=list)  # 每一回合戰局怎麼走（resolve_round 記），寫敗因用；舊資料沒有是空的
    marked: dict[str, int] = Field(default_factory=dict)  # 名號 → 在第幾幕變得顯眼（被點名、或自己放手一搏成過）；同一幕才算
    last_targets: dict[str, list[str]] = Field(default_factory=dict)  # 上一回合：被點名的人 → 點名他的人（場景寫「X 盯上了你」）
    outcome_world_flags: list[str] = Field(default_factory=list)  # 結果要套用到共用賽季的世界旗標（複製自
    # BattleOutcome.world_flags_add，不是參照——戰鬥結算只碰共用戰鬥狀態本身，套用到賽季是
    # 呼叫端 engine.py 的事，見 Game._apply_battle_outcome；這裡存一份複本給它讀，不用
    # 重新比對一次是哪個 BattleOutcome）。
    outcome_trend_delta: dict[str, int] = Field(default_factory=dict)  # 同上，複製自 BattleOutcome.trend_delta
    end_time: float | None = None  # 收場時的賽季時間（遊戲秒）：收場那一下由 engine 寫入，給參戰者的戰報用（FB-027）；
    # 舊資料、或不是經過 engine 收場的是 None
    unfinished_text: str = ""  # 沒打完收起來時參戰者那一則寫的話；空的是季終收兵（UNFINISHED_TEXT），管理者取消另外寫（T10）
    unfinished: bool = False  # 季終時還沒打完就收起來的決戰（FB-035，見 Game._shelve_unfinished_battle）：phase 是 ended、
    # 這樣 ended_battles 才讀得到、參戰者才補得到一則交代，但沒有結果——不套任何大勢或旗標、不寫江湖史、不加戰報。
    # 舊資料沒有這一欄＝False
    record_id: int | None = None  # 資料庫裡這一場的流水號；None＝還沒寫進資料庫（見 sqlite_world）
    # 玉璽碎片（玉璽碎片設計 3.2、4.3）：集結那一刻擲中的現世與璽動，持有者的陣營在那一刻快照；舊資料沒有＝沒有
    seal_emerge: str | None = None  # 這一場現世哪一片（收場時從勝方抽得主）
    seal_shard: str | None = None  # 這一場牽動哪一片
    seal_holder: str | None = None  # 那一片的持有者（名號）
    seal_holder_faction: str | None = None  # 持有者那一刻在投靠名冊上的陣營（散人、這一季還沒上線過是 None）
    seal_holder_side: str | None = None  # 上一欄是交戰兩方之一就記那一方，否則 None（旁觀）
    seal_notes: list[str] = Field(default_factory=list)  # 收場時寫進每個參戰者戰報的那一兩行（下戰書、現世的得主）
    rounds: list[BattleRoundRecord] = Field(default_factory=list)  # 這次讀出來之後才結算、還沒寫進資料庫的回合


def start_muster(definition: BattleDef, now: float, trend_start: int | None = None) -> BattleInstance:
    """開一場集結。trend_start 是這一場的起點（時刻表決戰照前線戰況算，見 start_from_front）；不給時照
    definition.trend_start（beta 那場不變）。起點寫進 trend 之後就不再跟著戰線變。"""
    start = definition.trend_start if trend_start is None else trend_start
    return BattleInstance(
        battle_id=definition.id, trend=start, trend_start=start, muster_deadline_real=now + definition.muster_seconds,
    )


def shift_deadlines(instance: BattleInstance, seconds: float) -> None:
    """賽季時鐘暫停後繼續（WorldStateStore.resume_clock）：現實時間的期限往後挪停的長度。集結中挪集結截止，開打了挪這一回合
    開放的時間（回合逾時照它算），剩下的時間都跟暫停前一樣；收場的不動。開打之後不碰集結截止：它也是這一場的識別值
    （假人程式看它決定誰趕來參戰，bot_runner._battle_sides）。集結中暫停的那一場，截止一挪，識別值也跟著變：繼續之後
    那幾個不照作息、看這個值決定要不要趕來的假人會重新抽一次——看不出來、無害。"""
    if instance.phase == "muster":
        instance.muster_deadline_real += seconds
    elif instance.phase == "active":
        instance.round.opened_real += seconds


def start_from_front(front_value: int) -> int:
    """時刻表決戰的起點（戰鬥系統 5.3）：50 ＋（50 − 戰況）÷ 2，用 int(x + 0.5) 進位。戰況是 0 官軍穩控、100 黃巾控制，
    戰局以官軍為正向，所以翻過來再折一半：潁川 40 → 長社 55、南陽 35 → 宛城 58、冀州 55 → 廣宗 48。
    只看公開的戰況，不會洩漏伏筆鎖定（戰鬥系統 4.3）。"""
    return int(CENTER + (CENTER - front_value) / 2 + 0.5)


def sides(definition: BattleDef) -> list[str]:
    """這場決戰能站的每一方：交戰的兩軍（Joy 2026-10-13「豪強在大決戰還是要加入某一陣營，主軸還是官兵跟黃巾」：
    沒有第三方了，豪強跟散人一樣臨時投效兩軍之一）。"""
    return [f.id for f in definition.factions]


ROLE_MOVES: dict[str, str] = {"str": "強攻", "agi": "奇襲", "con": "固守"}  # 職位拿手的那一招（份量多 role_move_bonus）
CAVALRY_MOVES = ("強攻", "奇襲")  # 騎兵衝殺的兩招（裝備四欄 5.9）：份量 ×（1＋騎兵）；固守不加（騎兵衝殺不守）


def role_for(stats: dict[str, float], order: tuple[str, ...]) -> str:
    """進場的職位：本人屬性裡最高的那一項（同分照 order 的順序）；每一項都一樣高（例如剛開局全是 5）沒有職位。"""
    values = [stats.get(k, 0.0) for k in order]
    if not values or max(values) == min(values):
        return ""
    return order[values.index(max(values))]


def role_name(tuning: BattleTuning, role: str) -> str:
    return tuning.roles.get(role, "")


def role_text(tuning: BattleTuning, role: str) -> str:
    """職位與它做什麼，一句話（決戰畫面用）；沒有職位是空字串。數字照 tuning 寫。"""
    name = role_name(tuning, role)
    if not name:
        return ""
    if role in ROLE_MOVES:
        does = f"{ROLE_MOVES[role]}的份量多 {round(tuning.role_move_bonus * 100)}%"
    elif role == "wis":
        does = f"放手一搏的成功率多 {tuning.role_gamble_rate} 個百分點"
    elif role == "lore":
        does = f"被對面剋住時，吃虧少 {round(tuning.role_counter_relief * 100)}%"
    else:
        return name
    return f"{name}（{does}）"


def strength(tuning: BattleTuning, power: float) -> float:
    """實力（份量的底子）：power_base ＋ power_per × min(威力, power_cap)。越強越有份量（試玩回饋 2026-10-08）。"""
    return tuning.power_base + tuning.power_per * min(max(power, 0.0), tuning.power_cap)


def move_scores(
    tuning: BattleTuning, power: float, outer: str | None, inner: str | None, role: str = "", cavalry: float = 0.0,
    troops: float = 0.0,
) -> dict[str, float]:
    """這個人每一招的份量（還沒乘氣血狀態，戰鬥系統 3.4）：實力 × 適性 ÷ 100，職位拿手的那一招再乘（1＋role_move_bonus），
    騎著馬時強攻、奇襲再乘（1＋cavalry）（裝備四欄 5.9：跟職位疊乘；cavalry 是 mounts.cavalry，已經乘過飽足係數）；
    帶著部下時強攻、奇襲再乘（1＋troops）（PM 2026-10-12：每名部下 Config.follower.battle_per，跟職位、騎兵疊乘）。
    實力見 strength；適性 ＝ 75 ± 武學（招式）屬性 15 ± 內功屬性 10，夾在 50～100。
    outer／inner 是武學與內功的屬性（沒學是 None，不加減）。加入戰局時由那個玩家自己的 Game 算好快照進來。
    最後只 round 一次：沒騎馬時乘的是 1，數字跟以前一模一樣。"""
    base = strength(tuning, power)
    scores = {}
    for move in MOVES:
        fit = tuning.affinity_base
        for attribute, step in ((outer, tuning.affinity_outer), (inner, tuning.affinity_inner)):
            good, bad = tuning.affinity.get(attribute, (None, None)) if attribute else (None, None)
            fit += step if move == good else -step if move == bad else 0.0
        bonus = 1 + tuning.role_move_bonus if ROLE_MOVES.get(role) == move else 1.0
        ride = (1 + cavalry) * (1 + troops) if move in CAVALRY_MOVES else 1.0
        scores[move] = round(base * max(50.0, min(100.0, fit)) / 100 * bonus * ride, 1)
    return scores


def join_faction(
    instance: BattleInstance, name: str, faction: str, neili_cap: float, power: float = 0.0, is_bot: bool = False,
    scores: dict[str, float] | None = None, attribute: str = "", role: str = "", mount: str = "", cavalry: float = 0.0,
    troops: str = "", troop_bonus: float = 0.0, turncoat: bool = False, newbie: bool = False,
    kit: tactics.BoutSide | None = None,
) -> None:
    """集結期選陣營；已經選過的人再選一次視為改選（還沒進入 active 都還能換）。
    scores 是這個人此刻每招的份量快照（move_scores），之後戰局只讀這份；沒給＝每招 0。
    mount、cavalry 是加入那一刻騎的馬與騎兵加成（裝備四欄 5.9）；沒給＝沒騎馬。troops、troop_bonus 是帶的部下與份量加成（沒給＝沒帶）。
    turncoat、newbie 是加入那一刻的快照（玉璽碎片設計 4.6）；沒給＝都不是。"""
    if instance.phase != "muster":
        return
    instance.participants[name] = BattleParticipant(
        name=name, faction=faction, neili=neili_cap, neili_cap=neili_cap, power=power, is_bot=is_bot,
        scores=dict(scores or {}), attribute=attribute, role=role, mount=mount, cavalry=cavalry,
        troops=troops, troop_bonus=troop_bonus, turncoat=turncoat, newbie=newbie, kit=kit,
    )


def close_muster(instance: BattleInstance, definition: BattleDef, rng: random.Random, now: float = 0.0) -> None:
    """集結期結束：還沒選陣營的人（名字已經在 participants 裡但沒指定，或完全沒動作、
    呼叫端另外傳進來的在線名單）由這個函式統一處理——這裡只負責「把已經報名但沒選邊的人
    隨機分配」，呼叫端自己決定要不要把從沒選過的在線玩家也塞進 participants。"""
    if instance.phase != "muster":
        return
    armies = sides(definition)  # 沒選邊的分到兩軍之一
    for p in instance.participants.values():
        if p.faction not in armies:
            p.faction = rng.choice(armies)
    instance.phase = "active"
    instance.round = BattleRound(opened_real=now)
    instance.narrative_log.append(f"【{definition.name}】集結完畢，戰鬥開始！")


def auto_assign_latecomer(
    instance: BattleInstance, definition: BattleDef, name: str, neili_cap: float, rng: random.Random,
    power: float = 0.0, is_bot: bool = False, faction: str | None = None, scores: dict[str, float] | None = None,
    attribute: str = "", role: str = "", mount: str = "", cavalry: float = 0.0, troops: str = "", troop_bonus: float = 0.0,
    turncoat: bool = False, newbie: bool = False, kit: tactics.BoutSide | None = None,
) -> None:
    """集結期結束後才出現的人（包含機器人）：有指定陣營（劇本分陣營時的玩家、臨時投效的人投效的那一軍）就站自己那邊，
    否則塞進兩軍裡人數較少的一方，維持陣營平衡。scores、mount、cavalry、troops、troop_bonus、turncoat、newbie
    同 join_faction。"""
    if faction not in sides(definition):
        armies = sides(definition)
        counts = {fid: sum(1 for p in instance.participants.values() if p.faction == fid) for fid in armies}
        faction = min(counts, key=lambda fid: (counts[fid], rng.random()))
    instance.participants[name] = BattleParticipant(
        name=name, faction=faction, neili=neili_cap, neili_cap=neili_cap, power=power, is_bot=is_bot,
        scores=dict(scores or {}), attribute=attribute, role=role, mount=mount, cavalry=cavalry,
        troops=troops, troop_bonus=troop_bonus, turncoat=turncoat, newbie=newbie, kit=kit,
    )


def _active_participants(instance: BattleInstance) -> list[BattleParticipant]:
    """還在場上、這回合要出手的人：沒倒下，也沒離開決戰的大區。"""
    return [p for p in instance.participants.values() if not p.eliminated and not p.away]


def idle(p: BattleParticipant) -> bool:
    """掛機中：上一回合（或更早，連續）是逾時被代選的，還沒自己按過行動。"""
    return p.idle_streak > 0


def set_away(instance: BattleInstance, name: str, away: bool) -> None:
    """參戰者離開／回到決戰的大區（地圖擴充設計第六節）：離開的人這回合不出手，已經選好的行動也作廢；
    回來之後從當下這一回合起照常出手。不在名單上的人不理會。"""
    p = instance.participants.get(name)
    if p is None:
        return
    p.away = away
    if away:
        instance.round.pending_actions.pop(name, None)
        instance.round.custom_texts.pop(name, None)
        instance.round.success_rates.pop(name, None)
        instance.round.stories.pop(name, None)


def current_act(instance: BattleInstance, definition: BattleDef) -> BattleAct:
    return definition.acts[instance.act_index]


def act_text(instance: BattleInstance, definition: BattleDef) -> str:
    """這一幕的文字（戰鬥系統 3.2）：照誰佔上風換版本——戰局高於 50 用第一方佔上風的那一版、低於 50 用第二方的，
    剛好 50 或那一方沒寫就用 text。只看公開的戰局，不看伏筆鎖定（4.3）。"""
    act = current_act(instance, definition)
    first, second = definition.factions[0].id, definition.factions[1].id
    leader = first if instance.trend > CENTER else second if instance.trend < CENTER else None
    return act.text_by_lead.get(leader, act.text) if leader else act.text


def total_rounds(definition: BattleDef) -> int:
    """整場打幾回合（戰鬥系統設計 3.2）：每幕 rounds_per_act 回合 × 幕數；黃巾決戰是 3 × 3 ＝ 9。"""
    return definition.rounds_per_act * len(definition.acts)


def options_for(instance: BattleInstance, definition: BattleDef, name: str) -> list[BattleOption]:
    """這個人這回合能選的選項：框架給的選項，依陣營篩選（faction=None 的選項雙方都能選）。"""
    p = instance.participants.get(name)
    if p is None:
        return []
    act = current_act(instance, definition)
    options = [o for o in act.options if o.faction in (None, p.faction)]
    if pinned(instance, p):  # 被險招牽制住：這一回合只能固守
        held = [o for o in options if o.move == "固守" and not o.free_text]
        if held:
            return held
    if not can_gamble(instance, definition, p):  # 這一幕放手一搏過了
        options = [o for o in options if not o.free_text]
    return options


def pinned(instance: BattleInstance, p: BattleParticipant) -> bool:
    """這一回合（整場第 round_number＋1 回合）是不是被牽制住、只能固守。"""
    return p.pinned_round == instance.round_number + 1


def can_gamble(instance: BattleInstance, definition: BattleDef, p: BattleParticipant) -> bool:
    """這一幕還能不能放手一搏（FreeTextGamble.per_act；0 ＝ 不限，每回合都能搏）。"""
    limit = definition.free_text_gamble.per_act if definition.free_text_gamble is not None else 0
    if limit <= 0:
        return True
    return p.gambled_act != instance.act_index or p.gambles_this_act < limit


def find_target(instance: BattleInstance, definition: BattleDef, name: str, text: str) -> BattleParticipant | None:
    """放手一搏的文字裡點名的對面參戰者：名號 2 字以上、在文字裡最先出現的那一個（一樣早取長的）。只認交戰兩軍裡對面那一邊、
    還沒倒下的人。由引擎認，不靠模型。"""
    me = instance.participants.get(name)
    armies = {f.id for f in definition.factions}
    if me is None or me.faction not in armies:
        return None
    found = [
        (text.find(q.name), -len(q.name), q.name) for q in instance.participants.values()
        if q.faction in armies and q.faction != me.faction and not q.eliminated and len(q.name) >= 2 and q.name in text
    ]
    return instance.participants[min(found)[2]] if found else None


def target_line(instance: BattleInstance, definition: BattleDef, name: str, text: str, tuning: BattleTuning) -> str:
    """給模型評成功率的那一行：點名的對手是誰、身手跟你比如何（只寫比較，不寫數字）；沒點名是空字串。"""
    target = find_target(instance, definition, name, text)
    me = instance.participants.get(name)
    if target is None or me is None:
        return ""
    ratio = strength(tuning, target.power) / max(1.0, strength(tuning, me.power))
    how = ("遠比玩家強" if ratio >= 1.5 else "比玩家強" if ratio >= 1.1 else "跟玩家不相上下" if ratio > 0.9
           else "比玩家弱" if ratio > 0.6 else "遠比玩家弱")
    role = role_name(tuning, target.role)
    side = next((f.name for f in definition.factions if f.id == target.faction), target.faction)
    hurt = "，已經帶傷" if target.neili < target.neili_cap * 0.5 else ""
    return f"{target.name}（{side}{'的' + role if role else ''}，身手{how}{hurt}）"


def fixed_options(instance: BattleInstance, definition: BattleDef, name: str) -> list[BattleOption]:
    """這個人這回合能選的三招（固定選項，有 move；放手一搏不算）。"""
    return [o for o in options_for(instance, definition, name) if not o.free_text and o.move is not None]


def submit_action(
    instance: BattleInstance, name: str, tag: str, text: str | None = None, success_rate: int | None = None,
    stories: tuple[str, str] | list[str] | None = None, sex: str | None = None,
) -> None:
    """記錄一個人這回合選的行動；已經陣亡或不在這場戰鬥裡的人送出無效。text/success_rate
    是 free_text 選項才有（見 BattleOption.free_text）——success_rate 是呼叫端（engine.py
    ::submit_battle_custom_action）在送出的當下先問過 LLM 評好的成功率，resolve_round
    靠這個欄位有沒有值決定這個人這回合是賭局型行動還是一般查表行動，自己不會、也不能
    呼叫 LLM（見模組說明）。"""
    p = instance.participants.get(name)
    if p is None or p.eliminated or p.away or instance.phase != "active":
        return
    instance.round.pending_actions[name] = tag
    if name in instance.round.auto_picked:  # 系統代選過、結算前自己又選了：這回合算自己出手
        instance.round.auto_picked.remove(name)
    p.idle_streak = 0  # 按了任何行動就不算掛機
    if text:
        instance.round.custom_texts[name] = text
    if success_rate is not None:
        instance.round.success_rates[name] = max(0, min(100, success_rate))
        if sex:
            instance.round.sexes[name] = sex
        if stories:
            instance.round.stories[name] = [str(stories[0]), str(stories[1])]


def round_is_complete(instance: BattleInstance, timed_out: bool = False) -> bool:
    """所有還在場上、沒在掛機的人都送出行動了（陣亡的人不用等；掛機的人也不等，結算前由 fill_idle_actions 代選）。
    場上全是掛機的人時照舊等這一回合逾時；timed_out（這一回合已經逾時，呼叫端剛照逾時代選完）時就算齊了，照代選的結算
    （FB-173：以前沒有要等的人就一直回假，掛機的人鈕又是灰的，整場卡死）。場上沒人（全倒下、全走開）不算，那是 end_without_fighters 的事。"""
    active = _active_participants(instance)
    awaited = [p for p in active if not idle(p)]
    if not awaited:
        return timed_out and bool(active) and all(p.name in instance.round.pending_actions for p in active)
    return all(p.name in instance.round.pending_actions for p in awaited)


def round_progress(instance: BattleInstance, definition: BattleDef) -> tuple[int, int]:
    """這一回合（已送出, 在場）的人數：在場是還沒倒下、沒離開大區、沒在掛機的人，已送出是其中選好行動的。
    畫面寫「已送出 X／在場 Y」，讓人知道是在等人、不是壞了（試玩回饋 2026-10-08）。
    跟 round_is_complete 等的是同一批人（Joy 2026-10-13：以前全員送出了倒數還在跳）。"""
    active = [p for p in _active_participants(instance) if not idle(p)]
    return sum(1 for p in active if p.name in instance.round.pending_actions), len(active)


def idle_count(instance: BattleInstance, definition: BattleDef) -> int:
    """掛機中的人數（round_progress 的「在場」不算他們；畫面另寫「掛機 N 人」）。"""
    return sum(1 for p in _active_participants(instance) if idle(p))


def _war_rally(instance: BattleInstance, moves: dict[str, str], on: bool) -> dict[tuple[str, str], list[tuple[str, float]]]:
    """名將本命兵器〔號令〕（本命戰法第三批）：帶著它出固定招的人，同一邊出同一招的友軍份量 +war_ally_pct（自己不算）。
    （陣營, 招）→ [(帶著它的人, 加幾成)]；戰法關著是空的。"""
    out: dict[tuple[str, str], list[tuple[str, float]]] = {}
    if not on:
        return out
    for name, move in moves.items():
        p = instance.participants.get(name)
        if p is None or p.eliminated or p.kit is None:
            continue
        pct = max((h.tactic.params.get("war_ally_pct", 0.0) for h in p.kit.holders), default=0.0)
        if pct > 0:
            out.setdefault((p.faction, move), []).append((name, pct))
    return out


def counter_coefficient(tuning: BattleTuning, move: str, enemy_mix: dict[str, float]) -> float:
    """剋制係數（戰鬥系統 3.4）：1 ＋ 0.5 × 對面出「被你剋的招」的比例 － 0.5 × 對面出「剋你的招」的比例，0.5～1.5。
    enemy_mix 是對面這回合各招的比例（_mix；對面沒人出固定招時呼叫端不呼叫、係數當 1）。"""
    beaten = BEATS[move]
    beater = next(m for m, v in BEATS.items() if v == move)
    return 1 + tuning.counter * enemy_mix.get(beaten, 0.0) - tuning.counter * enemy_mix.get(beater, 0.0)


def condition(p: BattleParticipant) -> float:
    """這一場的氣血狀態：0.5 ＋ 0.5 × 剩的 ÷ 上限（同遭遇戰，戰鬥系統 3.4）。"""
    return encounter.condition_of(p.neili, p.neili_cap)


def option_of(definition: BattleDef, act_index: int, faction: str, tag: str) -> BattleOption | None:
    """這一幕、這個陣營能選的、tag 是 tag 的那個選項；沒有就是 None。"""
    return next(
        (o for o in definition.acts[act_index].options if o.tag == tag and o.faction in (None, faction)), None,
    )


def _mix(moves: dict[str, str], factions: dict[str, str], side: str) -> dict[str, float]:
    """這一邊這回合各招的比例（只算出固定招的人）；沒人出就是空的。"""
    mine = [moves[name] for name in moves if factions[name] == side]
    return {m: mine.count(m) / len(mine) for m in MOVES} if mine else {}


def safest_option_tag(
    instance: BattleInstance, definition: BattleDef, name: str, tuning: BattleTuning | None = None,
) -> str | None:
    """這個人這回合最保守的固定選項（氣血損耗最低：三招時就是固守；一樣低時取框架裡排前面的）。只看他自己陣營能選的，
    所以逾時代選不會把黃巾的人代選成官軍的招、替對面推戰局。這一幕沒有他能選的固定選項就回 None。"""
    options = fixed_options(instance, definition, name)
    if not options:
        return None
    tuning = tuning or BattleTuning()
    return min(options, key=lambda o: tuning.damage[o.move]).tag


def fill_idle_actions(instance: BattleInstance, definition: BattleDef, tuning: BattleTuning | None = None) -> None:
    """其他人都送齊了、不等掛機的人：還沒送出的掛機者照逾時一樣代選（fill_timed_out_actions）。"""
    fill_timed_out_actions(instance, definition, tuning, only_idle=True)


def fill_timed_out_actions(
    instance: BattleInstance, definition: BattleDef, tuning: BattleTuning | None = None, only_idle: bool = False,
) -> None:
    """逾時：還沒送出行動的在場者（沒倒下、沒離開大區），系統代選他自己陣營最保守的固定選項（三招時是固守）；
    這一幕他沒有固定選項（驗過的內容每邊每幕都有三招，走不到這裡）就跳過他。
    代選的人記進 round.auto_picked：這一回合不算他自己出手（FB-027）。"""
    for p in _active_participants(instance):
        if only_idle and not idle(p):
            continue
        if p.name not in instance.round.pending_actions:
            tag = safest_option_tag(instance, definition, p.name, tuning)
            if tag is None:
                continue
            instance.round.pending_actions[p.name] = tag
            instance.round.auto_picked.append(p.name)


def diversity(instance: BattleInstance, moves: dict[str, str], side: str, tuning: BattleTuning) -> float:
    """這一回合這一邊出固定招的人，身上武學有幾路不同的屬性（一門打不遍）：每多一路，力量多乘 diversity_per，最多 diversity_cap。
    屬性是加入時的快照（BattleParticipant.attribute），空的（第一季沒開、舊資料）不算一路，所以開關關著時一律是 1。"""
    roads = {
        p.attribute for name in moves if (p := instance.participants.get(name)) is not None and p.faction == side and p.attribute
    }
    return 1 + min(tuning.diversity_cap, tuning.diversity_per * max(0, len(roads) - 1))


def resolve_round(
    instance: BattleInstance, definition: BattleDef, rng: random.Random, now: float = 0.0,
    tuning: BattleTuning | None = None, tactic: TacticTuning | None = None,
) -> list[str]:
    """結算一回合：固定招走三招（戰鬥系統 3.4）：每個人的力量＝份量（加入時快照的 scores，乘這一場的氣血狀態）×
    剋制係數（對面這回合出招的比例），一邊的力量＝Σ ÷ √（這一邊出固定招的人數），推力＝push_max ×（第一方 − 第二方）÷
    （兩方相加），四捨五入；一邊沒人出固定招、另一邊有就推滿，兩邊都沒有是 0。扣氣血照招的損耗 ×（2 − 剋制係數）。
    放手一搏照舊走賭局公式、推動加在三招合成之後（決戰改版三再改）。
    沒有 scores（舊資料、沒走 Game 加入的人）份量算 0：照常出招、扣血、出局，只是推不動戰局。
    氣血歸零的人出局；一開頭先把所有人的 last_result 清空，只有這一回合出了固定招的人才寫上新的。
    回合數加一之後照戰鬥系統設計 3.2 決定接下來怎麼走（只有兩個時機判結果）：
    - 戰局偏離中線 50 到 decisive_margin（壓倒性，戰局到 90 或 10）：當回合收場，不再換幕——剛好是該換幕的那一回合
      也一樣。看的是 50、不是這一場的起點（戰鬥系統 5.3：時刻表決戰的起點照戰況走，看起點會不對稱）；
    - 打完最後一回合（total_rounds）：看戰局收場；
    - 都不是、而且這一幕的回合打滿了：換下一幕。換幕只看回合數，不看戰局。
    最後把回合狀態重置給下一回合用（opened_real
    設成 now，給下一回合的逾時判斷當起點）。威力抵銷（mitigated_by_power）直接讀
    BattleParticipant.power——那是加入戰鬥當下由各自的 Game 執行個體算好快照進來的
    （見 BattleParticipant 的欄位註解），這裡不需要、也不能臨時去查任何人的角色資料。
    回傳這回合發生的事件訊息（系統判定的部分，不含 LLM 潤色、也不會自己寫進
    narrative_log——那兩件事都是呼叫端的事，見 narrate_round：呼叫端通常是先結算拿到
    msgs，請 LLM 潤色成一段敘事，再把潤色後的文字（或潤色失敗時的 msgs 本身）加進
    narrative_log，這裡不越俎代庖）。
    參戰者自己的戰報（FB-027）也在這裡記：這回合的行動不是系統代選的（不在 round.auto_picked 裡），出手回合數
    加一——在結算時數，一回合只會數一次，送出後又離開大區（行動作廢）的也不會被數到；倒下的人記下第幾回合。"""
    tuning = tuning or BattleTuning()
    act_index = instance.act_index
    msgs: list[str] = []
    first, second = definition.factions[0].id, definition.factions[1].id  # first 是戰局的正向方
    for p in instance.participants.values():
        p.last_result = ""  # 沒出固定招的人（放手一搏、離開大區、倒下、沒出手）不留上一回合的字
    # 這一回合出固定招的人：名號 → 哪一招（放手一搏的人不算進比例；不在交戰雙方的陣營這一份不算）
    factions = {name: p.faction for name, p in instance.participants.items()}
    moves: dict[str, str] = {}
    for name, tag in instance.round.pending_actions.items():
        p = instance.participants.get(name)
        if p is None or p.eliminated or name in instance.round.success_rates or p.faction not in (first, second):
            continue
        option = option_of(definition, act_index, p.faction, tag)
        if option is not None and option.move is not None:
            moves[name] = option.move
    mixes = {side: _mix(moves, factions, side) for side in (first, second)}
    force, counts = {first: 0.0, second: 0.0}, {first: 0, second: 0}
    names = {f.id: f.name for f in definition.factions}
    gambles: dict[str, int] = {}  # 陣營 → 這一回合放手一搏替自己這一邊推了多少（正是推進、負是倒退），回合摘要用
    gains: dict[str, int] = {}  # 陣營 → 其中成了的合起來推進多少（success_trend_cap 夾）
    losses: dict[str, int] = {}  # 陣營 → 其中失手的合起來倒退多少（負的，side_trend_cap 夾）
    coefs: dict[str, list[float]] = {first: [], second: []}  # 陣營 → 這一回合每個出固定招的人的剋制係數，回合摘要用
    fitness: dict[str, list[tuple[float, float]]] = {first: [], second: []}  # 陣營 → 每個出固定招的人的（份量, 氣血狀態），回合摘要用
    shares: dict[str, list[tuple[float, str, str]]] = {first: [], second: []}  # 陣營 →（力量, 名號, 招）：回合原因點名帶頭的人
    hits: list[_Hit] = []  # 點名的放手一搏成了：對被點名的人的傷害等這一圈結算完才一起扣（誰先誰後不影響這一回合的力量）
    targets_now: dict[str, list[str]] = {}  # 這一回合被點名的人 → 點名他的人
    trend_before = instance.trend
    rnd_no = instance.round_number + 1  # 這是整場的第幾回合（round_number 結算完才加一）
    fired: dict[str, list[str]] = {}  # 陣營 → 這一回合發動本命戰法的那幾句（〔名〕開頭，誰發動的寫在句子裡）

    rally = _war_rally(instance, moves, tactic is not None)  # 名將本命兵器〔號令〕：（陣營, 招）→ [(號令的人, 加幾成)]
    for side, move_, who, _pct in sorted({(k[0], k[1], w, pc) for k, rows in rally.items() for w, pc in rows}):
        if any(n != who and q.faction == side and moves.get(n) == move_ for n, q in instance.participants.items() if not q.eliminated):
            fired.setdefault(side, []).append(f"{tactics.LEAD}號令〕{who}號令一下，同出{move_}的友軍份量加重")

    def war(name: str, p: BattleParticipant, move: str | None, coef: float) -> tactics.War:
        """本命戰法（本命戰法第二批）：只算自己身上的（tactics.WAR_KINDS）；沒帶著或沒開是中性值。"""
        if p.kit is None or tactic is None:
            return tactics.War()
        edge = instance.trend if p.faction == first else 100 - instance.trend
        ratio = p.neili / p.neili_cap if p.neili_cap else 1.0
        out = tactics.war_round(p.kit, move, 1 if coef > 1 else 0, rnd_no, edge, ratio, tactic, _war_rng(instance, name, rnd_no))
        if out.lines:
            fired.setdefault(p.faction, []).extend(out.lines)
        if out.hp:
            p.neili = max(0.0, min(p.neili_cap, p.neili + p.neili_cap * out.hp))
        return out

    def tale(name: str, p: BattleParticipant, text: str, won: bool, target: str, fixed: str, numbers: str) -> None:
        """沒有現成劇情的放手一搏：先播固定句，記一筆等著回合結算後補（GambleTale）。"""
        instance.tales.append(GambleTale(
            round=rnd_no, act_index=act_index, name=name, faction=p.faction, text=text, won=won, target=target,
            sex=instance.round.sexes.get(name, "男"), fixed=fixed, numbers=numbers,
        ))
    for name, tag in list(instance.round.pending_actions.items()):
        p = instance.participants.get(name)
        if p is None or p.eliminated:
            continue
        if name not in instance.round.auto_picked:
            p.acted_rounds += 1
        else:  # 逾時被代選：掛機（下一回合起不等他）
            p.idle_streak += 1
            p.held_rounds += 1
        success_rate = instance.round.success_rates.get(name)
        custom_text = instance.round.custom_texts.get(name)
        if success_rate is not None and definition.free_text_gamble is not None:
            gamble = definition.free_text_gamble
            assessed = success_rate
            if p.role == "wis":  # 軍師：模型評完再加（職位，試玩回饋 2026-10-08）
                success_rate = min(100, success_rate + tuning.role_gamble_rate)
            risk = 100 - success_rate
            succeeded = rng.random() * 100 < success_rate
            saved = None
            if not succeeded and tactic is not None and p.kit is not None:  # 神上使：失手改成功（自己的亂數，不碰 rng）
                saved = tactics.divine_save(p.kit.holders, _war_rng(instance, name, rnd_no, "神上使"))
                succeeded = saved is not None
            p.moves[rnd_no] = f"放手一搏「{custom_text}」，{'成了' if succeeded else '沒成'}" if custom_text else f"放手一搏，{'成了' if succeeded else '沒成'}"
            if custom_text:
                plus = f"，{role_name(tuning, p.role)} +{success_rate - assessed}" if success_rate != assessed else ""
                msgs.append(f"{name}放手一搏：「{custom_text}」（評估成功率 {assessed}%{plus}）")
            if saved is not None:
                msgs.append(tactics.divine_line(saved))
            fx = war(name, p, None, 1.0)
            if fx.lines:
                p.moves[rnd_no] += "；" + "；".join(fx.lines)
            side_name = names.get(p.faction, p.faction)
            win_story, lose_story = (instance.round.stories.get(name) or ["", ""])[:2]
            if p.gambled_act == act_index:  # 一幕最多搏幾次（FreeTextGamble.per_act）
                p.gambles_this_act += 1
            else:
                p.gambled_act, p.gambles_this_act = act_index, 1
            target = find_target(instance, definition, name, custom_text or "")
            if target is not None:  # 點名：這一幕他變得顯眼；成不成都記下誰盯上了他
                instance.marked[target.name] = act_index
                if name not in target.targeted_by:
                    target.targeted_by.append(name)
                targets_now.setdefault(target.name, []).append(name)
            # 試玩回饋 2026-10-08：對戰局只有小影響，主要的代價是自己的氣血池（扣到 0 就照下面倒下出局）
            if succeeded:
                # 越強越有份量：推進乘實力（新手打五折、練滿最多兩倍）
                might = max(tuning.gamble_strength_min, min(tuning.gamble_strength_max, strength(tuning, p.power) / tuning.gamble_strength_ref))
                delta = max(1, round((gamble.success_trend_base + risk * gamble.success_trend_per_risk) * might))
                damage = p.neili_cap * gamble.success_neili_share
                instance.marked[name] = act_index  # 搏成了的人也顯眼
                p.gambles_won += 1
                if target is not None:  # 點名：推進打折，其餘化成對他的傷害（等這一圈結算完才扣，訊息到時候再寫）
                    delta = max(1, round(delta * tuning.target_push_share))
                    want = target.neili_cap * min(tuning.target_hit_max, tuning.target_hit_base + risk * tuning.target_hit_per_risk)
                    hits.append(_Hit(
                        len(msgs), name, target.name, want, success_rate <= tuning.pin_rate, win_story, side_name, delta, damage,
                        custom_text or "",
                    ))
                    msgs.append("")
                elif win_story:  # 模型寫的劇情，數字照引擎算的另外附在後面
                    msgs.append(f"{win_story}（{shove(side_name, delta)}，自己氣血 -{round(damage)}）")
                else:
                    numbers = f"{shove(side_name, delta)}，自己氣血 -{round(damage)}"
                    msgs.append(f"{name}這一搏成功了！{numbers}。")
                    if custom_text:
                        tale(name, p, custom_text, True, "", msgs[-1], numbers)
            else:
                delta = -min(gamble.failure_trend_cap, round(risk * gamble.failure_trend_per_risk))
                damage = p.neili_cap * min(1.0, gamble.failure_neili_share_base + risk * gamble.failure_neili_share_per_risk)
                # 代價照引擎算的寫出來（試玩回饋 2026-10-08：「慘痛的代價是什麼？」）
                cost = f"{shove(side_name, delta)}，" if delta else ""
                if lose_story:
                    msgs.append(f"{lose_story}（{cost}自己氣血 -{round(damage)}）")
                else:
                    msgs.append(f"{name}這一搏失敗了，付出了慘痛代價：{cost}自己氣血 -{round(damage)}。")
                    if custom_text:
                        tale(name, p, custom_text, False, target.name if target is not None else "", msgs[-1],
                             f"{cost}自己氣血 -{round(damage)}")
            if custom_text:
                moment = GambleMoment(
                    name=name, faction=p.faction, text=custom_text, story=win_story if succeeded else lose_story,
                    rate=assessed, won=succeeded, target=target.name if target is not None else "", round=rnd_no,
                )
                if len(p.gambles) < GAMBLES_KEPT:
                    p.gambles.append(moment)
                if more_dramatic(moment, instance.highlight):
                    instance.highlight = moment
            gambles[p.faction] = gambles.get(p.faction, 0) + delta
            if delta > 0:
                gains[p.faction] = gains.get(p.faction, 0) + delta
            elif delta < 0:
                losses[p.faction] = losses.get(p.faction, 0) + delta
        elif name in moves:
            move = moves[name]
            enemy = second if p.faction == first else first
            coef = counter_coefficient(tuning, move, mixes[enemy]) if mixes[enemy] else 1.0
            if p.role == "lore" and coef < 1:  # 參謀：被剋時吃虧少一些
                coef = 1 - (1 - coef) * (1 - tuning.role_counter_relief)
            fx = war(name, p, move, coef)
            if fx.unbeaten:  # 無隙：被剋也不吃虧
                coef = max(coef, 1.0)
            might = p.scores.get(move, 0.0) * condition(p) * coef * fx.force
            might *= 1 + sum(pct for who, pct in rally.get((p.faction, move), []) if who != name)
            force[p.faction] += might  # 份量在扣這一回合的血之前算
            shares[p.faction].append((might, name, move))
            counts[p.faction] += 1
            coefs[p.faction].append(coef)
            fitness[p.faction].append((p.scores.get(move, 0.0), condition(p)))
            damage = tuning.damage[move] * (2 - coef)
            if move == "強攻":
                damage *= 1 - min(tuning.strong_mitigation_cap, p.power / 200)
            damage *= fx.damage
            p.last_result = f"{move}（剋制 ×{coef:.1f}）"
            p.moves[rnd_no] = move + ("（逾時代選）" if name in instance.round.auto_picked else "") + "".join("；" + x for x in fx.lines)
        else:  # 這個人這回合沒有三招可算（選項不在這一幕、不在交戰雙方、放手一搏卻沒有賭局設定）：不推戰局、不扣血
            continue
        p.neili = max(0.0, p.neili - damage)
        if p.neili <= 0 and not p.eliminated:
            p.eliminated = True
            p.fell_round = instance.round_number + 1  # 這一回合（round_number 結算完才加一）
            msgs.append(f"{name}氣血耗盡，倒在戰場上，退出了這場戰鬥（轉為觀戰）。")
    harmed: dict[str, float] = {}  # 這一回合每個人被別人打掉多少（點名＋集火，target_round_cap）
    for hit in hits:
        msgs[hit.index], fixed, numbers = _land_hit(instance, tuning, hit, harmed, msgs)
        if fixed and hit.text:
            tale(hit.attacker, instance.participants[hit.attacker], hit.text, True, hit.target, fixed, numbers)
    msgs += _focus_fire(instance, tuning, moves, factions, (first, second), names, act_index, harmed)
    for hurt_name, amount in harmed.items():  # 被盯上打掉了氣血、回合結束還站著：戰功（撐住）
        q = instance.participants.get(hurt_name)
        if q is not None and amount >= 0.5 and not q.eliminated:
            q.stood_marked += 1
    instance.last_targets = targets_now
    # 同一邊同一回合放手一搏合起來有上限，成了的與失手的分開夾（Joy 2026-10-15「成功另算」）：失手的合起來最多退
    # side_trend_cap（一群人亂寫拖不垮全軍），成了的照人數疊、最多推 success_trend_cap
    if definition.free_text_gamble is not None:
        gamble = definition.free_text_gamble
        back_cap = gamble.side_trend_cap
        push_cap = gamble.success_trend_cap if gamble.success_trend_cap is not None else back_cap
        for side in list(gambles):
            up, down = gains.get(side, 0), losses.get(side, 0)
            up_capped, down_capped = min(push_cap, up), max(-back_cap, down)
            gambles[side] = up_capped + down_capped
            if up_capped != up:
                msgs.append(f"各路奇招互相牽扯，{names.get(side, side)}這一回合成了的放手一搏合起來只把戰線推前了{shove_size(up_capped)}。")
            if down_capped != down:
                msgs.append(f"各路奇招互相牽扯，{names.get(side, side)}這一回合失手的放手一搏合起來只讓戰線退了{shove_size(down_capped)}。")
    gamble_delta = sum((1 if side == first else -1) * d for side, d in gambles.items())
    push = 0.0
    if counts[first] or counts[second]:
        mine = force[first] / math.sqrt(counts[first]) * diversity(instance, moves, first, tuning) if counts[first] else 0.0
        theirs = force[second] / math.sqrt(counts[second]) * diversity(instance, moves, second, tuning) if counts[second] else 0.0
        if not counts[second]:
            push = tuning.push_max
        elif not counts[first]:
            push = -tuning.push_max
        elif mine + theirs > 0:
            push = tuning.push_max * (mine - theirs) / (mine + theirs)
        sides = "；".join(
            f"{names[side]}：" + "・".join(f"{m} {round(mixes[side][m] * 100)}%" for m in MOVES)
            for side in (first, second) if mixes[side]
        )
        # 這一行放在這一回合訊息的最前面（只進戰報，場景上拿掉，見 without_mix_line）；推了多少照 shove 的說法，數字記在 RoundSwing.fixed
        leader = names[first] if round(push) > 0 else names[second]
        moved = f"三招交鋒，戰線往{leader}那邊推了{shove_size(round(push))}" if round(push) else "三招交鋒，兩軍持平"
        msgs.insert(0, f"{sides}（{moved}）")
    instance.trend = max(0, min(100, instance.trend + round(push) + gamble_delta))
    for side in (first, second):  # 這一回合哪一邊有人發動本命戰法（放在固定句之後，回合原因之前插在第二行）
        if fired.get(side):
            msgs.append(tactics.WAR_LINE.format(side=names[side], who="；".join(fired[side])))
    if tactic is not None:
        gained = instance.trend - trend_before
        for q in instance.participants.values():
            if q.kit is not None and not q.eliminated:
                won = gained > 0 if q.faction == first else gained < 0
                tactics.war_close(q.kit, won, tactic, _war_rng(instance, q.name, rnd_no, "收"))
    instance.last_mix = mixes
    instance.round_number += 1
    # 這一回合為什麼往哪邊推（試玩回饋 2026-10-08：全是官軍卻輸了，卻看不出為什麼）：放在場景上看得到的第一行
    auto = {side: sum(1 for n in moves if factions[n] == side and n in instance.round.auto_picked) for side in (first, second)}
    leads = _leads(instance, shares, mixes, tuning, push, (first, second))
    causes = round_causes(names, (first, second), push, counts, mixes, coefs, gambles, auto, fitness, leads, tuning.lead_crowd)
    msgs.insert(1 if counts[first] or counts[second] else 0, round_line(names, (first, second), trend_before, instance.trend, causes))
    instance.swings.append(RoundSwing(
        round=instance.round_number, delta=instance.trend - trend_before, causes="；".join(causes), fixed=round(push),
    ))
    decisive = abs(instance.trend - CENTER) >= definition.decisive_margin
    if decisive or instance.round_number >= total_rounds(definition):
        msgs += _record_outcome(instance, decide_outcome(instance, definition))
        instance.outcome_reason = outcome_reason(instance, definition)
        if instance.outcome_reason:
            msgs.append(instance.outcome_reason)
    else:
        # 只往後換：回合上限之前就開打的舊資料，round_number 從 0 數起，不能把幕倒退回去
        next_act = min(instance.round_number // definition.rounds_per_act, len(definition.acts) - 1)
        if next_act > instance.act_index:
            instance.act_index = next_act
            act = current_act(instance, definition)
            msgs.append(f"【{act.title}】{act_text(instance, definition)}")
    instance.rounds.append(BattleRoundRecord(
        act_index=act_index, round_number=instance.round_number, resolved_real=now,
        actions=dict(instance.round.pending_actions), custom_texts=dict(instance.round.custom_texts),
        success_rates=dict(instance.round.success_rates), messages=list(msgs), trend_after=instance.trend,
    ))
    del instance.tales[:-TALES_KEPT]  # 沒有伺服器補劇情（假人程式、測試、腳本）時不會一直長
    instance.round = BattleRound(opened_real=now)
    return msgs


def _war_rng(instance: BattleInstance, name: str, round_: int, what: str = "") -> random.Random:
    """決戰裡本命戰法的亂數：自己一份，不碰回合結算的 rng（沒帶戰法的人一場打下來一個字都不變）。"""
    return random.Random(f"決戰|{instance.battle_id}|{instance.record_id}|{round_}|{name}|{what}")


TALES_KEPT = 60  # 等著補劇情的放手一搏最多留幾筆（一回合二十人搏也留得下三回合）


class _Hit(NamedTuple):
    """一次點名成了的放手一搏，等這一圈結算完才扣被點名的人（_land_hit）。index 是訊息先佔好的位置。"""

    index: int
    attacker: str
    target: str
    want: float
    pin: bool
    story: str
    side_name: str
    delta: int
    damage: float
    text: str = ""  # 玩家寫的那一句（沒有現成劇情時記一筆等著補，GambleTale）


def _harm(tuning: BattleTuning, q: BattleParticipant, want: float, harmed: dict[str, float]) -> float:
    """別人這一回合打掉 q 的氣血：不超過他剩的、也不超過這一回合被打的上限（target_round_cap，免得被圍毆秒殺）。"""
    room = q.neili_cap * tuning.target_round_cap - harmed.get(q.name, 0.0)
    hit = max(0.0, min(want, room, q.neili))
    q.neili -= hit
    q.hurt_taken += hit
    harmed[q.name] = harmed.get(q.name, 0.0) + hit
    return hit


def _fell(instance: BattleInstance, q: BattleParticipant, msgs: list[str]) -> None:
    if q.neili <= 0 and not q.eliminated:
        q.eliminated = True
        q.fell_round = instance.round_number + 1
        msgs.append(f"{q.name}氣血耗盡，倒在戰場上，退出了這場戰鬥（轉為觀戰）。")


def _land_hit(
    instance: BattleInstance, tuning: BattleTuning, hit: _Hit, harmed: dict[str, float], msgs: list[str],
) -> tuple[str, str, str]:
    """點名的放手一搏成了：扣被點名的人、記帳；險招成了他下一回合被牽制。回傳那一搏的訊息（劇情＋括號裡的數字），
    加上沒有現成劇情時先播的固定句與括號裡的數字（等著補劇情，GambleTale；有劇情時兩個都是空字串）。"""
    q, me = instance.participants[hit.target], instance.participants[hit.attacker]
    dealt = _harm(tuning, q, hit.want, harmed)
    me.hurt_dealt += dealt
    if dealt >= 0.5:
        me.hits_landed += 1
    pinned_now = hit.pin and q.neili > 0
    if pinned_now:
        q.pinned_round = instance.round_number + 2  # 這一回合是第 round_number＋1 回合，牽制的是下一回合
    numbers = f"{shove(hit.side_name, hit.delta)}，{q.name}氣血 -{round(dealt)}，自己氣血 -{round(hit.damage)}"
    fixed = "" if hit.story else f"{hit.attacker}這一搏成功了，正中{q.name}！{numbers}。"
    line = f"{hit.story}（{numbers}）" if hit.story else fixed
    if pinned_now:
        line += f"{q.name}被牽制住了，下一回合只能固守。"
    _fell(instance, q, msgs)
    return line, fixed, numbers if fixed else ""


def _focus_fire(
    instance: BattleInstance, tuning: BattleTuning, moves: dict[str, str], factions: dict[str, str],
    armies: tuple[str, str], names: dict[str, str], act_index: int, harmed: dict[str, float],
) -> list[str]:
    """引人注目：對面這一回合每一個出強攻的人，另外有 focus_per_attacker 的傷害平分到這一邊這一幕顯眼的人身上
    （每人最多他上限的 focus_cap，也受 target_round_cap 夾）。"""
    out: list[str] = []
    for side in armies:
        enemy = armies[1] if side == armies[0] else armies[0]
        attackers = sum(1 for n, m in moves.items() if factions.get(n) == enemy and m == "強攻")
        marked = [
            q for q in instance.participants.values()
            if q.faction == side and not q.eliminated and not q.away and instance.marked.get(q.name) == act_index
        ]
        if not attackers or not marked or tuning.focus_per_attacker <= 0:
            continue
        each = tuning.focus_per_attacker * attackers / len(marked)
        landed = []
        for q in marked:
            dealt = _harm(tuning, q, min(each, q.neili_cap * tuning.focus_cap), harmed)
            if dealt >= 0.5:
                landed.append(f"{q.name}氣血 -{round(dealt)}")
        if landed:
            out.append(f"{names.get(enemy, enemy)}的強攻盯著顯眼的人打：{'、'.join(landed)}。")
        for q in marked:
            _fell(instance, q, out)
    return out


def _leads(
    instance: BattleInstance, shares: dict[str, list[tuple[float, str, str]]], mixes: dict[str, dict[str, float]],
    tuning: BattleTuning, push: float, armies: tuple[str, str],
) -> dict[str, tuple[str, str, int]]:
    """每一邊這一回合帶頭出固定招的人：出得最多的那一招裡力量最大的那一個（名號, 招, 出這一招的人數）。
    推力往哪邊，那一邊帶頭的人記一個 led_rounds（戰報寫）。帶頭只從自己下令的人裡挑、人數也只算他們：逾時被代為固守的
    （round.auto_picked）照記固守的基本戰功，但不算帶頭、回合原因與勝負的關鍵都不寫他；這一招都是代選的就沒有帶頭的人（FB-181）。"""
    out: dict[str, tuple[str, str, int]] = {}
    auto = set(instance.round.auto_picked)
    for side in armies:
        if not shares[side]:
            continue
        move = _main_move(mixes[side])
        crew = [row for row in shares[side] if row[2] == move and row[1] not in auto]
        if not crew:
            continue
        _, lead, _ = max(crew, key=lambda row: (row[0], row[1]))
        out[side] = (lead, move, len(crew))
    shift = round(push)
    winner = armies[0] if shift > 0 else armies[1] if shift < 0 else None
    if winner in out:
        instance.participants[out[winner][0]].led_rounds += 1
    return out


def lead_clause(lead: tuple[str, str, int], crowd: int, with_move: bool = True) -> str:
    """「張三帶頭強攻」／「張三等 4 人結成強攻陣勢」；前一句已經寫了招（剋住的那一句）就不再寫招：「張三一馬當先」／「張三等 4 人結成陣勢」。"""
    name, move, count = lead
    if count >= crowd:
        return f"{name}等 {count} 人結成{move if with_move else ''}陣勢"
    return f"{name}帶頭{move}" if with_move else f"{name}一馬當先"


def _main_move(mix: dict[str, float]) -> str:
    """這一邊這回合出得最多的那一招（一樣多時照 MOVES 的順序）。"""
    return max(MOVES, key=lambda m: mix.get(m, 0.0))


def round_causes(
    names: dict[str, str], armies: tuple[str, str], push: float, counts: dict[str, int], mixes: dict[str, dict[str, float]],
    coefs: dict[str, list[float]], gambles: dict[str, int], auto: dict[str, int],
    fitness: dict[str, list[tuple[float, float]]] | None = None, leads: dict[str, tuple[str, str, int]] | None = None,
    crowd: int = 3,
) -> list[str]:
    """這一回合戰局為什麼這樣走，寫成幾句話（試玩回饋 2026-10-08：輸了要看得懂為什麼）。都照結算的數字挑，不叫模型：
    - 三招交鋒（推力不是 0）：對面沒人正面出招 → 一邊壓上；平均剋制係數差到 0.2 → 誰的哪招剋住誰的哪招；
      人數差到 1.5 倍 → 人多；都不是 → 份量（武藝）與氣血狀態，兩者裡差得多的那一個（fitness 是每個人的（份量, 氣血狀態））；
    - 放手一搏：每一邊這一回合賭贏賭輸的淨推動（失手寫倒退多少）；
    - 逾時沒出手、被系統代為固守的人數（固守會被奇襲剋）。
    leads 給了，佔上風那一邊帶頭出固定招的人接在第一句後面（Joy 2026-10-10：「跟從預設選項的玩家……應該也要有出場機會」）。"""
    out: list[str] = []
    shift = round(push)
    if shift:
        win, lose = (armies[0], armies[1]) if shift > 0 else (armies[1], armies[0])
        w, lo = names.get(win, win), names.get(lose, lose)
        lead = (leads or {}).get(win)
        tail = f"，{lead_clause(lead, crowd)}" if lead else ""
        if not counts[lose]:
            out.append(f"{lo}沒有人正面出陣迎戰，{w}放手壓了上去{tail}")
        else:
            avg = {side: sum(coefs[side]) / len(coefs[side]) for side in armies if coefs[side]}
            if avg.get(win, 1.0) - avg.get(lose, 1.0) >= 0.2:
                tail = f"，{lead_clause(lead, crowd, with_move=False)}" if lead else ""
                out.append(f"{w}的{_main_move(mixes[win])}剋住了{lo}的{_main_move(mixes[lose])}{tail}")
            elif counts[win] >= 1.5 * counts[lose]:
                out.append(f"{w}人多勢眾（{counts[win]} 人對 {counts[lose]} 人）{tail}")
            else:
                out.append(_edge(w, lo, (fitness or {}).get(win, []), (fitness or {}).get(lose, [])) + tail)
    for side in armies:
        delta = gambles.get(side, 0)
        if delta < 0:
            out.append(f"{names.get(side, side)}有人放手一搏失手，戰線退了{shove_size(delta)}")
        elif delta > 0:
            out.append(f"{names.get(side, side)}有人放手一搏得手，把戰線推前了{shove_size(delta)}")
    for side in armies:
        if auto.get(side):
            out.append(f"{names.get(side, side)}有 {auto[side]} 人遲遲沒有下令，只能原地固守")
    return out


def _edge(w: str, lo: str, mine: list[tuple[float, float]], theirs: list[tuple[float, float]]) -> str:
    """出招沒剋、人數也差不多時，贏的一方贏在哪：平均份量（武藝）與平均氣血狀態，比例差得多的那一個。"""
    def avg(rows: list[tuple[float, float]], i: int) -> float:
        return sum(r[i] for r in rows) / len(rows) if rows else 0.0

    ratio = [avg(mine, i) / avg(theirs, i) if avg(theirs, i) > 0 else math.inf for i in (0, 1)]
    if ratio[1] > ratio[0]:
        return f"{lo}氣血耗損，漸漸撐不住{w}"
    return f"{w}的武藝更勝一籌"


def round_line(names: dict[str, str], armies: tuple[str, str], before: int, after: int, causes: list[str]) -> str:
    """場景上這一回合的第一行：誰佔了上風、把戰線往他那邊推了多少（shove 的說法，不寫數字；數字畫在戰局條上），再接原因。"""
    if after != before:
        side = names.get(armies[0], armies[0]) if after > before else names.get(armies[1], armies[1])
        head = f"這一回合{side}佔了上風，把戰線往自己這邊推了{shove_size(after - before)}"
    else:
        head = "這一回合兩軍相持不下，戰線沒有動"
    return head + ("：" + "；".join(causes) + "。" if causes else "。")


MERIT_TOP = 3  # 戰局條旁「本場戰功」每一邊列幾個人
MERIT_PARTS = (  # 戰功的每一項怎麼寫（順序就是戰報與畫面上的順序）
    ("acted", "出手 {n} 回合"), ("held", "代為固守 {n} 回合"), ("led", "帶頭佔上風 {n} 回合"), ("gamble", "搏成 {n} 次"),
    ("hit", "點名打傷 {n} 次"), ("stood", "被盯上撐住 {n} 回合"),
)


def merit_counts(p: BattleParticipant) -> dict[str, int]:
    return {"acted": p.acted_rounds, "held": p.held_rounds, "led": p.led_rounds, "gamble": p.gambles_won, "hit": p.hits_landed, "stood": p.stood_marked}


def merit(tuning: BattleTuning, p: BattleParticipant) -> int:
    """個人戰功（Joy 2026-10-10：「戰線推進是陣營，個人的部分有辦法做出戰績跟區別嗎」）：每一項照 BattleTuning.merit_points 記分。"""
    return sum(tuning.merit_points.get(key, 0) * n for key, n in merit_counts(p).items())


def merit_parts(p: BattleParticipant) -> list[str]:
    counts = merit_counts(p)
    return [text.format(n=counts[key]) for key, text in MERIT_PARTS if counts[key]]


def merit_ranking(instance: BattleInstance, tuning: BattleTuning, side: str) -> list[tuple[BattleParticipant, int]]:
    """一邊的參戰者照戰功排（同分照名號，免得每次刷新順序亂跳）。"""
    rows = [(p, merit(tuning, p)) for p in instance.participants.values() if p.faction == side]
    return sorted(rows, key=lambda row: (-row[1], row[0].name))


def top_merit(instance: BattleInstance, tuning: BattleTuning, side: str) -> BattleParticipant | None:
    """這一邊的首功：自己至少按過一招的人裡戰功最高、至少 1 分的那一個；一邊全員都沒按過就從缺。
    代為固守的回合照算戰功，但全程掛機的人不拿首功（PM 2026-10-10：認真打的人看了不服）。"""
    return next((p for p, m in merit_ranking(instance, tuning, side) if m > 0 and p.acted_rounds > 0), None)


def merit_board(
    instance: BattleInstance, tuning: BattleTuning, left: str, right: str, viewer: str | None,
) -> dict:
    """戰局條旁的「本場戰功」：兩邊各列前 MERIT_TOP 名（戰功 0 的不列）、看的人自己在自己那一邊排第幾、戰功怎麼來的。"""
    board: dict = {"me": None}
    for key, side in (("left", left), ("right", right)):
        ranking = merit_ranking(instance, tuning, side)
        board[key] = [{"name": p.name, "merit": m, "mine": p.name == viewer} for p, m in ranking[:MERIT_TOP] if m > 0]
        for rank, (p, m) in enumerate(ranking, 1):
            if p.name == viewer:
                board["me"] = {"rank": rank, "of": len(ranking), "merit": m, "parts": merit_parts(p)}
    return board


def gauge(
    instance: BattleInstance, definition: BattleDef, viewer_side: str | None, timetable: bool,
    tuning: BattleTuning | None = None, viewer: str | None = None,
) -> dict:
    """決戰畫面的即時戰局條（Joy 2026-10-10 轉玩家反饋：「有辦法看即時戰局？」）：拔河，兩軍各佔一頭，數字只畫在這裡。

    左邊是看的人那一邊（兩軍以外的人看第一方在左）；lean 是「往左邊那一方偏多少」（0～100，100 是左邊大獲全勝），
    網頁把旗子畫在 100−lean：誰佔上風，旗子就被拉到誰那一頭。zones 是分勝負的那一截（時刻表決戰是偏離中線 BIG_WIN_MARGIN
    的大勝，其餘照 outcomes 的門檻），decisive 是偏離中線多少當場收場。rounds 是每一回合從哪裡到哪裡、誰佔上風。
    merit 是條旁的「本場戰功」（merit_board；viewer 是看的人的名號）。"""
    first, second = definition.factions[0].id, definition.factions[1].id
    names = {f.id: f.name for f in definition.factions}
    left = viewer_side if viewer_side in (first, second) else first
    right = second if left == first else first

    def lean(trend: int) -> int:
        return trend if left == first else 100 - trend

    def span(lo: int, hi: int) -> tuple[int, int]:  # 戰局座標的一段換成 lean 座標
        a, b = lean(lo), lean(hi)
        return min(a, b), max(a, b)

    zones: list[dict] = []
    if timetable:
        for side, (lo, hi) in ((first, (CENTER + BIG_WIN_MARGIN, 100)), (second, (0, CENTER - BIG_WIN_MARGIN))):
            a, b = span(lo, hi)
            zones.append({"from": a, "to": b, "side": "left" if side == left else "right", "label": f"{names[side]}大勝"})
    else:
        for o in definition.outcomes:
            if o.trend_min is None and o.trend_max is None or o.faction not in (first, second):
                continue
            a, b = span(o.trend_min if o.trend_min is not None else 0, o.trend_max if o.trend_max is not None else 100)
            zones.append({"from": a, "to": b, "side": "left" if o.faction == left else "right", "label": o.title})
    start = instance.trend_start if instance.trend_start is not None else (instance.trend if instance.phase == "muster" else CENTER)
    rounds, at = [], start
    for s in instance.swings:
        after = max(0, min(100, at + s.delta))
        mover = "tie" if after == at else ("left" if lean(after) > lean(at) else "right")
        rounds.append({"n": s.round, "from": lean(at), "to": lean(after), "side": mover})
        at = after
    now = lean(instance.trend)
    leader = left if now > CENTER else right if now < CENTER else None
    if instance.phase == "ended":
        caption = instance.outcome_title or "收場"
    elif instance.phase == "muster":
        caption = (f"集結中：開戰時戰線偏向{names[leader]}{shove_size(now - CENTER)}" if leader
                   else "集結中：開戰時戰線在正中間")
    elif leader is None:
        caption = "兩軍不分上下，戰線在正中間"
    else:
        gap = definition.decisive_margin - abs(now - CENTER)
        caption = f"{names[leader]}佔上風；再推{shove_size(gap)}就當場分出勝負"
    return {
        "name": definition.name, "phase": instance.phase,
        "round": instance.round_number + (0 if instance.phase == "ended" else 1), "total": total_rounds(definition),
        "left": {"id": left, "name": names[left], "mine": viewer_side == left},
        "right": {"id": right, "name": names[right], "mine": viewer_side == right},
        "lean": now, "start": lean(start), "decisive": definition.decisive_margin, "zones": zones, "rounds": rounds,
        "caption": caption,
        "merit": merit_board(instance, tuning or BattleTuning(), left, right, viewer),
    }


KEY_ROUNDS = 2  # 敗因最多舉幾個回合


def outcome_reason(instance: BattleInstance, definition: BattleDef) -> str:
    """收場時寫勝負的關鍵（試玩回饋 2026-10-08）：戰局停在哪一邊（剛好 50 不寫），就挑往那一邊推得最多的幾個回合
    （最多 KEY_ROUNDS 個，照回合先後寫），連同那一回合的原因；開打時起點就偏向贏家的也寫一句。只看公開的戰局，不看伏筆鎖定。"""
    first, second = definition.factions[0].id, definition.factions[1].id
    names = {f.id: f.name for f in definition.factions}
    if instance.trend == CENTER:
        return ""
    winner, sign = (first, 1) if instance.trend > CENTER else (second, -1)
    parts: list[str] = []
    start = instance.trend_start
    if start is not None and (start - CENTER) * sign > 0:
        parts.append(f"開戰時{names[winner]}就佔了地利，戰線一開始就偏向他們")
    key = sorted((s for s in instance.swings if s.delta * sign > 0 and s.causes), key=lambda s: -abs(s.delta))[:KEY_ROUNDS]
    parts += [f"第 {s.round} 回合，{s.causes}" for s in sorted(key, key=lambda s: s.round)]
    return f"勝負的關鍵：{'；'.join(parts)}。" if parts else ""


def overruled_reason(instance: BattleInstance, definition: BattleDef, lock_side: str | None, defender: str) -> str:
    """時刻表決戰收場時，伏筆鎖定的一方贏了、戰場上卻是另一方佔上風：勝負的關鍵改寫這一句（原本那一句寫的是戰場上的贏家）。
    戰場上的贏家跟最後的贏家是同一方就是空字串（照舊用 outcome_reason）。"""
    field, _ = result_at(instance.trend, definition, None, defender)
    winner, _ = result_at(instance.trend, definition, lock_side, defender)
    if field == winner:
        return ""
    name = next((f.name for f in definition.factions if f.id == field), field)
    return f"勝負的關鍵：戰場上{name}佔了上風，卻沒能扭轉大局。"


def _record_outcome(instance: BattleInstance, outcome: BattleOutcome) -> list[str]:
    """把終局記到戰鬥上（套用到共用賽季是呼叫端 engine.py 的事，見 BattleInstance 的欄位註解），
    回傳要給大家看的兩行。"""
    instance.phase = "ended"
    instance.outcome_title, instance.outcome_text = outcome.title, outcome.text
    if outcome.trend_min is not None or outcome.trend_max is not None:  # 有門檻的才是分出了勝負；最後那個保底是膠著
        instance.outcome_side = outcome.faction
        instance.outcome_margin = "大勝" if abs(instance.trend - CENTER) >= BIG_WIN_MARGIN else "險勝"
    instance.outcome_world_flags = list(outcome.world_flags_add)
    instance.outcome_trend_delta = dict(outcome.trend_delta)
    return [f"══ {outcome.title} ══", outcome.text]


def end_without_fighters(
    instance: BattleInstance, definition: BattleDef, now: float, tuning: BattleTuning | None = None,
) -> list[str]:
    """場上已經沒有任何還能打的人（沒人參戰、或全都倒下了），而且這一回合已經逾時：
    沒有人能送出行動，round_is_complete 永遠不會成立，這場戰鬥就會永遠卡著——這時直接用
    內容最後那個無條件的保底結果（definition.outcomes[-1]，content.py::validate 保證它
    沒有門檻）收場，記錄方式跟 resolve_round 分出勝負時一樣。這裡沒有 LLM 潤色，收場的
    幾句話直接寫進 narrative_log。還有人在場、還在集結、或回合還沒逾時，什麼都不做、回傳空清單。"""
    armies = {f.id for f in definition.factions}
    if instance.phase != "active" or any(p.faction in armies for p in _active_participants(instance)):
        return []
    if now - instance.round.opened_real < definition.round_seconds:
        return []
    msgs = ["戰場上已經沒有人還能出手，這場戰鬥就此收場。"] + _record_outcome(instance, definition.outcomes[-1])
    instance.narrative_log.append("\n".join(msgs))
    instance.round_number += 1  # 這一回合逾時過去了，也算一回合
    instance.rounds.append(BattleRoundRecord(
        act_index=instance.act_index, round_number=instance.round_number, resolved_real=now,
        messages=list(msgs), trend_after=instance.trend,
    ))
    instance.round = BattleRound(opened_real=now)
    return msgs


def decide_outcome(instance: BattleInstance, definition: BattleDef) -> BattleOutcome:
    """從戰局決定結果：照 definition.outcomes 的順序，取第一個戰局落在門檻內的。最後那個沒有門檻的保底
    （content.py::validate 保證有）一定接得住，所以一定有結果。打完最後一回合與壓倒性提前收場都走這裡
    （戰鬥系統設計 3.2）。沒人能打的收場不走這裡，見 end_without_fighters。時刻表決戰的 outcomes 只有一筆保底，
    真正的結果（含伏筆鎖定誰贏，第四節）由 engine 在收場後照 decide_result 判、交給時刻表。"""
    for outcome in definition.outcomes:
        lo, hi = outcome.trend_min, outcome.trend_max
        if (lo is None or instance.trend >= lo) and (hi is None or instance.trend <= hi):
            return outcome
    return definition.outcomes[-1]


def decide_result(
    instance: BattleInstance, definition: BattleDef, lock_side: str | None, defender: str,
) -> tuple[str, str]:
    """時刻表決戰的結果（戰鬥系統 4.1、4.2）：回傳（贏家, "大勝" | "險勝"），贏家是 factions 的 id（guan／huang）。
    - 戰場上的贏家：戰局以 factions[0]（官軍）為正向，高於 50 是它、低於 50 是另一方，剛好 50 算守方守住（沒有膠著）；
      偏離 50 達 BIG_WIN_MARGIN（65 以上、35 以下）是大勝，否則險勝。
    - 有人鎖定（lock_side 是交戰的一方）：鎖定方一定贏，戰場上也贏是大勝、打輸是險勝。
    只有收場這一刻看鎖定（呼叫端讀 WorldState.locks 傳進來）；起點、推力、選項都不看，鎖定才不會在戰場上露出來（4.3）。"""
    return result_at(instance.trend, definition, lock_side, defender)


def result_at(trend: int, definition: BattleDef, lock_side: str | None, defender: str) -> tuple[str, str]:
    """decide_result 的本體，戰局直接給數字：從沒開成的決戰在季末收季前照起點判（world.settle_waiting_showdowns）也用它。"""
    first, second = definition.factions[0].id, definition.factions[1].id
    if trend == CENTER:
        field = defender
    else:
        field = first if trend > CENTER else second
    big = abs(trend - CENTER) >= BIG_WIN_MARGIN
    if lock_side not in (first, second):
        return field, "大勝" if big else "險勝"
    return lock_side, "大勝" if field == lock_side else "險勝"


BOT_BEST_MOVE_CHANCE = 0.7  # 機器人出自己份量最高的那一招的機率，其餘三成在三招裡隨便挑


def bot_choose_action(
    instance: BattleInstance, definition: BattleDef, name: str, rng: random.Random, tuning: BattleTuning | None = None,
) -> str | None:
    """機器人這回合要選什麼：七成出自己份量最高的那一招、三成在三招裡隨便挑
    （份量全一樣——例如沒有快照的舊資料全是 0——取損耗最低的固守，不是列在最前面的那一招）——這樣測試戰鬥用機器人
    湊場時行為會有變化，不會每次都選同一個，也不會像真的 AI 一樣聰明判斷局勢（那不是這裡的目標，
    設計討論原文：「不會全程 LLM 自由發展...大框架還是會進行下去」，機器人只是補位湊人數，
    不需要聰明）。正式營運時要用機器人增加活躍感，也是同一套函式。故意排除 free_text
    選項——機器人不會自己想出一段有意義的描述，用它只會得到一句空話，交給固定選項就好。
    （伺服器假人不走這裡：它們是一般參戰者，照 bot_policy 挑。）這一幕沒有三招可選就回 None。"""
    fixed = fixed_options(instance, definition, name)
    if not fixed:
        return None
    tuning = tuning or BattleTuning()
    p = instance.participants[name]
    if rng.random() < BOT_BEST_MOVE_CHANCE:
        return max(fixed, key=lambda o: (p.scores.get(o.move, 0.0), -tuning.damage[o.move])).tag
    return rng.choice(fixed).tag


class SuccessRateJudgment(BaseModel):
    success_rate: int = DEFAULT_FREE_TEXT_SUCCESS_RATE
    reasoning: str = ""
    win: str = ""  # 成功的那一版劇情（40 字內，試玩回饋 2026-10-08）
    lose: str = ""  # 失敗的那一版劇情


class GambleVerdict(NamedTuple):
    """評一次放手一搏：成功率，加上擲骰前先寫好的兩版劇情（成功、失敗；寫壞的是空字串，那一版就用固定句）。"""

    rate: int
    win: str = ""
    lose: str = ""


STORY_LIMIT = 60  # 劇情要模型寫 40 字內；多給一點餘裕，超過的整段不用（截斷的半句話比固定句難看）
_DIGITS = re.compile(r"[0-9０-９]")


def clean_story(raw: str, name: str) -> str:
    """模型寫的一版劇情整理成能播的一句：轉繁體、去掉換行與 markdown、引號；有阿拉伯數字（數字只能是引擎的）、太長、
    空的都不用（回空字串）。用「你」「妳」的也不用（FB-183：進天下大事與雙方的戰報，要第三人稱；名號裡本來就有的不算）。
    不是以名號開頭的補上名號，名號後面接冒號的換成逗號，句尾補句號。"""
    text = zh.to_traditional(str(raw or ""))
    text = re.sub(r"[\s*#>`_]+", "", text).strip("「」『』\"'“”")
    if not text or len(text) > STORY_LIMIT or _DIGITS.search(text):
        return ""
    if any(ch in (text.replace(name, "") if name else text) for ch in "你妳"):
        return ""
    if name and text.startswith(name) and text[len(name):len(name) + 1] in ("：", ":"):
        text = name + "，" + text[len(name) + 1:]
    if not text.startswith(name):
        text = name + text
    return text if text[-1] in "。！？…" else text + "。"


def assess_action_success_rate(
    client: OllamaClient | None, act: BattleAct, faction_name: str, text: str,
) -> int:
    """只要成功率（舊的呼叫端）：見 assess_gamble。"""
    return assess_gamble(client, act, faction_name, text).rate


def assess_gamble(
    client: OllamaClient | None, act: BattleAct, faction_name: str, text: str, name: str = "",
    setting: str = "漢末兩軍交戰的戰場", place: str = "戰場", target: str = "", sex: str = "男",
) -> GambleVerdict:
    """請 LLM 評估這段自訂行動聽起來有多可能成功（0~100）——只評機率，不評「成不成功」
    本身（那是 resolve_round 擲骰決定的），也不會被拿去當作任何數值直接套用，只是擲骰
    用的機率輸入。連不上/生成失敗/格式不對都回傳保底值（見 DEFAULT_FREE_TEXT_SUCCESS_RATE），
    不會讓整個行動失敗——這類評估本來就是錦上添花，寧可給一個偏低的保守值，也不要卡住
    玩家的回合。
    act 只讀 title 與 text（單人頭目戰傳 duel 的 Scene）；setting、place 換掉提示裡的「漢末兩軍交戰的戰場」與「戰場」。
    target 是玩家點名的對手（target_line，引擎認的）：多給模型一行，成功率要反映打的是誰。
    sex 是玩家的性別（gender）：女的提示多一行，劇情裡的稱呼跟著換（PM 2026-10-12）。"""
    if client is None:
        return GambleVerdict(DEFAULT_FREE_TEXT_SUCCESS_RATE)
    who = name or "這位" + gender.hero(sex)
    messages = [
        {"role": "system", "content": (
            f"你是{setting}判定系統，也是說書人。第一件事：評估玩家描述的行動在{place}上合理的成功機率，"
            "給出 0~100 的整數 success_rate 與一句話 reasoning（只根據行動本身的合理性，荒唐的行動就給低分）。"
            "第二件事：替這個行動寫兩版結果，win 是成功的那一版、lose 是失敗的那一版，各一句、40 字以內、繁體中文，"
            # 第三人稱：FB-183；身分不當代名詞、名號就是出手的人：FB-185（以前使用者訊息只寫「玩家所屬：散人」，真模型 18／18 寫成
            # 「驗收官見……散人趁勢……」，把名號當成旁觀的人、拿身分當出手的人）
            f"以「{who}」開頭、用第三人稱寫（不用「你」，名號後面不接冒號）；「{who}」就是出手的那個人，不是在一旁看的人；"
            "用名號稱呼雙方，不要拿「散人」「官軍」「黃巾」這類身分當代名詞。要具體接住玩家寫的內容，可以荒謬、好笑，失敗也要有戲（出糗、被識破、反被追打都行），"
            "不要寫任何數字、不要寫戰局推進多少或扣多少氣血，也不要替玩家決定最後的勝負以外的事。"
            + gender.prompt_line(sex)
        )},
        {"role": "user", "content": (
            f"{place}情境：【{act.title}】{act.text}\n玩家：{who}（所屬：{faction_name}）\n"
            + (f"玩家點名攻擊的對手：{target}\n" if target else "")
            + f"玩家的行動：「{text}」\n請給出 success_rate、reasoning、win、lose。"
        )},
    ]
    try:
        result = client.chat_structured(messages, SuccessRateJudgment, temperature=0.7, required_fields=["success_rate"])
    except Exception:
        return GambleVerdict(DEFAULT_FREE_TEXT_SUCCESS_RATE)
    rate = max(0, min(100, int(result.success_rate)))
    return GambleVerdict(rate, clean_story(result.win, who), clean_story(result.lose, who))


class GambleScore(BaseModel):
    success_rate: int = DEFAULT_FREE_TEXT_SUCCESS_RATE


SCORE_PREDICT = 24  # 只評成功率的那一次最多生幾個 token：{"success_rate": 35} 十個上下，多留一點不被截斷


def score_gamble(
    client: OllamaClient | None, act: BattleAct, faction_name: str, text: str, name: str = "",
    target: str = "", sex: str = "男",
) -> int:
    """決戰的放手一搏只評成功率（Joy 2026-10-13「這是我們效能問題，我們應該要做到能承受」：二十人同一回合各搏一次，
    每一個都要在回合結算前評到）：提示短、只要一個整數、num_predict 只給 SCORE_PREDICT，劇情等回合結算後一整回合批給
    write_tales 寫。跟 assess_gamble 同一套評法（只評行動本身合不合理，荒唐的給低分）；評不到回保底值。"""
    if client is None:
        return DEFAULT_FREE_TEXT_SUCCESS_RATE
    who = name or "這位" + gender.hero(sex)
    messages = [
        {"role": "system", "content": (
            "你是漢末兩軍交戰的戰場判定系統。評估玩家描述的行動在戰場上合理的成功機率，只回 0~100 的整數 success_rate："
            "只根據行動本身的合理性，荒唐、灌水、亂寫的行動給低分。"
        )},
        {"role": "user", "content": (
            f"戰場情境：【{act.title}】{act.text}\n玩家：{who}（所屬：{faction_name}）\n"
            + (f"玩家點名攻擊的對手：{target}\n" if target else "")
            + f"玩家的行動：「{text}」"
        )},
    ]
    try:
        result = client.chat_structured(
            messages, GambleScore, temperature=0.3, num_predict=SCORE_PREDICT, required_fields=["success_rate"],
        )
    except Exception:
        return DEFAULT_FREE_TEXT_SUCCESS_RATE
    return max(0, min(100, int(result.success_rate)))


class TaleItem(BaseModel):
    """寫劇情的單子上的一搏（GambleTale 拿掉場景記錄用的欄位，加上陣營的名字）。"""

    name: str
    faction_name: str
    text: str
    won: bool
    target: str = ""
    sex: str = "男"


class TaleLine(BaseModel):
    name: str = ""
    story: str = ""


class TaleBatch(BaseModel):
    lines: list[TaleLine] = Field(default_factory=list)


TALE_PREDICT_EACH = 90  # 一搏一句四十字上下，加上 JSON 的名號與括號
TALE_BATCH = 20  # 一次最多寫幾搏（一回合二十人都搏時一次寫完；再多下一次再寫）


def write_tales(
    client: OllamaClient | None, act: BattleAct, items: list[TaleItem], setting: str = "漢末兩軍交戰的戰場",
) -> dict[str, str]:
    """回合結算後，把這一回合等著補劇情的放手一搏一次批給模型寫（Joy 2026-10-13：評分與劇情拆開，二十人同時搏也撐得住）：
    成敗已經擲好了，一搏一句、照成敗寫，以名號開頭、第三人稱，不寫數字。回傳 名號 → 整理過的一句（clean_story）；
    寫壞的、名單外的、沒寫到的不在裡面（那一搏照舊播固定句）。模型失敗回空的。"""
    if client is None or not items:
        return {}
    women = {item.name for item in items if item.sex == "女"}
    listing = "\n".join(
        f"{i}. {item.name}（{item.faction_name}{'，女子' if item.name in women else ''}）："
        f"「{item.text}」——{'成功' if item.won else '失敗'}"
        + (f"，點名攻擊的對手是{item.target}" if item.target else "")
        for i, item in enumerate(items, 1)
    )
    messages = [
        {"role": "system", "content": (
            f"你是{setting}的說書人。下面每一位玩家這一回合都放手一搏，成敗已經定了。替每一位各寫一句結果：40 字以內、繁體中文，"
            "以那位玩家的名號開頭、用第三人稱寫（不用「你」，名號後面不接冒號）；名號就是出手的那個人，不是在一旁看的人；"
            "用名號稱呼雙方，不要拿「散人」「官軍」「黃巾」這類身分當代名詞。要具體接住玩家寫的內容，照成敗寫：成功就寫成了，"
            "失敗就寫出糗、被識破、反被追打，可以荒謬、好笑。不要寫任何數字、不要寫戰局推進多少或扣多少氣血。"
            "標了女子的玩家用「她」稱呼。回傳 lines：每一位一筆，name 照抄名號，story 是那一句。"
        )},
        {"role": "user", "content": f"戰場情境：【{act.title}】{act.text}\n這一回合的放手一搏：\n{listing}"},
    ]
    try:
        result = client.chat_structured(
            messages, TaleBatch, temperature=0.7, num_predict=64 + TALE_PREDICT_EACH * len(items), required_fields=["lines"],
        )
    except Exception:
        return {}
    wanted = {item.name for item in items}
    out: dict[str, str] = {}
    for line in result.lines:
        name = str(line.name or "").strip()
        if name in wanted and name not in out:
            story = clean_story(line.story, name)
            if story:
                out[name] = story
    return out


def tales_due(instance: BattleInstance) -> list[GambleTale]:
    """下一批要寫的：等著補劇情的最早那一回合的放手一搏（最多 TALE_BATCH 筆）。"""
    if not instance.tales:
        return []
    first = min(t.round for t in instance.tales)
    return [t for t in instance.tales if t.round == first][:TALE_BATCH]


def apply_tales(instance: BattleInstance, done: list[tuple[int, str]], stories: dict[str, str]) -> int:
    """寫好的劇情補回去：場景記錄（narrative_log）裡那一搏的固定句換成「劇情（數字）」，這個人那一回合的放手一搏（GambleMoment，
    戰報、行狀、最有戲的一幕都讀它）記下劇情。done 是這一批的（回合, 名號）：寫到沒寫到都從等著補的單子拿掉（寫不出來就照固定句，
    不重寫）。回傳補了幾句。"""
    keys = set(done)
    patched = 0
    for tale in [t for t in instance.tales if (t.round, t.name) in keys]:
        story = stories.get(tale.name)
        if not story:
            continue
        line = f"{story}（{tale.numbers}）"
        # 一回合一段：往後的回合（同一個人、同樣的數字可能寫出一模一樣的固定句）不碰，從那一回合那一段往前找
        start = min(len(instance.narrative_log) - 1, len(instance.narrative_log) - 1 - (instance.round_number - tale.round))
        for i in range(start, -1, -1):
            if tale.fixed in instance.narrative_log[i]:
                instance.narrative_log[i] = instance.narrative_log[i].replace(tale.fixed, line, 1)
                patched += 1
                break
        p = instance.participants.get(tale.name)
        moments = (p.gambles if p is not None else []) + ([instance.highlight] if instance.highlight is not None else [])
        for moment in moments:
            if moment.name == tale.name and moment.round == tale.round and not moment.story:
                moment.story = story
    instance.tales = [t for t in instance.tales if (t.round, t.name) not in keys]
    return patched


def without_mix_line(instance: BattleInstance, msgs: list[str]) -> list[str]:
    """這回合的系統訊息拿掉最前面那一行出招比例（resolve_round 在有人出固定招的回合才加那一行，而且一定放第一行；
    判斷看 instance.last_mix：任何一邊有比例就代表有那一行）。出招比例只留在回合紀錄（戰報）裡，
    場景上的記錄（narrative_log）不放它——場景已經有「對面上一回合」那一段，每回合再留一行 53 字會讓場景每回合多約 88px。"""
    return list(msgs[1:] if any(instance.last_mix.values()) else msgs)
