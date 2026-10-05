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


def _touch_daily(folder: Path, when: dt.datetime) -> Path:
    path = folder / backup_db.backup_name("daily", when)
    path.write_bytes(b"")
    return path


def test_prune_keeps_fourteen_days_and_eight_weeks(tmp_path):
    """設計 8.5：最近 14 個日曆日每天留最新的一份，加上最近 8 個 ISO 週每週留最新的一份；其他每日備份刪掉。"""
    folder = tmp_path / "cloud"
    folder.mkdir()
    stamps = [NOW.replace(minute=m) - dt.timedelta(days=d) for d in range(80) for m in (0, 30)]  # 80 天、每天兩份
    paths = {when: _touch_daily(folder, when) for when in stamps}
    removed = backup_db.prune(folder, NOW)
    kept = {when for when, path in paths.items() if path.exists()}
    recent_days = {NOW.replace(minute=30) - dt.timedelta(days=d) for d in range(14)}  # 每天只留 5:30 那份
    monday = NOW.date() - dt.timedelta(days=NOW.weekday())
    week_keys = {(monday - dt.timedelta(weeks=i)).isocalendar()[:2] for i in range(8)}  # （年, 週）：跨年週數會重複
    newest_of_week = {}
    for when in stamps:
        key = when.isocalendar()[:2]
        if key in week_keys and when > newest_of_week.get(key, dt.datetime.min):
            newest_of_week[key] = when
    assert kept == recent_days | set(newest_of_week.values())
    assert sorted(removed) == sorted(paths[when] for when in stamps if when not in kept)


def test_prune_never_touches_manual_or_foreign_files(tmp_path):
    """手動備份、.partial、.bad、別人放的檔：一個都不碰（Review Focus 5）。"""
    folder = tmp_path / "cloud"
    folder.mkdir()
    old = NOW - dt.timedelta(days=400)
    keep = [
        folder / backup_db.backup_name("manual", old),
        folder / (backup_db.backup_name("daily", old) + ".partial"),
        folder / (backup_db.backup_name("daily", old) + ".bad"),
        folder / "企劃者的筆記.txt",
        folder / "tianxia-daily-壞掉的名字.db",
    ]
    for p in keep:
        p.write_bytes(b"")
    gone = _touch_daily(folder, old)
    assert backup_db.prune(folder, NOW) == [gone]
    assert all(p.exists() for p in keep)


def test_main_daily_prunes_only_with_the_flag(tmp_path, capsys):
    src = _live_db(tmp_path)
    folder = tmp_path / "cloud"
    folder.mkdir()
    stale = _touch_daily(folder, NOW - dt.timedelta(days=400))
    assert backup_db.main(["--db", str(src), "--dest", str(folder), "--tag", "daily"]) == 0
    assert stale.exists()  # 沒給 --prune 不刪
    assert backup_db.main(["--db", str(src), "--dest", str(folder), "--tag", "daily", "--prune"]) == 0
    assert not stale.exists()
    assert "刪掉 1 份舊的每日備份" in capsys.readouterr().out
    with pytest.raises(SystemExit) as stop:  # 手動備份不能帶 --prune：parser.error 結束碼 2
        backup_db.main(["--db", str(src), "--dest", str(folder), "--prune"])
    assert stop.value.code == 2


def test_main_prune_that_cannot_delete_says_so_and_fails(tmp_path, capsys, monkeypatch):
    """雲端硬碟正在同步、舊檔刪不掉：新的備份已經做好，但要用白話講出刪舊失敗、結束碼不是 0（工作排程器才看得出來）。"""
    src = _live_db(tmp_path)
    folder = tmp_path / "cloud"
    folder.mkdir()
    stale = _touch_daily(folder, NOW - dt.timedelta(days=400))

    def locked(self, *args, **kwargs):
        raise PermissionError("檔案正在使用中")

    with monkeypatch.context() as patched:
        patched.setattr(Path, "unlink", locked)
        assert backup_db.main(["--db", str(src), "--dest", str(folder), "--tag", "daily", "--prune"]) == 1
    captured = capsys.readouterr()
    assert "tianxia-daily-" in captured.out  # 備份本身是做好了的
    assert "刪舊備份失敗" in captured.err
    assert stale.exists()
