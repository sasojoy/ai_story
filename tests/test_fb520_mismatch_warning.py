"""FB-520（7 天測試季整合預演，2026-10-20）：季中換上新程式只印一行 ⚠ 就照跑，那一行叫人「帶開季時那一份設定」，可是設定的名字
一樣是 week7、內容換了（週末式 → 照現實天）。PM 定不擋（擋了伺服器起不來更糟），部署說明寫死休季才換；這裡只改那一行的字，讓主機端
的人看得懂該怎麼辦（字待 joy 潤）。"""
from __future__ import annotations

import pytest
from conftest import real_content

from tianxia import calendar
from tianxia.world_state import fresh_season, stamp_season

pytestmark = pytest.mark.slow  # 載真實內容

MON = 1792339200  # 2026-10-19 週一 00:00（台灣）


def test_matching_programs_and_ended_seasons_stay_quiet():
    c7 = real_content("week7")
    season = fresh_season(c7)
    stamp_season(season, c7, now=MON)
    assert calendar.profile_warning(c7, season) is None
    season.ended = True
    assert calendar.profile_warning(real_content("week7"), season) is None
