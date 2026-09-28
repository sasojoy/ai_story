"""江湖大勢：大勢線門檻、虛擬玩家、賽季結局。"""
from __future__ import annotations

import random

from .models import Content, Ending
from .rules import add_chronicle, add_rumor, change_trend, check_condition
from .state import GameState


def check_thresholds(state: GameState, content: Content) -> list[str]:
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
        w.fired_thresholds.add(th.id)
        w.flags |= set(th.world_flags_add)
        add_rumor(state, th.text)
        add_chronicle(state, th.text)
        msgs.append(f"【江湖大事】{th.text}")
        if th.ends_season:
            msgs += end_season(state, content)
            break
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
                add_rumor(state, text)
                msgs.append(f"【江湖傳聞】{text}")
        msgs += check_thresholds(state, content)
        if state.world.ended:
            break
    return msgs


def evaluate_ending(state: GameState, content: Content) -> Ending:
    for ending in content.scenario.endings:
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
