"""江湖大勢：大勢門檻、世界事件、分幕主線與主線改寫、虛擬玩家、賽季結局。"""
from __future__ import annotations

import random

from . import flavor, leaderboard
from .models import Act, Content, Ending, SimPlayer, SimRumor, Storyline
from .ollama_client import OllamaClient
from .rules import add_chronicle, add_rumor, add_world_flags, change_trend, check_condition
from .state import GameState
from .world_state import WorldStateStore


def check_thresholds(
    state: GameState, content: Content, world: WorldStateStore | None = None, client: OllamaClient | None = None,
) -> list[str]:
    """依序處理大勢門檻、世界事件（各只觸發一次），最後更新主線進度。world/client 給
    _fire() 用來潤色江湖大事的傳聞文字（設計文件 8.2 第 4 點）；不傳就是原本的純文字，
    兩者都是選填，不影響既有呼叫端或測試。"""
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
        msgs += _fire(state, content, th.id, th.text, th.world_flags_add, th.ends_season, th.location, world, client)
        if w.ended:
            return msgs
    for event in content.scenario.world_events:
        if event.id in w.fired_thresholds or not check_condition(event.condition, state):
            continue
        msgs += _fire(
            state, content, event.id, event.text, event.world_flags_add, event.ends_season, event.location,
            world, client,
        )
        if w.ended:
            return msgs
    return msgs + update_storyline(state, content)


def _fire(
    state: GameState, content: Content, fire_id: str, text: str, flags: list[str], ends_season: bool,
    location: str | None = None, world: WorldStateStore | None = None, client: OllamaClient | None = None,
) -> list[str]:
    state.world.fired_thresholds.add(fire_id)
    add_world_flags(state, flags)
    add_rumor(state, text, location)
    add_chronicle(state, text)
    shown_text = text
    if world is not None:
        flourish = world.get_event_flavor(fire_id)
        if not flourish and client is not None:
            flourish = flavor.polish_world_event(client, text)
            if flourish:
                world.set_event_flavor(fire_id, flourish)
                flourish = world.get_event_flavor(fire_id)  # 可能被別的玩家搶先寫入，讀回真正共用的那一份
        if flourish:
            shown_text = f"{text}\n\n{flourish}"
    msgs = [f"【江湖大事】{shown_text}"]
    if ends_season:
        msgs += end_season(state, content, world)
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
        w.act_reached = max(w.act_reached, w.act)
        nxt = line.acts[w.act]
        msgs.append(f"【主線】第{w.act + 1}幕「{nxt.title}」：{nxt.text}")
        add_chronicle(state, f"{line.name}・第{w.act + 1}幕「{nxt.title}」")
    return msgs


def sim_active(sim: SimPlayer, state: GameState) -> bool:
    """虛擬玩家的這一條設定現在會不會行動：它需要的隱藏大勢已浮現，而且條件成立。世界模擬與大地圖詳情共用。"""
    if sim.requires_revealed and sim.requires_revealed not in state.world.revealed:
        return False
    return check_condition(sim.condition, state)


def sim_tick(state: GameState, content: Content, hours: int, rng: random.Random) -> list[str]:
    msgs: list[str] = []
    for _ in range(hours):
        for sim in content.scenario.sim_players:
            if not sim_active(sim, state):
                continue
            if rng.random() >= sim.actions_per_day / 24:
                continue
            for trend_id, delta in sim.trend.items():
                change_trend(state, content, trend_id, delta, reveal=False)
            if sim.rumors and rng.random() < sim.rumor_chance:
                text, where = _rumor_place(sim, rng.choice(sim.rumors))  # 和以前一樣只抽一次亂數
                text = text.format(name=sim.name)
                add_rumor(state, text, where)
                msgs.append(f"【江湖傳聞】{text}")
        msgs += check_thresholds(state, content)
        if state.world.ended:
            break
    return msgs


def _rumor_place(sim: SimPlayer, rumor: str | SimRumor) -> tuple[str, str | None]:
    """虛擬玩家一則傳聞的（文字, 發生地）：寫明地點的記在那裡，否則記在第一個常出沒處。不用亂數。"""
    if isinstance(rumor, SimRumor):
        return rumor.text, rumor.location
    return rumor, sim.haunts[0] if sim.haunts else None


def evaluate_ending(state: GameState, content: Content) -> Ending:
    for ending in content.scenario.endings:
        if ending.storyline not in (None, state.world.storyline):
            continue
        if check_condition(ending.condition, state):
            return ending
    return content.scenario.endings[-1]


def end_season(state: GameState, content: Content, world: WorldStateStore | None = None) -> list[str]:
    """world 給的話，順便算一次天下武學榜／內功榜附在結局後面（設計文件 6.5）；不傳就是
    原本的純結局文字，選填不影響既有呼叫端或測試。"""
    w = state.world
    if w.ended:
        return []
    ending = evaluate_ending(state, content)
    w.ended = True
    w.ending_title = ending.title
    w.ending_text = ending.text
    add_chronicle(state, f"賽季落幕：{ending.title}")
    msgs = [f"══ 賽季落幕：{ending.title} ══", ending.text]
    if world is not None:
        board = leaderboard.compute_leaderboard(content, world)
        msgs += leaderboard.format_lines(board)
    return msgs
