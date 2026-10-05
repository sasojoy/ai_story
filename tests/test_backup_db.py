"""資料庫備份與還原的腳本（線上架構設計 8.5）：線上備份、驗證、保留規則、還原。"""
import datetime as dt
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import backup_db  # noqa: E402

from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.database import SCHEMA_VERSION, open_database  # noqa: E402
from tianxia.state import new_game_state  # noqa: E402

NOW = dt.datetime(2026, 10, 6, 5, 0, 0)
FIXTURE = ROOT / "tests" / "fixtures" / "content"


def _live_db(tmp_path: Path, names=("甲", "乙")) -> Path:
    """一份真的遊戲資料庫（照現在的結構建好，存了幾個角色），模擬試玩伺服器的那個檔。"""
    path = tmp_path / "live" / "tianxia.db"
    db = open_database(path)
    content = load_content(FIXTURE)
    store = CharacterStore(db)
    for name in names:
        store.save(new_game_state(content, name))
    return path


def test_backup_makes_a_verified_self_contained_copy(tmp_path):
    src = _live_db(tmp_path)
    out = backup_db.backup(src, tmp_path / "cloud", tag="manual", now=NOW)
    assert out == tmp_path / "cloud" / "tianxia-manual-20261006-050000.db"
    assert not (tmp_path / "cloud" / "tianxia-manual-20261006-050000.db-wal").exists()
    conn = sqlite3.connect(out)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"  # 自足的單一檔，雲端同步不會只到一半
    finally:
        conn.close()
    report = backup_db.verify(out)
    assert report["version"] == SCHEMA_VERSION and report["characters"] == 2
    assert not list((tmp_path / "cloud").glob("*.partial"))


def test_backup_while_someone_keeps_writing(tmp_path):
    """伺服器開著、一直在寫：線上備份照樣拿到一份一致、驗得過的檔（Review Focus 1）。"""
    src = _live_db(tmp_path)
    stop = threading.Event()

    def writer():
        conn = sqlite3.connect(src, timeout=5)
        conn.execute("PRAGMA journal_mode = WAL")
        i = 0
        while not stop.is_set():
            conn.execute("INSERT INTO chronicle (season, time, location, text) VALUES (1, ?, NULL, ?)", (i, f"第{i}筆"))
            conn.commit()
            i += 1
        conn.close()

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        out = backup_db.backup(src, tmp_path / "cloud", tag="manual", now=NOW)
    finally:
        stop.set()
        thread.join()
    assert backup_db.verify(out)["characters"] == 2


def test_backup_of_a_big_database_finishes_while_writes_never_stop(tmp_path):
    """資料庫長大（好幾步才複製得完）、寫入又一直不停：一步一步複製的線上備份每次被寫入打斷就從頭來，
    永遠做不完（量過：41MB、每秒三百多筆寫入，十二秒內沒做完）。要一口氣讀完同一個時間點的快照，不被寫入打斷。"""
    src = _live_db(tmp_path)
    conn = sqlite3.connect(src)
    conn.executemany(
        "INSERT INTO chronicle (season, time, location, text) VALUES (1, ?, NULL, ?)",
        [(i, "字" * 1000) for i in range(20000)],  # 約 20MB，比一步複製的量大很多
    )
    conn.commit()
    conn.close()
    started = time.monotonic()
    deadline = started + 10  # 備份做不完時，寫入自己在十秒後停，測試才不會永遠掛著
    stop = threading.Event()

    def writer():
        w = sqlite3.connect(src, timeout=5)
        w.execute("PRAGMA journal_mode = WAL")
        i = 0
        while not stop.is_set() and time.monotonic() < deadline:
            w.execute("INSERT INTO chronicle (season, time, location, text) VALUES (1, ?, NULL, ?)", (i, f"第{i}筆"))
            w.commit()
            i += 1
        w.close()

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        time.sleep(0.2)  # 讓寫入先跑起來
        out = backup_db.backup(src, tmp_path / "cloud", tag="manual", now=NOW)
        took = time.monotonic() - started
    finally:
        stop.set()
        thread.join()
    assert took < 5, f"備份花了 {took:.1f} 秒：寫入一直打斷它"
    assert backup_db.verify(out)["characters"] == 2


def test_backup_into_a_folder_that_cannot_be_written(tmp_path):
    """目的地是一個檔、不是資料夾（雲端資料夾設錯）：清楚的錯，不留 .partial（Review Focus 2）。"""
    src = _live_db(tmp_path)
    blocked = tmp_path / "not_a_folder"
    blocked.write_text("x", encoding="utf-8")
    with pytest.raises(backup_db.BackupError, match="備份資料夾"):
        backup_db.backup(src, blocked, tag="manual", now=NOW)
    assert list(tmp_path.glob("**/*.partial")) == []


def test_backup_of_a_missing_database(tmp_path):
    with pytest.raises(backup_db.BackupError, match="找不到資料庫"):
        backup_db.backup(tmp_path / "nope.db", tmp_path / "cloud", tag="manual", now=NOW)


def test_verify_rejects_a_newer_schema_and_garbage(tmp_path):
    """版本比程式新、或根本不是資料庫：verify 丟錯（Review Focus 4）。"""
    newer = tmp_path / "newer.db"
    conn = sqlite3.connect(newer)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(backup_db.BackupError, match="版本"):
        backup_db.verify(newer)
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(backup_db.BackupError):
        backup_db.verify(junk)


def test_backup_into_a_folder_with_url_special_characters(tmp_path):
    """資料夾名字帶 # 或 %（雲端資料夾名字不一定乾淨）：照樣備份、驗得過，不能驗到別的檔上。"""
    src = _live_db(tmp_path)
    for name in ("雲端#備份", "100%41備份", "my backup"):
        out = backup_db.backup(src, tmp_path / name, tag="manual", now=NOW)
        assert out.parent.name == name
        assert backup_db.verify(out)["characters"] == 2
    assert [p.name for p in tmp_path.iterdir() if p.is_file()] == []  # 沒有因為路徑被切斷而多出別的檔


def test_main_manual_backup_prints_where_and_returns_zero(tmp_path, capsys):
    src = _live_db(tmp_path)
    assert backup_db.main(["--db", str(src), "--dest", str(tmp_path / "cloud")]) == 0
    out = capsys.readouterr().out
    assert "tianxia-manual-" in out and "角色 2" in out
    assert backup_db.main(["--db", str(tmp_path / "nope.db"), "--dest", str(tmp_path / "cloud")]) == 1
