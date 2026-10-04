"""季曆（計畫 T2、第六節）：世界時鐘照舊走真實秒，季曆＝世界秒 × cal_scale。"""
import pytest

from tianxia import calendar
from tianxia.calendar import CalPoint

HOUR = 3600
DAY = 86400


@pytest.fixture
def condensed(content):
    content.config.season_days, content.config.season_weeks = 2.5, 12
    return content


def test_cal_scale_condensed(condensed):
    assert calendar.cal_scale(condensed) == pytest.approx(33.6)
    assert calendar.week_start(1, condensed) == 0
    assert calendar.week_start(2, condensed) == pytest.approx(18000)  # 一週＝真實 5 小時
    assert calendar.cal_hour_seconds(condensed) == pytest.approx(HOUR / 33.6)


def test_the_prototype_fourteen_days_is_scale_six(content):
    content.config.season_days, content.config.season_weeks = 14, 12
    assert calendar.cal_scale(content) == pytest.approx(6)  # 兩種只差設定檔，同一套程式（第六節）


def test_point_week_and_clock(condensed):
    assert calendar.point(0, condensed) == CalPoint(week=1, weekday=0, hour=0, minute=0, cal_day=1)
    later = calendar.point(18000 + calendar.cal_hour_seconds(condensed), condensed)
    assert later == CalPoint(week=2, weekday=0, hour=1, minute=0, cal_day=8)
    tuesday = calendar.point(calendar.week_start(3, condensed) + (DAY + 21 * HOUR + 40 * 60) / 33.6, condensed)
    assert (tuesday.week, tuesday.weekday, tuesday.hour, tuesday.minute) == (3, 1, 21, 40)  # 第 3 週・週二 21:40


def test_the_moment_the_season_ends_is_the_last_minute_of_week_twelve(condensed):
    """季末那一刻（真實 60 小時整）寫成第 12 週週日 23:59，不會變成不存在的第 13 週。"""
    assert calendar.point(2.5 * DAY, condensed) == CalPoint(week=12, weekday=6, hour=23, minute=59, cal_day=84)
    assert calendar.point(3 * DAY, condensed).week == 12


def test_event_time_is_the_week_start_plus_its_day(condensed):
    from tianxia.models import TimetableEvent

    event = TimetableEvent(id="e", week=3, day=1.5, title="測試", kind="fixed")
    assert calendar.event_time(event, condensed) == pytest.approx(calendar.week_start(3, condensed) + 1.5 * DAY / 33.6)


def test_is_night_by_calendar_hour(condensed):
    def at(hour: int, minute: int = 0) -> float:  # 第 1 週週一的季曆時刻換成世界秒
        return (hour * HOUR + minute * 60) / 33.6

    assert calendar.is_night(at(23, 30), condensed)
    assert calendar.is_night(at(4, 59), condensed)
    assert not calendar.is_night(at(5), condensed)
    assert not calendar.is_night(at(22, 59), condensed)
