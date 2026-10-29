"""人物的行程與盤算（Joy 2026-10-29「讓整個世界活起來」：「世界會自己變，不管你在不在都會出事」；「有一堆武將真的很像是
木頭人，例如劉關張」「其他角色也是，尤其有名的」；設計稿 https://claude.ai/artifact/LFooPvhRw5NHosh3wDUKRV 第一節；
數字在 Config.plans，行程在 content/itineraries.json）。

- 行程（tick，world.advance_world_state 每一步叫）：有名的人物照史書排的幾站自己動身。一般的一站到時間就做：人走到那裡、
  發一則天下大事、記一筆世界記事（deeds）。跟著別人走的人（關羽、張飛跟著劉備）一起走。
- 盤算（行程上寫了 contest 的那一站）：提前 lead_days7（照季長換算）公告，人物先走到那裡；全服同時最多開 max_open 件，滿了就等。
  公告期間人在那裡的玩家可以助他一臂、或壞他的事（花 stamina；散人兩樣都行，兩軍與豪強照此刻站的那一邊），到點引擎照兩邊各幾人
  擲骰（亂數「盤算｜天機｜站 id」，不碰 Game.rng）：成了照 contest 推大勢線、立旗標；不成退到 lose_place。沒人插手也照樣結算。
  一直等不到空位、到點還沒公告的那一件不讓人插手，直接照 base 擲。
- 結果（deliver，Game.sync 叫）：助他辦成的人情誼照 Config.plans 加，其他人寫一句結果。
- 有行程的人不再在常去的地方之間隨機晃（figure_life._act 問 holds）。大勢人物倒下、不在場時他的站跳過（記成沒辦成）。
只 import models、state、rules、calendar、figures、figure_life、deeds、renown；world、engine 呼叫它。"""
from __future__ import annotations

import random

from . import calendar, deeds, figure_life, figures, renown
from .models import Content, Itinerary, ItineraryStop
from .rules import add_rumor, add_world_flags, change_trend, trend_shown
from .state import GameState, Plan

TITLE = "盤算"  # 江湖紀錄那一則的標題

# 待 joy 潤
HELP_LABEL = "助{name}一臂"
BLOCK_LABEL = "壞{name}的事"
DONE_HELP = "助{name}一臂（你已經出過力了）"
DONE_BLOCK = "壞{name}的事（你已經出過手了）"
HELPED = "你替{name}出了一份力。{when}見分曉。"
BLOCKED = "你暗中壞了{name}的事。{when}見分曉。"
GONE = "這件事已經有了結果。"
NOT_HERE = "你不在那裡。"
ALREADY = "這件事你已經插過手了。"
WRONG_SIDE = "你站的那一邊不會這麼做。"
FELL_OFF = "{name}倒下了，{place}那件事不了了之。"  # 天下大事：盤算還沒到點人物就倒下
WON_HELPED = "{name}在{place}那件事成了，你出的那一份力他記著。"
WON_BLOCKED = "{name}在{place}那件事還是成了，你沒能攔住。"
LOST_HELPED = "{name}在{place}那件事沒成，你那一份力白費了。"
LOST_BLOCKED = "{name}在{place}那件事沒成，你壞事得手了。"
CARD_HEAD = "{name}的打算"


def on(content: Content) -> bool:
    return content.config.plans.enabled and bool(content.itineraries) and figure_life.on(content)


def holds(content: Content, cid: str) -> bool:
    """這位人物照行程走（不在常去的地方之間隨機晃）。"""
    return on(content) and any(it.who == cid for it in content.itineraries)


def _all_stops(content: Content) -> list[tuple[Itinerary, ItineraryStop]]:
    pairs = [(it, st) for it in content.itineraries for st in it.stops]
    return sorted(pairs, key=lambda x: x[1].day)


def find_stop(content: Content, stop_id: str) -> tuple[Itinerary, ItineraryStop] | None:
    return next(((it, st) for it, st in _all_stops(content) if st.id == stop_id), None)


def find(state: GameState, stop_id: str) -> Plan | None:
    return next((p for p in state.world.plans if p.stop == stop_id), None)


def open_plans(state: GameState) -> list[Plan]:
    return [p for p in state.world.plans if not p.settled]


def _name(content: Content, cid: str) -> str:
    ch = content.characters.get(cid)
    return ch.name if ch is not None else cid


def _place(content: Content, loc: str) -> str:
    return content.locations[loc].name if loc in content.locations else loc


def _fill(text: str, content: Content, cid: str, loc: str) -> str:
    return text.replace("{name}", _name(content, cid)).replace("{place}", _place(content, loc))


# ── 季上的位置：照 7 天季的「第幾天」算（別的季長照比例）────────


def day7(content: Content, world, time: float, end: float) -> float:
    """世界秒 time 換成 7 天季的第幾天（1.0 是第 1 天 00:00，8.0 是季末）。季曆照 calendar.cal_days（7 天季、21 天季對得上時刻表的天）。"""
    total = calendar.cal_days(end, content, world)
    if total <= 0:
        return 1.0
    return 1.0 + 7.0 * calendar.cal_days(time, content, world) / total


def _time_of(content: Content, world, day: float, end: float) -> float:
    """7 天季的第 day 天是哪一個世界秒（day7 的反函數；季曆天跟世界秒是線性的）。"""
    now = world.time
    here, there = day7(content, world, now, end), day7(content, world, end, end)
    if there <= here:
        return now
    return now + (day - here) * (end - now) / (there - here)


# ── 行程與盤算（季的事）────────────────────────────────


def _alive(state: GameState, content: Content, cid: str) -> bool:
    fid = figures.of_character(content, cid)
    return fid is None or figures.state_of(state, content, fid).status == "active"


def _gate(state: GameState, st: ItineraryStop) -> bool | None:
    """if_won／if_lost 都對得上是 True、有一件還沒結果是 None（再等）、對不上是 False（這一站不會有）。"""
    done = state.world.stops_done
    for ref in st.if_won + st.if_lost:
        if ref not in done:
            return None
    return all(done[r] for r in st.if_won) and not any(done[r] for r in st.if_lost)


def _go(state: GameState, content: Content, cid: str, dest: str) -> None:
    """人走到 dest，跟著他的人一起走（關羽、張飛跟著劉備）。"""
    figure_life._place_at(state, content, cid, figures.of_character(content, cid), dest)
    for other, ch in content.characters.items():
        if ch.follows == cid and ch.deep_interaction and _alive(state, content, other):
            figure_life._place_at(state, content, other, figures.of_character(content, other), dest)


def _company(content: Content, cid: str) -> list[str]:
    return [cid] + [other for other, ch in content.characters.items() if ch.follows == cid]


def tick(state: GameState, content: Content, end: float) -> None:
    """照時間做行程的每一站：一般的一站到點就做；盤算到了公告的時候開（空位不夠就等）、到點結算。end 是這一季收季的世界秒
    （world.season_end_time，呼叫端給：plans 不 import world）。"""
    w = state.world
    if not on(content) or w.ended:
        return
    tuning = content.config.plans
    pos = day7(content, w, w.time, end)
    for it, st in _all_stops(content):
        if st.id in w.stops_done:
            continue
        gate = _gate(state, st)
        if gate is None:
            continue
        if gate is False or not _alive(state, content, it.who):
            plan = find(state, st.id)
            if plan is not None and not plan.settled:
                _fall_off(state, content, it, st, plan)
            elif pos >= st.day or gate is False:
                w.stops_done[st.id] = False  # 這一站不會有了（倒下、不在場，或前面那一站的結果不對）
            continue
        if st.contest is None:
            if pos >= st.day:
                _arrive(state, content, it, st)
            continue
        plan = find(state, st.id)
        if plan is None:
            if pos >= st.day:
                _settle(state, content, it, st, Plan(stop=st.id, who=it.who, place=st.place, open_at=w.time, due=w.time))
            elif pos >= st.day - tuning.lead_days7 and len(open_plans(state)) < tuning.max_open:
                _open(state, content, it, st, end)
        elif w.time >= plan.due:
            _settle(state, content, it, st, plan)


def _arrive(state: GameState, content: Content, it: Itinerary, st: ItineraryStop) -> None:
    _go(state, content, it.who, st.place)
    text = _fill(st.text, content, it.who, st.place)
    add_rumor(state, text, st.place, content=content, layer="world")
    deeds.record(state, content, "move", text, place=st.place, figures=_company(content, it.who),
                 side=figure_life.side_of(content, it.who))
    state.world.stops_done[st.id] = True


def _open(state: GameState, content: Content, it: Itinerary, st: ItineraryStop, end: float) -> None:
    w = state.world
    plan = Plan(stop=st.id, who=it.who, place=st.place, open_at=w.time, due=max(w.time, _time_of(content, w, st.day, end)))
    w.plans.append(plan)
    _go(state, content, it.who, st.place)  # 人先到那裡：公告期間在那裡見得到他
    add_rumor(state, _fill(st.contest.announce, content, it.who, st.place), st.place, content=content, layer="world")


def chance(content: Content, st: ItineraryStop, plan: Plan) -> float:
    """成的機會：base ＋ swing ×（助－壞）÷（助＋壞＋soft），夾在 [floor, cap]。"""
    t = content.config.plans
    h, b = len(plan.helpers), len(plan.blockers)
    raw = st.contest.base + t.swing * (h - b) / (h + b + t.soft)
    return max(t.floor, min(t.cap, raw))


def _settle(state: GameState, content: Content, it: Itinerary, st: ItineraryStop, plan: Plan) -> None:
    w = state.world
    c = st.contest
    if plan not in w.plans:
        w.plans.append(plan)
    won = random.Random(f"盤算|{w.tianji}|{st.id}").random() < chance(content, st, plan)
    plan.settled, plan.won = True, won
    w.stops_done[st.id] = won
    if won:
        _go(state, content, it.who, st.place)
    elif c.lose_place is not None:
        _go(state, content, it.who, c.lose_place)
    for line, n in (c.trends_win if won else c.trends_lose).items():
        if n and trend_shown(content, w, line):
            change_trend(state, content, line, n, reveal=False)
    if won and c.flag_win:
        add_world_flags(state, [c.flag_win])
    text = _fill(c.win if won else c.lose, content, it.who, st.place)
    add_rumor(state, text, st.place, content=content, layer="world")
    other = _other_side(content, c.side)
    deeds.record(state, content, "plan", text, place=st.place, figures=_company(content, it.who),
                 actors=plan.helpers if won else plan.blockers, side=c.side if won else other)


def _fall_off(state: GameState, content: Content, it: Itinerary, st: ItineraryStop, plan: Plan) -> None:
    """盤算還沒到點人物就倒下：不了了之，不推線、兩邊都沒有人算贏。"""
    plan.settled, plan.won = True, False
    state.world.stops_done[st.id] = False
    add_rumor(state, FELL_OFF.format(name=_name(content, it.who), place=_place(content, st.place)), st.place,
              content=content, layer="world")


def _warring(content: Content) -> list[str]:
    return [f.id for f in content.scenario.factions if f.goals and "geju" not in f.goals]


def _other_side(content: Content, side: str) -> str | None:
    return next((f for f in _warring(content) if f != side), None)


# ── 玩家插手 ─────────────────────────────────────────


def stance(state: GameState, content: Content, plan: Plan) -> str:
    """這個人能怎麼插手：help、block，或 both（散人、還沒選邊的豪強）。豪強照此刻幫的那一軍（PlayerState.ally）。"""
    pair = find_stop(content, plan.stop)
    p = state.player
    side = p.ally or p.faction
    if pair is None or side not in _warring(content):
        return "both"
    return "help" if side == pair[1].contest.side else "block"


def joined(state: GameState, plan: Plan) -> str | None:
    key = state.player.name.casefold()
    if any(n.casefold() == key for n in plan.helpers):
        return "help"
    if any(n.casefold() == key for n in plan.blockers):
        return "block"
    return None


def here(state: GameState, content: Content) -> list[Plan]:
    """人在這裡（不在路上）、這裡正開著的盤算。"""
    p = state.player
    if not on(content) or p.journey is not None:
        return []
    return [plan for plan in open_plans(state) if plan.place == p.location]


def options(state: GameState, content: Content) -> list[tuple[str, str, bool]]:
    """這裡能按的鈕：（選項 id、字、按不按得下）。插過手的那一件留一顆灰的。"""
    out: list[tuple[str, str, bool]] = []
    for plan in here(state, content):
        name = _name(content, plan.who)
        done = joined(state, plan)
        if done is not None:
            out.append((f"plan:{done}:{plan.stop}", (DONE_HELP if done == "help" else DONE_BLOCK).format(name=name), False))
            continue
        how = stance(state, content, plan)
        if how in ("help", "both"):
            out.append((f"plan:help:{plan.stop}", HELP_LABEL.format(name=name), True))
        if how in ("block", "both"):
            out.append((f"plan:block:{plan.stop}", BLOCK_LABEL.format(name=name), True))
    return out


def problem(state: GameState, content: Content, verb: str, stop_id: str) -> str | None:
    plan = find(state, stop_id)
    if plan is None or plan.settled or not on(content):
        return GONE
    if plan not in here(state, content):
        return NOT_HERE
    if joined(state, plan) is not None:
        return ALREADY
    how = stance(state, content, plan)
    if verb not in ("help", "block") or (how != "both" and how != verb):
        return WRONG_SIDE
    return None


def join(state: GameState, content: Content, verb: str, stop_id: str, when: str) -> list[str]:
    """記下這個人插了手（呼叫端已經驗過 problem、扣了體力）。when 是到點那一刻的寫法（Game.stamp）。"""
    plan = find(state, stop_id)
    name = _name(content, plan.who)
    if verb == "help":
        plan.helpers.append(state.player.name)
        return [HELPED.format(name=name, when=when)]
    plan.blockers.append(state.player.name)
    return [BLOCKED.format(name=name, when=when)]


def deliver(state: GameState, content: Content) -> list[str]:
    """同步時叫：我插過手、已經結算、還沒領過的盤算。站對了邊、助他辦成的人情誼照 Config.plans 加（名望的來源有固定的幾條，這裡不給）。"""
    p = state.player
    t = content.config.plans
    out: list[str] = []
    for plan in state.world.plans:
        if not plan.settled or plan.stop in p.plans_paid:
            continue
        mine = joined(state, plan)
        if mine is None:
            continue
        p.plans_paid.append(plan.stop)
        name, place = _name(content, plan.who), _place(content, plan.place)
        good = (mine == "help") == bool(plan.won)
        tmpl = (WON_HELPED if mine == "help" else WON_BLOCKED) if plan.won else (LOST_HELPED if mine == "help" else LOST_BLOCKED)
        out.append(tmpl.format(name=name, place=place))
        if not good:
            continue
        if mine == "help" and t.affinity:
            before = p.affinities.get(plan.who, 0)
            p.affinities[plan.who] = max(0, min(100, before + renown.warmed(content, t.affinity)))
            if p.affinities[plan.who] != before:
                out.append(f"{name}情誼 {p.affinities[plan.who] - before:+d}")
    return out


# ── 江湖頁那一張卡：全服開著的盤算裡，最切身的一件 ──────────


def _score(state: GameState, content: Content, plan: Plan) -> int:
    p = state.player
    score = 0
    if stance(state, content, plan) != "both":
        score += 2  # 跟你那一邊有關
    if p.journey is None and plan.place == p.location:
        score += 4
    elif figure_life._region(content, plan.place) == figure_life._region(content, p.location):
        score += 2
    if p.affinities.get(plan.who, 0) > 0:
        score += 1  # 你認識的人
    return score


def pick(state: GameState, content: Content) -> Plan | None:
    """全服開著的盤算裡最切身的一件（一樣切身看哪一件先到點）；其他的不上江湖頁。"""
    live = open_plans(state) if on(content) else []
    if not live:
        return None
    return max(live, key=lambda plan: (_score(state, content, plan), -plan.due))


def card(state: GameState, content: Content, plan: Plan, *, when: str, minutes: int | None) -> dict:
    """江湖頁的盤算卡（main_view 的 plan）：誰、打算做什麼、在哪、什麼時候、兩邊各幾人、我插手了沒、這裡能按哪一顆。"""
    pair = find_stop(content, plan.stop)
    st = pair[1]
    name = _name(content, plan.who)
    acts = [{"id": oid, "label": label} for oid, label, ok in options(state, content) if ok and oid.endswith(f":{plan.stop}")]
    side = st.contest.side
    return {
        "id": plan.stop,
        "head": CARD_HEAD.format(name=name),
        "text": _fill(st.contest.announce, content, plan.who, plan.place),
        "place": _place(content, plan.place),
        "when": when,
        "minutes": minutes,
        "help": len(plan.helpers),
        "block": len(plan.blockers),
        "help_side": content.scenario.faction_name(side, side),
        "mine": joined(state, plan),
        "acts": acts,
    }
