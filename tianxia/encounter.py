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

# 隨機「戰場運氣」項的半幅：resolve_encounter 會在 -LUCK_HALF..+LUCK_HALF 之間加減。
LUCK_HALF = 15.0

# 結果等級門檻（margin = 我方威力 - 對手難度 + 運氣，由高到低比對，第一個達標的就是結果）。
TIER_THRESHOLDS = (("大勝", 40.0), ("險勝", 10.0), ("僵持", -20.0))
FALLBACK_TIER = "落敗"

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


def member_power(member: HasMartialArts, arts: dict[str, MartialArt], opponent_attribute: str | None = None) -> float:
    """這個人目前貢獻的威力：沒學武學就是 0（內功沒有武學可以加成，貢獻也是 0）。"""
    if not member.wugong_id or member.wugong_id not in arts:
        return 0.0
    wugong = arts[member.wugong_id]
    power = power_at(wugong, member.wugong_level)
    if member.neigong_id and member.neigong_id in arts:
        neigong = arts[member.neigong_id]
        power *= 1 + power_at(neigong, member.neigong_level) / NEIGONG_BONUS_DIVISOR
    if opponent_attribute and counters(wugong.attribute, opponent_attribute):
        power *= COUNTER_BONUS
    return power


def team_power(members: list[HasMartialArts], arts: dict[str, MartialArt], opponent_attribute: str | None = None) -> float:
    return sum(member_power(m, arts, opponent_attribute) for m in members)


def resolve_encounter(our_power: float, difficulty: float, rng: Random) -> EncounterResult:
    luck = rng.uniform(-LUCK_HALF, LUCK_HALF)
    margin = our_power - difficulty + luck
    for tier, threshold in TIER_THRESHOLDS:
        if margin >= threshold:
            return EncounterResult(tier=tier, margin=margin, our_power=our_power, difficulty=difficulty)
    return EncounterResult(tier=FALLBACK_TIER, margin=margin, our_power=our_power, difficulty=difficulty)


def describe_result(result: EncounterResult, ours: str, theirs: str) -> str:
    """範本敘事文字（LLM 潤色是選用的加分項，見設計文件八.2 第 4 點，這裡是永遠可用的保底）。"""
    return RESULT_NARRATION[result.tier].format(ours=ours, theirs=theirs)
