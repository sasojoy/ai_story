"""全服決戰的資料型別與「讀」的那一半判定（全部拆包第 54 批，同第 27 批 seal_base、第 21 批 duel_base）：原本在 tianxia/battle_instance.py，逐字搬來。
全服狀態（world_state、sqlite_world）存的 BattleInstance、BattleRoundRecord、SiegeInfo 這些資料型別，加上核心、共用規則層、舊模組、別的包非讀不可的那幾樣判定：
招式比重與誰還沒出招（move_scores、idle、strength）、戰功（merit、merit_counts）、攻城與三方混戰的名字（neutral_guard、melee、fields、side_names、GUARD、GUARD_SIDE）、
調度軍令（caller、call_orders）、開集結（start_muster、start_from_front、shift_deadlines）、收場的理由（outcome_reason、result_at、BLOW_REASON…）、
放手一搏的評分（assess_gamble、SuccessRateJudgment、GambleVerdict、clean_story、claims_a_kill）。

規則那一半（集結、出招、結算回合、畫面的字、鎖外評分與補劇情）在決戰包 tianxia/features/battle/instance.py，它 re-export 這裡全部的名字，舊名 tianxia/battle_instance.py
是指到它的別名。邊界測試不准核心、共用規則層、舊模組、別的包碰決戰包或它的別名，所以它們讀的都得留在這裡；這裡一個字都不讀決戰包。

誰讀：核心本體的 world_state、sqlite_world、world、team（函式裡，延後）、core/duel_base、core/seal_base；共用規則層的 chiefs、conquest、event_llm、siege；舊模組 tale、seal_duel、
bot_policy、bot_runner；engine；bout、seal、tale、territory_acts、looks、faction 幾包（bout、seal、tale 的鎖外路由也讀這裡，第二輪第 102 批）。讀的時候區域名照舊叫 battle_instance（from tianxia.core import battle_base as battle_instance）。

換掉 assess_gamble 的測試：放手一搏的路由（bout、seal 的 routes，第二輪第 102 批）與鎖內退路（duel_actions、arena_actions）讀這裡，test_server、單挑包的 test_bout_shell、test_arena_crowd、test_duel、test_arena
換這裡這一格；決戰的 view.py 讀決戰包那一格，換那裡。engine 的奪璽那一處也讀這裡，沒有測試換它。

核心本體（tianxia/core/ 底下的檔），不進 MODULES。
"""
from __future__ import annotations

from collections.abc import Sequence

import random
import re
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field, model_serializer

from .. import gender, tactics, zh
from ..models import BEATS, MOVES, BattleAct, BattleDef, BattleTuning
from ..ollama_client import OllamaClient

Phase = Literal["muster", "active", "ended"]

UNFINISHED_TITLE = "未分勝負"  # 季終收兵的決戰：結果標題與江湖紀錄標題的尾巴（FB-035）

CENTER = 50  # 戰局的中線：提前收場看偏離它多少（戰鬥系統 5.3），時刻表決戰的勝負也以它為界（4.1、4.2）
BIG_WIN_MARGIN = 15  # 時刻表決戰：戰局偏離中線達到這麼多是大勝，否則險勝（戰鬥系統 4.1【預設】）


DEFAULT_FREE_TEXT_SUCCESS_RATE = 40  # LLM 評估失敗/無 client 時的保底值——明顯偏低（放手一搏預設不利），
# 不是 50/50，呼應「不會全程 LLM 自由發展」的框架精神：評不出來就當作風險自負，不讓機制因為評估失敗而意外變得穩賺不賠。


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


class Escort(BaseModel):
    """隨主人上陣的歷史武將（歷史武將同行第五節；Config.companions）：加入決戰那一刻由主人自己的 Game 快照（Game._escort_of），
    存在主人那一筆 BattleParticipant.escort。不是參戰者——不佔人數、不等他、不拿軍餉、不進戰功榜。每回合照主人出的固定招出手
    （主人放手一搏、倒下時固守；主人離開大區時他也不在場上），份量 score 乘這一場的氣血狀態與剋制係數，算進那一邊。
    對面出強攻的集火平分打到這一邊的同伴、放手一搏寫到他的名字打得到他，同一邊出固守的人照人物的規則護他；池子打光就敗走
    （戰局往對面推 GeneralTuning.escort_fall_push）。本命戰法照決戰的規矩（kit，tactics.war_round）。收場後回江湖（escorts.after_battle）。"""

    cid: str
    name: str
    score: float = 0.0
    neili: float = 0.0
    neili_cap: float = 0.0
    kit: tactics.BoutSide | None = None  # 他自己身上的本命戰法（team.mate_side）；沒有是 None
    fallen_round: int | None = None  # 第幾回合敗走；None 是還在陣上
    felled_by: str = ""  # 最後一擊的人
    released: bool = False  # 收場後回江湖了（escorts.after_battle 只放一次）


class SealBare(BaseModel):
    """不含玉璽碎片戰力的那一份快照（玉璽碎片改版第三章：奪璽單挑不吃戰力，碎片才搶得走）：加入那一刻的威力與每招份量
    （同 power、scores 的算法，只是本人的加成不乘 treasures.power_scale）。決戰份量照 strength 算、不是威力的倍數，所以不能拿
    scores 除回去，要另外快照（計畫開工核對第 2 條）。"""

    power: float = 0.0
    scores: dict[str, float] = Field(default_factory=dict)


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
    slew: int = 0  # 擊退了幾位上陣的大勢人物（最後一擊，龍頭上陣）
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
    renown: list[str] = Field(default_factory=list)  # 名聲：加入時快照的稱號（本場戰功、論功那一句寫；善惡第 1 段起、名望名動一方起）
    # 玉璽碎片（玉璽碎片設計 4.6）：加入那一刻的快照，挑挑戰者只讀它；舊資料沒有＝False
    turncoat: bool = False  # 這一季叛投過（PlayerState.defected）
    newbie: bool = False  # 還在新手期（roster.newbie）
    escort: Escort | None = None  # 隨他上陣的歷史武將（歷史武將同行第五節）；沒派、舊資料是 None
    # 玉璽碎片改版：加入那一刻身上有碎片（改版開著）時，不含碎片戰力的那一份（奪璽單挑的快照用，seal_duel.side_from_participant）；
    # 沒碎片、改版關著、舊資料是 None（單挑照 power、scores）
    seal_bare: SealBare | None = None
    # 鐵匠鋪與合成流程 3.9：加入那一刻的防具減損（含耐久，夾在 Config.armor.total_cap；team.duel_armor_cut），照坐騎的先例快照；
    # 奪璽單挑（seal_duel.side_from_participant）帶過去，對手打中他的那一下乘 1 − 它。決戰本身不吃（一個字不改）。舊資料沒有＝0
    cut: float = 0.0
    card: dict | None = None  # 五項屬性的季：加入那一刻的五項與加成（team.pvp_card），奪璽單挑照對手重算；舊的季、舊資料 None


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
    ults: dict[str, dict[str, str]] = Field(default_factory=dict)  # 名號 → 放手一搏送出那一刻身上的絕招（功能包 looks 的 mvp.snapshot：
    # move、name、look、weapon）；沒穿絕招、沒放手一搏的人沒有。回合 MVP 只從這裡挑（Joy 2026-11-03），純展示、不碰數字


class BattleMvp(BaseModel):
    """一回合的 MVP（Joy 2026-11-03「在放手一搏成功的人裡面且他有絕招動畫的挑一個當這回合的MVP，播放他的絕招」）：
    這一回合放手一搏成了、送出那一刻身上穿著絕招的人裡挑一位（功能包 looks 的 mvp.crown）。只給畫面演，不讀回結算。"""

    round: int  # 整場的第幾回合（1 起算）
    name: str
    faction: str
    move: str  # 絕招（m<購買 id>）：網頁照 /api/looks/scene/<move> 抓導演稿
    move_name: str = ""  # 絕招的名字（導演稿的 name）
    look: str = ""  # 送出那一刻穿的形象
    weapon: str = ""  # 送出那一刻手上兵器的種類（劍、槍……；空的是空手）
    text: str = ""  # 他這一搏寫的那一句
    target: str = ""  # 這一搏點名的對面參戰者（Joy 2026-11-03「點名敵對玩家，變成兩位玩家單挑的場景」）；沒點名是空的
    target_faction: str = ""
    target_look: str = ""  # 被點名的人穿的形象（畫面上受擊的是他的樣子）


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
    mvp: str = ""  # 這一回合的 MVP（名號；功能包 looks 的 mvp.crown）：沒人符合、舊資料是空的


class RoundSwing(BaseModel):
    """一回合戰局往哪邊走、為什麼（round_causes 寫的那幾句）：收場時挑出關鍵的回合寫成敗因（outcome_reason）。
    存在 BattleInstance 裡（不像 rounds 寫進資料庫就讀不回來），一場最多 total_rounds 筆。"""

    round: int  # 整場的第幾回合（1 起算）
    delta: int  # 這一回合戰局變了多少（正是往第一方，負是往第二方）
    causes: str = ""  # 這一回合的原因，「；」分開
    fixed: int = 0  # 其中三招交鋒推的（同 delta 的正負；其餘是放手一搏）；舊資料沒有是 0


class Commander(BaseModel):
    """上陣的大勢人物（龍頭上陣，Joy 2026-10-17；GeneralTuning）：開集結那一刻由 generals.on_muster 派上來，不是參戰者——不佔人數、
    不等他、不拿軍餉、不進戰功榜。每回合照他這一方喊的那一招出手（orders），份量是 score（已經乘過位階與聲威），
    乘這一場的氣血狀態與剋制係數。整場都顯眼：對面的集火與點名打得到他（_strike_commanders）；池子打光就敗走（fallen_round）。"""

    fid: str
    name: str
    faction: str
    rank: int = 0  # 0 主將、1 副將
    score: float = 0.0
    neili: float = 0.0
    neili_cap: float = 0.0
    prestige: int = 0  # 上陣那一刻的聲威（畫面寫）
    fallen_round: int | None = None  # 第幾回合敗走；None 是還在陣上
    felled_by: str = ""  # 最後一擊的人（名望、天下大事）
    settled: bool = False  # 收場後聲威扣過了（generals.after_battle 只扣一次）


def standing_commanders(instance: BattleInstance, side: str) -> list[Commander]:
    """這一方還在陣上的人物，照位階。"""
    return sorted((c for c in instance.commanders if c.faction == side and c.fallen_round is None), key=lambda c: c.rank)


def caller(instance: BattleInstance, side: str) -> Commander | None:
    """這一方此刻喊令的人（位階最高、還在陣上的那一位）；沒有是 None。"""
    rows = standing_commanders(instance, side)
    return rows[0] if rows else None


def call_orders(instance: BattleInstance, definition: BattleDef, tuning: BattleTuning | None = None) -> None:
    """這一回合開打前，每一方喊令的人喊一招（BattleInstance.orders）：order_read 的機會看對面上一回合出最多的那一招、喊剋它的那一招，
    其餘照自己的亂數隨口喊（第一回合沒有上一回合，都是隨口喊）。亂數自己一份（將令|戰役|流水號|回合|陣營），不碰回合結算的 rng。"""
    tuning = tuning or BattleTuning()
    instance.orders = {}
    if not instance.commanders or instance.phase != "active":
        return
    for side in fields(instance, definition):
        c = caller(instance, side)
        if c is None:
            continue
        rng = random.Random(f"將令|{instance.battle_id}|{instance.record_id}|{instance.round_number}|{side}")
        if side == GUARD:  # 三方混戰的守將（裁決 22）：看兩軍上一回合合起來出最多的那一招
            seen = {m: sum(instance.last_mix.get(f.id, {}).get(m, 0.0) for f in definition.factions) for m in MOVES}
            seen = seen if any(seen.values()) else {}
        else:
            enemy = next((e.id for e in definition.factions if e.id != side), None)
            seen = instance.last_mix.get(enemy or "", {})
        if seen and rng.random() < tuning.generals.order_read:
            main = _main_move(seen)
            instance.orders[side] = next(m for m, v in BEATS.items() if v == main)  # 剋它的那一招
        else:
            instance.orders[side] = rng.choice(MOVES)


ORDER_MARK = "・主將令"  # 三招的按鈕上，照令的那一顆接這幾個字（假人照它認）


class SiegeInfo(BaseModel):
    """這一場是攻城戰（領地爭奪第二批，tianxia/siege.py）：打哪一塊、誰攻、開集結那一刻誰佔著。BattleInstance.battle_id 是那個大區的
    攻城範本（content/battles.json 的 siege_<大區>），名字照 siege.title（「攻城・地點」）。攻城另存一串（SharedWorldState.sieges），
    可以跟時刻表決戰、別的攻城戰同時打。"""

    slot_id: str  # 時程表上那一場（ConquestState.schedule 的 SiegeSlot.id）
    loc: str  # 攻哪一塊
    attackers: list[str] = Field(default_factory=list)  # 攻方（兩軍同時搶同一塊中立地是兩個）
    holder: str | None = None  # 開集結那一刻的控制方；None＝中立地還沒人佔
    # 單方攻中立地時守將站的那一格（另一軍的 id）：另一軍的人站不進去，散人可以投效助守（裁決 8）。兩軍同時攻同一塊中立地（三方混戰，
    # 裁決 22）是 GUARD：守將與助守的人站第三格，不是任何一軍
    guard_side: str | None = None
    void: str = ""  # 作罷的原因（攻方沒人到、攻方已經是主人、管理者取消）；空的是照常打完
    settled: bool = False  # 收場的事做過了（易手、進度歸 50、時程表記 done；只做一次）
    blow: str = ""  # 三方混戰：補上守將最後一刀的那一軍（拿下這一塊）；守將還沒倒、守住了、不是三方混戰是空的
    # 三方混戰集結結束時只有一軍到場（裁決 23）：沒到場的那一軍（棄權）。這一場轉回單方攻中立地——attackers 只剩到場的那一軍，
    # guard_side 是這一軍的 id（守將站它那一格），之後一切照單方攻中立地；這裡只留著給場景多寫一句。其餘的場是空的
    absent: str = ""


GUARD_SUFFIX = "（守將）"  # 待 joy 潤：中立地守將顯示名的後綴（siege.GUARD_NAME 用它；find_commander 的 guard_alias 拿它拆回隊伍名）
GUARD = "guard"  # 三方混戰（裁決 22，企劃者 2026-10-21）：守將與助守的人站的第三格；範本照舊只有官軍、黃巾兩格
GUARD_SIDE = "守軍"  # 待 joy 潤：單方攻中立地時守將那一格在畫面、戰報、天下大事上的名字（不冠任何一軍，FB-540）
BLOW_REASON = "勝負的關鍵：第 {n} 回合，{side}的{who}補上了最後一刀，{guard}倒下了。"
BLOW_REASON_NOBODY = "勝負的關鍵：第 {n} 回合，{side}補上了最後一刀，{guard}倒下了。"
MELEE_HOLD_REASON = "勝負的關鍵：守軍撐過了 {n} 回合，兩軍都沒能補上最後一刀。"


def neutral_guard(instance: BattleInstance) -> str | None:
    """單方攻中立地時守將站的那一格（另一軍的 id，SiegeInfo.guard_side）：規則照那一格算（誰能站、勝負），寫給人看的一律寫中立的守軍
    （GUARD_SIDE），不寫那一軍（FB-540）。不是這種攻城（決戰、陣營佔著的區塊、兩軍同時搶中立地）是 None。"""
    s = instance.siege
    return s.guard_side if s is not None and s.holder is None and s.guard_side else None


def melee(instance: BattleInstance) -> bool:
    """兩軍同時攻同一塊中立地、那裡有守將：三方混戰（裁決 22）。守將站第三格 GUARD，兩軍都打他、兩軍之間也互打，
    誰補上守將最後一刀誰拿下（resolve_round、_strike_guard）。"""
    s = instance.siege
    return s is not None and s.holder is None and s.guard_side == GUARD


def fields(instance: BattleInstance, definition: BattleDef) -> list[str]:
    """這一場站得了人的每一格：交戰的兩軍，三方混戰再加守軍那一格（GUARD）。"""
    return [f.id for f in definition.factions] + ([GUARD] if melee(instance) else [])


def side_names(instance: BattleInstance, definition: BattleDef) -> dict[str, str]:
    """這一場兩邊寫給人看的名字（陣營 id → 名字）：照範本的陣營名字，守將那一格（neutral_guard）換成 GUARD_SIDE；三方混戰多一格
    守軍（GUARD）。認東西照舊用 id。"""
    names = {f.id: f.name for f in definition.factions}
    guard = neutral_guard(instance)
    if guard in names or (guard == GUARD and melee(instance)):
        names[guard] = GUARD_SIDE
    return names


class FrontNote(BaseModel):
    """時刻表決戰的起點照哪一條戰線算（start_from_front），開集結那一刻的快照（領地爭奪開著的季才記；conquest.front_note 算、
    world._open_claimed 記）：那條線上的區塊（大本營、廣宗也算，同輿圖）此刻各歸誰、還沒人佔的幾處、照戰況換算的起點（屯糧、天命之爭偏之前）。
    開集結那一則天下大事與決戰畫面那一句（conquest.front_rumor／front_scene）照它寫。企劃者 2026-10-22：不另加主場偏移，補一句說明。"""

    line: str  # 戰線 id（BattleDef.front）
    start: int  # 照戰況換算的起點（偏離 CENTER 往 factions[0] 為正）
    held: dict[str, int] = Field(default_factory=dict)  # 陣營 id → 佔幾處：交戰兩軍一定有（0 也記），別的陣營佔著才記；照寫的順序
    open: int = 0  # 還沒人佔的中立地幾處


class BattleInstance(BaseModel):
    battle_id: str
    siege: SiegeInfo | None = None  # 攻城戰（領地爭奪第二批）；決戰是 None
    phase: Phase = "muster"
    muster_deadline_real: float = 0.0
    participants: dict[str, BattleParticipant] = Field(default_factory=dict)
    trend: int = 50
    trend_start: int | None = None  # 開打時的戰局（時刻表決戰照戰況算，不一定是 50）；舊資料沒有是 None
    seal_lean: dict[str, int] = Field(default_factory=dict)  # 天命之爭開集結那一刻各方握幾片（玉璽碎片設計 8.3；起點已經照兩軍的數偏過）
    supply_lean: dict[str, int] = Field(default_factory=dict)  # 屯糧練兵（works.on_muster）：開集結那一刻兩軍各屯了幾下（起點已經照它偏過）
    act_index: int = 0
    round_number: int = 0  # 已經結算了幾回合（換幕與最後一回合都照這個數，見 resolve_round）
    round: BattleRound = Field(default_factory=BattleRound)
    last_mix: dict[str, dict[str, float]] = Field(default_factory=dict)  # 陣營 → 上一回合各招的比例（只算出固定招的人；
    # 那一邊沒人出固定招是空的），畫面寫「對面上一回合」（戰鬥系統 3.4）；舊資料沒有就是空的
    narrative_log: list[str] = Field(default_factory=list)
    # 戰況裡發動過的戰法名 → kind（tactics.War.kinds；名將本命兵器的〔號令〕記 "order"）：場景與戰報把一軍的那幾句摺成一行時分類（Joy 2026-10-30）；舊資料是空的
    tactic_kinds: dict[str, str] = Field(default_factory=dict)
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
    mvps: list[BattleMvp] = Field(default_factory=list)  # 每一回合的 MVP（有人符合的那幾回合才有；功能包 looks 的 mvp.crown）：
    # 決戰畫面播他的絕招。純展示，戰局、戰功一個數字都不動；舊資料沒有是空的
    # 龍頭上陣（GeneralTuning）：開集結那一刻上陣的大勢人物、這一回合每一方喊的那一招；舊資料、開關關著是空的
    commanders: list[Commander] = Field(default_factory=list)
    orders: dict[str, str] = Field(default_factory=dict)
    # 起點照哪一條戰線（領地爭奪開著的季的時刻表決戰；企劃者 2026-10-22，計畫 2026-10-22-長社火攻主場）：開集結那一刻的快照，
    # 決戰畫面照它寫、不事後重算；舊資料、領地爭奪關著、沒寫戰線的是 None（存的時候連鍵都不寫，見 _drop_empty_front_note）
    front_note: FrontNote | None = None

    @model_serializer(mode="wrap")
    def _drop_empty_front_note(self, handler):
        """front_note 是 None 時不寫這個鍵：領地爭奪關著的季，決戰那一列的 JSON 跟加這一欄之前一個位元組都一樣。"""
        data = handler(self)
        if isinstance(data, dict) and "front_note" in data and data["front_note"] is None:
            del data["front_note"]
        if isinstance(data, dict) and data.get("mvps") == []:  # 回合 MVP 同理：沒人當過的場，JSON 跟加這一欄之前一樣
            del data["mvps"]
        return data


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


def idle(p: BattleParticipant) -> bool:
    """掛機中：上一回合（或更早，連續）是逾時被代選的，還沒自己按過行動。"""
    return p.idle_streak > 0


def _main_move(mix: dict[str, float]) -> str:
    """這一邊這回合出得最多的那一招（一樣多時照 MOVES 的順序）。"""
    return max(MOVES, key=lambda m: mix.get(m, 0.0))


def merit_counts(p: BattleParticipant) -> dict[str, int]:
    return {"acted": p.acted_rounds, "held": p.held_rounds, "led": p.led_rounds, "gamble": p.gambles_won, "hit": p.hits_landed,
            "stood": p.stood_marked, "slew": p.slew}


def merit(tuning: BattleTuning, p: BattleParticipant) -> int:
    """個人戰功（Joy 2026-10-10：「戰線推進是陣營，個人的部分有辦法做出戰績跟區別嗎」）：每一項照 BattleTuning.merit_points 記分。"""
    return sum(tuning.merit_points.get(key, 0) * n for key, n in merit_counts(p).items())


KEY_ROUNDS = 2  # 敗因最多舉幾個回合


def outcome_reason(instance: BattleInstance, definition: BattleDef) -> str:
    """收場時寫勝負的關鍵（試玩回饋 2026-10-08）：戰局停在哪一邊（剛好 50 不寫），就挑往那一邊推得最多的幾個回合
    （最多 KEY_ROUNDS 個，照回合先後寫），連同那一回合的原因；開打時起點就偏向贏家的也寫一句。只看公開的戰局，不看伏筆鎖定。"""
    first, second = definition.factions[0].id, definition.factions[1].id
    names = side_names(instance, definition)  # 守將那一格寫守軍（FB-540）
    if melee(instance):  # 三方混戰（裁決 22）：誰補上最後一刀，或守軍撐過了幾回合
        keeper = next((c for c in instance.commanders if c.faction == GUARD), None)
        if keeper is not None and keeper.fallen_round is not None and instance.siege.blow:
            line = BLOW_REASON if keeper.felled_by else BLOW_REASON_NOBODY
            return line.format(n=keeper.fallen_round, side=names.get(instance.siege.blow, instance.siege.blow),
                               who=keeper.felled_by, guard=keeper.name)
        return MELEE_HOLD_REASON.format(n=instance.round_number)
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

# 放手一搏「成了」只代表引擎把戰線推過去、傷害算下去——**不代表玩家喊的那件事真的做到了**。
# 企劃者 2026-11-04 在第 8 季廣宗抓到：玩家喊「取其首級讓她下班！」判成功，戰報就寫對方被斬首，
# 可是她整場沒倒下（倒下只看氣血歸零，engine 另外記 fell_round）。誰死誰活一律由引擎決定，
# 寫到死人的那一句要有引擎這一回合真的放倒的人才算數，不然整句不用、照固定句播。
# 只挑不會誤傷的詞：「死戰」「拚死」「死守」裡的單字「死」不算，「倒下」「倒地」也不算（被打倒不是死）。
KILL_WORDS = ("首級", "斬首", "斬殺", "梟首", "斃命", "氣絕", "斷氣", "殞命", "殞落", "身亡", "喪命", "命喪",
              "陣亡", "戰死", "伏誅", "屍", "血泊", "取其性命", "一命嗚呼", "送命", "死於")


def claims_a_kill(story: str) -> bool:
    """這一句有沒有寫死人。"""
    return any(word in story for word in KILL_WORDS)


def clean_story(raw: str, name: str, known: Sequence[str] = ()) -> str:
    """模型寫的一版劇情整理成能播的一句：轉繁體、去掉換行與 markdown、引號；有阿拉伯數字（數字只能是引擎的）、太長、
    空的都不用（回空字串）。有英文字母也不用（M-07），名號、known（玩家寫的那一句、點名的對手）裡本來就有的不算。用「你」「妳」的也不用（FB-183：進天下大事與雙方的戰報，要第三人稱；名號裡本來就有的不算）。
    不是以名號開頭的補上名號，名號後面接冒號的換成逗號，句尾補句號。"""
    text = zh.to_traditional(str(raw or ""))
    text = re.sub(r"[\s*#>`_]+", "", text).strip("「」『』\"'“”")
    # 數字那一關比的是「挖掉名號之後」的字：名號裡本來就有阿拉伯數字（管理者建的角色，例「Rayal2」）時不挖的話，
    # 模型只要提到他整句就被丟掉、退回固定句（企劃者 2026-11-04 讀的那一場：24 次放手一搏有 7 次旁白是空的，7 次都是提到他）
    bare = text
    for one in sorted({x for x in (name, *known) if x}, key=len, reverse=True):
        bare = bare.replace(one, "")
    if not text or len(text) > STORY_LIMIT or _DIGITS.search(bare) or zh.stray_latin(text, name, *known):
        return ""
    if any(ch in (text.replace(name, "") if name else text) for ch in "你妳"):
        return ""
    if name and text.startswith(name) and text[len(name):len(name) + 1] in ("：", ":"):
        text = name + "，" + text[len(name) + 1:]
    if not text.startswith(name):
        text = name + text
    return text if text[-1] in "。！？…" else text + "。"


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
    real = name or "這位" + gender.hero(sex)
    who, said = zh.prompt_safe(real) or real, zh.prompt_safe(text)  # 名號與那一句夾掉引號、換行（M-13）；劇情裡寫的名號換回本名
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
            + f"玩家的行動：「{said}」\n請給出 success_rate、reasoning、win、lose。"
        )},
    ]
    try:
        result = client.chat_structured(messages, SuccessRateJudgment, temperature=0.7, required_fields=["success_rate"])
    except Exception:
        return GambleVerdict(DEFAULT_FREE_TEXT_SUCCESS_RATE)
    rate = max(0, min(100, int(result.success_rate)))
    # 這兩版是**擲骰之前**寫的，這時候誰會倒下還不知道：寫到死人的那一版不用（claims_a_kill 上面那段）。
    # 不用＝這一搏沒有現成劇情，引擎先播固定句、記一筆等回合結算後再寫（write_tales 那條路知道這一回合誰真的倒了）。
    def ok(raw) -> str:
        story = clean_story(_real_name(raw, who, real), real, (text, target))
        return "" if claims_a_kill(story) else story

    return GambleVerdict(rate, ok(result.win), ok(result.lose))


def _real_name(story, safe: str, name: str) -> str:
    """提示裡的名號夾過標點（zh.prompt_safe）時，模型照抄的是夾過的那一個：換回本名，clean_story 才認得是名號開頭。"""
    story = str(story or "")
    return story.replace(safe, name) if safe and safe != name else story
