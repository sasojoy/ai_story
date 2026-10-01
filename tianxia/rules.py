"""數值規則的核心：條件判定、效果套用、屬性檢定、大勢推進、習得武學。"""
from __future__ import annotations

import random

from . import roster, team  # 與 roster 互相 import：只能引入整個模組、呼叫時才取屬性，不能 from .roster import …
from .models import Check, Condition, Content, Effect
from .state import PLAYER, GameState, Rumor
from .world_state import JADE_SEAL_FRAGMENT_COUNT, WorldStateStore

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
    known_skills = {p.member.neigong_id, p.member.wugong_id} - {None}
    if any(s not in known_skills for s in cond.skills_all):
        return False
    if any(s in known_skills for s in cond.skills_none):
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
    if set(cond.members_none) & set(p.team):
        return False
    if cond.any_of and not any(check_condition(sub, state) for sub in cond.any_of):
        return False
    return True


def check_chance(check: Check, state: GameState, content: Content, world: WorldStateStore) -> float:
    """出手者的屬性每高於難度 1 點，成功率 +10%；範圍 5%～95%。"""
    key = team.check_actor(state, content, world, check)
    value = team.check_value(state, content, world, key, check.stat)
    return min(0.95, max(0.05, 0.5 + (value - check.difficulty) * 0.1))


def roll_check(check: Check, state: GameState, content: Content, world: WorldStateStore, rng: random.Random) -> bool:
    return rng.random() < check_chance(check, state, content, world)


def check_who(check: Check, state: GameState, content: Content, world: WorldStateStore) -> str:
    """選項與結果上寫的出手者：本人檢定寫「本人」；隊伍檢定寫「某某出手」，派出的是本人時寫「本人出手」。"""
    if check.by == "self":
        return "本人"
    key = team.check_actor(state, content, world, check)
    return "本人出手" if key == PLAYER else f"{team.member_name(state, content, key)}出手"


def add_rumor(state: GameState, text: str, location: str | None = None) -> None:
    state.world.rumors.append(Rumor(time=state.world.time, text=text, location=location))


def add_chronicle(state: GameState, text: str) -> None:
    state.world.chronicle.append(Rumor(time=state.world.time, text=text))


def trend_name(content: Content, trend_id: str) -> str:
    return next(t.name for t in content.scenario.trends if t.id == trend_id)


def change_trend(
    state: GameState, content: Content, trend_id: str, delta: int, reveal: bool = True
) -> list[str]:
    """推動大勢線。隱藏線只有在 reveal=True 且正向推進時才會浮現；未浮現前其他推動一律無效。

    已浮現的大勢線，每次真的推動（夾在 0~100 之後實際有變化）都會多回傳一則顯示用的
    訊息，跟「銀兩 -5」「名望 +1」同一種呈現方式——改這個之前，大勢線只有「第一次浮現」
    那一刻才有任何文字反饋，之後不管是打贏遭遇戰、選了某個事件分支推動了多少，玩家在
    劇情文字裡完全看不到，必須自己點開「江湖大勢」分頁才看得到數字，等於看不出自己的
    行動有沒有用。sim_tick()（背景虛擬玩家，每小時自動微幅推動）刻意不接住這個回傳值，
    所以背景推動依然維持安靜，不會洗版；只有玩家自己選擇/打贏的那一刻才會顯示。"""
    w = state.world
    msgs: list[str] = []
    if trend_id not in w.revealed:
        if not reveal or delta <= 0:
            return msgs
        w.revealed.add(trend_id)
        msgs.append(f"（江湖暗流湧動——「{trend_name(content, trend_id)}」浮上檯面。）")
    before = w.trends.get(trend_id, 0)
    after = min(100, max(0, before + delta))
    w.trends[trend_id] = after
    actual = after - before
    if actual:
        msgs.append(f"（{trend_name(content, trend_id)} {'+' if actual >= 0 else ''}{actual}）")
    return msgs


def learn_skill(state: GameState, content: Content, skill_id: str) -> list[str]:
    """每人最多學一門內功、一門武學（設計文件六.4）：對應的欄位已經有人時直接跳過，不覆蓋。"""
    member = state.player.member
    skill = content.skills[skill_id]
    slot = "neigong_id" if skill.kind == "內功" else "wugong_id"
    if getattr(member, slot) == skill_id:
        return []
    if getattr(member, slot) is not None:
        return [f"你已經學了一門{skill.kind}，【{skill.name}】這次先無緣習得。"]
    setattr(member, slot, skill_id)
    setattr(member, slot.replace("_id", "_level"), 1)
    return [f"你習得了【{skill.name}】！"]


def apply_effect(effect: Effect, state: GameState, content: Content, world: WorldStateStore) -> list[str]:
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
    if effect.leave_sect and p.sect:
        msgs.append(f"你叛出了{content.sects[p.sect].name}。")
        p.flags.add(f"叛出:{p.sect}")
        p.sect = None
    if effect.recruit:
        msgs += roster.recruit(state, content, world, effect.recruit)
    for trend_id, delta in effect.trend.items():
        msgs += change_trend(state, content, trend_id, delta)
    jade_seal_flag = content.scenario.jade_seal_flag
    newly_found_shard = (
        jade_seal_flag is not None and jade_seal_flag in effect.world_flags_add and jade_seal_flag not in state.world.flags
    )
    add_world_flags(state, effect.world_flags_add)
    name = display_name(state)
    if effect.rumor:
        text = effect.rumor.format(name=name)
        add_rumor(state, text, state.player.location)  # 玩家觸發的傳聞記在當時所在地
        msgs.append(f"【江湖傳聞】{text}")
    if effect.chronicle:
        add_chronicle(state, effect.chronicle.format(name=name))
    if newly_found_shard:
        fragment_text = effect.chronicle.format(name=name) if effect.chronicle else f"{name}取得了傳國玉璽的一塊碎片。"
        fragment = world.record_jade_seal_fragment(name, content.scenario.name, fragment_text)
        if fragment is not None:
            msgs.append(f"🏺 【天下大事】{name}尋得傳國玉璽第 {fragment.number} 塊碎片！（{fragment.number}/{JADE_SEAL_FRAGMENT_COUNT} 已現世）")
    return msgs
