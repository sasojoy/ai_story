"""正式季整合第 6 批：軍階、每週上限、人物回復（設計 3.7～3.9；12.3 第 17、18 條）。只在 21 天季（season21 設定），週末與 14 天一個字都不變。"""
from __future__ import annotations

from conftest import real_content

from tianxia import calendar, ranks, treasures
from tianxia.state import GameState, new_game_state
from tianxia.world_state import fresh_season, stamp_season

MON = 1792339200  # 2026-10-19 週一 00:00（台灣）


def _state(profile="season21") -> GameState:
    c = real_content(profile)
    s = new_game_state(c, "甲")
    season = fresh_season(c)
    stamp_season(season, c, now=MON)
    s.world = season
    return s, c


def test_season21_rank_thresholds():
    c21 = real_content("season21")
    assert [ranks.threshold(c21, r) for r in (2, 3, 4)] == [400, 1300, 2600]
    for profile in ("weekend", None):
        assert [ranks.threshold(real_content(profile), r) for r in (2, 3, 4)] == [300, 900, 1800]


# ── Task 2：挑戰本人的寶物每週 1 件、一季 3 件 ──


def _drops(s, c, figures, start=0):
    got = []
    for i, fid in enumerate(figures):
        item, _ = treasures.challenge_drop(s, c, fid, 1, start + i + 1)
        got.append(item is not None)
    return got


def test_treasure_weekly_cap_resets_on_the_calendar_week():
    s, c = _state()
    c.config.treasures.challenge_chance = 1.0
    figs = list(c.figures)
    assert _drops(s, c, figs[:2]) == [True, False]  # 第 1 週：一件
    s.world.time = calendar.week_start(2, c, s.world)
    assert _drops(s, c, figs[2:4], 10) == [True, False]  # 第 2 週週一 00:00 起又一件
    s.world.time = calendar.week_start(3, c, s.world) + 3600
    assert _drops(s, c, figs[4:5], 20) == [True]
    s.player.treasure_weeks = s.player.treasure_weeks[:-1]  # 就算這一週還沒掉過，一季到 3 件也不再掉
    assert _drops(s, c, figs[5:6], 30) == [False]
    assert len(s.player.treasure_drops) == 3


def test_weekend_treasure_cap_is_unchanged():
    s, c = _state("weekend")
    c.config.treasures.challenge_chance = 1.0
    assert c.config.figure_treasure_weekly == 0 and c.config.figure_treasure_cap == 2
    assert _drops(s, c, list(c.figures)[:3]) == [True, True, False]


def test_old_save_without_treasure_weeks_loads():
    from tianxia.state import PlayerState

    s, _ = _state()
    raw = s.player.model_dump()
    raw.pop("treasure_weeks", None)
    assert PlayerState.model_validate(raw).treasure_weeks == []
