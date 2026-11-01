"""時刻表（計畫 T2；時刻表結算文件）：第一季 12 件大事什麼時候發生、怎麼結算、公告怎麼寫。

- 什麼時候：一般大事看季曆（calendar.event_time）；決戰與季末看 WorldState.schedule（管理者可以改）。
- 怎麼結算：給了結果鍵照它（決戰由 T8 給、管理者也用）→ 有人鎖定關鍵伏筆照 lock_result → 固定的照 "fixed"
  → 其餘照戰況擲骰（roll_chance）。
- 公告：「【江湖大事】」開頭，同時記在時間軸（TimelineResult.text）、寫一則天下大事傳聞與一行江湖史。進每個人的江湖紀錄是
  Game._deliver_big_events 的事（每個角色同步時補自己還沒看過的），不是只進推進到那一刻的人（FB-038）。

state 是 GameState（季的事用的是 world._season_vehicle 那個空殼玩家），只讀寫 state.world；不碰儲存。"""
from __future__ import annotations

import math
import random
import re
from collections.abc import Collection
from typing import Literal

from . import calendar, figures, territory
from .models import Content, TimetableEvent, TimetableOutcome
from .rules import add_chronicle, add_rumor, add_world_flags, change_trend, trend_value
from .state import GameState, Lock, TimelineResult, WorldState

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
    weekday = SHOWDOWN_WEEKDAY if event.weekday is None else event.weekday  # 天命之爭寫週一（玉璽二）；其他照週四
    hour = SHOWDOWN_HOUR if event.hour is None else event.hour
    offset = (weekday * DAY + hour * HOUR) / calendar.cal_scale(content, season)
    return calendar.week_start(event.week, content, season) + offset


def default_time(event: TimetableEvent, content: Content, season: WorldState | None) -> float:
    """這件決戰的預設時刻（世界秒，照這一季的章）：蓋天命之季的章時排天命之爭用（玉璽二；seal.stamp_mandate 的呼叫端算好傳進去）。"""
    return _showdown_default(event, content, season)


def events(season: WorldState | None, content: Content) -> list[TimetableEvent]:
    """這一季的時刻表：內容的那一份；蓋了天命之季的章（WorldState.mandate）時再把標 mandate_only 的那一件插進去（玉璽碎片設計 8.3；
    要 PM 定的第 1 條：選擇加入）：插在第一件週次比它晚、或同一週的季末之前（管理者排時間照這個順序檢查前後）。內容那 12 件的
    順序一件都不動（不重新排序）。沒蓋章時回 content.timetable 本身。"""
    extra = content.mandate_timetable if season is not None and season.mandate else []
    if not extra:
        return content.timetable
    out = list(content.timetable)
    for event in extra:
        at = next((i for i, e in enumerate(out) if e.week > event.week or (e.week == event.week and e.kind == "finale")), len(out))
        out.insert(at, event)
    return out


def find(content: Content, event_id: str) -> TimetableEvent | None:
    """照 id 找一件大事，天命之爭也找得到、不看這一季的章：只給「已經開出來、正在收場或補結算」的路徑用（_settle_showdown、
    settle_waiting_showdowns、_event〔軍令的 add_mod〕、server 的鎖定列）。會「開」或「定」一件大事的入口（_claim_showdown、
    Game._timetable_event）一律走 events，一般季碰不到天命之爭。"""
    return next((e for e in (*content.timetable, *content.mandate_timetable) if e.id == event_id), None)


def default_schedule(content: Content, season: WorldState | None = None) -> dict[str, float]:
    """開季時填進 WorldState.schedule 的預設值：決戰在那一週的週四 20:00（季曆），季末在季長整。
    季長照 season 蓋的章（world_state.stamp_season 先蓋章再呼叫這裡）；不給 season 時照設定。
    這時還不知道季在現實的哪一刻開，避開半夜由開季、換季的人照開的那一刻再挪（avoid_quiet_hours）。"""
    schedule = {e.id: _showdown_default(e, content, season) for e in content.timetable if e.kind == "showdown"}
    schedule["finale"] = finale_default(content, season)
    return schedule


def finale_default(content: Content, season: WorldState | None) -> float:
    """季末的預設時刻（世界秒）：21 天季是季曆最後一週週日 24:00（照錨點算，週三開季也落在第 3 週週日，正式季整合設計 1.2 給開發 3），
    其他照季長整（以前的寫法，一個字都不變）。就是 calendar.nominal_end（懸賞的「到季末」也比它，FB-500）。"""
    if season is None:
        return content.config.season_days * DAY
    return calendar.nominal_end(content, season)


DEFAULT_DATES = "預設在{battles}、季末第 {end} 天過完"  # 待 joy 潤：管理者開季、開下一季的問句括號裡（FB-501，7 天濃縮季）
DEFAULT_DATES_WEEKLY = "預設在{battles}、季末第 {end} 週週日過完"  # 待 joy 潤：同上，21 天季（季曆是現實的週，PM 2026-10-20）


def default_dates_note(content: Content) -> str | None:
    """管理者開季、開下一季的問句「記得排三場大戲與季末的時間（…）」括號裡那一句，照這份設定的時刻表寫（FB-501）：
    7 天濃縮季（Config.season_segments，開季之前還沒有章，照設定）「預設在第 2、4、7 天 20:00、季末第 7 天過完」；
    21 天季（PM 2026-10-20：網頁原本那一句寫週末的第 6、9、11 週，21 天季只有 3 週）「預設在第 1、2、3 週週六 20:00、季末第 3 週週日過完」，
    照 content.timetable（season21_timetable 換過的 week／weekday／hour）寫；週末與 14 天是 None，網頁照原本那一句。"""
    if not content.config.season_segments:
        return _weekly_dates_note(content) if content.config.season21 else None
    shows = [e.real7 for e in content.timetable if e.kind == "showdown" and e.real7 is not None]
    end = next((e.real7.day for e in content.timetable if e.kind == "finale" and e.real7 is not None), calendar.total_days(content))
    hours = {r.hour for r in shows}
    if len(hours) == 1:
        battles = f"第 {'、'.join(str(r.day) for r in shows)} 天 {next(iter(hours)):02d}:00"
    else:
        battles = "、".join(f"第 {r.day} 天 {r.hour:02d}:00" for r in shows)
    return DEFAULT_DATES.format(battles=battles, end=end)


def _weekly_dates_note(content: Content) -> str | None:
    """21 天季那一句：三場決戰各自的「第 N 週週X HH:00」（時刻都一樣就合起來寫「第 1、2、3 週週六 20:00」）、季末那一週。"""
    shows = [(e.week, SHOWDOWN_WEEKDAY if e.weekday is None else e.weekday, SHOWDOWN_HOUR if e.hour is None else e.hour)
             for e in content.timetable if e.kind == "showdown"]
    end = next((e.week for e in content.timetable if e.kind == "finale"), None)
    if not shows or end is None:
        return None
    if len({(day, hour) for _, day, hour in shows}) == 1:
        _, day, hour = shows[0]
        battles = f"第 {'、'.join(str(week) for week, _, _ in shows)} 週週{calendar.WEEKDAYS[day]} {hour:02d}:00"
    else:
        battles = "、".join(f"第 {week} 週週{calendar.WEEKDAYS[day]} {hour:02d}:00" for week, day, hour in shows)
    return DEFAULT_DATES_WEEKLY.format(battles=battles, end=end)


MANDATE_AT = "第 {day} 天 {hour:02d}:00"  # 待 joy 潤（FB-503）
MANDATE_AT_WEEKLY = "第 {week} 週週{weekday} {hour:02d}:{minute:02d}"  # 待 joy 潤：21 天季，寫法同網頁原本那一句「第 12 週週一 20:00」


def mandate_note(content: Content, season: WorldState | None) -> str | None:
    """管理者「這一季立刻蓋天命之季的章」問句裡天命之爭排在哪一刻（FB-503）：7 天濃縮季（week7_on）照時刻表的 real7 寫
    「第 7 天 22:00」；21 天季（PM 2026-10-20，以前也是 None、網頁退回週末的「第 12 週週一 20:00」）照蓋章真正會排的預設時刻
    （default_time，天命之爭的 week／weekday／hour 已經是 season21_timetable 換過的）換成季曆寫「第 3 週週日 20:00」；
    週末與 14 天是 None，網頁照原本那一句（週末的第 12 週週一 20:00 是對的）。"""
    if not calendar.season21_on(season, content):
        return None
    if calendar.week7_on(season, content):
        when = next((e.real7 for e in content.mandate_timetable if e.real7 is not None), None)
        return None if when is None else MANDATE_AT.format(day=when.day, hour=when.hour)
    event = next(iter(content.mandate_timetable), None)
    if event is None:
        return None
    at = calendar.point(default_time(event, content, season), content, season)
    return MANDATE_AT_WEEKLY.format(week=at.week, weekday=calendar.WEEKDAYS[at.weekday], hour=at.hour, minute=at.minute)


# ── 決戰避開半夜（企劃者 2026-10-15，經 PM；Config.battle_quiet_hours）─────────────

# 管理者那一行（開季、開下一季）：兩邊都挪不開、照原時間的那一場。待 joy 潤
QUIET_KEPT = "（{title}排在現實 {clock}，前後的大事擋著挪不開，照原時間；要改用「排時間」。）"
# 天命之爭得排在最後一場時刻表決戰之後（FB-564）卻排不好：後面只剩半夜、或放不下集結加打一幕就到季末。待 joy 潤
ORDER_KEPT = "（{title}要排在{last}之後，排在現實 {clock}，前後的大事擋著挪不開；要改用「排時間」。）"


def showdown_span(content: Content, event: TimetableEvent) -> float:
    """這件決戰要有人在的那一段（現實秒）：schedule 排的是集結開始（時間到了開集結，world.open_waiting_showdown），
    集結 muster_seconds，再打一幕（rounds_per_act 回合，每回合最多等 round_seconds）——玩家趕來集結、打前幾回合的那一段。
    分版本的（宛城甲乙）取最長的；內容沒有那一場是 0（開不成，不必挪）。"""
    return max(
        (b.muster_seconds + b.rounds_per_act * b.round_seconds for b in content.battles.values() if b.timetable_event == event.id),
        default=0.0,
    )


def _local(season: WorldState, content: Content, now: float, at: float) -> float:
    """世界秒 at 換成當地時間（照 pill_day_utc_offset_hours 換過時區的 epoch 秒）；now 是 season.time 那一刻的現實秒。"""
    return now + (at - season.time) / content.config.time_scale + content.config.pill_day_utc_offset_hours * HOUR


def _quiet_hit(local: float, span: float, content: Content) -> tuple[float, float] | None:
    """從 local 起 span 秒碰到哪一段不開的時間：回那一段的（開始, 結束）當地秒；沒碰到是 None。"""
    quiet = content.config.battle_quiet_hours
    day = local // DAY
    for d in (day - 1, day, day + 1):
        start, end = d * DAY + quiet.start * HOUR, d * DAY + quiet.end * HOUR
        if local < end and local + span > start:
            return start, end
    return None


def _mandate_floor(season: WorldState, content: Content, event: TimetableEvent) -> float | None:
    """天命之爭最早能排在哪一刻（世界秒；FB-564，PM 2026-10-20）：那一季最後一場時刻表決戰（廣宗）的集結加打一幕之後。
    不是天命之爭、時刻表上沒有決戰回 None。"""
    if not event.mandate_only:
        return None
    last = next((e for e in reversed(content.timetable) if e.kind == "showdown"), None)
    if last is None:
        return None
    return when_in(season, content, last) + showdown_span(content, last) * content.config.time_scale


def _last_showdown(content: Content) -> TimetableEvent:
    """時刻表上（不含天命之爭）最後一場決戰。"""
    return next(e for e in reversed(content.timetable) if e.kind == "showdown")


def _placed_at(season: WorldState, content: Content, event: TimetableEvent) -> float:
    """挪的時候排前後順序用的時刻：天命之爭排得比最後一場時刻表決戰早的（管理者先把廣宗排晚了，再蓋章），照它該在的地方算
    （廣宗收尾之後），其餘就是 when_in。"""
    at = when_in(season, content, event)
    floor = _mandate_floor(season, content, event)
    return at if floor is None else max(at, floor)


def _neighbours(season: WorldState, content: Content, event: TimetableEvent) -> tuple[float, float]:
    """這件決戰能挪的範圍（世界秒，兩頭都不含）：時刻表上排在它前面的最後一件之後、後面的第一件之前（照時刻排，同一刻照時刻表的
    順序；季末也算）。前一件是決戰時再讓開它的集結加一幕、後一件是決戰時這一場的集結加一幕要在它之前打完：一次只打一場，
    擠在一起的會排隊、拖過 00:00 才開。"""
    ordered = sorted(enumerate(events(season, content)), key=lambda pair: (_placed_at(season, content, pair[1]), pair[0]))
    at = [i for i, (_, e) in enumerate(ordered) if e.id == event.id][0]
    scale = content.config.time_scale
    before, after = float("-inf"), float("inf")
    if at > 0:
        prev = ordered[at - 1][1]
        before = when_in(season, content, prev) + (showdown_span(content, prev) * scale if prev.kind == "showdown" else 0)
    if at + 1 < len(ordered):
        nxt = ordered[at + 1][1]
        after = when_in(season, content, nxt) - (showdown_span(content, event) * scale if nxt.kind == "showdown" else 0)
    return before, after


def quiet_place(season: WorldState, content: Content, event: TimetableEvent, now: float) -> float | None:
    """這件決戰此刻排的時刻（世界秒），集結加打一幕碰到半夜不開的那一段時，挪去哪裡：往前挪到那一段開始之前剛好打完一幕的那一刻
    （取整到曆時交界，只會更早），或往後挪到那一段結束（取整到曆時交界，只會更晚），哪個近挪哪個；挪過去不能早於此刻、
    不能跟時刻表前後的大事打亂先後（季末也算，所以不會挪過季末），近的那邊不行就換另一邊。不必挪回原來的時刻；
    兩邊都不行回 None。now 是 season.time 那一刻的現實秒。"""
    at = when_in(season, content, event)
    span = showdown_span(content, event)
    local = _local(season, content, now, at)
    floor = _mandate_floor(season, content, event)
    early = floor is not None and span > 0 and season.time < at < floor  # 天命之爭排在最後一場時刻表決戰收尾之前：得往後挪（FB-564）
    hit = _quiet_hit(local, span, content) if span > 0 and at > season.time else None  # 已經到期的（管理者這一季才蓋章）馬上開，不挪
    if hit is None and not early:
        return at
    scale = content.config.time_scale
    before, after = _neighbours(season, content, event)
    if floor is not None:
        before = max(before, floor)  # 天命之爭一定排在最後一場時刻表決戰之後，往前挪也不能越過它
        after = min([after, *(when_in(season, content, e) for e in events(season, content) if e.kind == "finale")])  # 照樣不能越過季末
    if early:
        return _place_behind(season, content, now, before, after, span)
    # 取整到季曆的整點（FB-331：21 天季開季不在整點時，世界秒的整點對不到季曆；偏移是 0 的季照舊）
    back = calendar.hour_floor(at - (local - (hit[0] - span)) * scale, content, season)
    forward = _hour_up(at + (hit[1] - local) * scale, content, season)
    for t in sorted((back, forward), key=lambda t: abs(t - at)):
        if max(before, season.time) < t < after and _quiet_hit(_local(season, content, now, t), span, content) is None:
            return t
    return None


def _place_behind(season: WorldState, content: Content, now: float, before: float, after: float, span: float) -> float | None:
    """before 之後（不含）、after 之前（不含）的第一個集結加打一幕碰不到半夜的季曆整點；半夜躲不開時，先後順序比避開半夜重要
    （FB-564：天命之爭一定排在最後一場時刻表決戰之後），排在 before 之後最近的整點（碰到半夜，管理者那一行說）；連這個都放不下回 None。"""
    scale, hour = content.config.time_scale, calendar.cal_hour_seconds(content, season)
    low = max(before, season.time)
    first = _hour_up(low, content, season)
    if first <= low:
        first += hour
    t = first
    while t < after:
        local = _local(season, content, now, t)
        hit = _quiet_hit(local, span, content)
        if hit is None:
            return t
        t = max(_hour_up(t + (hit[1] - local) * scale, content, season), t + hour)
    return first if first < after else None


def _hour_up(time: float, content: Content, season: WorldState) -> float:
    """quiet_place 往後挪的那一邊：time 當下或之後的季曆整點，浮點誤差照以前的 1e-9 曆時（不是 calendar.hour_ceil 的 EPS_SECONDS），
    偏移是 0 時跟以前一模一樣。"""
    hour, shift = calendar.cal_hour_seconds(content, season), calendar.hour_shift(content, season)
    return math.ceil((time + shift) / hour - 1e-9) * hour - shift


def _quiet_pending(season: WorldState, content: Content) -> list[TimetableEvent]:
    """還沒開過、還沒結算的時刻表決戰（天命之季含天命之爭）。"""
    return [
        e for e in events(season, content)
        if e.kind == "showdown" and e.id not in season.timeline and e.id not in season.showdowns_opened
    ]


def avoid_quiet_hours(season: WorldState, content: Content, now: float) -> list[TimetableEvent]:
    """照季曆排好的決戰挪開半夜（quiet_place），照時刻表的先後一件一件挪、寫回 season.schedule；回兩邊都挪不開、照原時間的那幾件。
    開季（SqliteWorldStore.open_season）、換季（next_season，含換季時蓋的天命之季章）與管理者「這一季立刻蓋章」呼叫；
    管理者「排時間」不走這裡。開關關著、這一季沒有時刻表，什麼都不做。只改傳進來的 season。"""
    if not content.config.battle_quiet_hours.enabled or not calendar.season_one_on(season, content):
        return []
    stuck = []
    for event in _quiet_pending(season, content):
        placed = quiet_place(season, content, event, now)
        if placed is None:
            stuck.append(event)
        else:
            season.schedule[event.id] = placed
    return stuck


def quiet_notes(season: WorldState, content: Content, now: float) -> list[str]:
    """管理者那一行：還沒開的決戰裡，集結加打一幕仍碰到半夜的（挪不開、照原時間）各一句，寫現實的幾點幾分（當地時間）。"""
    if not content.config.battle_quiet_hours.enabled or not calendar.season_one_on(season, content):
        return []
    notes = []
    for event in _quiet_pending(season, content):
        at = when_in(season, content, event)
        local = _local(season, content, now, at)
        span = showdown_span(content, event)
        floor = _mandate_floor(season, content, event)
        clock = f"{int(local % DAY // HOUR):02d}:{int(local % HOUR // 60):02d}"
        if floor is not None and span > 0 and at < floor:  # 還排在最後一場時刻表決戰收尾之前：後面放不下（FB-564）
            notes.append(ORDER_KEPT.format(title=event.title, last=_last_showdown(content).title, clock=clock))
        elif span > 0 and _quiet_hit(local, span, content) is not None:
            if floor is not None and at - floor < calendar.cal_hour_seconds(content, season):  # 緊接在它收尾之後、只能排進半夜（FB-564）
                notes.append(ORDER_KEPT.format(title=event.title, last=_last_showdown(content).title, clock=clock))
            else:
                notes.append(QUIET_KEPT.format(title=event.title, clock=clock))
    return notes


def when(state: GameState, content: Content, event: TimetableEvent) -> float:
    """這件大事的世界秒。決戰與季末看排定的時間（舊季沒排就用預設），其他看季曆。伏筆的時間窗（T7）也用它。"""
    return when_in(state.world, content, event)


def when_in(season: WorldState, content: Content, event: TimetableEvent) -> float:
    """同 when，只要季本身（開季、換季時排決戰還沒有 GameState）。"""
    schedule = season.schedule
    if event.kind == "showdown":
        return schedule.get(event.id, _showdown_default(event, content, season))
    if event.kind == "finale":
        return schedule.get("finale", finale_default(content, season))
    return calendar.event_time(event, content, season)


NEVER = math.inf  # happened_at：這件大事沒有發生（管理者取消的決戰），輿圖不列


def happened_at(season: WorldState, content: Content, event: TimetableEvent) -> float:
    """輿圖「這一段大事」「天下怎麼變」把這件大事當成發生了的世界秒（FB-561、FB-562、FB-563）：照排定的時刻（when_in）；
    例外是決戰提早開了——管理者「立刻開戰」記在 showdowns_opened，開的那一刻記在 showdown_opened_at——不等排定的時刻，
    開了那一刻就算發生了：取排定的時刻與開的那一刻較早的，之後收場了、過了週界也照開的那一刻歸週，不跟著收場或此刻換週。
    開打後被管理者取消、沒有結果的（showdowns_cancelled）沒有發生，回 NEVER（之後管理者「定結果」了，照有結果的寫法：取排定的時刻
    與定結果那一刻較早的）。舊存檔沒記開的那一刻的：收場了取排定的時刻與收場那一刻較早的，開了還沒收場取排定的時刻與此刻較早的。
    其他大事（含季末、時間到了才結算的）一律是排定的時刻，跟 when_in 逐刻一樣。
    FB-654：休季時換了程式的上一季（calendar.weekend_style）一般大事的時刻不能照新程式的時刻表（週次與日子是新程式那一份）：
    只算這一季真的結算過的（season.timeline），時刻就是結算那一刻，沒結算過的是 NEVER、不列。決戰與季末的排定時刻本來就存在這一季的
    schedule 裡，照舊。"""
    at = when_in(season, content, event)
    if event.kind not in NOT_BY_SEASON_HOUR and calendar.weekend_style(season, content):
        done = season.timeline.get(event.id)
        return NEVER if done is None else done.time
    if event.kind != "showdown":
        return at
    done = season.timeline.get(event.id)
    cancelled = event.id in season.showdowns_cancelled
    opened = None if cancelled else season.showdown_opened_at.get(event.id)
    if opened is not None and opened < at - calendar.EPS_SECONDS:  # 自然開的（時間到了才開）不早於排定的時刻，只差浮點誤差的不算提早
        return opened
    if done is not None:
        return at if opened is not None else min(at, done.time)
    if cancelled:
        return NEVER
    if opened is not None:
        return at
    return min(at, season.time) if event.id in season.showdowns_opened else at


def happened_week(season: WorldState, content: Content, event: TimetableEvent) -> int:
    """輿圖把這件大事歸在第幾週（7 天季是第幾段）：決戰與季末照實際排定的時刻落在季曆的哪一週（FB-562：被「避開半夜」或管理者挪到
    別週的，不再照時刻表原本寫的那一週），提早開的決戰照開的那一刻（FB-563）；其他大事照時刻表寫的週次。沒有發生的（取消的）
    不列，歸哪一週都一樣，回時刻表寫的週次。休季時換了程式的上一季（FB-654，calendar.weekend_style）一般大事也照結算那一刻落在
    這一季自己的季曆的哪一週，不照新程式的時刻表寫的週次。"""
    if event.kind not in NOT_BY_SEASON_HOUR and not calendar.weekend_style(season, content):
        return event.week
    at = happened_at(season, content, event)
    return event.week if at == NEVER else calendar.point(at, content, season).week


def _pending(state: GameState, content: Content) -> list[TimetableEvent]:
    """還沒結算的大事，照時間排（同一刻照 timetable.json 的順序）。"""
    pending = [e for e in events(state.world, content) if e.id not in state.world.timeline]  # 天命之季多天命之爭（玉璽二）
    return sorted(pending, key=lambda e: when(state, content, e))


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
    from . import chapters  # noqa: PLC0415  章回主線 import storyline → rules → 這裡

    # 章回主線做成的份量（chapters.roll_mod，自己夾在 ±chapter_roll_cap）跟伏筆、軍令合計仍夾在 ±0.20
    total = w.event_mods.get(event.id, 0.0) + chapters.roll_mod(w, content, event)
    mods = max(-EVENT_MODS_CAP, min(EVENT_MODS_CAP, total))
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
    found = find(content, event_id)  # 天命之爭也找得到（玉璽二）
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
    """戰況移動。劇本沒有這條線（沒寫三條戰線的內容，例如測試夾具）就略過；真實內容的三條戰線都在，
    照 change_trend 推（時刻表只在第一季開關開著時結算，那時這些線才有值）；推動的文字不另外顯示，公告已經寫了。"""
    if any(t.id == trend_id for t in content.scenario.trends):
        change_trend(state, content, trend_id, delta)


def shown(lock: Lock) -> str:
    """公告與江湖史上寫的名字：名號。只有這一版之前匿名鎖定、記了 Lock.shown（「某位少俠」）的照記下的寫（不回溯揭名）；
    之後的鎖定不記 shown（傳聞分層第七節：天下大事與江湖史一律具名）。"""
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
    losers = [x.name for x in losing]  # 時間軸留名號（T9 的稱號）；公告寫 shown（一律名號；這一版之前匿名鎖定的是「某位少俠」）
    # 文字先填好再套效果：{官軍主將}、{人物:…} 指的是這件事發生「之前」的人（例：廣宗黃巾大勝，重挫的就是他）；
    # 人物效果落在誰身上也在這時定好——文字寫誰，效果就落在誰身上（FB-042），不因前一筆效果換了主將而改落到別人身上
    # 公告的組法（伏筆文件 3.4、5.4）：具名的一段＋這一檔的結果（含 note 與人物的後話）＋搶輸的一筆（豪強第三方那一筆 2026-10-31 拿掉）
    text = _headline(state, content, event, outcome, lock) + fill_slots(state, content, event, outcome.note)
    loser_line = _loser_line(state, content, event, outcome, lock, [shown(x) for x in losing])
    chronicle = _chronicle(state, content, event, outcome, lock if named else None)
    effects = [
        (_target(state, content, event, key), change, fill_slots(state, content, event, change.note))
        for key, change in outcome.figures.items()
    ]
    for trend_id, delta in outcome.trends.items():
        _push(state, content, trend_id, delta)
    for fid, change, note in effects:
        if fid is None or not figures.holds(state, content, change):
            continue
        text += "".join(figures.apply(state, content, fid, change)) + note
    territory.assign(w, content, outcome.control)  # 大事指定易手（設計 4.2 第 3 點）：戰況推完、人物改完之後
    for target, mod in outcome.chance_mods.items():
        w.event_bonus[target] = w.event_bonus.get(target, 0.0) + mod
    add_world_flags(state, outcome.world_flags_add)
    text += loser_line
    w.timeline[event.id] = TimelineResult(
        key=full_key, time=w.time, locked_by=lock.name if named else None, losers=losers if named else [], text=text,
    )
    add_rumor(state, text, content=content, layer="world")
    if chronicle:
        add_chronicle(state, chronicle)
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


def schedulable(content: Content, season: WorldState | None = None) -> list[TimetableEvent]:
    """管理者能排時間的大事：三場決戰與季末，照時刻表的順序（天命之季多天命之爭，玉璽二）。"""
    return [e for e in events(season, content) if e.kind in NOT_BY_SEASON_HOUR]


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


def status_rows(state: GameState, content: Content, cancelled: Collection[str] = ()) -> list[dict]:
    """設定頁「時刻表」的每一列：id、週次、標題、種類、世界秒、狀態（done 已結算／running 決戰開過集結還沒收場／
    cancelled 開打後被取消、還沒有結果（FB-099，呼叫端照 Game.cancelled_showdowns 給）／due 時間到了還沒結算／later 還沒到）、
    結果鍵（含版本）、能不能排時間（決戰與季末，還沒結算也還沒開過）。"""
    w = state.world
    rows = []
    for event in events(state.world, content):  # 天命之季多天命之爭（玉璽二）
        at = when(state, content, event)
        done = w.timeline.get(event.id)
        opened = event.id in w.showdowns_opened
        status = (
            "done" if done else ("cancelled" if event.id in cancelled else "running") if opened
            else "due" if at <= w.time + calendar.EPS_SECONDS else "later"
        )
        rows.append({
            "id": event.id, "week": event.week, "title": event.title, "kind": event.kind, "when": at, "state": status,
            "result": done.key if done else None,
            "schedulable": event.kind in NOT_BY_SEASON_HOUR and done is None and not opened,
        })
    return rows
