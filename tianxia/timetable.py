"""時刻表（計畫 T2；時刻表結算文件）：第一季 12 件大事什麼時候發生、怎麼結算、公告怎麼寫。

- 什麼時候：一般大事看季曆（calendar.event_time）；決戰與季末看 WorldState.schedule（管理者可以改）。
- 怎麼結算：給了結果鍵照它（決戰由 T8 給、管理者也用）→ 有人鎖定關鍵伏筆照 lock_result → 固定的照 "fixed"
  → 其餘照戰況擲骰（roll_chance）。
- 公告：「【江湖大事】」開頭，同時記在時間軸（TimelineResult.text）、寫一則天下大事傳聞與一行江湖史。進每個人的江湖紀錄是
  Game._deliver_big_events 的事（每個角色同步時補自己還沒看過的），不是只進推進到那一刻的人（FB-038）。

state 是 GameState（季的事用的是 world._season_vehicle 那個空殼玩家），只讀寫 state.world；不碰儲存。"""
from __future__ import annotations

import random
from typing import Literal

from . import calendar, figures
from .models import Content, TimetableEvent, TimetableOutcome
from .rules import add_chronicle, add_rumor, add_world_flags, change_trend
from .state import GameState, Lock, TimelineResult, WorldState
from .world_state import season_length_days

HOUR = 3600
DAY = 86400
SKIPPED = "skip"  # skip_if_out 的人物已經退場：記成這個結果鍵，不公告、不套效果
NOT_BY_SEASON_HOUR = ("showdown", "finale")  # 決戰到時間開集結（T8）、季末收季（T9），不在季的事裡結算
CHANCE_FLOOR, CHANCE_CEIL = 0.1, 0.9  # 照戰況算出的成功率先夾在這裡（結算文件第二節）
EVENT_MODS_CAP = 0.20  # 一般伏筆、軍令的修正合計上限（event_bonus 不受這個限制）
SIDE_NAMES = {"guan": "官軍", "huang": "黃巾"}
COMMANDER_SLOTS = {"{官軍主將}": "guan", "{黃巾主將}": "huang"}
COMMANDER_KEY = "@commander:"  # 人物效果的鍵「@commander:<戰線>:<guan|huang>」＝當時那條戰線那一方的主將
SHOWDOWN_HOUR = 20  # 決戰預設在那一週週四 20:00（季曆，計畫第六節）
SHOWDOWN_WEEKDAY = 3


# ── 什麼時候 ─────────────────────────────────────────────


def _showdown_default(event: TimetableEvent, content: Content, season: WorldState | None) -> float:
    offset = (SHOWDOWN_WEEKDAY * DAY + SHOWDOWN_HOUR * HOUR) / calendar.cal_scale(content, season)
    return calendar.week_start(event.week, content, season) + offset


def default_schedule(content: Content, season: WorldState | None = None) -> dict[str, float]:
    """開季時填進 WorldState.schedule 的預設值：決戰在那一週的週四 20:00（季曆），季末在季長整。
    季長照 season 蓋的章（world_state.stamp_season 先蓋章再呼叫這裡）；不給 season 時照設定。"""
    days = season_length_days(season, content) if season is not None else content.config.season_days
    schedule = {e.id: _showdown_default(e, content, season) for e in content.timetable if e.kind == "showdown"}
    schedule["finale"] = days * DAY
    return schedule


def when(state: GameState, content: Content, event: TimetableEvent) -> float:
    """這件大事的世界秒。決戰與季末看排定的時間（舊季沒排就用預設），其他看季曆。伏筆的時間窗（T7）也用它。"""
    schedule = state.world.schedule
    if event.kind == "showdown":
        return schedule.get(event.id, _showdown_default(event, content, state.world))
    if event.kind == "finale":
        return schedule.get("finale", season_length_days(state.world, content) * DAY)
    return calendar.event_time(event, content, state.world)


def _pending(state: GameState, content: Content) -> list[TimetableEvent]:
    """還沒結算的大事，照時間排（同一刻照 timetable.json 的順序）。"""
    events = [e for e in content.timetable if e.id not in state.world.timeline]
    return sorted(events, key=lambda e: when(state, content, e))


def due(state: GameState, content: Content) -> list[TimetableEvent]:
    """時間到了、還沒結算、不是決戰或季末的大事，照時間排序。"""
    now = state.world.time + calendar.EPS_SECONDS
    return [e for e in _pending(state, content) if e.kind not in NOT_BY_SEASON_HOUR and when(state, content, e) <= now]


def next_event(state: GameState, content: Content) -> TimetableEvent | None:
    """狀態列倒數的那一件：還沒結算、時間還沒到的最早一件（決戰照排定的時間）。"""
    return next((e for e in _pending(state, content) if when(state, content, e) > state.world.time), None)


def next_event_on(state: GameState, content: Content, front: str) -> TimetableEvent | None:
    """那條戰線上最早一件還沒結算的大事，不分固定、擲骰、決戰（時間過了還沒收場的決戰也算）。
    軍令（T6）拿它判斷「這條戰線的下一件大事在兩週內」與一般伏筆修正要加在哪一件。"""
    return next((e for e in _pending(state, content) if e.front == front), None)


# ── 擲骰的機率 ───────────────────────────────────────────


def _front_value(state: GameState, content: Content, front: str) -> int:
    """戰線的戰況。T1 的 rules.trend_value 進來後換掉（規則相同：有存值回存值，沒有回劇本的起始值）；
    劇本也沒有這條線（T1 之前的真實內容）才當 50。"""
    if front in state.world.trends:
        return state.world.trends[front]
    trend = next((t for t in content.scenario.trends if t.id == front), None)
    return trend.start if trend is not None else 50


def apply_mods(p: float, m: float) -> float:
    """修正量照「那一邊還剩多少空間」等比例縮放，在 50% 時正好是原本的量（企劃者 2026-10-04，計畫 7.1）：
    正的 p + m × (1 − p) ÷ 0.5，負的 p + m × p ÷ 0.5；最後仍夾在 [0, 1]，以防將來的修正量更大。"""
    scaled = p + m * (1 - p) / 0.5 if m >= 0 else p + m * p / 0.5
    return min(1.0, max(0.0, scaled))


def roll_chance(state: GameState, content: Content, event: TimetableEvent) -> float:
    """「成」的機率（結算文件第二節）：戰線值 v，成對黃巾有利是 v／100、對官軍有利是 (100 − v)／100；
    沒有戰線用 base_chance。夾在 0.1～0.9，再加一般伏筆修正（夾在 ±0.20）與時刻表結果的修正，等比例調整。"""
    if event.front is not None:
        v = _front_value(state, content, event.front) / 100
        p = v if event.roll_side == "huang" else 1 - v
    else:
        p = event.base_chance if event.base_chance is not None else 0.5
    p = min(CHANCE_CEIL, max(CHANCE_FLOOR, p))
    w = state.world
    mods = max(-EVENT_MODS_CAP, min(EVENT_MODS_CAP, w.event_mods.get(event.id, 0.0)))
    return apply_mods(p, mods + w.event_bonus.get(event.id, 0.0))


def add_mod(state: GameState, content: Content, event_id: str, side: Literal["guan", "huang"], amount: float) -> None:
    """一般伏筆、軍令的修正（例：「往官軍 +0.05」）。event_mods 加在 roll_side 那一方的成功率上，所以站在另一邊
    就變號；累計夾在 ±0.20。不靠擲骰結算的大事（固定、決戰、季末）沒有 roll_side，修正沒有意義，什麼都不做。"""
    event = _event(content, event_id)
    if event.roll_side is None:
        return
    signed = amount if side == event.roll_side else -amount
    total = state.world.event_mods.get(event_id, 0.0) + signed
    state.world.event_mods[event_id] = max(-EVENT_MODS_CAP, min(EVENT_MODS_CAP, total))


def _event(content: Content, event_id: str) -> TimetableEvent:
    found = next((e for e in content.timetable if e.id == event_id), None)
    if found is None:
        raise KeyError(f"時刻表沒有這件大事：{event_id}")
    return found


# ── 公告的插槽 ───────────────────────────────────────────


def _figure_name(content: Content, fid: str) -> str:
    character = content.characters.get(fid)
    return character.name if character is not None else fid


def fill_slots(state: GameState, content: Content, event: TimetableEvent, text: str) -> str:
    """{官軍主將}／{黃巾主將}：這件大事所在戰線當時那一方的主將（宛城是南陽的、廣宗是冀州的）；
    沒有主將時填「官軍」「黃巾」。公告、鎖定公告、搶輸的一句、江湖史都經過這裡（T7、T8 也用）。"""
    for slot, side in COMMANDER_SLOTS.items():
        if slot in text:
            fid = figures.commander(state, content, event.front, side)
            text = text.replace(slot, SIDE_NAMES[side] if fid is None else _figure_name(content, fid))
    return text


def _commander_target(state: GameState, content: Content, key: str) -> str | None:
    """人物效果的鍵換成人物 id：「@commander:<戰線>:<方>」是那時的主將（沒有就 None，效果略過）。"""
    if not key.startswith(COMMANDER_KEY):
        return key
    front, _, side = key.removeprefix(COMMANDER_KEY).partition(":")
    return figures.commander(state, content, front, side)


# ── 結算 ─────────────────────────────────────────────────


def _version(state: GameState, event: TimetableEvent) -> str | None:
    """有版本的大事（宛城、秦頡）看 version_from 那件的結果；那件還沒有結果時當史書那一版（versions 的第一個）。"""
    if event.version_from is None or not event.versions:
        return None
    source = state.world.timeline.get(event.version_from)
    if source is not None and source.key in event.versions:
        return event.versions[source.key]
    return next(iter(event.versions.values()))


def _full_key(state: GameState, event: TimetableEvent, key: str) -> str:
    version = _version(state, event)
    if version is None or any(key.startswith(f"{v}:") for v in event.versions.values()):  # 已經帶版本的照用
        return key
    return f"{version}:{key}"


def _pick_key(state: GameState, content: Content, event: TimetableEvent, lock: Lock | None, rng: random.Random) -> str:
    if lock is not None and lock.side in event.lock_result:
        return event.lock_result[lock.side]
    if event.kind == "fixed":
        return "fixed"
    return "成" if rng.random() < roll_chance(state, content, event) else "不成"


def _push(state: GameState, content: Content, trend_id: str, delta: int) -> None:
    """戰況移動。劇本還沒有這條線（T1 之前的真實內容）就略過；推動的文字不另外顯示，公告已經寫了。"""
    if any(t.id == trend_id for t in content.scenario.trends):
        change_trend(state, content, trend_id, delta)


def _headline(
    state: GameState, content: Content, event: TimetableEvent, outcome: TimetableOutcome, lock: Lock | None,
) -> str:
    """公告的主體：有人鎖定、這個結果也有他那一方的具名版本時用具名版本，否則用開頭＋公告。"""
    if lock is None or lock.side not in outcome.locked_text:
        return fill_slots(state, content, event, event.preface + outcome.text)
    return fill_slots(state, content, event, outcome.locked_text[lock.side]).replace("{name}", lock.name)


def _loser_line(
    state: GameState, content: Content, event: TimetableEvent, outcome: TimetableOutcome, lock: Lock | None,
    losers: list[str],
) -> str:
    """搶輸的一筆：有具名版本、有另一方搶輸的人，而且這一格寫了才有。"""
    if lock is None or lock.side not in outcome.locked_text or not losers or lock.side not in outcome.loser_text:
        return ""
    return fill_slots(state, content, event, outcome.loser_text[lock.side]).replace("{loser}", "、".join(losers))


def resolve(
    state: GameState, content: Content, event: TimetableEvent, rng: random.Random, *, key: str | None = None,
) -> list[str]:
    """結算一件大事，回傳「【江湖大事】」開頭的公告；已經結算過（或記成跳過）就回空串列、什麼都不做。
    key 是不含版本的結果鍵（決戰的 "guan:大勝"、管理者定的結果）；有版本的大事自動加上版本。"""
    w = state.world
    if event.id in w.timeline:
        return []
    if event.skip_if_out and figures.is_out(state, event.skip_if_out):
        w.timeline[event.id] = TimelineResult(key=SKIPPED, time=w.time)
        return []
    lock = w.locks.get(event.id)
    full_key = _full_key(state, event, key if key is not None else _pick_key(state, content, event, lock, rng))
    outcome = event.outcomes.get(full_key)
    if outcome is None:
        raise ValueError(f"大事 {event.id} 沒有結果 {full_key}")
    named = lock is not None and lock.side in outcome.locked_text
    losers = [x.name for x in w.lock_losers.get(event.id, []) if lock is not None and x.side != lock.side]
    # 文字先填好再套效果：{官軍主將} 指的是這件事發生「之前」的主將（例：廣宗黃巾大勝，重挫的就是他）
    # 公告的組法（伏筆文件 3.4、5.4）：具名的一段＋這一檔的結果（含 note 與人物的後話）＋搶輸的一筆＋豪強的一筆
    text = _headline(state, content, event, outcome, lock) + fill_slots(state, content, event, outcome.note)
    loser_line = _loser_line(state, content, event, outcome, lock, losers)
    chronicle = fill_slots(state, content, event, outcome.chronicle)
    for trend_id, delta in outcome.trends.items():
        _push(state, content, trend_id, delta)
    for target_key, change in outcome.figures.items():
        fid = _commander_target(state, content, target_key)
        if fid is None or not figures.holds(state, change):
            continue
        text += "".join(figures.apply(state, content, fid, change)) + fill_slots(state, content, event, change.note)
    for target, mod in outcome.chance_mods.items():
        w.event_bonus[target] = w.event_bonus.get(target, 0.0) + mod
    add_world_flags(state, outcome.world_flags_add)
    text += loser_line
    third = w.third_party.get(event.id, [])
    if third:  # 豪強是第三方：不論誰贏，每個做完的名字各套一次自己的效果（伏筆文件 2.6）
        for _ in third:
            for trend_id, delta in event.third_party_trends.items():
                _push(state, content, trend_id, delta)
        line = outcome.third_party_text or event.third_party_text
        if line:
            text += fill_slots(state, content, event, line).replace("{name}", "、".join(third))
    w.timeline[event.id] = TimelineResult(
        key=full_key, time=w.time, locked_by=lock.name if named else None, losers=losers if named else [], text=text,
    )
    add_rumor(state, text, content=content, layer="world")
    if chronicle:
        add_chronicle(state, chronicle)
    return [f"【江湖大事】{text}"]
