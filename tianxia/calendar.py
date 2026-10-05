"""季曆（計畫第六節）：世界時鐘照舊走真實秒，體力、走路、打坐、決戰回合都看它；另外把一季壓成
season_weeks 週的「季曆」——季曆秒＝世界秒 × cal_scale。第一季的規則（時刻表的週次、週初發軍令、伏筆的夜裡）
一律看季曆。濃縮版 2.5 天、12 週時 cal_scale 是 33.6：一週是真實 5 小時，夜裡每 43 分鐘有 11 分鐘。

季長照這一季開季時蓋的章（WorldState.length_days）：設定中途換了，正在跑的這一季週次不會移動；沒有章的舊季照預設的 14 天。
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


class CalPoint(NamedTuple):
    week: int  # 第幾週，從 1 起、最多 season_weeks
    weekday: int  # 0＝週一
    hour: int
    minute: int
    cal_day: int  # 季曆第幾天，從 1 起、跨整季


def season_one_on(season: WorldState, content: Content) -> bool:
    """季曆與季的事只在開關開著、而且這一季開季時也是開的才跑：開關打開時還在跑的舊季不補算（計畫 T2）。"""
    return content.config.season_one and season.season_one


def cal_scale(content: Content, season: WorldState | None = None) -> float:
    """季曆秒 ÷ 世界秒。季長照 season 蓋的章（沒有章的舊季照 DEFAULT_SEASON_DAYS）；不給 season 時照現在的設定。"""
    days = season_length_days(season, content) if season is not None else content.config.season_days
    return content.config.season_weeks * 7 / days


def point(time: float, content: Content, season: WorldState | None = None) -> CalPoint:
    """世界秒落在季曆的哪一刻。季末那一刻（或之後）寫成最後一週週日 23:59，不會冒出不存在的下一週。"""
    total = content.config.season_weeks * WEEK
    cal = min(max(0.0, time * cal_scale(content, season)), total - MINUTE)
    minutes = math.floor(cal / MINUTE + EPS_MINUTES)
    day, minute_of_day = divmod(minutes, 24 * 60)
    return CalPoint(
        week=day // 7 + 1, weekday=day % 7, hour=minute_of_day // 60, minute=minute_of_day % 60, cal_day=day + 1,
    )


def week_start(week: int, content: Content, season: WorldState | None = None) -> float:
    """第 week 週週一 00:00 的世界秒。"""
    return (week - 1) * WEEK / cal_scale(content, season)


def event_time(event: TimetableEvent, content: Content, season: WorldState | None = None) -> float:
    return week_start(event.week, content, season) + event.day * DAY / cal_scale(content, season)


def is_night(time: float, content: Content, season: WorldState | None = None) -> bool:
    hour = point(time, content, season).hour
    return hour >= NIGHT_FROM or hour < NIGHT_UNTIL


def cal_hour_seconds(content: Content, season: WorldState | None = None) -> float:
    """一個曆時是幾個世界秒：季的事每跨過一個曆時跑一次（world.advance_world_state）。"""
    return HOUR / cal_scale(content, season)


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
