"""江湖大勢：大勢門檻、世界事件、分幕主線與主線改寫、虛擬玩家、賽季結局。"""
from __future__ import annotations

import random

from .models import Act, Content, Ending, Storyline
from .rules import add_chronicle, add_rumor, add_world_flags, change_trend, check_condition
from .state import GameState


def check_thresholds(state: GameState, content: Content) -> list[str]:
    """依序處理大勢門檻、世界事件（各只觸發一次），最後更新主線進度。"""
    w = state.world
    msgs: list[str] = []
    if w.ended:
        return msgs
    for th in content.scenario.thresholds:
        if th.id in w.fired_thresholds:
            continue
        value = w.trends.get(th.trend, 0)
        if not (value >= th.value if th.op == ">=" else value <= th.value):
            continue
        msgs += _fire(state, content, th.id, th.text, th.world_flags_add, th.ends_season, th.location)
        if w.ended:
            return msgs
    for event in content.scenario.world_events:
        if event.id in w.fired_thresholds or not check_condition(event.condition, state):
            continue
        msgs += _fire(state, content, event.id, event.text, event.world_flags_add, event.ends_season, event.location)
        if w.ended:
            return msgs
    return msgs + update_storyline(state, content)


def _fire(
    state: GameState, content: Content, fire_id: str, text: str, flags: list[str], ends_season: bool,
    location: str | None = None,
) -> list[str]:
    state.world.fired_thresholds.add(fire_id)
    add_world_flags(state, flags)
    add_rumor(state, text, location)
    add_chronicle(state, text)
    msgs = [f"【江湖大事】{text}"]
    if ends_season:
        msgs += end_season(state, content)
    return msgs


def current_storyline(state: GameState, content: Content) -> Storyline:
    return next(s for s in content.scenario.storylines if s.id == state.world.storyline)


def current_act(state: GameState, content: Content) -> Act:
    return current_storyline(state, content).acts[state.world.act]


def update_storyline(state: GameState, content: Content) -> list[str]:
    """還在主線時，檢查是否被支線主線取代；接著一路推進已滿足條件的幕。"""
    w = state.world
    msgs: list[str] = []
    main = content.scenario.storylines[0]
    if w.storyline == main.id:
        for branch in content.scenario.storylines[1:]:
            if branch.replaces_when is not None and check_condition(branch.replaces_when, state):
                w.storyline, w.act = branch.id, 0
                text = f"主線改寫——「{branch.name}」。{branch.intro}"
                add_rumor(state, text)
                add_chronicle(state, text)
                msgs.append(f"【主線改寫】{branch.name}：{branch.intro}")
                break
    line = current_storyline(state, content)
    while w.act < len(line.acts) - 1:
        act = line.acts[w.act]
        if act.advance_when is None or not check_condition(act.advance_when, state):
            break
        w.act += 1
        nxt = line.acts[w.act]
        msgs.append(f"【主線】第{w.act + 1}幕「{nxt.title}」：{nxt.text}")
        add_chronicle(state, f"{line.name}・第{w.act + 1}幕「{nxt.title}」")
    return msgs


def sim_tick(state: GameState, content: Content, hours: int, rng: random.Random) -> list[str]:
    msgs: list[str] = []
    for _ in range(hours):
        for sim in content.scenario.sim_players:
            if sim.requires_revealed and sim.requires_revealed not in state.world.revealed:
                continue
            if not check_condition(sim.condition, state):
                continue
            if rng.random() >= sim.actions_per_day / 24:
                continue
            for trend_id, delta in sim.trend.items():
                change_trend(state, content, trend_id, delta, reveal=False)
            if sim.rumors and rng.random() < sim.rumor_chance:
                text = rng.choice(sim.rumors).format(name=sim.name)
                add_rumor(state, text, sim.haunts[0] if sim.haunts else None)  # 記在第一個常出沒處；不多用亂數
                msgs.append(f"【江湖傳聞】{text}")
        msgs += check_thresholds(state, content)
        if state.world.ended:
            break
    return msgs


def evaluate_ending(state: GameState, content: Content) -> Ending:
    for ending in content.scenario.endings:
        if ending.storyline not in (None, state.world.storyline):
            continue
        if check_condition(ending.condition, state):
            return ending
    return content.scenario.endings[-1]


def end_season(state: GameState, content: Content) -> list[str]:
    w = state.world
    if w.ended:
        return []
    ending = evaluate_ending(state, content)
    w.ended = True
    w.ending_title = ending.title
    w.ending_text = ending.text
    add_chronicle(state, f"賽季落幕：{ending.title}")
    return [f"══ 賽季落幕：{ending.title} ══", ending.text]
