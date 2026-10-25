"""FB-500（7 天濃縮季 QA，2026-10-20）：最後兩天的懸賞，同一個期限寫成兩種字。

照現實天的季（21 天季、7 天濃縮季）有開季偏移 cal_offset：週三 14:00 開的 7 天季，季末是第 8 天 00:00，世界秒是 7 天減 14 小時。
bounties.to_season_end 比的是名義季長 × DAY（7 天），剛好在季末到期的第 6 天那一批判不成「到季末」，告示寫「期限 第 7 天」，
第 7 天那一批卻寫「到季末」——兩批其實都撐到季末。修成比這一季的季曆終點（季曆最後一刻之後那一瞬，同 timetable.finale_default，
管理者往後排的季末不算）。週末、14 天的季偏移是 0，照舊比季長 × DAY，一個字都不變。"""
from __future__ import annotations

import pytest
from conftest import real_content

from tianxia import bounties, calendar
from tianxia.state import Bounty
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


def _batch(content, season, day):
    """季曆第 day 天 00:00 掛的那一批（bounties.issue_day），回這一天掛的單。"""
    from tianxia import world

    vehicle = world._season_vehicle(content, season)
    season.time = calendar.day_start(day, content, season) + 1
    season.bounty_day = day - 1
    bounties.issue_day(vehicle, content, day)
    hung = [b for b in season.bounties if b.day == day]
    assert hung, day
    return hung


def test_the_last_two_days_of_an_afternoon_week7_season_both_say_season_end():
    """修前重現：週三 14:00 開的 7 天季，第 6 天那一批（第 8 天 00:00 到期＝季末）寫「期限 第 7 天・剩 N」、紙上「第 7 天 23:59」，
    第 7 天那一批寫「到季末」。修後兩批都寫「到季末」。"""
    c7 = real_content("week7")
    season = _season(c7, WED14)
    assert season.cal_offset == 14 * HOUR
    end = season.schedule["finale"]
    for day in (6, 7):
        for b in _batch(c7, season, day):
            assert b.expires >= end - calendar.EPS_SECONDS, (day, b.id)
            assert bounties.to_season_end(b, c7, season), (day, b.id)
            assert bounties.due_text(b, c7, season) == bounties.SEASON_END
            assert bounties.due_short(b, c7, season).startswith(f"{bounties.SEASON_END}・剩 ")
    for b in _batch(c7, season, 5):  # 第 5 天那一批在第 7 天 00:00 到期，照舊寫最後還有效的那一天
        assert not bounties.to_season_end(b, c7, season)
        assert bounties.due_short(b, c7, season).startswith("到第 6 天・剩 ")
        assert bounties.due_text(b, c7, season) == "第 7 天 00:00"


def test_a_midnight_week7_season_was_already_right():
    """00:00 開的季偏移是 0：修前修後一樣，第 6、7 天兩批都寫「到季末」。"""
    c7 = real_content("week7")
    season = _season(c7, MON)
    assert season.cal_offset == 0
    for day in (6, 7):
        assert all(bounties.to_season_end(b, c7, season) for b in _batch(c7, season, day))


def test_season21_last_two_days_say_season_end_too():
    """21 天季同一個錯（QA 對照腳本：週三 10:30 開，最後兩天的單都寫「期限 第 3 週週日」）：修後寫「到季末」；
    第 19 天那一批（第 21 天 00:00 到期）照舊寫「到第 3 週週六」。"""
    c21 = real_content("season21")
    season = _season(c21, WED10)
    assert season.cal_offset == 2 * DAY + 10.5 * HOUR
    for day in (20, 21):
        for b in _batch(c21, season, day):
            assert bounties.to_season_end(b, c21, season), (day, b.id)
            assert bounties.due_short(b, c21, season).startswith(f"{bounties.SEASON_END}・剩 ")
    for b in _batch(c21, season, 19):
        assert not bounties.to_season_end(b, c21, season)
        assert bounties.due_short(b, c21, season).startswith("到第 3 週週六・剩 ")


def test_an_admin_pushed_finale_keeps_both_batches_until_the_real_close():
    """連帶（QA）：管理者把季末往後排時，第 6、7 天兩批都撐到季真的收了（past_due 照 to_season_end），不是一批第 8 天 00:00 就作廢。"""
    c7 = real_content("week7")
    season = _season(c7, WED14)
    hung = _batch(c7, season, 6) + _batch(c7, season, 7)
    season.schedule["finale"] = season.schedule["finale"] + 6 * HOUR
    season.time = calendar.day_start(8, c7, season) + HOUR  # 名義季末過了一小時，季還在跑
    assert not season.ended
    assert not any(bounties.past_due(b, c7, season) for b in hung)


@pytest.mark.parametrize("profile", [None])
def test_weekend_and_fourteen_day_seasons_compare_with_the_season_length_as_before(profile):
    """週末、14 天的季沒有偏移：照舊比季長 × DAY，一個字都不變（剛好在季長、差一秒、多一秒三種都跟以前同一個答案）。"""
    content = real_content(profile) if profile else real_content()
    season = _season(content, MON)
    assert season.cal_offset == 0 and not calendar.season21_on(season, content)
    length = season_length_days(season, content) * DAY
    probe = Bounty(id="b0", kind="scout", faction="guan", week=1, expires=0.0, silver=10, deeds=1)
    for expires in (length - 1, length - calendar.EPS_SECONDS / 2, length, length + 1, length + 7 * DAY):
        b = probe.model_copy(update={"expires": expires})
        assert bounties.to_season_end(b, content, season) == (expires >= length - calendar.EPS_SECONDS), expires
