"""事件抽選與選項顯示。選項的效果處理在 engine.py（因為可能牽涉戰鬥與事件串接）。"""
from __future__ import annotations

import random
from typing import Literal

from . import foreshadow
from .models import Choice, Content, Event, Location
from .rules import check_condition, check_who, season_one_off
from .state import GameState
from .world_state import WorldStateStore


def event_matches_location(event: Event, location: Location) -> bool:
    if not event.locations and not event.tags:
        return True
    return location.id in event.locations or bool(set(event.tags) & set(location.tags))


def has_events_here(content: Content, location: Location, action: str) -> bool:
    return any(
        action in event.actions and event_matches_location(event, location)
        for event in content.events.values()
    )


EventPool = Literal["rare", "common"]
MIN_DECAY_FACTOR = 1e-9  # event_weight 的看過遞減乘數下限（約 decay 0.5 看過 30 次之後就不再往下）


def is_rare(event: Event) -> bool:
    """一次性或奇遇事件：探索時只走奇遇那一步，不進事件那一支（探索三選一設計第二節、4.3）。"""
    return event.once or event.qiyu


def event_candidates(
    state: GameState, content: Content, action: str, pool: EventPool | None = None,
) -> list[Event]:
    """這裡、現在可以抽的事件（依內容順序）。pool 給探索三選一用："rare" 只要一次性與奇遇，
    "common" 只要可重複的；None 是全部（遊歷、交友照舊用這個）。
    看過的一次性事件不再出現；奇遇沒標 once 的看過也照樣留著（企劃者 2026-10-03 改）。
    伏筆的事件（片段事件、準備事件，foreshadow.event_ids）只在伏筆在跑時出現（foreshadow.active：開關、蓋章、有鏈）。
    第一季的規則開著時，劇本 season_one_off.events 裡的 beta 事件不出現（例：kou_boss，由挑戰大勢人物本人取代，T4）。"""
    location = content.locations[state.player.location]
    hidden = set() if foreshadow.active(state, content) else foreshadow.event_ids(content)
    hidden |= season_one_off(content, state.world, "events")
    candidates: list[Event] = []
    for event in content.events.values():
        if action not in event.actions:
            continue
        if pool is not None and is_rare(event) != (pool == "rare"):
            continue
        if not event_matches_location(event, location):
            continue
        if event.once and event.id in state.player.seen_events:
            continue
        if event.id in hidden:
            continue
        if not check_condition(event.condition, state, content):
            continue
        candidates.append(event)
    return candidates


def event_weight(event: Event, state: GameState, content: Content) -> float:
    """抽選權重：事件自己的權重 × 奇遇倍率（奇遇才乘）× event_repeat_decay ^ 這個玩家這一季看過幾次。
    看過的事件下次更少出現（週末試玩項目 B）；decay 設 1.0 時乘的是 1.0，浮點數跟舊的純權重抽法逐位相同。
    遞減有下限 MIN_DECAY_FACTOR：機器人整季亂逛可以把同一則事件看上千次，0.5 ^ 1100 在浮點數裡是 0.0，
    只剩那一則候選時總權重為 0 會讓 random.choices 丟 ValueError。"""
    config = content.config
    weight = event.weight * (config.qiyu_weight_multiplier if event.qiyu else 1.0)
    return weight * max(config.event_repeat_decay ** state.player.event_seen.get(event.id, 0), MIN_DECAY_FACTOR)


def pick_event(
    state: GameState, content: Content, action: str, rng: random.Random, pool: EventPool | None = None,
) -> Event | None:
    """照權重抽一則（權重怎麼算見 event_weight：奇遇乘 qiyu_weight_multiplier、看過幾次就乘幾次 event_repeat_decay）；
    沒有合格的就是 None。pool 見 event_candidates。"""
    candidates = event_candidates(state, content, action, pool)
    if not candidates:
        return None
    weights = [event_weight(event, state, content) for event in candidates]
    return rng.choices(candidates, weights=weights)[0]


def fortune_events(state: GameState, content: Content) -> list[Event]:
    """還能觸發的新立門戶福緣事件（條件成立，也就是那位地品還沒入門），依內容順序。"""
    return [e for e in content.events.values() if e.fortune and check_condition(e.condition, state, content)]


def visible_choices(event: Event, state: GameState, content: Content | None = None) -> list[tuple[int, Choice]]:
    """content 給了才判得了季曆的條件（night、week_*，見 rules.check_condition）。"""
    return [(i, c) for i, c in enumerate(event.choices) if check_condition(c.condition, state, content)]


def choice_label(choice: Choice, state: GameState, content: Content, world: WorldStateStore) -> str:
    """有檢定的選項寫出由誰出手（不寫成功率）；其餘照原文。"""
    if choice.check:
        return f"{choice.text}（{check_who(choice.check, state, content, world)}）"
    return choice.text
