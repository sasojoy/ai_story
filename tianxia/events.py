"""事件抽選與選項顯示。選項的效果處理在 engine.py（因為可能牽涉戰鬥與事件串接）。"""
from __future__ import annotations

import random
from typing import Literal

from . import check_lines, foreshadow, team
from .models import Choice, Content, Event, Location
from .rules import check_condition, check_gap, check_outlook, practice_line, season_one_off
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


def rotation_pool(event: Event, location_id: str, action: str) -> str | None:
    """防重複的池子（交友與人物別傳設計稿第八節）：掛在特定地點的事件，每個地點、每種行動各一池
    （「潁川郡:explore」）；不掛地點的通用事件每種行動共用一池（「*:explore」）。一次性與奇遇不輪替，回 None。"""
    if is_rare(event):
        return None
    return f"{location_id}:{action}" if event.locations else f"*:{action}"


def pick_event(
    state: GameState, content: Content, action: str, rng: random.Random, pool: EventPool | None = None,
) -> Event | None:
    """照權重抽一則（奇遇的權重乘上 qiyu_weight_multiplier）；沒有合格的就是 None。pool 見 event_candidates。
    防重複（設計稿第八節）：同一個池子這一輪看過的先拿掉，在剩下的裡面抽；全都看過了，就是新的一輪
    （剛看過的那一則這次先不抽，免得換輪時連著兩次一樣）。
    這個函式**不改狀態**：抽中的那一則要等 Game._present 真的端給玩家時，才由 note_round 記進
    PlayerState.event_rounds（全都看過時的清空也在那裡）。所以選單、勝算、機器人怎麼預覽都不會讓輪替往前走。"""
    candidates = event_candidates(state, content, action, pool)
    if not candidates:
        return None
    location = state.player.location
    rounds = state.player.event_rounds
    pools = {e.id: rotation_pool(e, location, action) for e in candidates}
    fresh = [e for e in candidates if pools[e.id] is None or e.id not in rounds.get(pools[e.id], [])]
    if not fresh:
        last = {rounds[key][-1] for key in set(pools.values()) if key is not None and rounds.get(key)}
        fresh = [e for e in candidates if e.id not in last] or candidates
    multiplier = content.config.qiyu_weight_multiplier
    weights = [event.weight * (multiplier if event.qiyu else 1.0) for event in fresh]
    return rng.choices(fresh, weights=weights)[0]


def note_round(state: GameState, content: Content, event: Event, action: str) -> None:
    """事件真的端到玩家眼前時（只有 Game._present 呼叫）記進這一輪。抽中的那一則已經在它那一池的這一輪裡，
    表示 pick_event 是在「全都看過了」之後抽的：先把這裡、這個行動所有合格事件所屬的池子清空、重開一輪，再記
    （跟 joy 原本在 pick_event 裡清空的是同一組池子；rare／common 的篩選不影響池子，一次性與奇遇不輪替）。"""
    location = state.player.location
    key = rotation_pool(event, location, action)
    if key is None:
        return
    rounds = state.player.event_rounds
    if event.id in rounds.get(key, []):
        for candidate in event_candidates(state, content, action):
            pool_key = rotation_pool(candidate, location, action)
            if pool_key is not None:
                rounds.pop(pool_key, None)
    rounds.setdefault(key, []).append(event.id)


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


def choice_hint(choice: Choice, state: GameState, content: Content, world: WorldStateStore) -> str:
    """有檢定的選項底下那一句人物心聲（content/check_voice.json，依屬性減難度分檔）；沒有檢定或沒寫心聲是空字串。
    吃到熟練加成（Check.practice）時，前面先補一句「這種事你幹得多了。」（rules.practice_line）。"""
    check = choice.check
    bands = content.check_voice.bands
    if check is None:
        return ""
    practiced = practice_line(check, state, content, world)
    if not bands:
        return practiced
    gap = check_gap(check, state, content, world)
    band = next((b for b in bands if gap >= b.min_gap), bands[-1])
    line = band.lines.get(check.stat) or band.lines.get("default", "")
    key = team.check_actor(state, content, world, check)
    who = "你" if key == PLAYER else team.member_name(state, content, key)
    return practiced + line.replace("{who}", who)
