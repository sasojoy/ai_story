import gc
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tianxia import database
from tianxia.database import SCHEMA_VERSION, Database, open_database

ROOT = Path(__file__).resolve().parent.parent

TABLES = {
    "world", "seasons", "rumors", "rumor_heard", "chronicle", "skills", "recipes", "faction_rolls",
    "battles", "battle_rounds", "characters", "character_backups", "accounts", "logins",
}


def _count(db: Database, table: str) -> int:
    with db.snapshot() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_a_new_file_gets_every_table(tmp_path):
    db = open_database(tmp_path / "t.db")
    with db.snapshot() as conn:
        names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert TABLES <= names


def test_one_file_is_one_database_in_a_program(tmp_path):
    assert open_database(tmp_path / "t.db") is open_database(tmp_path / "t.db")


def test_the_environment_variable_picks_the_default_file(tmp_path, monkeypatch):
    monkeypatch.setenv(database.ENV_VAR, str(tmp_path / "live.db"))
    assert open_database().path == (tmp_path / "live.db").resolve()


def test_a_transaction_commits_on_success_and_rolls_back_on_error(tmp_path):
    db = open_database(tmp_path / "t.db")
    with db.transaction() as conn:
        conn.execute("INSERT INTO seasons (number, data) VALUES (1, '{}')")
    with pytest.raises(ZeroDivisionError):
        with db.transaction() as conn:
            conn.execute("INSERT INTO seasons (number, data) VALUES (2, '{}')")
            1 / 0
    assert _count(db, "seasons") == 1


def test_a_nested_transaction_joins_the_outer_one(tmp_path):
    db = open_database(tmp_path / "t.db")
    with pytest.raises(ZeroDivisionError):
        with db.transaction():
            with db.transaction() as conn:
                conn.execute("INSERT INTO seasons (number, data) VALUES (1, '{}')")
            1 / 0  # 外層出錯：裡面那一筆寫入也一起撤回
    assert _count(db, "seasons") == 0


def test_a_second_writer_times_out_while_the_first_holds_the_transaction(tmp_path):
    db = open_database(tmp_path / "t.db")
    errors = []

    def other():
        try:
            with db.transaction(timeout=0.2):
                pass
        except TimeoutError as error:
            errors.append(error)

    with db.transaction():
        thread = threading.Thread(target=other)
        thread.start()
        thread.join(10)
    assert len(errors) == 1


def test_a_reader_does_not_wait_for_a_writer(tmp_path):
    db = open_database(tmp_path / "t.db")
    writing, done = threading.Event(), threading.Event()

    def writer():
        with db.transaction() as conn:
            conn.execute("INSERT INTO seasons (number, data) VALUES (1, '{}')")
            writing.set()
            done.wait(10)

    thread = threading.Thread(target=writer)
    thread.start()
    assert writing.wait(10)
    assert _count(db, "seasons") == 0  # 還沒 COMMIT 的寫入看不到，而且不用等
    done.set()
    thread.join(10)
    assert _count(db, "seasons") == 1


def test_writing_inside_a_snapshot_is_refused(tmp_path):
    db = open_database(tmp_path / "t.db")
    with db.snapshot():
        assert not db.writing()
        with pytest.raises(RuntimeError):
            with db.transaction():
                pass


def test_writing_tells_whether_this_thread_holds_a_transaction(tmp_path):
    db = open_database(tmp_path / "t.db")
    assert not db.writing()
    with db.transaction():
        assert db.writing()
    assert not db.writing()


def test_writing_does_not_open_a_connection(tmp_path, monkeypatch):
    db = open_database(tmp_path / "t.db")
    opened = []
    real_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: opened.append(args) or real_connect(*args, **kwargs))
    seen = []
    thread = threading.Thread(target=lambda: seen.append(db.writing()))  # 這個執行緒從沒碰過資料庫
    thread.start()
    thread.join(10)
    assert seen == [False]
    assert opened == []


def test_a_failed_commit_does_not_leave_the_write_lock_behind(tmp_path):
    db = open_database(tmp_path / "t.db")
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys = ON")
            # 外鍵指到不存在的戰鬥：延後到 COMMIT 才檢查，COMMIT 會失敗，而且失敗後交易還開著
            conn.execute("INSERT INTO battle_rounds (battle_id, data) VALUES (999, '{}')")
    assert not db.writing()
    errors = []

    def other():
        try:
            with db.transaction(timeout=0.5):
                pass
        except TimeoutError as error:
            errors.append(error)

    thread = threading.Thread(target=other)
    thread.start()
    thread.join(10)
    assert errors == []  # 別的執行緒拿得到寫入權
    with db.transaction(timeout=0.5) as conn:  # 同一個執行緒也能再開交易
        conn.execute("INSERT INTO seasons (number, data) VALUES (1, '{}')")
    assert _count(db, "battle_rounds") == 0  # 失敗的那一筆整筆撤掉
    assert _count(db, "seasons") == 1


def test_the_bodys_own_error_is_not_masked_when_sqlite_already_ended_the_transaction(tmp_path):
    """磁碟滿了、I/O 出錯時 SQLite 會自己撤掉交易，這時再下 ROLLBACK 會出另一個錯把真正的錯蓋掉。"""
    db = open_database(tmp_path / "t.db")
    with pytest.raises(ValueError):
        with db.transaction() as conn:
            conn.execute("INSERT INTO seasons (number, data) VALUES (1, '{}')")
            conn.execute("ROLLBACK")  # 模擬 SQLite 已經把交易結束了
            raise ValueError("本來的錯")
    assert _count(db, "seasons") == 0
    with db.transaction(timeout=0.5):  # 這條連線之後還能用
        pass


def test_a_snapshot_whose_transaction_was_already_ended_closes_quietly(tmp_path):
    db = open_database(tmp_path / "t.db")
    with db.snapshot() as conn:
        conn.execute("ROLLBACK")
    with db.transaction(timeout=0.5):
        pass


def test_a_snapshot_never_writes(tmp_path):
    """快照是唯讀的：離開時用 ROLLBACK 收掉，在裡面誤寫的東西不會留下來。"""
    db = open_database(tmp_path / "t.db")
    with db.snapshot() as conn:
        conn.execute("INSERT INTO seasons (number, data) VALUES (1, '{}')")
    assert _count(db, "seasons") == 0


def test_a_thread_that_ends_gives_its_connection_back(tmp_path):
    """Gradio 的工作執行緒會來來去去：執行緒結束時，它那條連線也要跟著關掉。"""
    db = open_database(tmp_path / "t.db")
    conns = []

    def short_lived():
        with db.snapshot() as conn:
            conns.append(conn)
            conn.execute("SELECT 1").fetchone()

    thread = threading.Thread(target=short_lived)
    thread.start()
    thread.join(10)
    gc.collect()
    with pytest.raises(sqlite3.ProgrammingError):
        conns[0].execute("SELECT 1")
    assert _count(db, "seasons") == 0  # 主執行緒的連線不受影響


def test_closing_the_database_closes_every_thread_connection(tmp_path):
    db = open_database(tmp_path / "t.db")
    ready, release = threading.Event(), threading.Event()
    conns = []

    def alive():
        with db.snapshot() as conn:
            conns.append(conn)
        ready.set()
        release.wait(10)

    thread = threading.Thread(target=alive)
    thread.start()
    assert ready.wait(10)
    db.close()
    release.set()
    thread.join(10)
    with pytest.raises(sqlite3.ProgrammingError):
        conns[0].execute("SELECT 1")
    db.close()  # 關兩次也沒事


def test_an_unknown_schema_version_is_refused(tmp_path):
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    with pytest.raises(RuntimeError, match="第 99 版"):
        Database(path)


_HOLDER = """
import os, sys
from pathlib import Path
from tianxia.database import Database
db = Database(Path(sys.argv[1]))
with db.transaction() as conn:
    conn.execute("INSERT INTO seasons (number, data) VALUES (9, 'half')")
    print("holding", flush=True)
    sys.stdin.readline()
    os._exit(1)
"""


def test_a_program_killed_mid_transaction_leaves_nothing_behind(tmp_path):
    """程式被強制結束（關掉終端機、taskkill /F）時沒 COMMIT 的交易由 SQLite 撤掉，鎖也跟著放掉。"""
    path = tmp_path / "t.db"
    db = open_database(path)
    with subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(path)], cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    ) as proc:  # 離開時把兩條管子也關掉
        try:
            assert proc.stdout.readline().strip() == "holding"
            with pytest.raises(TimeoutError):
                with db.transaction(timeout=0.2):
                    pass
        finally:
            proc.kill()
            proc.wait(timeout=60)
    with db.transaction(timeout=5) as conn:
        assert conn.execute("SELECT COUNT(*) FROM seasons WHERE number = 9").fetchone()[0] == 0


_COUNTER = """
import sys, time
from pathlib import Path
from tianxia.database import Database
db = Database(Path(sys.argv[1]))
go = Path(sys.argv[3])
print("ready", flush=True)
deadline = time.monotonic() + 120
while not go.exists():  # 等起跑訊號：兩邊同時開跑，不會一邊跑完了另一邊才啟動
    if time.monotonic() > deadline:
        sys.exit(3)
    time.sleep(0.0005)
for _ in range(int(sys.argv[2])):
    with db.transaction(timeout=60) as conn:
        value = int(conn.execute("SELECT data FROM seasons WHERE number = 1").fetchone()[0])
        time.sleep(0.001)  # 讀與寫之間留一段空檔：沒有寫入權擋著的話，另一邊一定會插進來
        conn.execute("UPDATE seasons SET data = ? WHERE number = 1", (str(value + 1),))
"""


def test_two_programs_counting_at_once_lose_no_updates(tmp_path):
    """伺服器與假人程式同時「讀一份、改、寫回」：寫入交易讓兩邊一個一個來，一次都不少。"""
    path = tmp_path / "t.db"
    go = tmp_path / "go"
    db = open_database(path)
    with db.transaction() as conn:
        conn.execute("INSERT INTO seasons (number, data) VALUES (1, '0')")
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _COUNTER, str(path), "200", str(go)], cwd=ROOT,
            stdout=subprocess.PIPE, text=True,
        )
        for _ in range(2)
    ]
    try:
        for proc in procs:
            assert proc.stdout.readline().strip() == "ready"
        go.write_text("go")  # 兩邊都就緒了才一起開跑
        assert [proc.wait(timeout=180) for proc in procs] == [0, 0]
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=60)
            proc.stdout.close()
    with db.snapshot() as conn:
        assert conn.execute("SELECT data FROM seasons WHERE number = 1").fetchone()[0] == "400"
