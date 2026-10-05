"""單次判定的遭遇/劇情戰結算（取代 battle.py 的 3v3 全自動戰鬥，見設計文件六.3）。

我方隊伍武學總威力（含內功加成、屬性相剋加成）vs 對手難度值，加一個隨機的「戰場運氣」
項，一次算出結果等級——不是回合制，沒有中途決策點，威力數字是練功有沒有效的唯一驗證，
文字敘事由呼叫端（engine.py，之後串上 companion_agent.py 的敘事潤色）另外處理。
"""
from __future__ import annotations

from random import Random
from typing import Protocol

from pydantic import BaseModel

from .martial_arts import MartialArt, counters, power_at


class HasMartialArts(Protocol):
    """玩家 Member 與同伴 CompanionProgress（見 world_state.py）都符合這個形狀，
    member_power() 不在乎實際是哪一個型別。"""

    neigong_id: str | None
    neigong_level: int
    wugong_id: str | None
    wugong_level: int

# 內功威力換算成武學威力的加成比例：內功威力 100 大約是 +100% 加成，跟自創功法
# QUALITY_TOP_POWER 的量級（絕學上限 120）對齊，故意讓「絕學等級的內功」能接近翻倍。
NEIGONG_BONUS_DIVISOR = 100.0

# 屬性相剋加成：己方招式屬性克制對方時，這一位的威力乘這個倍率。
COUNTER_BONUS = 1.3

# 氣血狀態對威力的影響（氣血設計 §1.1【定】：剩越少出手越弱，0.5 + 0.5 × 剩餘／上限）。
# 滿血是 1.0、見底是 0.5。等級因此是「續戰力」——上限越高，同樣的絕對損耗壓下來的比例越小。
CONDITION_FLOOR = 0.5


def condition_of(now: float, cap: float, floor: float = CONDITION_FLOOR) -> float:
    """氣血狀態係數：滿血 1.0，見底 floor（預設五成；本人帶【厚】時高一點，武學與成長設計 13.2）。"""
    if cap <= 0:
        return 1.0
    return floor + (1 - floor) * max(0.0, min(1.0, now / cap))

# 「戰場運氣」與結果門檻都**按對手難度的比例**算，不是固定點數（2026-10-02 重新校準）。
#
# 原本是絕對值（運氣 ±15、大勝 +40、險勝 +10、僵持 -20），但那讓氣血設計 §1.4 的平衡目標
# 達不到：武學成數高 3 成在低等級只差 9.7 點威力，完全被 ±15 的運氣蓋過（實測勝率 48%，
# 目標是 ≥75%）。改成比例之後，一場仗的運氣與門檻跟「這場仗多大」成正比——打難度 150 的
# 對手運氣擺幅 ±45（真的是一場賭），打難度 8 的散兵則幾乎沒有變數。
#
# 參數是掃過之後挑的：武學高 3 成勝率 80%（目標 ≥75%）、雙方完全一樣時 25%、而既有內容的
# 勝算最大偏移 7 個百分點（§1.4 第 3 條要求 ≤10）。
LUCK_RATIO = 0.3
LUCK_MIN = 5.0  # 難度很低時也還是留一點變數
TIER_RATIOS = (("大勝", 0.5), ("險勝", 0.15), ("僵持", -0.5))
FALLBACK_TIER = "落敗"


def luck_half(difficulty: float) -> float:
    return max(LUCK_MIN, abs(difficulty) * LUCK_RATIO)


def tier_thresholds(difficulty: float) -> tuple[tuple[str, float], ...]:
    return tuple((tier, abs(difficulty) * ratio) for tier, ratio in TIER_RATIOS)

RESULT_NARRATION = {
    "大勝": "{ours}招招搶先，{theirs}幾乎沒有還手的餘地，一場酣暢淋漓的大勝。",
    "險勝": "{ours}與{theirs}纏鬥多時，堪堪在最後關頭扳回局面，驚險取勝。",
    "僵持": "{ours}與{theirs}你來我往、難分高下，最終各自收手，算不上輸贏。",
    "落敗": "{ours}使盡渾身解數，仍不敵{theirs}，只得狼狽退下。",
}


class EncounterResult(BaseModel):
    tier: str
    margin: float
    our_power: float
    difficulty: float
    dodged: bool = False  # 落敗被身法閃成僵持（人物資質設計 14.4）；tier 已經是僵持
    guarded: bool = False  # 護命把落敗改判成僵持（武學與成長設計 13.4）；tier 已經是僵持


class Mods(BaseModel):
    """這一場本人身上的功效換算成的數字（武學與成長設計 13.2、13.4）。由呼叫端（team.trait_mods）算好傳進來，
    這個模組照舊只算數字。全部是預設值時，結果與亂數用法跟沒有功效時一模一樣。"""

    luck_scale: float = 1.0  # 穩縮小、險放大運氣的起伏（1 − 穩 ＋ 險）
    big_win_cut: float = 0.0  # 先手：大勝的門檻降低（對手強度的比例）
    difficulty_cut: float = 0.0  # 破甲：對手強度當作低這麼多（比例）
    power_add: float = 0.0  # 借力：威力加上對手強度的這麼多（比例）
    double_luck: bool = False  # 連環：擲兩次運氣，取好的


class Boost(BaseModel):
    """一個人在這一場的加成（武學與成長設計 5.1、6.1、7.4）。由呼叫端算好傳進來，這個模組只算數字。"""

    outer: float = 0.0  # 武學（外功）威力加幾成：臂力
    inner: float = 0.0  # 內功威力加幾成：根骨
    factor: float = 1.0  # 整個人的乘數：內外搭配 × 正邪共鳴（計畫二 Task 3）


BOOST_FLOOR = 0.1  # 1 + 加成再低也夾在這裡：屬性被扣到很低時威力變小，但不會變成負的


def member_power(
    member: HasMartialArts, arts: dict[str, MartialArt], opponent_attribute: str | None = None,
    condition: float = 1.0, boost: Boost | None = None,
) -> float:
    """這個人目前貢獻的威力：沒學武學就是 0（內功沒有武學可以加成，貢獻也是 0）。

    `condition` 是氣血狀態係數（見 condition_of）：帶傷上陣的人出手比較弱。呼叫端算好傳進來，
    因為氣血上限要讀 content 的設定，而這個模組刻意只處理數字、不碰內容模型。
    `boost` 是這個人的加成（本人、同伴、部下各一份，見 team.player_boost、mate_boost、follower_boost）：outer 乘在武學的威力上、
    inner 乘在內功的威力上（所以只放大內功那一項加成，不是整個人）、factor 乘在整個人上。
    """
    if not member.wugong_id or member.wugong_id not in arts:
        return 0.0
    boost = boost or Boost()
    wugong = arts[member.wugong_id]
    power = power_at(wugong, member.wugong_level) * max(BOOST_FLOOR, 1 + boost.outer)
    if member.neigong_id and member.neigong_id in arts:
        neigong = arts[member.neigong_id]
        inner = power_at(neigong, member.neigong_level) * max(BOOST_FLOOR, 1 + boost.inner)
        power *= 1 + inner / NEIGONG_BONUS_DIVISOR
    power *= boost.factor
    if opponent_attribute and counters(wugong.attribute, opponent_attribute):
        power *= COUNTER_BONUS
    return power * condition


def team_power(
    members: list[HasMartialArts], arts: dict[str, MartialArt], opponent_attribute: str | None = None,
    conditions: list[float] | None = None, boosts: list[Boost | None] | None = None,
) -> float:
    """隊伍總威力。`conditions`（氣血狀態係數）與 `boosts`（加成）都跟 members 一一對應，省略時當作
    全員滿血、沒有加成。長度對不上就報錯（strict）：默默少算一個人正是部下曾經消失的方式（計畫二 G1）。"""
    if conditions is None:
        conditions = [1.0] * len(members)
    if boosts is None:
        boosts = [None] * len(members)
    return sum(
        member_power(m, arts, opponent_attribute, c, b) for m, c, b in zip(members, conditions, boosts, strict=True)
    )


def advantage_shift(difficulty: float, advantage: int) -> float:
    """大場面模型給的優勢（百分點，武學與成長設計 8.3）換成判定差距的平移：戰場運氣是均勻分佈、全幅 2 × luck_half，
    差距平移 advantage/100 × 全幅，越過門檻的機會剛好差 advantage 個百分點（在運氣範圍內）。"""
    return advantage / 100 * 2 * luck_half(difficulty)


def resolve_encounter(
    our_power: float, difficulty: float, rng: Random, shift: float = 0.0, mods: Mods | None = None,
) -> EncounterResult:
    """shift 是判定差距的平移（大場面的優勢，見 advantage_shift）；平常是 0。mods 是本人的功效（13.2）：破甲讓對手
    當作弱一點（門檻與運氣都照當作的強度算）、借力加威力、穩與險改運氣的起伏、先手降大勝門檻、連環多擲一次運氣取好的。
    沒有連環時照舊只擲一次運氣；mods 是空的（預設）時，每一步都乘 1、減 0，結果與亂數用法跟沒有這個參數時一模一樣。
    結果記的 difficulty 還是原來的強度（戰報照實寫），破甲只改判定。"""
    mods = mods or Mods()
    effective = difficulty * (1 - mods.difficulty_cut)
    half = luck_half(effective) * max(0.0, mods.luck_scale)
    luck = rng.uniform(-half, half)
    if mods.double_luck:
        luck = max(luck, rng.uniform(-half, half))
    margin = our_power + abs(difficulty) * mods.power_add - effective + luck + shift
    for tier, threshold in tier_thresholds(effective):
        if tier == "大勝":
            threshold -= abs(effective) * mods.big_win_cut
        if margin >= threshold:
            return EncounterResult(tier=tier, margin=margin, our_power=our_power, difficulty=difficulty)
    return EncounterResult(tier=FALLBACK_TIER, margin=margin, our_power=our_power, difficulty=difficulty)


def dodge(result: EncounterResult, chance: float, rng: Random) -> EncounterResult:
    """身法閃避（人物資質設計 14.4）：結果定了之後（大場面的優勢也已經算進去）才擲；只有落敗、而且有機會時才動亂數，
    閃中就改成僵持、記下 dodged。別的情形原封不動回傳，同一個種子的亂數順序跟沒有這一條時一樣。"""
    if result.tier != FALLBACK_TIER or chance <= 0:
        return result
    if rng.random() < chance:
        return result.model_copy(update={"tier": "僵持", "dodged": True})
    return result


def describe_result(result: EncounterResult, ours: str, theirs: str) -> str:
    """範本敘事文字（LLM 潤色是選用的加分項，見設計文件八.2 第 4 點，這裡是永遠可用的保底）。"""
    return RESULT_NARRATION[result.tier].format(ours=ours, theirs=theirs)
