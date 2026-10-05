"""引擎層壓測（線上架構設計 9.1 第 1 層）：小數字跑通流程，數字本身不驗。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import load_engine  # noqa: E402


def test_small_run_reports_every_number(tmp_path):
    report = load_engine.run(characters=5, actions=40, seed=1, workdir=tmp_path, end_season=True)
    assert len(report["locked"]) == 40 and len(report["total"]) == 40
    assert report["rate"] > 0 and report["db_mb"] > 0 and report["peak_mb"] > 0
    assert report["end_season_seconds"] is not None  # 季末結算量到了（Review Focus 4）
    assert report["stopped_early"] is False


def test_lock_timer_counts_only_outermost_transactions_and_cleans_up(tmp_path):
    """握鎖時間只算最外層那一筆寫入交易（行動鎖）；裡面巢狀的存檔不另外算；離開後把計時拆掉。"""
    import time  # noqa: PLC0415

    from tianxia.database import open_database  # noqa: PLC0415

    db = open_database(tmp_path / "timer.db")
    with load_engine.lock_timer(db) as held:
        with db.transaction():
            with db.transaction():
                pass
        with db.transaction():
            time.sleep(0.05)
        try:
            with db.transaction():
                raise ValueError("動作出錯")
        except ValueError:
            pass
    assert len(held) == 3 and held[1] >= 0.05  # 出錯撤回的那一筆也算握過鎖
    assert "transaction" not in vars(db)


def test_process_memory_peak_reads_a_sane_number():
    """Windows 上讀得到整個程序的記憶體尖峰（其他系統回 None）。"""
    peak = load_engine._peak_working_set_mb()
    if sys.platform == "win32":
        assert 10 < peak < 100_000
    else:
        assert peak is None


def test_season_end_leaves_the_server_answering(tmp_path):
    """收季量到的是真的收完（休季），而且收季之後別的角色照常能做動作、不丟例外（Review Focus 4）。"""
    report = load_engine.run(characters=5, actions=10, seed=1, workdir=tmp_path, end_season=True)
    assert report["end_season_ok"] is True
    assert report["after_end_season_ok"] is True and report["errors"] == {}


def test_ctrl_c_still_reports(tmp_path, monkeypatch):
    """跑到一半中斷：印出到目前為止的結果（Review Focus 3）。"""
    calls = {"n": 0}
    real = load_engine.one_action

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 10:
            raise KeyboardInterrupt
        return real(*args, **kwargs)

    monkeypatch.setattr(load_engine, "one_action", flaky)
    report = load_engine.run(characters=3, actions=50, seed=1, workdir=tmp_path, end_season=False)
    assert report["stopped_early"] is True and len(report["locked"]) == 9
    assert report["end_season_seconds"] is None


def test_an_action_that_blows_up_is_counted_and_the_run_goes_on(tmp_path, monkeypatch):
    """一個動作丟例外：記成錯誤、不算進握鎖時間，其餘的照常跑完（不讓一次例外毀掉一輪長時間的壓測）。"""
    calls = {"n": 0}
    real = load_engine.one_action

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 5:
            raise ValueError("壞掉了")
        return real(*args, **kwargs)

    monkeypatch.setattr(load_engine, "one_action", flaky)
    report = load_engine.run(characters=3, actions=20, seed=1, workdir=tmp_path, end_season=False)
    assert report["errors"] == {"ValueError": 1}
    assert len(report["locked"]) == 19 and report["stopped_early"] is False


def test_poll_requests_between_actions_are_measured_separately(tmp_path):
    """--polls-per-action：每個動作之間穿插畫面請求（/api/main：一次無事的 act 加一次 look），握鎖時間另外記。"""
    report = load_engine.run(characters=3, actions=6, seed=1, workdir=tmp_path, end_season=False, polls_per_action=2)
    assert len(report["locked"]) == 6 and len(report["poll_locked"]) == 12 and len(report["poll_total"]) == 12
    plain = load_engine.run(characters=3, actions=6, seed=1, workdir=tmp_path / "again", end_season=False)
    assert plain["poll_locked"] == []  # 預設不穿插，跟只量動作時一樣


def test_run_leaves_the_process_as_it_found_it(tmp_path):
    """run 動了環境變數、內容設定與伺服器的角色表：跑完都要放回去，不然同一個 pytest 程序裡別的測試會被帶歪。"""
    import server  # noqa: PLC0415

    before = (os.environ.get("TIANXIA_DB"), server.CONTENT.config.auto_open_first_season,
              list(server.CONTENT.config.admins), server.CONTENT.config.ollama_url)
    load_engine.run(characters=3, actions=5, seed=1, workdir=tmp_path, end_season=True)
    after = (os.environ.get("TIANXIA_DB"), server.CONTENT.config.auto_open_first_season,
             list(server.CONTENT.config.admins), server.CONTENT.config.ollama_url)
    assert after == before
    assert not any(key.startswith("壓測") for key in server.GAMES)


def test_the_engine_run_never_asks_a_model(tmp_path, monkeypatch):
    """引擎層不叫任何模型：連線一碰就失敗的測試替身，跑完也不會被碰到。"""
    from tianxia.ollama_client import OllamaClient  # noqa: PLC0415

    def boom(self, *args, **kwargs):
        raise AssertionError("引擎層壓測不該叫模型")

    monkeypatch.setattr(OllamaClient, "chat_text", boom)
    monkeypatch.setattr(OllamaClient, "chat_structured", boom)
    report = load_engine.run(characters=4, actions=60, seed=2, workdir=tmp_path, end_season=False)
    assert report["errors"] == {}
