"""時刻表（計畫 T2；時刻表結算文件）：第一季 12 件大事什麼時候發生、怎麼結算、公告怎麼寫。

- 什麼時候：一般大事看季曆（calendar.event_time）；決戰與季末看 WorldState.schedule（管理者可以改）。
- 怎麼結算：給了結果鍵照它（決戰由 T8 給、管理者也用）→ 有人鎖定關鍵伏筆照 lock_result → 固定的照 "fixed"
  → 其餘照戰況擲骰（roll_chance）。
- 公告：「【江湖大事】」開頭，同時記在時間軸（TimelineResult.text）、寫一則天下大事傳聞與一行江湖史。進每個人的江湖紀錄是
  Game._deliver_big_events 的事（每個角色同步時補自己還沒看過的），不是只進推進到那一刻的人（FB-038）。

state 是 GameState（季的事用的是 world._season_vehicle 那個空殼玩家），只讀寫 state.world；不碰儲存。"""
from __future__ import annotations

import random
import re
from typing import Literal

from . import calendar, figures
from .models import Content, TimetableEvent, TimetableOutcome
from .rules import add_chronicle, add_rumor, add_world_flags, change_trend, trend_value
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
# 人物欄位（FB-042，濃縮版內容表 8.1）：文字裡的 {人物:<人物 id>} 與人物效果的鍵 @人物:<人物 id>，照 person 找人
PERSON_SLOT = re.compile(r"\{人物:([^{}]+)\}")
PERSON_KEY = "@人物:"
PERSON_FALLBACK = {"guan": "官軍主將", "huang": "黃巾渠帥"}  # 這條戰線那一方沒有人時寫的泛稱
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


def due_showdowns(state: GameState, content: Content) -> list[TimetableEvent]:
    """時間到了、還沒收場（時間軸上沒有）的決戰，照時間排序。決戰不在季的事裡結算，T8 照這個開集結（world.season_events）。"""
    now = state.world.time + calendar.EPS_SECONDS
    return [e for e in _pending(state, content) if e.kind == "showdown" and when(state, content, e) <= now]


def next_event(state: GameState, content: Content) -> TimetableEvent | None:
    """狀態列倒數的那一件：還沒結算、時間還沒到的最早一件（決戰照排定的時間）。"""
    return next((e for e in _pending(state, content) if when(state, content, e) > state.world.time), None)


def next_event_on(state: GameState, content: Content, front: str) -> TimetableEvent | None:
    """那條戰線上最早一件還沒結算的大事，不分固定、擲骰、決戰（時間過了還沒收場的決戰也算）。
    軍令（T6）拿它判斷「這條戰線的下一件大事在兩週內」與一般伏筆修正要加在哪一件。"""
    return next((e for e in _pending(state, content) if e.front == front), None)


# ── 擲骰的機率 ───────────────────────────────────────────


def _front_value(state: GameState, content: Content, front: str) -> int:
    """戰線的戰況：rules.trend_value（有存值回存值，沒有回劇本的起始值）。劇本也沒有這條線（測試夾具）才當 50。"""
    if not any(t.id == front for t in content.scenario.trends):
        return 50
    return trend_value(state, content, front)


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
    return figures.name_of(content, fid)  # 人物表的名字（彭脫、韓忠沒有對話人物）


def person(state: GameState, content: Content, event: TimetableEvent, fid: str) -> str | None:
    """{人物:<fid>}／@人物:<fid> 指的是誰（FB-042，濃縮版內容表 8.1）：fid 此刻在場、而且在這件大事的戰線上，就是他；
    否則是這條戰線、他那一方當時的主將（figures.commander，就是接手的人）；也沒有就是 None（文字寫泛稱、效果略過）。
    fid 要在人物表上、大事要有戰線（載入時檢查過）。"""
    now = figures.state_of(state, content, fid)
    if event.front is not None and now.status == "active" and now.front == event.front:
        return fid
    return figures.commander(state, content, event.front, content.figures[fid].faction)


def _person_name(state: GameState, content: Content, event: TimetableEvent, fid: str) -> str:
    who = person(state, content, event, fid)
    return PERSON_FALLBACK[content.figures[fid].faction] if who is None else _figure_name(content, who)


def fill_slots(state: GameState, content: Content, event: TimetableEvent, text: str, *, people: bool = True) -> str:
    """{官軍主將}／{黃巾主將}：這件大事所在戰線當時那一方的主將（宛城是南陽的、廣宗是冀州的）；
    沒有主將時填「官軍」「黃巾」。{人物:<id>}（people 為真時）：照 person 找到的人，沒有人寫泛稱（PERSON_FALLBACK）。
    公告、鎖定公告、搶輸的一句、note、人物效果的 note、江湖史都經過這裡（T7、T8 也用）；preface 只填主將、不填人物欄位
    （「史書上」那半句照寫真名，濃縮版內容表 8.1）。"""
    for slot, side in COMMANDER_SLOTS.items():
        if slot in text:
            fid = figures.commander(state, content, event.front, side)
            text = text.replace(slot, SIDE_NAMES[side] if fid is None else _figure_name(content, fid))
    if people:
        text = PERSON_SLOT.sub(lambda m: _person_name(state, content, event, m.group(1)), text)
    return text


def _target(state: GameState, content: Content, event: TimetableEvent, key: str) -> str | None:
    """人物效果的鍵換成人物 id：「@commander:<戰線>:<方>」是那時的主將、「@人物:<id>」照 person 找人（沒有就 None，
    效果略過）；其他的鍵就是人物 id。"""
    if key.startswith(PERSON_KEY):
        return person(state, content, event, key.removeprefix(PERSON_KEY))
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
    """戰況移動。劇本沒有這條線（沒寫三條戰線的內容，例如測試夾具）就略過；真實內容的三條戰線與豪強割據都在，
    照 change_trend 推（時刻表只在第一季開關開著時結算，那時這些線才有值）；推動的文字不另外顯示，公告已經寫了。"""
    if any(t.id == trend_id for t in content.scenario.trends):
        change_trend(state, content, trend_id, delta)


def shown(lock: Lock) -> str:
    """公告與江湖史上寫的名字：鎖定時匿名的人是「某位少俠」（Lock.shown）；舊資料沒有 shown 就寫名號。"""
    return lock.shown or lock.name


def _headline(
    state: GameState, content: Content, event: TimetableEvent, outcome: TimetableOutcome, lock: Lock | None,
) -> str:
    """公告的主體：有人鎖定、這個結果也有他那一方的具名版本時用具名版本，否則用開頭＋公告。"""
    if lock is None or lock.side not in outcome.locked_text:
        preface = fill_slots(state, content, event, event.preface, people=False)  # 「史書上」那半句照寫真名
        return preface + fill_slots(state, content, event, outcome.text)
    return fill_slots(state, content, event, outcome.locked_text[lock.side]).replace("{name}", shown(lock))


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
    losing = [x for x in w.lock_losers.get(event.id, []) if lock is not None and x.side != lock.side]
    losers = [x.name for x in losing]  # 時間軸留真名（T9 的稱號）；公告寫顯示名（匿名的是「某位少俠」）
    # 文字先填好再套效果：{官軍主將}、{人物:…} 指的是這件事發生「之前」的人（例：廣宗黃巾大勝，重挫的就是他）；
    # 人物效果落在誰身上也在這時定好——文字寫誰，效果就落在誰身上（FB-042），不因前一筆效果換了主將而改落到別人身上
    # 公告的組法（伏筆文件 3.4、5.4）：具名的一段＋這一檔的結果（含 note 與人物的後話）＋搶輸的一筆＋豪強的一筆
    text = _headline(state, content, event, outcome, lock) + fill_slots(state, content, event, outcome.note)
    loser_line = _loser_line(state, content, event, outcome, lock, [shown(x) for x in losing])
    chronicle = _chronicle(state, content, event, outcome, lock if named else None)
    effects = [
        (_target(state, content, event, key), change, fill_slots(state, content, event, change.note))
        for key, change in outcome.figures.items()
    ]
    third = w.third_party.get(event.id, [])
    third_names = "、".join(w.third_party_shown.get(event.id, {}).get(name, name) for name in third)
    third_line = outcome.third_party_text or event.third_party_text
    third_text = fill_slots(state, content, event, third_line).replace("{name}", third_names) if third and third_line else ""
    third_chronicle = (  # 豪強另記一行（例：「{name} 取得新野」），不論誰贏；同樣先填好（FB-042 審查 I2）
        fill_slots(state, content, event, event.third_party_chronicle).replace("{name}", third_names)
        if third and event.third_party_chronicle else ""
    )
    for trend_id, delta in outcome.trends.items():
        _push(state, content, trend_id, delta)
    for fid, change, note in effects:
        if fid is None or not figures.holds(state, content, change):
            continue
        text += "".join(figures.apply(state, content, fid, change)) + note
    for target, mod in outcome.chance_mods.items():
        w.event_bonus[target] = w.event_bonus.get(target, 0.0) + mod
    add_world_flags(state, outcome.world_flags_add)
    text += loser_line
    for _ in third:  # 豪強是第三方：不論誰贏，每個做完的名字各套一次自己的效果（伏筆文件 2.6）
        for trend_id, delta in event.third_party_trends.items():
            _push(state, content, trend_id, delta)
    text += third_text
    w.timeline[event.id] = TimelineResult(
        key=full_key, time=w.time, locked_by=lock.name if named else None, losers=losers if named else [], text=text,
    )
    add_rumor(state, text, content=content, layer="world")
    if chronicle:
        add_chronicle(state, chronicle)
    if third_chronicle:
        add_chronicle(state, third_chronicle)
    return [f"【江湖大事】{text}"]


def _chronicle(
    state: GameState, content: Content, event: TimetableEvent, outcome: TimetableOutcome, named: Lock | None,
) -> str:
    """江湖史那一行（計畫 T7、伏筆文件 2.4）：公告具名（named 是鎖定者）時，用這件大事寫給鎖定方的那一行；
    那一方沒寫就在原本那一行後面接「（名號改寫）」。沒人鎖定、或結果不是鎖定方的（公告沒有具名）照原本那一行。"""
    plain = fill_slots(state, content, event, outcome.chronicle)
    if named is None:
        return plain
    if named.side in event.locked_chronicle:
        return fill_slots(state, content, event, event.locked_chronicle[named.side]).replace("{name}", shown(named))
    return f"{plain}（{shown(named)}改寫）" if plain else plain


# ── 管理者（計畫 T10）─────────────────────────────────────


FINALE_KEY = "finale"  # WorldState.schedule 裡季末的鍵（三場決戰用大事 id）


def schedulable(content: Content) -> list[TimetableEvent]:
    """管理者能排時間的大事：三場決戰與季末，照時刻表的順序。"""
    return [e for e in content.timetable if e.kind in NOT_BY_SEASON_HOUR]


def clear_of_events(state: GameState, content: Content, mark: float) -> tuple[float, str | None]:
    """決戰的時間（曆時交界上）剛好碰上一件還沒結算的一般大事，就往後挪一個曆時，直到沒碰上（T10 審查 I1：同一刻那件大事
    先結算，排在它前面、還沒開成的決戰會照起點判掉，見 world.settle_waiting_showdowns）。回傳（挪好的時間, 第一次碰上的那件的標題）。
    管理者排時間（Game._showdown_mark）與賽季時鐘繼續後把決戰往前挪（world.keep_showdowns_on_time）共用。"""
    cal_hour = calendar.cal_hour_seconds(content, state.world)
    regular = [e for e in _pending(state, content) if e.kind not in NOT_BY_SEASON_HOUR]
    avoided = None
    while hit := next((e for e in regular if abs(mark - when(state, content, e)) < calendar.EPS_SECONDS), None):
        avoided, mark = avoided or hit.title, mark + cal_hour
    return mark, avoided


def schedule_key(event: TimetableEvent) -> str:
    return FINALE_KEY if event.kind == "finale" else event.id


def result_keys(state: GameState, content: Content, event: TimetableEvent) -> list[str]:
    """管理者此刻能替這件大事定的結果鍵（不含版本）：有版本的（宛城、秦頡）要等 version_from 那件結算了才知道是哪一版，
    之前是空的；季末沒有（收季另外按）。"""
    if event.kind == "finale":
        return []
    if event.version_from is None:
        return list(event.outcomes)
    if event.version_from not in state.world.timeline:
        return []
    prefix = f"{_version(state, event)}:"
    return [key[len(prefix):] for key in event.outcomes if key.startswith(prefix)]


def status_rows(state: GameState, content: Content) -> list[dict]:
    """設定頁「時刻表」的每一列：id、週次、標題、種類、世界秒、狀態（done 已結算／running 決戰開過集結還沒收場／
    due 時間到了還沒結算／later 還沒到）、結果鍵（含版本）、能不能排時間（決戰與季末，還沒結算也還沒開過）。"""
    w = state.world
    rows = []
    for event in content.timetable:
        at = when(state, content, event)
        done = w.timeline.get(event.id)
        opened = event.id in w.showdowns_opened
        status = "done" if done else "running" if opened else "due" if at <= w.time + calendar.EPS_SECONDS else "later"
        rows.append({
            "id": event.id, "week": event.week, "title": event.title, "kind": event.kind, "when": at, "state": status,
            "result": done.key if done else None,
            "schedulable": event.kind in NOT_BY_SEASON_HOUR and done is None and not opened,
        })
    return rows
