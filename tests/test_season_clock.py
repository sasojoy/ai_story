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
    """主機端直接暫停（暫停前有一大段沒人補算，裡面有第 4 週的波才），停四十個鐘頭：繼續時先補算、波才先結算，
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


def test_resume_with_a_profile_that_does_not_match_the_season_is_refused(tmp_path, content, capsys):
    """I-1：伺服器開著第一季設定（weekend），主機端那一個視窗沒設 TIANXIA_PROFILE、也沒給 --profile，讀到的是預設設定
    （第一季規則關著）：季曆與排好的決戰會照錯的規則算（長社晚開三個鐘頭、還印「照原本的時間開」），而繼續撤不回來。
    所以對不上這一季開季時蓋的章（第一季規則開／關、季長）就拒絕，時鐘還停著；設定對得上才繼續。"""
    path, paused = _paused_before_changshe(tmp_path, content, caught_up=True)
    capsys.readouterr()
    resumed = paused + 3 * 3600
    for field, wrong in (("season_one", False), ("season_days", 14.0)):
        right = getattr(content.config, field)
        setattr(content.config, field, wrong)
        assert season_clock.main(["resume", "--db", str(path)], clock=lambda: resumed, content=content) == 1
        out = capsys.readouterr().out
        # 說清楚怎麼辦：先對一下 --profile／TIANXIA_PROFILE；已經一樣（開季之後設定改過）就改用遊戲裡管理者工具的「▶ 繼續」
        assert "--profile" in out and "▶ 繼續" in out and "接著走了" not in out
        assert open_world(path).paused_at() == paused and open_world(path).get_battle() is None  # 還停著、什麼都沒動
        setattr(content.config, field, right)
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: resumed, content=content) == 0
    assert open_world(path).paused_at() is None and "接著走了" in capsys.readouterr().out


def test_resuming_an_unpaused_clock_does_not_need_the_matching_profile(tmp_path, content, capsys):
    """沒有暫停就沒有什麼要算：照舊說「沒有暫停」，不拿設定不對來嚇人。"""
    path, _ = _paused_before_changshe(tmp_path, content, caught_up=True)
    season_clock.main(["resume", "--db", str(path)], clock=lambda: 1.0e9, content=content)
    capsys.readouterr()
    content.config.season_one = False
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: 1.0e9 + 10, content=content) == 0
    assert "沒有暫停" in capsys.readouterr().out


def test_the_host_resume_line_says_whether_the_pause_was_taken_off_the_season(tmp_path, content, capsys):
    """停不到一個季曆鐘頭的話，什麼都沒扣（B12：跳過的長度照整個曆時往下取整）——那一行不能再說「不算進賽季」；
    停得夠久就說扣了多少。"""
    path, paused = _paused_before_changshe(tmp_path, content, caught_up=True)
    capsys.readouterr()
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: paused + 30, content=content) == 0
    short = capsys.readouterr().out
    assert "不另外扣" in short and "不算進賽季" not in short
    season_clock.main(["pause", "--db", str(path)], clock=lambda: paused + 100)
    capsys.readouterr()
    assert season_clock.main(["resume", "--db", str(path)], clock=lambda: paused + 100 + 3 * 3600, content=content) == 0
    long = capsys.readouterr().out
    assert "不算進賽季" in long and "不另外扣" not in long
