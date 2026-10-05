"""事件抽選與選項顯示。選項的效果處理在 engine.py（因為可能牽涉戰鬥與事件串接）。"""
from __future__ import annotations

import random
from typing import Literal

from . import check_lines, foreshadow, team
from .models import Choice, Content, Event, Location
from .rules import check_condition, check_outlook, season_one_off
from .state import PLAYER, GameState
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


def pick_event(
    state: GameState, content: Content, action: str, rng: random.Random, pool: EventPool | None = None,
) -> Event | None:
    """照權重抽一則（奇遇的權重乘上 qiyu_weight_multiplier）；沒有合格的就是 None。pool 見 event_candidates。"""
    candidates = event_candidates(state, content, action, pool)
    if not candidates:
        return None
    multiplier = content.config.qiyu_weight_multiplier
    weights = [event.weight * (multiplier if event.qiyu else 1.0) for event in candidates]
    return rng.choices(candidates, weights=weights)[0]


def fortune_events(state: GameState, content: Content) -> list[Event]:
    """還能觸發的新立門戶福緣事件（條件成立，也就是那位地品還沒入門），依內容順序。"""
    return [e for e in content.events.values() if e.fortune and check_condition(e.condition, state, content)]


def visible_choices(event: Event, state: GameState, content: Content | None = None) -> list[tuple[int, Choice]]:
    """content 給了才判得了季曆的條件（night、week_*，見 rules.check_condition）。"""
    return [(i, c) for i, c in enumerate(event.choices) if check_condition(c.condition, state, content)]


def choice_label(
    choice: Choice, state: GameState, content: Content, world: WorldStateStore, key: str | None = None,
) -> str:
    """有檢定的選項寫「（出手者・屬性 數值：一句心裡話）」，不寫成功率與難度（週末試玩 A，推翻 9/29 的「不顯示成功率」）；
    其餘照原文。出手者、數值與成功率都出自 rules.check_outlook（跟擲骰同一個函式）。
    key 是挑心裡話用的種子（引擎傳「事件 id#選項序號」），沒給就用選項文字——同一個選項每次畫都是同一句。"""
    check = choice.check
    if not check:
        return choice.text
    outlook = check_outlook(check, state, content, world)
    who = "本人" if outlook.actor == PLAYER else team.member_name(state, content, outlook.actor)
    stat = content.config.stat_names.get(check.stat, check.stat)
    line = check_lines.pick_line(content.check_lines, check.stat, outlook.chance, choice.text if key is None else key)
    return f"{choice.text}（{who}・{stat} {round(outlook.value, 1):g}：{line}）"
