"""FB-505（7 天濃縮季第二輪，PM 2026-10-20；同 FB-500 那一類）：rules.day_turn 比名義季長 × DAY。照現實天的季有開季偏移
（週三 14:00 開的 7 天季，季曆終點是 7 天減 14 小時）：管理者把季末往後排時，最後一天的換日落在季曆終點，卻比季長 × DAY 早，
判成 "at"、寫「第 7 天 23:59」（季曆夾在最後一刻）——那一刻其實已經在季曆之外，該寫 "later"（過一陣子）。修成比
calendar.nominal_end（同 FB-500）。週末、14 天的季偏移是 0，照舊比季長 × DAY，一個字都不變。"""
from __future__ import annotations

import pytest
from conftest import real_content

from tianxia import calendar, rules
from tianxia.world_state import fresh_season, season_length_days, stamp_season

pytestmark = pytest.mark.slow  # 每一條都載真實內容、開一季

HOUR, DAY = 3600, 86400
WED10 = 1792549800  # 2026-10-21 週三 10:30（台灣）
WED14 = WED10 + 3.5 * HOUR  # 2026-10-21 週三 14:00（台灣）
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）


def _season(content, now):
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    return season


def test_week7_last_day_turn_is_later_when_the_admin_pushed_the_finale():
    """修前重現：週三 14:00 開的 7 天季，季末往後排 6 小時，第 7 天的換日寫成「第 7 天 23:59」（"at"）。"""
    c7 = real_content("week7")
    season = _season(c7, WED14)
    assert season.cal_offset == 14 * HOUR
    season.schedule["finale"] += 6 * HOUR
    season.time = calendar.day_start(7, c7, season) + HOUR
    assert rules.day_turn(c7, season) == ("later", None)
    season.time = calendar.day_start(6, c7, season) + HOUR  # 第 6 天的換日（第 7 天 00:00）照舊寫得出來
    assert rules.day_turn(c7, season) == ("at", "第 7 天 00:00")


def test_week7_last_day_without_a_push_is_the_season_end():
    c7 = real_content("week7")
    season = _season(c7, WED14)
    season.time = calendar.day_start(7, c7, season) + HOUR
    assert rules.day_turn(c7, season) == ("season", None)


def test_season21_last_day_turn_is_later_when_the_admin_pushed_the_finale():
    """21 天季同一個錯（週三 10:30 開，偏移 2 天 10.5 小時）。"""
    c21 = real_content("season21")
    season = _season(c21, WED10)
    season.schedule["finale"] += 6 * HOUR
    season.time = calendar.day_start(21, c21, season) + HOUR
    assert rules.day_turn(c21, season) == ("later", None)
    season.time = calendar.day_start(20, c21, season) + HOUR
    assert rules.day_turn(c21, season) == ("at", "第 3 週・週日 00:00")


@pytest.mark.parametrize("profile", [None])
def test_weekend_and_fourteen_day_compare_with_the_season_length_as_before(profile):
    """週末、14 天的季沒有偏移：季末往後排一天，最後幾天每一刻跟改之前（季長 × DAY）同一個答案。"""
    content = real_content(profile) if profile else real_content()
    season = _season(content, MON)
    assert season.cal_offset == 0 and not calendar.season21_on(season, content)
    assert calendar.nominal_end(content, season) == season_length_days(season, content) * DAY
    from tianxia.world import season_end_time

    length = season_length_days(season, content) * DAY
    season.schedule["finale"] = length + DAY  # 週末照排定的季末；14 天的季沒有時刻表，季末照季長（season_end_time）
    step = rules.day_seconds(content, season) / 4
    kinds = set()
    for k in range(-8, 6):
        season.time = length + k * step
        kind, _ = rules.day_turn(content, season)
        end = rules.day_ends(content, season)
        old = "season" if end >= season_end_time(season, content) - calendar.EPS_SECONDS else (
            "later" if end >= length - calendar.EPS_SECONDS else "at")
        assert kind == old, k
        kinds.add(kind)
    assert kinds >= ({"at", "later"} if profile == "week7" else {"at", "season"})  # 兩種季的交界都量到了
