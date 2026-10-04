"""季曆（計畫第六節）：世界時鐘照舊走真實秒，體力、走路、打坐、決戰回合都看它；另外把一季壓成
season_weeks 週的「季曆」——季曆秒＝世界秒 × cal_scale。第一季的規則（時刻表的週次、週初發軍令、伏筆的夜裡）
一律看季曆。濃縮版 2.5 天、12 週時 cal_scale 是 33.6：一週是真實 5 小時，夜裡每 43 分鐘有 11 分鐘。

只是換算，不改任何狀態；引擎不讀電腦時鐘，時間一律是傳進來的世界秒。"""
from __future__ import annotations

import math
from typing import NamedTuple

from .models import Content, TimetableEvent
from .state import WorldState

MINUTE = 60
HOUR = 3600
DAY = 86400
WEEK = 7 * DAY
WEEKDAYS = "一二三四五六日"  # weekday 0＝週一
NIGHT_FROM, NIGHT_UNTIL = 23, 5  # 夜裡＝子時到寅時，季曆 23:00～04:59（伏筆文件 3.1）
EPS = 1e-6  # 換算成整分時的浮點誤差：世界秒乘回季曆常差一點點，不然整點會算成前一分鐘


class CalPoint(NamedTuple):
    week: int  # 第幾週，從 1 起、最多 season_weeks
    weekday: int  # 0＝週一
    hour: int
    minute: int
    cal_day: int  # 季曆第幾天，從 1 起、跨整季


def season_one_on(season: WorldState, content: Content) -> bool:
    """季曆與季的事只在開關開著、而且這一季開季時也是開的才跑：開關打開時還在跑的舊季不補算（計畫 T2）。"""
    return content.config.season_one and season.season_one


def cal_scale(content: Content) -> float:
    cfg = content.config
    return cfg.season_weeks * 7 / cfg.season_days


def point(time: float, content: Content) -> CalPoint:
    """世界秒落在季曆的哪一刻。季末那一刻（或之後）寫成最後一週週日 23:59，不會冒出不存在的下一週。"""
    total = content.config.season_weeks * WEEK
    cal = min(max(0.0, time * cal_scale(content)), total - MINUTE)
    minutes = math.floor(cal / MINUTE + EPS)
    day, minute_of_day = divmod(minutes, 24 * 60)
    return CalPoint(
        week=day // 7 + 1, weekday=day % 7, hour=minute_of_day // 60, minute=minute_of_day % 60, cal_day=day + 1,
    )


def week_start(week: int, content: Content) -> float:
    """第 week 週週一 00:00 的世界秒。"""
    return (week - 1) * WEEK / cal_scale(content)


def event_time(event: TimetableEvent, content: Content) -> float:
    return week_start(event.week, content) + event.day * DAY / cal_scale(content)


def is_night(time: float, content: Content) -> bool:
    hour = point(time, content).hour
    return hour >= NIGHT_FROM or hour < NIGHT_UNTIL


def cal_hour_seconds(content: Content) -> float:
    """一個曆時是幾個世界秒：季的事每跨過一個曆時跑一次（world.advance_world_state）。"""
    return HOUR / cal_scale(content)
