"""一類一顆（docs/superpowers/specs/2026-10-17-正式季整合-design.md 第二章；正式季整合第 3 批）：每一顆行動鈕只給一類東西，
按了一定拿到那一類，運氣只決定拿到多少。找素材一定給、不打仗；練功（新）一定打一場；找事件寫這裡多半給哪一類；交友只談話；
靜心感悟選錯給心得、不鎖；應召不再換掉別的鈕。

開關 Config.precise_actions，照開季蓋章（WorldState.precise_actions）；探索三選一（Config.explore_modes）也開著時才生效——
找素材只存在於三選一裡（10.1）。關著時一個字都不變。這裡放不看引擎的純規則，engine.Game 接線。
"""
from __future__ import annotations

from . import explore_modes
from .models import Content, Effect, Event
from .state import WorldState

MEET_FLAG = "結識:"  # 結識事件立的旗標（rules.can_meet 看到它就不看名望門檻）


def on(content: Content, world: WorldState | None) -> bool:
    """一類一顆開著沒：設定打開、這一季開季時也蓋了章、探索三選一開著。"""
    return (content.config.precise_actions and world is not None and world.precise_actions
            and explore_modes.on(content))


def _effects(event: Event) -> list[Effect]:
    effects = [e for choice in event.choices for e in (choice.effect, choice.fail_effect)]
    if event.free_text is not None:
        effects += [event.free_text.effect, event.free_text.fail_effect]
    return effects


def meets(event: Event) -> set[str]:
    """這則事件結識得到的人物 id（選項立「結識:X」旗標）。"""
    return {flag.removeprefix(MEET_FLAG) for e in _effects(event) for flag in e.flags_add if flag.startswith(MEET_FLAG)}


def joins_sect(event: Event) -> bool:
    """拜入門派的事件（選項帶 join_sect）：一類一顆開著時改成「此地還能做」的一顆（2.7【PM】），不再從交友抽。"""
    return any(e.join_sect for e in _effects(event))


def kept_social(event: Event) -> bool:
    """一類一顆開著時還留在交友的事件（2.7【PM】）：結識（名望不夠時見到人物的另一條路）與一次性、奇遇（搬進找事件會落進 2.5% 的奇遇池）。
    一次性的那幾則不是人物類，是 2.8「交友只談話」的例外（待企劃者）。"""
    return bool(meets(event)) or event.once or event.qiyu


def actions_of(event: Event, content: Content, world: WorldState | None) -> set[str]:
    """這則事件此刻算在哪幾種行動的池子裡（events.event_candidates 照它篩）。開關關著照內容寫的 actions。
    開著時：交友事件除了留在交友的（kept_social）都併進找事件（explore）；拜入門派的改成 sect（Game 的「此地還能做」）。"""
    acts = set(event.actions)
    if not on(content, world) or "socialize" not in acts:
        return acts
    if joins_sect(event):
        return (acts - {"socialize"}) | {"sect"}
    if not kept_social(event):
        return (acts - {"socialize"}) | {"explore"}
    return acts
