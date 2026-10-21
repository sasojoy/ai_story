"""FB-636（QA 上線前整合預演最後一輪，2026-10-21）：全新的資料庫在「籌備中」帶 week7 或 season21 開，伺服器與假人程式啟動時都印
「⚠ 正在跑的這一季是用另一種季曆開的……」。籌備中的季還沒蓋 season21 的章（False），跟設定的 True 對不上就回 SEASON21_MISMATCH，
可是還沒開過任何一季，什麼都沒換，那一句會叫主機端的人去還原備份。PM 定：籌備中（還沒開過季）不印；季真的在跑而且對不上才印
（FB-520 那一行的警告不能被這一條弄丟）。"""
from __future__ import annotations

import pytest
from conftest import real_content

from tianxia import calendar
from tianxia.sqlite_world import open_world
from tianxia.state import WorldState

import run_bots
import server

pytestmark = pytest.mark.slow  # 載真實內容

NOW = 1792339200  # 2026-10-19 週一 00:00（台灣）
MARK = calendar.SEASON21_MISMATCH


def _start_server(monkeypatch, capsys, profile: str) -> str:
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "PROFILE", profile)
    monkeypatch.setattr(server, "CONTENT", real_content(profile))
    server.main([])
    return capsys.readouterr().out


def _start_bots(monkeypatch, capsys, profile: str) -> str:
    monkeypatch.setattr(run_bots.time, "sleep", lambda seconds: None)
    monkeypatch.setenv("TIANXIA_PROFILE", profile)
    run_bots.main(ticks=0)
    return capsys.readouterr().out


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_a_fresh_database_still_in_preparation_prints_no_mismatch(monkeypatch, capsys, profile):
    """還沒種過季的全新資料庫（單上的重現步驟）：兩支程式都不印。"""
    assert open_world().season_phase() == "preparing"
    assert MARK not in _start_server(monkeypatch, capsys, profile)
    assert MARK not in _start_bots(monkeypatch, capsys, profile)


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_a_seeded_but_unopened_season_prints_nothing_either(monkeypatch, capsys, profile):
    """種好了、管理者還沒開季（以前沒帶設定種的，章是 false）：開季時才重新蓋章，這時候什麼都沒換，一樣不印。"""
    old = real_content("weekend")
    open_world().seed_first_season(old)
    assert open_world().season_phase() == "preparing" and not open_world().get_season().season21
    assert MARK not in _start_server(monkeypatch, capsys, profile)
    assert MARK not in _start_bots(monkeypatch, capsys, profile)


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_a_running_season_opened_with_another_calendar_still_prints_the_fb520_warning(monkeypatch, capsys, profile):
    """FB-520 的警告沒有被弄丟：週末式的季已經開了（章上 season21 是 false），換上照現實天的程式，兩支程式都印。"""
    old = real_content("weekend")
    world = open_world()
    world.seed_first_season(old)
    assert world.open_season(old, NOW)
    assert world.season_phase() == "running"
    assert MARK in _start_server(monkeypatch, capsys, profile)
    assert MARK in _start_bots(monkeypatch, capsys, profile)


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_a_running_season_with_the_matching_calendar_prints_nothing(monkeypatch, capsys, profile):
    content = real_content(profile)
    world = open_world()
    world.seed_first_season(content)
    assert world.open_season(content, NOW)
    assert MARK not in _start_server(monkeypatch, capsys, profile)
    assert MARK not in _start_bots(monkeypatch, capsys, profile)


def test_the_warning_function_itself_knows_the_phase():
    """calendar.profile_warning(content, season, phase)：籌備中不印；跑著而且對不上才印；不給 phase 照舊（只看季收了沒）。"""
    c7 = real_content("week7")
    bare = WorldState()  # 全新資料庫讀回來的樣子：沒蓋章
    assert not bare.season21
    assert calendar.profile_warning(c7, bare, "preparing") is None
    assert calendar.profile_warning(c7, bare, "running") == MARK
    assert calendar.profile_warning(c7, bare) == MARK  # 沒給 phase：跟以前一樣
    bare.ended = True
    assert calendar.profile_warning(c7, bare, "resting") is None
    assert calendar.profile_warning(c7, None, "preparing") is None
