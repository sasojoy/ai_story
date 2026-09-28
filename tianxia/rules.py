"""數值規則的核心：條件判定、效果套用、屬性檢定、大勢推進、習得武學。"""
from __future__ import annotations

import random

from .models import Check, Condition, Content, Effect
from .state import GameState, Rumor

DAY = 86400


def display_name(state: GameState) -> str:
    return "某位少俠" if state.player.anonymous else state.player.name


def current_day(state: GameState) -> int:
    """賽季第幾天（從 1 開始）。"""
    return int(state.world.time // DAY) + 1


def add_world_flags(state: GameState, flags) -> None:
    """加入世界旗標並記錄第一次成立的時間；已存在的旗標不重設時間。"""
    w = state.world
    for flag in flags:
        if flag not in w.flags:
            w.flags.add(flag)
            w.flag_times[flag] = w.time


def check_condition(cond: Condition, state: GameState) -> bool:
    p, w = state.player, state.world
    if any(p.stats.get(k, 0) < v for k, v in cond.min_stats.items()):
        return False
    if any(p.stats.get(k, 0) > v for k, v in cond.max_stats.items()):
        return False
    if not set(cond.flags_all) <= p.flags or set(cond.flags_none) & p.flags:
        return False
    if cond.sects and p.sect not in cond.sects:
        return False
    if cond.no_sect and p.sect is not None:
        return False
    if any(s not in p.skills for s in cond.skills_all):
        return False
    if any(s in p.skills for s in cond.skills_none):
        return False
    if any(w.trends.get(t, 0) < v for t, v in cond.trend_min.items()):
        return False
    if any(w.trends.get(t, 0) > v for t, v in cond.trend_max.items()):
        return False
    if not set(cond.world_flags_all) <= w.flags or set(cond.world_flags_none) & w.flags:
        return False
    day = current_day(state)
    if cond.day_min is not None and day < cond.day_min:
        return False
    if cond.day_max is not None and day > cond.day_max:
        return False
    if not set(cond.revealed_all) <= w.revealed or set(cond.revealed_none) & w.revealed:
        return False
    for flag, hours in cond.flag_age_hours.items():
        if flag not in w.flag_times or w.time - w.flag_times[flag] < hours * 3600:
            return False
    if cond.any_of and not any(check_condition(sub, state) for sub in cond.any_of):
        return False
    return True


def check_chance(check: Check, state: GameState) -> float:
    """屬性每高於難度 1 點，成功率 +10%；範圍 5%～95%。"""
    value = state.player.stats.get(check.stat, 0)
    return min(0.95, max(0.05, 0.5 + (value - check.difficulty) * 0.1))


def roll_check(check: Check, state: GameState, rng: random.Random) -> bool:
    return rng.random() < check_chance(check, state)


def add_rumor(state: GameState, text: str) -> None:
    state.world.rumors.append(Rumor(time=state.world.time, text=text))


def add_chronicle(state: GameState, text: str) -> None:
    state.world.chronicle.append(Rumor(time=state.world.time, text=text))


def trend_name(content: Content, trend_id: str) -> str:
    return next(t.name for t in content.scenario.trends if t.id == trend_id)


def change_trend(
    state: GameState, content: Content, trend_id: str, delta: int, reveal: bool = True
) -> list[str]:
    """推動大勢線。隱藏線只有在 reveal=True 且正向推進時才會浮現；未浮現前其他推動一律無效。"""
    w = state.world
    msgs: list[str] = []
    if trend_id not in w.revealed:
        if not reveal or delta <= 0:
            return msgs
        w.revealed.add(trend_id)
        msgs.append(f"（江湖暗流湧動——「{trend_name(content, trend_id)}」浮上檯面。）")
    w.trends[trend_id] = min(100, max(0, w.trends.get(trend_id, 0) + delta))
    return msgs


def learn_skill(state: GameState, content: Content, skill_id: str) -> list[str]:
    p = state.player
    if skill_id in p.skills:
        return []
    p.skills[skill_id] = 1
    return [f"你習得了【{content.skills[skill_id].name}】！（可在「門下」分頁配置給隊中的人。）"]


def apply_effect(effect: Effect, state: GameState, content: Content) -> list[str]:
    p = state.player
    names = content.config.stat_names
    msgs: list[str] = []
    if effect.text:
        msgs.append(effect.text)
    for key, delta in effect.stats.items():
        p.stats[key] = max(0, p.stats.get(key, 0) + delta)
        msgs.append(f"{names.get(key, key)} {'+' if delta >= 0 else ''}{delta}")
    if effect.stamina:
        p.stamina = min(content.config.stamina_max, max(0.0, p.stamina + effect.stamina))
        msgs.append(f"體力 {'+' if effect.stamina > 0 else ''}{effect.stamina}")
    p.flags |= set(effect.flags_add)
    p.flags -= set(effect.flags_remove)
    for skill_id in effect.learn_skills:
        msgs += learn_skill(state, content, skill_id)
    if effect.join_sect:
        sect = content.sects[effect.join_sect]
        p.sect = sect.id
        msgs.append(f"你拜入了{sect.name}！")
        for skill_id in sect.starter_skills:
            msgs += learn_skill(state, content, skill_id)
    if effect.leave_sect and p.sect:
        msgs.append(f"你叛出了{content.sects[p.sect].name}。")
        p.flags.add(f"叛出:{p.sect}")
        p.sect = None
    for trend_id, delta in effect.trend.items():
        msgs += change_trend(state, content, trend_id, delta)
    add_world_flags(state, effect.world_flags_add)
    name = display_name(state)
    if effect.rumor:
        text = effect.rumor.format(name=name)
        add_rumor(state, text)
        msgs.append(f"【江湖傳聞】{text}")
    if effect.chronicle:
        add_chronicle(state, effect.chronicle.format(name=name))
    return msgs
