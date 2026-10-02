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


def condition_of(now: float, cap: float) -> float:
    if cap <= 0:
        return 1.0
    return CONDITION_FLOOR + (1 - CONDITION_FLOOR) * max(0.0, min(1.0, now / cap))

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


def member_power(
    member: HasMartialArts, arts: dict[str, MartialArt], opponent_attribute: str | None = None,
    condition: float = 1.0,
) -> float:
    """這個人目前貢獻的威力：沒學武學就是 0（內功沒有武學可以加成，貢獻也是 0）。

    `condition` 是氣血狀態係數（見 condition_of）：帶傷上陣的人出手比較弱。呼叫端算好傳進來，
    因為氣血上限要讀 content 的設定，而這個模組刻意只處理數字、不碰內容模型。
    """
    if not member.wugong_id or member.wugong_id not in arts:
        return 0.0
    wugong = arts[member.wugong_id]
    power = power_at(wugong, member.wugong_level)
    if member.neigong_id and member.neigong_id in arts:
        neigong = arts[member.neigong_id]
        power *= 1 + power_at(neigong, member.neigong_level) / NEIGONG_BONUS_DIVISOR
    if opponent_attribute and counters(wugong.attribute, opponent_attribute):
        power *= COUNTER_BONUS
    return power * condition


def team_power(
    members: list[HasMartialArts], arts: dict[str, MartialArt], opponent_attribute: str | None = None,
    conditions: list[float] | None = None,
) -> float:
    """隊伍總威力。`conditions` 是跟 members 一一對應的氣血狀態係數，省略時當作全員滿血。"""
    if conditions is None:
        conditions = [1.0] * len(members)
    return sum(member_power(m, arts, opponent_attribute, c) for m, c in zip(members, conditions))


def resolve_encounter(our_power: float, difficulty: float, rng: Random) -> EncounterResult:
    half = luck_half(difficulty)
    luck = rng.uniform(-half, half)
    margin = our_power - difficulty + luck
    for tier, threshold in tier_thresholds(difficulty):
        if margin >= threshold:
            return EncounterResult(tier=tier, margin=margin, our_power=our_power, difficulty=difficulty)
    return EncounterResult(tier=FALLBACK_TIER, margin=margin, our_power=our_power, difficulty=difficulty)


def describe_result(result: EncounterResult, ours: str, theirs: str) -> str:
    """範本敘事文字（LLM 潤色是選用的加分項，見設計文件八.2 第 4 點，這裡是永遠可用的保底）。"""
    return RESULT_NARRATION[result.tier].format(ours=ours, theirs=theirs)
