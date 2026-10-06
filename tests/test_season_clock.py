"""主機端的賽季時鐘開關（scripts/season_clock.py，賽季計畫 Task 5）。"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import season_clock  # noqa: E402

from conftest import install_season_one, install_showdowns  # noqa: E402
from tianxia.sqlite_world import SqliteWorldStore, open_world  # noqa: E402


def _seeded(tmp_path, content):
    path = tmp_path / "t.db"
    open_world(path).seed_first_season(content)  # 測試內容直接開季
    return path


def test_pause_status_and_resume_from_the_host(tmp_path, content, capsys):
    path = _seeded(tmp_path, content)
    assert season_clock.main(["pause", "--db", str(path)], clock=lambda: 1000.0) == 0
    assert open_world(path).paused_at() == 1000.0
    assert season_clock.main(["status", "--db", str(path)], clock=lambda: 1600.0) == 0
    assert "時鐘：停了 10 分鐘" in capsys.readouterr().out
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: 4600.0, content=content) == 0
    assert open_world(path).paused_at() is None
    assert "停了 60 分鐘" in capsys.readouterr().out
    season_clock.main(["status", "--db", str(path)], clock=lambda: 4700.0)
    assert "時鐘：在走" in capsys.readouterr().out


def test_pausing_twice_or_out_of_season_says_so(tmp_path, content, capsys):
    path = _seeded(tmp_path, content)
    season_clock.main(["pause", "--db", str(path)], clock=lambda: 1000.0)
    assert season_clock.main(["pause", "--db", str(path)], clock=lambda: 1300.0) == 0
    assert "已經停著" in capsys.readouterr().out
    assert open_world(path).paused_at() == 1000.0  # 起點不變
    season_clock.main(["resume", "--db", str(path)], clock=lambda: 1400.0, content=content)
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: 1500.0, content=content) == 0
    assert "沒有暫停" in capsys.readouterr().out
    open_world(path).mutate_season(lambda s: setattr(s, "ended", True))
    assert season_clock.main(["pause", "--db", str(path)], clock=lambda: 1600.0) == 1
    assert "現在是休季" in capsys.readouterr().out


def test_a_missing_database_is_not_created(tmp_path, capsys):
    path = tmp_path / "nope.db"
    assert season_clock.main(["status", "--db", str(path)]) == 1
    assert not path.exists() and "找不到" in capsys.readouterr().out


def _paused_before_changshe(tmp_path, content, caught_up: bool):
    """第一季：長社前十分鐘（季時間）主機端暫停。caught_up＝暫停前最後有人補算過（否則 0～暫停這一大段沒人補算，
    例如沒開排程、半夜沒人上線）。回傳（資料庫檔, 暫停的現實時間）。"""
    install_season_one(content)
    install_showdowns(content)
    path = _seeded(tmp_path, content)
    world = open_world(path)
    world.catch_up_season(content, 0.0, random.Random(0))
    paused = world.get_season().schedule["changshe_fire"] / content.config.time_scale - 600
    if caught_up:
        world.catch_up_season(content, paused, random.Random(0))
    season_clock.main(["pause", "--db", str(path)], clock=lambda: paused)
    return path, paused


def test_resume_from_the_host_opens_a_showdown_that_passed_during_the_pause(tmp_path, content, capsys):
    """第一季：長社原本的時間落在停機那段裡，主機端 resume 那一刻就開集結（B11，跟管理者按「繼續」一樣）。
    集結號角那一行印出來、只印一次（它可能出在補算那一路或緊接著的 start_pending_battle，兩邊都要印）。"""
    path, paused = _paused_before_changshe(tmp_path, content, caught_up=True)
    capsys.readouterr()
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: paused + 7200, content=content) == 0
    assert capsys.readouterr().out.count("集結號角") == 1
    battle = open_world(path).get_battle()
    assert (battle.battle_id, battle.phase) == ("changshe_fire", "muster")


def test_the_muster_call_is_printed_when_the_catch_up_has_nothing_to_advance(tmp_path, content, capsys, monkeypatch):
    """同一條的另一邊：繼續那一刻沒有零頭要補算（補算什麼都不做、回 []），長社由緊接著的 start_pending_battle 開，
    集結號角在它的回傳裡——一樣要印、一樣只印一次。"""
    path, paused = _paused_before_changshe(tmp_path, content, caught_up=True)
    capsys.readouterr()
    monkeypatch.setattr(SqliteWorldStore, "catch_up_season", lambda self, *args, **kwargs: [])
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: paused + 7200, content=content) == 0
    assert capsys.readouterr().out.count("集結號角") == 1
    assert open_world(path).get_battle().battle_id == "changshe_fire"


def test_host_resume_after_an_uncaught_span_keeps_the_order(tmp_path, content, capsys):
    """預檢 F2：主機端直接暫停（暫停前有一大段沒人補算，裡面有第 4 週的波才），停四十個鐘頭：繼續時先補算、波才先結算，
    長社才開集結——不是長社先開、波才還在時間軸外面（省掉補算就會這樣）。"""
    path, paused = _paused_before_changshe(tmp_path, content, caught_up=False)
    capsys.readouterr()
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: paused + 40 * 3600, content=content) == 0
    world = open_world(path)
    assert world.get_battle().battle_id == "changshe_fire"
    assert "bocai" in world.get_season().timeline and "changshe_fire" not in world.get_season().timeline


def test_the_host_resume_goes_through_the_one_resume_helper(tmp_path, content, capsys, monkeypatch):
    """每一條「繼續」的路都走 world.resume_season_clock（三步的順序只寫在那一個地方）：主機端腳本也是。"""
    path, paused = _paused_before_changshe(tmp_path, content, caught_up=True)
    calls = []
    real = season_clock.resume_season_clock
    monkeypatch.setattr(season_clock, "resume_season_clock", lambda *a, **k: calls.append(a) or real(*a, **k))
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: paused + 7200, content=content) == 0
    assert len(calls) == 1
