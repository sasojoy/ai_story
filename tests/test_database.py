import gc
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tianxia import accounts, database
from tianxia.accounts import AccountStore
from tianxia.characters import open_characters
from tianxia.database import SCHEMA_VERSION, Database, open_database
from tianxia.sqlite_world import open_world
from tianxia.state import new_game_state

ROOT = Path(__file__).resolve().parent.parent

V1_TABLES = {
    "world", "seasons", "rumors", "rumor_heard", "chronicle", "skills", "recipes", "faction_rolls",
    "battles", "battle_rounds", "characters", "character_backups", "accounts", "logins",
}
V2_TABLES = {"skill_aliases", "insights", "insight_recipes", "masters"}
TABLES = V1_TABLES | V2_TABLES


def _count(db: Database, table: str) -> int:
    with db.snapshot() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_a_new_file_gets_every_table(tmp_path):
    db = open_database(tmp_path / "t.db")
    with db.snapshot() as conn:
        names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert TABLES <= names


def _make_version_one_file(path):
    """照第 1 版的結構（SCHEMA_V1）建一個檔，user_version 設 1：就是目前試玩伺服器上那一份的樣子。"""
    conn = sqlite3.connect(path)
    for statement in database.SCHEMA_V1:
        conn.execute(statement)
    conn.execute("PRAGMA user_version = 1")
    return conn


def _dump(path, tables):
    """每張表的全部內容（照 rowid 排），拿來比升級前後有沒有東西不見或被改。"""
    conn = sqlite3.connect(path)
    try:
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall() for t in sorted(tables)}
    finally:
        conn.close()


def test_the_version_one_schema_is_exactly_the_old_tables(tmp_path):
    """SCHEMA_V1 是第 1 版的樣子，不能再改：改了，上面「第 1 版的檔」的測試就不是在測真的舊檔。"""
    conn = _make_version_one_file(tmp_path / "v1.db")
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert names == V1_TABLES


def test_a_version_one_file_is_upgraded_in_place(tmp_path):
    """第 1 版的檔（試玩伺服器上那一份）打開時就地加上新表，舊資料不動。"""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    for statement in database.SCHEMA_V1:
        conn.execute(statement)
    conn.execute("INSERT INTO world (id, data) VALUES (1, '{}')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    db = Database(path)
    with db.snapshot() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        names = {row["name"] for row in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert c.execute("SELECT data FROM world WHERE id = 1").fetchone()["data"] == "{}"
    assert {"skill_aliases", "insights", "insight_recipes", "masters"} <= names
    db.close()


def test_upgrading_a_populated_version_one_file_loses_nothing(tmp_path, content):
    """試玩伺服器的檔是第 1 版、裡面有帳號、角色、江湖史：換版時就地升到第 2 版，
    每張舊表的每一列都原封不動，帳號還登入得進去、角色還讀得回來、江湖史還看得到，新表在而且是空的。"""
    path = tmp_path / "live.db"
    salt = bytes(range(16))
    state = new_game_state(content, "沈浪")
    conn = _make_version_one_file(path)
    conn.execute("INSERT INTO accounts (id, character, character_key, created) VALUES (1, '沈浪', '沈浪', 100.0)")
    conn.execute(
        "INSERT INTO logins (provider, subject, account_id, display, salt, hash) VALUES ('password', 'shenlang', 1, "
        "'ShenLang', ?, ?)",
        (salt.hex(), accounts.hash_password("sesame88", salt)),
    )
    conn.execute("INSERT INTO accounts (id, created) VALUES (2, 200.0)")  # 註冊了、還沒建角色
    conn.execute(
        "INSERT INTO logins (provider, subject, account_id, display, salt, hash) VALUES ('password', 'nobody', 2, "
        "'NoBody', ?, ?)",
        (salt.hex(), accounts.hash_password("sesame99", salt)),
    )
    conn.execute(
        "INSERT INTO characters (key, name, is_bot, faction, data) VALUES ('沈浪', '沈浪', 0, NULL, ?)",
        (state.model_dump_json(),),
    )
    conn.execute("INSERT INTO characters (key, name, is_bot, faction, data) VALUES ('壞檔', '壞檔', 0, NULL, '{不是 json')")
    conn.execute("INSERT INTO character_backups (key, data) VALUES ('舊的', '{}')")
    conn.execute("INSERT INTO world (id, data) VALUES (1, '{\"season_number\": 2, \"tianji\": 1}')")
    conn.execute("INSERT INTO seasons (number, data) VALUES (2, '{}')")
    conn.executemany(
        "INSERT INTO chronicle (season, time, location, text) VALUES (?, ?, ?, ?)",
        [(1, 10.0, "洛陽", "第一季：黃巾起事。"), (1, 20.0, None, "第一季：天下大亂。"), (2, 5.0, "許昌", "第二季開張。")],
    )
    conn.execute(
        "INSERT INTO rumors (season, time, layer, faction, region, location, character, named, text) "
        "VALUES (2, 6.0, 'local', NULL, NULL, '許昌', '沈浪', 1, '許昌有人練功。')"
    )
    conn.execute("INSERT INTO rumor_heard (character, rumor_id) VALUES ('沈浪', 1)")
    conn.execute("INSERT INTO skills (season, name, creator, data) VALUES (2, '旋風腿', '沈浪', '{}')")
    conn.execute("INSERT INTO recipes (season, key, skill_name, creator) VALUES (2, 'k', '旋風腿', '沈浪')")
    conn.execute("INSERT INTO faction_rolls (season, character, faction) VALUES (2, '沈浪', 'huangjin')")
    conn.commit()
    conn.close()
    before = _dump(path, V1_TABLES)

    db = open_database(path)  # 升級就在開檔的時候

    assert _dump(path, V1_TABLES) == before  # 舊表原封不動（含 rowid 順序、流水號）
    with db.snapshot() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 2
        names = {row["name"] for row in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert names == TABLES
    assert all(_count(db, table) == 0 for table in V2_TABLES)
    # 真正的存取層讀得回來
    store = AccountStore(db)
    assert store.authenticate("shenlang", "sesame88").character == "沈浪"
    assert store.owner_of("沈浪") == "shenlang"
    assert store.get("nobody").character is None
    characters = open_characters(path)
    assert characters.names() == {"沈浪", "壞檔"}
    assert characters.load("沈浪").model_dump_json() == state.model_dump_json()  # world 只在記憶體，不進存檔
    assert [e.text for e in open_world(path).get_season().chronicle] == ["第二季開張。"]
    assert [e.text for e in open_world(path).chronicle_before(2)[0][1]] == ["第一季：黃巾起事。", "第一季：天下大亂。"]
    assert open_world(path).read().tianji == 1
    # 升完的檔再打開不會再升一次、也不會掉資料
    database.close_all()
    again = open_database(path)
    assert _dump(path, V1_TABLES) == before
    with again.snapshot() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_a_migrated_file_takes_writes_to_the_new_tables(tmp_path):
    """升級出來的檔，新表真的能用（跟新檔一樣）。"""
    path = tmp_path / "old.db"
    conn = _make_version_one_file(path)
    conn.commit()
    conn.close()
    store = open_world(path)
    assert store.claim_master("旋風腿", "甲") is True
    assert store.master_of("旋風腿") == "甲"


def test_a_failed_migration_leaves_the_old_file_as_it_was(tmp_path, monkeypatch):
    """升級是一筆交易：中途出錯整個撤回，檔還是第 1 版、沒有半張新表，下次還能再試。"""
    path = tmp_path / "old.db"
    conn = _make_version_one_file(path)
    conn.execute("INSERT INTO world (id, data) VALUES (1, '{}')")
    conn.commit()
    conn.close()
    with monkeypatch.context() as patched:
        patched.setitem(database.MIGRATIONS, 1, database.SCHEMA_V2_TABLES[:2] + ("CREATE TABLE oops (",))
        with pytest.raises(sqlite3.OperationalError):
            Database(path)
    conn = sqlite3.connect(path)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert names == V1_TABLES and version == 1
    assert Database(path).path == path  # 修好之後再開，照樣升得上去


def test_a_version_with_no_migration_path_is_refused(tmp_path, monkeypatch):
    """比目前版本舊、卻沒有遷移步驟接得上的檔不亂猜：直接擋下。"""
    path = tmp_path / "old.db"
    conn = _make_version_one_file(path)
    conn.commit()
    conn.close()
    monkeypatch.delitem(database.MIGRATIONS, 1)
    with pytest.raises(RuntimeError, match="第 1 版"):
        Database(path)


def test_every_connection_syncs_to_disk_on_each_commit(tmp_path):
    """設計 3.1：停電或當機最多少掉當下那一個動作。WAL 搭 NORMAL 可能少掉最後幾筆已經 COMMIT 的，要用 FULL（2）。"""
    db = open_database(tmp_path / "t.db")
    with db.snapshot() as conn:
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


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
    """網頁伺服器的工作執行緒會來來去去：執行緒結束時，它那條連線也要跟著關掉。"""
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


def test_a_connection_whose_setup_fails_is_closed(tmp_path, monkeypatch):
    """連上了、但設定用的 PRAGMA 出錯：剛開的連線要先關掉再把錯丟出去，不能留著沒人管。"""
    real_connect = sqlite3.connect
    made = []

    class SetupFails:
        row_factory = None

        def __init__(self, real):
            self.real = real
            self.closed = False

        def execute(self, sql, *args):
            if "foreign_keys" in sql:
                raise sqlite3.OperationalError("設定失敗")
            return self.real.execute(sql, *args)

        def close(self):
            self.closed = True
            self.real.close()

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: made.append(SetupFails(real_connect(*a, **k))) or made[-1])
    with pytest.raises(sqlite3.OperationalError, match="設定失敗"):
        Database(tmp_path / "t.db")
    assert len(made) == 1
    assert made[0].closed


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
