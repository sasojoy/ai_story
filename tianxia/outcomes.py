"""減法季批 4：隨口應對分岔的純規則（整合設計 5.1、5.9；主機側計畫 Task 4-2 的純規則那一半）。

模型（event_llm.classify_outcome）把玩家那句話歸到一種後果、評一個 0～100 的成功率；這裡決定那一種怎麼走（plan）：
- check：擲骰，成功率照隨口應對的算法（rules.value_rate：LLM 的分數＋（屬性 − 那一種後果的難度）× 4、夾 5～85；PM 2026-10-25 第 3 件
  把原本寫死的 5 換成難度），屬性看那一種後果自己的檢定（best_of 取最高，rules.check_stat_value；熟練照 Check.practice 加），
  難度寫在固定選項的帶子裡（content.check_outcomes）；
- combat：照固定選項開打（as_choice 交給 Game._event_battle），贏套 effect、輸套 fail_effect，不擲骰；
- cost：掏銀兩、必成（企劃者 2026-10-24 第 8 件 c）；銀兩不夠就不做、不扣次數（cost_problem 回那一句）；
- fallback（最後一種）：只套 effect。
模型回的 id、分數都再認一次（引擎拿到模型的數字一律再夾一次）。每天記得進陣營帳的貢獻有上限（contribution_room，
Config.jianfa.deed_contribution_cap，同出陣推線的量級）。

只 import models、rules、state、team、event_llm（認 id 的那一條）；接線在 Game.answer_event（C 段）與 server.answer_event（B 段叫
event_llm.judge_outcome），開關是 rules.jianfa(content, world, "free_text_outcomes")。
"""
from __future__ import annotations

from typing import NamedTuple

from . import team
from .event_llm import outcome_of
from .models import Choice, Content, Effect, Outcome, OutcomeKind
from .rules import check_stat_value, value_rate
from .state import GameState
from .world_state import WorldStateStore

NOT_ENOUGH_SILVER = "（你掏遍了身上，銀兩不夠，這件事只好作罷。）"  # 待 joy 潤：掏錢的後果、錢不夠（不做、不扣次數）


class Plan(NamedTuple):
    """歸類完要怎麼走：哪一種後果、哪一條路、擲骰的成功率（只有 check 有；combat 照打的那一場，cost 與 fallback 必成）。"""

    outcome: Outcome
    way: OutcomeKind
    rate: int | None


def pick(outcomes: list[Outcome], outcome_id) -> Outcome:
    """照 id 找那一種後果；不在清單（模型亂寫、空的）是最後一種（fallback）。"""
    chosen = outcome_of(outcome_id, [o.id for o in outcomes])
    return next(o for o in outcomes if o.id == chosen)


def rate(outcome: Outcome, llm_rate, state: GameState, content: Content, world: WorldStateStore) -> int:
    """check 那一種的成功率（百分比，5～85）：模型的分數先夾 0～100，再照那一種的檢定屬性修正（best_of 取最高、熟練照加），
    比的是那一種後果的難度（PM 2026-10-25 第 3 件）。"""
    try:
        llm = max(0, min(100, int(llm_rate)))
    except (TypeError, ValueError):
        llm = 0
    value = check_stat_value(outcome.check, state, content, world) + team.practice_bonus(state, content, outcome.check)
    return value_rate(llm, value, base=outcome.check.difficulty)


def plan(
    outcomes: list[Outcome], outcome_id, llm_rate, state: GameState, content: Content, world: WorldStateStore,
) -> Plan:
    """模型的歸類與分數 → 這一次怎麼走。"""
    outcome = pick(outcomes, outcome_id)
    if outcome.kind == "check":
        return Plan(outcome, "check", rate(outcome, llm_rate, state, content, world))
    return Plan(outcome, outcome.kind, None)


def cost_problem(outcome: Outcome, state: GameState) -> str:
    """掏錢的那一種：身上的銀兩不夠就回 NOT_ENOUGH_SILVER（不做、不扣次數）；夠、或不是掏錢的是空字串。"""
    if outcome.cost is None:
        return ""
    return NOT_ENOUGH_SILVER if state.player.stats.get("silver", 0) < outcome.cost.get("silver", 0) else ""


def paid(outcome: Outcome) -> Effect:
    """掏錢那一種實際套的效果：掏的銀兩接在 stats 最前面（江湖紀錄先寫「銀兩 -10」），效果裡本來就有的銀兩併在一起。
    不是掏錢的回原本的 effect。"""
    if outcome.cost is None:
        return outcome.effect
    stats = {"silver": outcome.effect.stats.get("silver", 0) - outcome.cost.get("silver", 0)}
    stats.update((k, v) for k, v in outcome.effect.stats.items() if k != "silver")
    return outcome.effect.model_copy(update={"stats": stats})


def as_choice(outcome: Outcome) -> Choice:
    """打仗的那一種寫成一個固定選項，交給 Game._event_battle：贏套 effect、輸套 fail_effect（跟固定選項同一條路）。"""
    return Choice(text=short_name(outcome.tag), combat=outcome.combat, effect=outcome.effect, fail_effect=outcome.fail_effect)


def short_name(tag: str) -> str:
    """tag 寫成「短名：給模型看的說明」（例「出力：替他拉犁、修犁、想省力的法子」）：給玩家看的地方一律只用冒號前的短名（FB-800，
    PM 2026-10-25）；給模型的提示（event_llm.classify_outcome）照舊用整句。沒有冒號（或冒號前沒有字）的照整句。"""
    head, colon, _ = tag.partition("：")
    return head.strip() if colon and head.strip() else tag.strip()


def tags(outcomes: list[Outcome]) -> list[dict[str, str]]:
    """事件選項 options[].outcomes（主機側計畫 1.3 欄位表）：畫面寫「可能的走向」用，只有 id 與 tag（內容是短名，short_name），
    不給後果的數字。"""
    return [{"id": o.id, "tag": short_name(o.tag)} for o in outcomes]


def kind_name(outcome: Outcome) -> str:
    """那一種後果的類名（短名，例「討牛」）：江湖紀錄的括號、行狀只寫它，不寫玩家的句子。"""
    return short_name(outcome.tag)


def contribution_room(points: int, used_today: int, cap: int) -> int:
    """這一筆實際記得進陣營帳的貢獻：今天已經記了 used_today，最多到 cap（Config.jianfa.deed_contribution_cap）。"""
    return max(0, min(points, cap - used_today))
