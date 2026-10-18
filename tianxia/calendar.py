"""季曆（計畫第六節）：世界時鐘照舊走真實秒，體力、走路、打坐、決戰回合都看它；另外把一季壓成
season_weeks 週的「季曆」——季曆秒＝世界秒 × cal_scale。第一季的規則（時刻表的週次、週初發軍令、伏筆的夜裡）
一律看季曆。濃縮版 2.5 天、12 週時 cal_scale 是 33.6：一週是真實 5 小時，夜裡每 43 分鐘有 11 分鐘。

季長照這一季開季時蓋的章（WorldState.length_days）：設定中途換了，正在跑的這一季週次不會移動；沒有章的舊季照預設的 14 天。
21 天季（Config.season21，正式季整合設計 1.1）：season_weeks 3、季長 21 天，cal_scale 是 1（季曆就是現實的三週），另加一段偏移
（WorldState.cal_offset）：開季那一刻離那一週台灣週一 00:00 多遠。世界秒照舊從開季那一刻算；只有這裡把它換成季曆，其他季偏移是 0。
每個函式都收一個 season；只有沒有季可看的呼叫端（例如蓋章本身之前）才不給，那時照現在的設定。

只是換算，不改任何狀態；引擎不讀電腦時鐘，時間一律是傳進來的世界秒。"""
from __future__ import annotations

import math
from typing import NamedTuple

from .models import Content, TimetableEvent
from .state import WorldState
from .world_state import season_length_days

MINUTE = 60
HOUR = 3600
DAY = 86400
WEEK = 7 * DAY
WEEKDAYS = "一二三四五六日"  # weekday 0＝週一
NIGHT_FROM, NIGHT_UNTIL = 23, 5  # 夜裡＝子時到寅時，季曆 23:00～04:59（伏筆文件 3.1）
# 浮點誤差，照單位分開命名，不要混用：
EPS_MINUTES = 1e-6  # 季曆換算成整分時（以分為單位）：世界秒乘回季曆常差一點點，不然整點會算成前一分鐘
EPS_SECONDS = 1e-6  # 比較世界秒時：剛好在大事時刻、曆時交界、週初的那一刻要算「到了」
EPS_CAL_HOURS = 1e-9  # 找下一個曆時交界時的浮點誤差（以曆時為單位）：剛好停在交界上的時間不能被算成上一個曆時（同 world.EPS_CAL_HOURS）


class CalPoint(NamedTuple):
    week: int  # 第幾週，從 1 起、最多 season_weeks
    weekday: int  # 0＝週一
    hour: int
    minute: int
    cal_day: int  # 季曆第幾天，從 1 起、跨整季


def season_one_on(season: WorldState, content: Content) -> bool:
    """季曆與季的事只在開關開著、而且這一季開季時也是開的才跑：開關打開時還在跑的舊季不補算（計畫 T2）。"""
    return content.config.season_one and season.season_one


def season21_on(season: WorldState | None, content: Content) -> bool:
    """21 天季的骨架（季曆＝現實週、錨點、21 天的時刻表、不提前收季、今天＝現實一天）：設定開著、這一季開季時也蓋了章。"""
    return season is not None and content.config.season21 and season.season21


def _offset(content: Content, season: WorldState | None) -> float:
    """季曆的偏移（季曆秒）：21 天季是開季那一刻離那一週台灣週一 00:00 多遠，其他季是 0（一個字都不變）。"""
    return season.cal_offset if season21_on(season, content) else 0.0


def anchor_offset(now: float, content: Content) -> float:
    """開季那一刻（現實的 epoch 秒）離那一週台灣週一 00:00 幾秒（正式季整合設計 1.1：週一以外開季，第一週就短幾天）。
    台灣照 pill_day_utc_offset_hours（同回體丹的換日）；1970-01-01 是週四。"""
    local = now + content.config.pill_day_utc_offset_hours * HOUR
    days = math.floor(local / DAY)
    return local - (days - (days + 3) % 7) * DAY


# 待 joy 潤（FB-157）：主機的人看的那一行，兩個程式啟動時印
PROFILE_MISMATCH = "⚠ 這一季開季時第一季規則是開著的，這個程式的設定卻是關著的：這樣跑會把第一季的規則全關掉、懸賞也會重掛。兩個程式都要帶同一份設定（TIANXIA_PROFILE）。"


def profile_warning(content: Content, season: WorldState | None) -> str | None:
    """啟動時設定對不上的那一行（FB-157；server.main、run_bots.main 印）：這一季蓋了第一季的章、這個程式卻沒開第一季規則（換版時
    其中一個程式沒帶 TIANXIA_PROFILE=weekend）。反過來（開關剛打開、還在跑的季開季時是關的）是正常的換季過渡，不印。沒有季是 None。
    季收了（休季）也不印：週末的季收了、主機故意不帶設定重開好開 14 天的下一季，這時印「要帶同一份設定」會叫人帶錯（審查）。"""
    if season is None or season.ended:
        return None
    if season.season21 and not content.config.season21:  # 21 天季的章、這個程式卻沒開（例：帶了週末的設定）：季曆整個對不上
        return PROFILE_MISMATCH
    if not season.season_one or content.config.season_one:
        return None
    return PROFILE_MISMATCH


def cal_scale(content: Content, season: WorldState | None = None) -> float:
    """季曆秒 ÷ 世界秒。季長照 season 蓋的章（沒有章的舊季照 DEFAULT_SEASON_DAYS）；不給 season 時照現在的設定。"""
    days = season_length_days(season, content) if season is not None else content.config.season_days
    return content.config.season_weeks * 7 / days


def point(time: float, content: Content, season: WorldState | None = None) -> CalPoint:
    """世界秒落在季曆的哪一刻。季末那一刻（或之後）寫成最後一週週日 23:59，不會冒出不存在的下一週。"""
    total = content.config.season_weeks * WEEK
    cal = min(max(0.0, time * cal_scale(content, season) + _offset(content, season)), total - MINUTE)
    minutes = math.floor(cal / MINUTE + EPS_MINUTES)
    day, minute_of_day = divmod(minutes, 24 * 60)
    return CalPoint(
        week=day // 7 + 1, weekday=day % 7, hour=minute_of_day // 60, minute=minute_of_day % 60, cal_day=day + 1,
    )


def week_start(week: int, content: Content, season: WorldState | None = None) -> float:
    """第 week 週週一 00:00 的世界秒（21 天季在週一以外開季時，第 1 週週一是負的：開季之前）。"""
    return ((week - 1) * WEEK - _offset(content, season)) / cal_scale(content, season)


def event_time(event: TimetableEvent, content: Content, season: WorldState | None = None) -> float:
    return week_start(event.week, content, season) + event.day * DAY / cal_scale(content, season)


def is_night(time: float, content: Content, season: WorldState | None = None) -> bool:
    hour = point(time, content, season).hour
    return hour >= NIGHT_FROM or hour < NIGHT_UNTIL


def cal_hour_seconds(content: Content, season: WorldState | None = None) -> float:
    """一個曆時是幾個世界秒：季的事每跨過一個曆時跑一次（world.advance_world_state）。"""
    return HOUR / cal_scale(content, season)


def next_hour_mark(time: float, content: Content, season: WorldState | None = None) -> float:
    """從世界秒 time 到下一個曆時交界還有幾個世界秒（world.advance_world_state 停在這裡跑季的事）：交界照季曆的整點，
    21 天季在 10:30 開季時第一個交界在 30 分鐘後；偏移是 0 時跟以前（世界秒照曆時的整數倍）一模一樣。"""
    hour = cal_hour_seconds(content, season)
    shift = _offset(content, season) / cal_scale(content, season)
    return (math.floor((time + shift) / hour + EPS_CAL_HOURS) + 1) * hour - (time + shift)


def cal_days(time: float, content: Content, season: WorldState | None = None) -> float:
    """世界秒 time 離第 1 週週一 00:00 幾個季曆天（含零頭；21 天季的人物照天數出兵用）。"""
    return (time * cal_scale(content, season) + _offset(content, season)) / DAY


# ── 畫面上的時間 ─────────────────────────────────────────


def day_clock_text(time: float) -> str:
    """沒有季曆時的寫法，例如「第2天 14:05」（戰報、江湖紀錄、地圖一直以來的樣子）。"""
    return f"第{int(time // DAY) + 1}天 {int(time % DAY // HOUR):02d}:{int(time % HOUR // 60):02d}"


def day_text(time: float) -> str:
    """沒有季曆時江湖史、傳聞只寫天數，例如「第2天」。"""
    return f"第{int(time // DAY) + 1}天"


def point_text(at: CalPoint) -> str:
    """季曆時刻唯一的寫法「第 3 週・週二 21:40」（N 前後有空格）：狀態列第二行、下一件、江湖史、傳聞、軍令截止都走這裡，
    不要在別處自己拼（FB-062 之後 PM 定：全部跟狀態列第二行一樣）。"""
    return f"第 {at.week} 週・週{WEEKDAYS[at.weekday]} {at.hour:02d}:{at.minute:02d}"


def stamp_text(time: float, content: Content, season: WorldState | None, *, clock: bool = True) -> str:
    """玩家看得到的遊戲時間，全部走這裡：第一季（開關開著、這一季也蓋了章）寫成狀態列那樣的「第 3 週・週二 21:40」（point_text）；
    其他時候照舊——clock 時「第2天 14:05」，不要時刻（江湖史、傳聞）時「第2天」，一個字都不變。
    season 是 None（例如上一季的江湖史）一律照舊。"""
    if season is not None and season_one_on(season, content):
        return point_text(point(time, content, season))
    return day_clock_text(time) if clock else day_text(time)
