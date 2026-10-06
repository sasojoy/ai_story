"""引擎層壓測（線上架構設計 9.1 第 1 層）：小數字跑通流程，數字本身不驗。"""
import contextlib
import os
import sys
import tracemalloc
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import load_engine  # noqa: E402


def test_small_run_reports_every_number(tmp_path):
    report = load_engine.run(characters=5, actions=40, seed=1, workdir=tmp_path, end_season=True)
    assert len(report["locked"]) == 40 and len(report["total"]) == 40
    assert report["rate"] > 0 and report["db_mb"] > 0 and report["peak_mb"] > 0
    assert report["end_season_seconds"] is not None  # 季末結算量到了（Review Focus 4）
    assert report["stopped_early"] is False
    # 壓測的角色是真人帳號的路徑：不碰 PlayerState.bot，也就不會有任何一個角色被存成假人
    from tianxia.characters import open_characters  # noqa: PLC0415

    store = open_characters(tmp_path / "load.db")
    assert len(store.names()) == 5 and store.all(bots_only=True) == []


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


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeDb:
    """假的資料庫：最外層的交易進來要先等 begin_wait 秒（BEGIN IMMEDIATE 等別人放掉寫入權），離開時花 commit 秒
    （COMMIT 寫進磁碟）；巢狀的交易不等也不 COMMIT。時間走假時鐘，所以測試不靠真的睡覺、也不會因為機器忙而抖動。"""

    def __init__(self, clock, begin_wait: float, commit: float):
        self.clock, self.begin_wait, self.commit, self.depth = clock, begin_wait, commit, 0

    def writing(self) -> bool:
        return self.depth > 0

    @contextlib.contextmanager
    def transaction(self, timeout=None):
        if self.depth == 0:
            self.clock.advance(self.begin_wait)
        self.depth += 1
        try:
            yield "conn"
        finally:
            self.depth -= 1
            if self.depth == 0:
                self.clock.advance(self.commit)


def test_lock_hold_runs_from_begin_returning_to_commit_done():
    """握鎖時間的定義釘在兩頭：從 BEGIN IMMEDIATE 回來（拿到寫入權）算起、到 COMMIT 做完為止。
    等寫入權的 0.7 秒不算（算進去＝把別人佔著鎖的時間記成自己的）；COMMIT 的 0.2 秒要算（寫進磁碟在鎖裡）。"""
    clock = FakeClock()
    db = FakeDb(clock, begin_wait=0.7, commit=0.2)
    with load_engine.lock_timer(db, clock=clock) as held:
        with db.transaction():
            clock.advance(0.1)  # 動作本身
            with db.transaction():  # 裡面巢狀的存檔：不另外算、也不多等
                clock.advance(0.05)
    assert held == [pytest.approx(0.35)]


def test_lock_hold_does_not_count_time_spent_waiting_for_the_write_lock(tmp_path):
    """同一件事用真的資料庫與真的競爭再驗一次：另一個執行緒佔著寫入權 0.4 秒，這邊的交易等到了才開始算，
    所以記下來的握鎖時間只有交易本身那一點點。"""
    import threading  # noqa: PLC0415
    import time  # noqa: PLC0415

    from tianxia.database import open_database  # noqa: PLC0415

    db = open_database(tmp_path / "contend.db")
    holding, release = threading.Event(), threading.Event()

    def hold_the_lock():
        with db.transaction():
            holding.set()
            release.wait(5)

    thread = threading.Thread(target=hold_the_lock)
    thread.start()
    try:
        assert holding.wait(5)
        threading.Timer(0.4, release.set).start()
        started = time.monotonic()
        with load_engine.lock_timer(db) as held:
            with db.transaction():
                pass
        waited = time.monotonic() - started
    finally:
        release.set()
        thread.join(5)
    assert waited >= 0.3  # 真的等了
    assert len(held) == 1 and held[0] < 0.15


def test_poll_takes_two_locks_and_reports_both(tmp_path):
    """/api/main ＝ 一次無事的 act ＋ 一次 look，各拿一次行動鎖；回報的是兩次握鎖加起來的秒數。"""
    import time  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    from tianxia.database import open_database  # noqa: PLC0415

    db = open_database(tmp_path / "poll.db")
    calls = []

    def locked_for_a_while(name):
        with db.transaction():
            calls.append(name)
            time.sleep(0.1)

    server = SimpleNamespace(
        act=lambda game, action: (locked_for_a_while("act"), action(game)),
        look=lambda game, view: (locked_for_a_while("look"), view(game)),
        main_view=lambda game: {},
    )
    held = load_engine.one_poll(server, SimpleNamespace(world=SimpleNamespace(db=db)))
    assert calls == ["act", "look"]
    assert held >= 0.19  # 兩次各 0.1 秒都算進去（只算一次的話是 0.1）


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
    assert not tracemalloc.is_tracing()  # 中斷也要把 tracemalloc 關掉：它會讓之後的 Python 慢上四成


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
    # 只留一個類型的次數，兩萬個動作之後看不出是什麼壞了：每種例外留下第一次的完整追蹤
    assert "ValueError: 壞掉了" in report["error_samples"]["ValueError"]
    assert "Traceback" in report["error_samples"]["ValueError"]


def test_a_blown_up_poll_is_counted_too(tmp_path, monkeypatch):
    """畫面請求出錯也一樣記成錯誤、照常跑完（兩個地方都有 try，各自釘住）。"""
    real = load_engine.one_poll
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyError("壞了的畫面")
        return real(*args, **kwargs)

    monkeypatch.setattr(load_engine, "one_poll", flaky)
    report = load_engine.run(characters=3, actions=5, seed=1, workdir=tmp_path, end_season=False, polls_per_action=2)
    assert report["errors"] == {"KeyError": 1} and len(report["poll_locked"]) == 9
    assert "壞了的畫面" in report["error_samples"]["KeyError"]


@pytest.mark.parametrize("name", ["saves", ".local", "tianxia-play"])
def test_workdir_cannot_be_where_real_game_data_lives(tmp_path, name):
    """--workdir 指到 saves/、.local/、試玩資料夾底下會在那裡留下壓測的資料庫：run 一開頭就拒絕，什麼都不建、不動。"""
    target = tmp_path / name / "load"
    before = os.environ.get("TIANXIA_DB")
    with pytest.raises(ValueError):
        load_engine.run(characters=2, actions=2, seed=1, workdir=target, end_season=False)
    assert not target.exists() and os.environ.get("TIANXIA_DB") == before


def test_workdir_cannot_hold_a_real_game_database(tmp_path):
    """資料夾裡已經有 tianxia.db（正式或試玩的資料庫）也不行，不管資料夾叫什麼名字。"""
    (tmp_path / "tianxia.db").write_bytes(b"")
    with pytest.raises(ValueError):
        load_engine.run(characters=2, actions=2, seed=1, workdir=tmp_path, end_season=False)


def test_a_run_needs_at_least_one_character(tmp_path):
    """沒有角色就沒有人可以做動作：講清楚，不是在 rng.choice 丟一個看不懂的 IndexError。"""
    with pytest.raises(ValueError, match="角色"):
        load_engine.run(characters=0, actions=5, seed=1, workdir=tmp_path, end_season=False)
    assert load_engine.main(["--characters", "0", "--workdir", str(tmp_path)]) == 2


def test_the_printed_summary_says_what_its_numbers_include(tmp_path, capsys):
    """資料庫大小含沒併回去的 WAL；穿插畫面請求時，每秒動作數是連同那些請求一起算時間的：標在輸出上，免得被當成純動作的上限。"""
    assert load_engine.main([
        "--characters", "3", "--actions", "4", "--polls-per-action", "1", "--no-tracemalloc", "--workdir", str(tmp_path),
    ]) == 0
    out = capsys.readouterr().out
    assert "WAL" in out and "穿插的畫面請求" in out and "握鎖時間" in out
    capsys.readouterr()
    assert load_engine.main(["--characters", "3", "--actions", "4", "--workdir", str(tmp_path / "plain")]) == 0
    assert "穿插的畫面請求" not in capsys.readouterr().out


def test_poll_requests_between_actions_are_measured_separately(tmp_path):
    """--polls-per-action：每個動作之間穿插畫面請求（/api/main：一次無事的 act 加一次 look），握鎖時間另外記。"""
    report = load_engine.run(characters=3, actions=6, seed=1, workdir=tmp_path, end_season=False, polls_per_action=2)
    assert len(report["locked"]) == 6 and len(report["poll_locked"]) == 12 and len(report["poll_total"]) == 12
    plain = load_engine.run(characters=3, actions=6, seed=1, workdir=tmp_path / "again", end_season=False)
    assert plain["poll_locked"] == []  # 預設不穿插，跟只量動作時一樣


@pytest.mark.parametrize("profile", [None, "weekend"])
def test_run_puts_back_everything_it_touched(tmp_path, monkeypatch, profile):
    """run 動了環境變數（TIANXIA_DB、TIANXIA_PROFILE）、內容設定的三個欄位與伺服器的角色表：跑完都要放回去，
    不然同一個 pytest 程序裡別的測試會被帶歪。「放回去」的對象是這個測試自己先設好的哨兵值，不是從目前狀態抄來的
    『之前』：前面的測試就算已經把狀態弄髒了，刪掉任何一行還原都一定會紅（跟測試的執行順序無關）。"""
    import server  # noqa: PLC0415

    config = server.CONTENT.config
    sentinel_db = str(tmp_path / "sentinel.db")
    monkeypatch.setattr(config, "auto_open_first_season", False)
    monkeypatch.setattr(config, "admins", ["甲"])
    monkeypatch.setattr(config, "ollama_url", "http://sentinel.invalid:9")
    monkeypatch.setenv("TIANXIA_DB", sentinel_db)
    if profile is None:
        monkeypatch.delenv("TIANXIA_PROFILE", raising=False)
    else:
        monkeypatch.setenv("TIANXIA_PROFILE", profile)

    load_engine.run(characters=3, actions=5, seed=1, workdir=tmp_path, end_season=True)

    assert config.auto_open_first_season is False
    assert config.admins == ["甲"]
    assert config.ollama_url == "http://sentinel.invalid:9"
    assert os.environ.get("TIANXIA_DB") == sentinel_db
    assert os.environ.get("TIANXIA_PROFILE") == profile
    assert not any(key.startswith("壓測") for key in server.GAMES)
    assert not tracemalloc.is_tracing()  # tracemalloc 會讓之後的 Python 慢上四成，跑完一定要關


def test_the_dead_model_address_is_nobodys_port():
    """上一條拿 NO_MODEL_URL 當標準答案，所以常數本身另外釘：只能是這台電腦上的埠，而且不是真的 Ollama（11434）、
    別人用的 11999、試玩伺服器（7861）與壓測假模型的 11990～11998。"""
    from urllib.parse import urlparse  # noqa: PLC0415

    url = urlparse(load_engine.NO_MODEL_URL)
    assert url.hostname == "127.0.0.1"
    assert url.port not in (11434, 11999, 7861) and not 11990 <= url.port <= 11998


def test_the_engine_run_never_asks_a_model(tmp_path, monkeypatch):
    """引擎層不叫任何模型，兩道防線各自釘住（拿掉任何一道都會紅）：每個角色的 Game 拿掉 client、內容設定的 ollama_url
    指到沒人聽的埠。引擎自己會吞掉鎖內模型呼叫的失敗、退回固定文字，所以「叫了也不出錯」不能當證據；這裡改成：
    1. 每個動作與畫面請求開始前，記下這個 Game 的 client 與目前的 ollama_url，要是 None 與 NO_MODEL_URL；
    2. 每次再走一次引擎在鎖內叫模型的入口（Game._quick_client）：有 client 就硬叫一次，叫了會被記下來（模型的方法與
       HTTP 都換成只記錄的替身，不會真的連線）。沒有 client 的 Game 這個入口回 None，什麼也不會發生。"""
    import requests  # noqa: PLC0415
    import server  # noqa: PLC0415
    from tianxia.ollama_client import OllamaClient  # noqa: PLC0415

    asked: list[tuple[str, str]] = []

    def recorder(kind):
        def record(self, *args, **kwargs):
            asked.append((kind, self.base_url))
            return "" if kind == "chat_text" else {}
        return record

    def no_network(url, *args, **kwargs):
        asked.append(("http", url))
        raise requests.ConnectionError("測試不連線")

    monkeypatch.setattr(OllamaClient, "chat_text", recorder("chat_text"))
    monkeypatch.setattr(OllamaClient, "chat_structured", recorder("chat_structured"))
    monkeypatch.setattr(requests, "post", no_network)
    monkeypatch.setattr(requests, "get", no_network)

    seen: list[tuple[object, str]] = []

    def look_for_a_model(game):
        seen.append((game.client, server.CONTENT.config.ollama_url))
        quick = game._quick_client()
        if quick is not None:  # 有 client 才會到這裡：硬叫一次，讓「有 client」變成看得見的模型呼叫
            quick.chat_text([{"role": "user", "content": "你好"}])

    real_action, real_poll = load_engine.one_action, load_engine.one_poll

    def watched_action(srv, game, rng):
        look_for_a_model(game)
        return real_action(srv, game, rng)

    def watched_poll(srv, game):
        look_for_a_model(game)
        return real_poll(srv, game)

    monkeypatch.setattr(load_engine, "one_action", watched_action)
    monkeypatch.setattr(load_engine, "one_poll", watched_poll)
    report = load_engine.run(
        characters=4, actions=30, seed=2, workdir=tmp_path, end_season=True, polls_per_action=1)

    assert len(seen) == 30 + 30 + load_engine.AFTER_END_ACTIONS  # 動作、畫面請求、收季之後的動作都看過了
    assert all(client is None for client, _ in seen)  # Game.client 是 None
    assert {url for _, url in seen} == {load_engine.NO_MODEL_URL}  # ollama_url 是沒人聽的埠
    assert asked == []  # 從頭到尾沒有模型呼叫、沒有 HTTP
    assert report["errors"] == {}
