"""事件抽選與選項顯示。選項的效果處理在 engine.py（因為可能牽涉戰鬥與事件串接）。"""
from __future__ import annotations

import random
from typing import Literal

from . import foreshadow, team
from .models import Choice, Content, Effect, Event, Location
from .rules import check_chance, check_condition, check_gap, check_who, rate_words, season_one_off
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


def choice_label(choice: Choice, state: GameState, content: Content, world: WorldStateStore) -> str:
    """有檢定的選項寫出看哪一項屬性與成算（企劃者 2026-10-05：玩家要知道為什麼有時拉得開、有時拉不開），
    同伴出手時前面寫是誰、本人檢定寫「本人」（同伴幫不上忙）；其餘照原文。"""
    check = choice.check
    if check is None:
        return choice.text
    stat = content.config.stat_names.get(check.stat, check.stat)
    rate = rate_words(round(check_chance(check, state, content, world) * 100))
    who = check_who(check, state, content, world)
    parts = [stat, rate] if who == "本人出手" else [who, stat, rate]
    return f"{choice.text}（{'・'.join(parts)}）"


def choice_hint(choice: Choice, state: GameState, content: Content, world: WorldStateStore) -> str:
    """有檢定的選項底下那一句人物心聲（content/check_voice.json，依屬性減難度分檔）；沒有檢定或沒寫心聲是空字串。"""
    check = choice.check
    bands = content.check_voice.bands
    if check is None or not bands:
        return ""
    gap = check_gap(check, state, content, world)
    band = next((b for b in bands if gap >= b.min_gap), bands[-1])
    line = band.lines.get(check.stat) or band.lines.get("default", "")
    key = team.check_actor(state, content, world, check)
    who = "你" if key == PLAYER else team.member_name(state, content, key)
    return line.replace("{who}", who)


# 選項標的報酬種類（企劃者 2026-10-05：選之前就知道這一步圖的是什麼）：只標種類、不寫數字，照這個順序
_STAT_REWARDS = ("fame", "silver", "xinde", "good", "str", "agi", "con", "wis")


def effect_rewards(effect: Effect, content: Content) -> list[str]:
    """這個效果會給的東西（只算給、不算扣）：名望、銀兩、心得、素材、情誼、武學、同伴……；惡名也標，那是選了的後果。"""
    names = content.config.stat_names
    kinds = [names.get(k, k) for k in _STAT_REWARDS if effect.stats.get(k, 0) > 0]
    if effect.stats.get("evil", 0) > 0:
        kinds.append(names.get("evil", "惡名"))
    if any(n > 0 for n in effect.materials.values()):
        kinds.append("素材")
    if any(n > 0 for n in effect.affinity.values()):
        kinds.append("情誼")
    if effect.learn_skills:
        kinds.append("武學")
    if effect.recruit:
        kinds.append("同伴")
    if effect.followers:
        kinds.append("部下")
    return kinds


def choice_rewards(choice: Choice, content: Content) -> list[str]:
    """選項成功（或沒有檢定時）會給的東西的種類。"""
    return effect_rewards(choice.effect, content)
