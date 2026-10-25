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
    assert [ranks.threshold(real_content(), r) for r in (2, 3, 4)] == [300, 900, 1800]


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


# ── Task 3：第一季的大勢人物也有回復與一天上限（21 天季）──


def _hurt(s, c, by=5):
    from tianxia import figures

    fid = next(f for f in c.figures if figures.state_of(s, c, f).status == "active" and c.figures[f].start_prestige > 30)
    now = figures._ensure(s, c, fid)
    now.prestige = c.figures[fid].start_prestige - by
    return fid, now


def test_season21_figures_recover_a_point_a_day():
    from tianxia import figures

    s, c = _state()
    assert figures.upkept(c, s.world)
    fid, now = _hurt(s, c, by=2)
    start = c.figures[fid].start_prestige
    figures.recover(s, c, 24)
    assert now.prestige == start - 1
    figures.recover(s, c, 48)
    assert now.prestige == start  # 回到開季值為止
    now.prestige, now.status = start - 3, "out"
    figures.recover(s, c, 72)
    assert now.prestige == start - 3  # 退場的不回


def test_season21_recovery_runs_when_the_world_advances(monkeypatch):
    """FB-350：回復要從推進世界的那一條路跑到，不能只有直接呼叫 recover 才回（以前只在第一季規則關著的那一支叫）。"""
    import random

    from tianxia import figures, world

    s, c = _state()
    monkeypatch.setattr(c.config.figure_life, "enabled", False)  # 不讓募兵混進來
    now = figures._ensure(s, c, "buji")
    start = c.figures["buji"].start_prestige
    now.prestige = start - 3
    day = 24 * world.HOUR / calendar.cal_scale(c, s.world)
    world.advance_world_state(s.world, c, day + 60, random.Random(0))
    assert figures.state_of(s, c, "buji").prestige == start - 2


def test_season21_daily_loss_cap_sums_across_players():
    from tianxia import figures

    s, c = _state()
    assert figures.loss_cap(c, s.world) == 15
    fid, now = _hurt(s, c, by=0)
    start = now.prestige
    figures.defeat(s, c, fid, 10, cap=figures.loss_cap(c, s.world))
    figures.defeat(s, c, fid, 10, cap=figures.loss_cap(c, s.world))  # 另一個人同一天再打一次：合計只扣 15
    assert now.prestige == start - 15


def test_howto_and_atlas_mention_recovery_in_season21():
    from tianxia import atlas, howto

    s, c = _state()
    text = "".join(howto._challenge_lines(c, s.world))
    assert "一天最多被打掉 15 點" in text and "慢慢回來" in text
    assert atlas.REGEN_NOTE in atlas._regen_note(s, c)


def test_old_save_without_treasure_weeks_loads():
    from tianxia.state import PlayerState

    s, _ = _state()
    raw = s.player.model_dump()
    raw.pop("treasure_weeks", None)
    assert PlayerState.model_validate(raw).treasure_weeks == []
