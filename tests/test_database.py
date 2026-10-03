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


def test_an_unknown_schema_version_is_refused(tmp_path):
    import sqlite3

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
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(path)], cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
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
import sys
from pathlib import Path
from tianxia.database import Database
db = Database(Path(sys.argv[1]))
for _ in range(int(sys.argv[2])):
    with db.transaction(timeout=60) as conn:
        value = int(conn.execute("SELECT data FROM seasons WHERE number = 1").fetchone()[0])
        conn.execute("UPDATE seasons SET data = ? WHERE number = 1", (str(value + 1),))
"""


def test_two_programs_counting_at_once_lose_no_updates(tmp_path):
    """伺服器與假人程式同時「讀一份、改、寫回」：寫入交易讓兩邊一個一個來，一次都不少。"""
    path = tmp_path / "t.db"
    db = open_database(path)
    with db.transaction() as conn:
        conn.execute("INSERT INTO seasons (number, data) VALUES (1, '0')")
    procs = [subprocess.Popen([sys.executable, "-c", _COUNTER, str(path), "40"], cwd=ROOT) for _ in range(2)]
    assert [p.wait(timeout=180) for p in procs] == [0, 0]
    with db.snapshot() as conn:
        assert conn.execute("SELECT data FROM seasons WHERE number = 1").fetchone()[0] == "80"
