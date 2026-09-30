"""事件抽選與選項顯示。選項的效果處理在 engine.py（因為可能牽涉戰鬥與事件串接）。"""
from __future__ import annotations

import random

from .models import Choice, Content, Event, Location
from .rules import check_condition, check_who
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


def pick_event(
    state: GameState, content: Content, action: str, rng: random.Random
) -> Event | None:
    location = content.locations[state.player.location]
    candidates: list[Event] = []
    weights: list[float] = []
    for event in content.events.values():
        if action not in event.actions:
            continue
        if not event_matches_location(event, location):
            continue
        if event.once and event.id in state.player.seen_events:
            continue
        if not check_condition(event.condition, state):
            continue
        candidates.append(event)
        bonus = content.config.qiyu_weight_multiplier if event.qiyu else 1.0
        weights.append(event.weight * bonus)
    if not candidates:
        return None
    return rng.choices(candidates, weights=weights)[0]


def fortune_events(state: GameState, content: Content) -> list[Event]:
    """還能觸發的新立門戶福緣事件（條件成立，也就是那位地品還沒入門），依內容順序。"""
    return [e for e in content.events.values() if e.fortune and check_condition(e.condition, state)]


def visible_choices(event: Event, state: GameState) -> list[tuple[int, Choice]]:
    return [(i, c) for i, c in enumerate(event.choices) if check_condition(c.condition, state)]


def choice_label(choice: Choice, state: GameState, content: Content, world: WorldStateStore) -> str:
    """有檢定的選項寫出由誰出手（不寫成功率）；其餘照原文。"""
    if choice.check:
        return f"{choice.text}（{check_who(choice.check, state, content, world)}）"
    return choice.text
