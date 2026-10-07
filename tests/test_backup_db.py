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
import restore_db  # noqa: E402

from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.database import SCHEMA_VERSION, close_all, open_database  # noqa: E402
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
    out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
    assert out == tmp_path / "backups" / "tianxia-manual-20261006-050000.db"
    assert not (tmp_path / "backups" / "tianxia-manual-20261006-050000.db-wal").exists()
    conn = sqlite3.connect(out)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"  # 自足的單一檔，之後放雲端同步資料夾也不會只同步到一半
    finally:
        conn.close()
    report = backup_db.verify(out)
    assert report["version"] == SCHEMA_VERSION and report["characters"] == 2
    assert not list((tmp_path / "backups").glob("*.partial"))


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
        out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
    finally:
        stop.set()
        thread.join()
    assert backup_db.verify(out)["characters"] == 2


@pytest.mark.slow
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
    deadline = time.monotonic() + 20  # 備份做不完時，寫入自己在二十秒後停，測試才不會永遠掛著
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
        out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
        writer_still_running = thread.is_alive()  # 不看備份花了幾秒（機器慢也不會誤報），只看備份做完時寫入還在不在跑
    finally:
        stop.set()
        thread.join()
    assert writer_still_running, "備份是等寫入自己停了才做完的：寫入一直打斷它"
    assert backup_db.verify(out)["characters"] == 2


def test_backup_into_a_folder_that_cannot_be_written(tmp_path):
    """目的地是一個檔、不是資料夾（備份資料夾設錯）：清楚的錯，不留 .partial（Review Focus 2）。"""
    src = _live_db(tmp_path)
    blocked = tmp_path / "not_a_folder"
    blocked.write_text("x", encoding="utf-8")
    with pytest.raises(backup_db.BackupError, match="備份資料夾"):
        backup_db.backup(src, blocked, tag="manual", now=NOW)
    assert list(tmp_path.glob("**/*.partial")) == []


def _bad_source(tmp_path: Path, kind: str) -> Path:
    """複製得動、但驗不過的來源資料庫：頁壞掉（完整性檢查不過）或結構版本比程式新。"""
    if kind == "newer":
        path = tmp_path / "live" / "tianxia.db"
        path.parent.mkdir()
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE accounts (x)")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        conn.close()
        return path
    path = _live_db(tmp_path)
    close_all()  # 沒有 -wal 了，內容都在主檔裡
    data = bytearray(path.read_bytes())
    data[4096:] = b"\xff" * (len(data) - 4096)  # 第一頁（檔頭與資料表清單）留著，後面的頁全壞
    path.write_bytes(bytes(data))
    return path


@pytest.mark.parametrize("kind", ["corrupt", "newer"])
def test_backup_of_a_bad_source_leaves_only_a_bad_file_and_prunes_nothing(tmp_path, kind, capsys):
    """來源壞掉、或版本比程式新：備份驗不過就改名成 .bad（錯誤訊息指的是 .bad，不是已經不存在的 .partial），
    不會有正式檔名的備份，也不會接著刪舊備份（審查次要 7）。"""
    src = _bad_source(tmp_path, kind)
    folder = tmp_path / "backups"
    with pytest.raises(backup_db.BackupError) as failure:
        backup_db.backup(src, folder, tag="daily", now=NOW)
    bad = folder / (backup_db.backup_name("daily", NOW) + ".bad")
    assert [p.name for p in folder.iterdir()] == [bad.name]  # 沒有正式檔名的備份，也沒有 .partial
    assert str(bad) in str(failure.value) and ".partial" not in str(failure.value)
    # 走指令列：每日備份加 --prune，失敗了就不能刪任何舊備份
    stale = _touch_daily(folder, NOW - dt.timedelta(days=400))
    fresh = _touch_daily(folder, NOW - dt.timedelta(days=1))
    assert backup_db.main(["--db", str(src), "--dest", str(folder), "--tag", "daily", "--prune"]) == 1
    assert stale.exists()  # 要是 prune 跑了，400 天前這份就被刪了
    assert sorted(p.name for p in folder.glob("tianxia-daily-*.db")) == sorted([stale.name, fresh.name])  # 沒有新的正式備份
    assert "備份失敗" in capsys.readouterr().err


def test_backup_of_a_file_that_is_not_a_database(tmp_path):
    """來源根本不是資料庫：講是資料庫本身壞了（不是「資料夾寫不進去」），資料夾裡什麼都不留。"""
    junk = tmp_path / "tianxia.db"
    junk.write_bytes(b"this is not sqlite" * 1000)
    with pytest.raises(backup_db.BackupError, match="資料庫本身壞了"):
        backup_db.backup(junk, tmp_path / "backups", tag="daily", now=NOW)
    assert list((tmp_path / "backups").iterdir()) == []


def test_backup_of_a_missing_database(tmp_path):
    with pytest.raises(backup_db.BackupError, match="找不到資料庫"):
        backup_db.backup(tmp_path / "nope.db", tmp_path / "backups", tag="manual", now=NOW)


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
    """資料夾名字帶 # 或 %（資料夾名字不一定乾淨）：照樣備份、驗得過，不能驗到別的檔上。"""
    src = _live_db(tmp_path)
    for name in ("備份#1", "100%41備份", "my backup"):
        out = backup_db.backup(src, tmp_path / name, tag="manual", now=NOW)
        assert out.parent.name == name
        assert backup_db.verify(out)["characters"] == 2
    assert [p.name for p in tmp_path.iterdir() if p.is_file()] == []  # 沒有因為路徑被切斷而多出別的檔


def test_main_manual_backup_prints_where_and_returns_zero(tmp_path, capsys):
    src = _live_db(tmp_path)
    assert backup_db.main(["--db", str(src), "--dest", str(tmp_path / "backups")]) == 0
    out = capsys.readouterr().out
    assert "tianxia-manual-" in out and "角色 2" in out
    assert backup_db.main(["--db", str(tmp_path / "nope.db"), "--dest", str(tmp_path / "backups")]) == 1


def _touch_daily(folder: Path, when: dt.datetime) -> Path:
    path = folder / backup_db.backup_name("daily", when)
    path.write_bytes(b"")
    return path


def test_prune_keeps_fourteen_days_and_eight_weeks(tmp_path):
    """設計 8.5：最近 14 個日曆日每天留最新的一份，加上最近 8 個 ISO 週每週留最新的一份；其他每日備份刪掉。"""
    folder = tmp_path / "backups"
    folder.mkdir()
    stamps = [NOW - dt.timedelta(days=d, minutes=m) for d in range(80) for m in (0, 30)]  # 80 天、每天兩份，都不晚於 NOW
    paths = {when: _touch_daily(folder, when) for when in stamps}
    removed = backup_db.prune(folder, NOW)
    kept = {when for when, path in paths.items() if path.exists()}
    recent_days = {NOW - dt.timedelta(days=d) for d in range(14)}  # 每天只留較晚的那份（5:00，不是早 30 分鐘的）
    monday = NOW.date() - dt.timedelta(days=NOW.weekday())
    week_keys = {(monday - dt.timedelta(weeks=i)).isocalendar()[:2] for i in range(8)}  # （年, 週）：跨年週數會重複
    newest_of_week = {}
    for when in stamps:
        key = when.isocalendar()[:2]
        if key in week_keys and when > newest_of_week.get(key, dt.datetime.min):
            newest_of_week[key] = when
    assert kept == recent_days | set(newest_of_week.values())
    assert sorted(removed) == sorted(paths[when] for when in stamps if when not in kept)


def test_prune_keeps_files_dated_in_the_future(tmp_path):
    """時鐘被調過、檔名的時間比現在還晚：不當成舊的刪掉。單獨一條，不跟 14 天規則混在一起。"""
    folder = tmp_path / "backups"
    folder.mkdir()
    ahead = [_touch_daily(folder, NOW + dt.timedelta(days=d)) for d in (3, 5)]  # 兩份都在未來：較早那份不是最新、不在 14 天裡
    stale = _touch_daily(folder, NOW - dt.timedelta(days=400))
    assert backup_db.prune(folder, NOW) == [stale]
    assert all(path.exists() for path in ahead)


def test_prune_always_keeps_the_newest_daily_even_when_it_is_old(tmp_path):
    """備份停了好幾個月才又跑 prune：全部都超過 8 週，也要留下最新的一份，不能把每日備份刪光（審查次要 5）。"""
    folder = tmp_path / "backups"
    folder.mkdir()
    newest = _touch_daily(folder, NOW - dt.timedelta(days=100))
    older = [_touch_daily(folder, NOW - dt.timedelta(days=d)) for d in (120, 200, 300)]
    assert sorted(backup_db.prune(folder, NOW)) == sorted(older)
    assert newest.exists()


def test_prune_keeps_going_when_one_file_cannot_be_deleted(tmp_path, monkeypatch):
    """其中一份刪不掉：其他能刪的照刪，最後一次講完哪幾份沒刪掉（審查次要 5）。"""
    folder = tmp_path / "backups"
    folder.mkdir()
    stale = [_touch_daily(folder, NOW - dt.timedelta(days=d)) for d in (400, 401, 402)]
    _touch_daily(folder, NOW)
    real_unlink = Path.unlink

    def locked_middle(self, *args, **kwargs):
        if self == stale[1]:
            raise PermissionError("檔案正在使用中")
        return real_unlink(self, *args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(Path, "unlink", locked_middle)
        with pytest.raises(backup_db.PruneError) as failure:
            backup_db.prune(folder, NOW)
    assert sorted(failure.value.removed) == sorted([stale[0], stale[2]])
    assert [path for path, _ in failure.value.failed] == [stale[1]]
    assert [p.exists() for p in stale] == [False, True, False]


def test_prune_never_touches_manual_or_foreign_files(tmp_path):
    """手動備份、.partial、.bad、別人放的檔：一個都不碰（Review Focus 5）。"""
    folder = tmp_path / "backups"
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
    today = _touch_daily(folder, NOW)  # 最新的一份永遠留著，所以要有一份比 gone 新的，gone 才是該刪的
    assert backup_db.prune(folder, NOW) == [gone]
    assert all(p.exists() for p in keep) and today.exists()


def test_main_daily_prunes_only_with_the_flag(tmp_path, capsys):
    src = _live_db(tmp_path)
    folder = tmp_path / "backups"
    folder.mkdir()
    stale = _touch_daily(folder, NOW - dt.timedelta(days=400))
    assert backup_db.main(["--db", str(src), "--dest", str(folder), "--tag", "daily"]) == 0
    assert stale.exists()  # 沒給 --prune 不刪
    for first_run in set(folder.glob("tianxia-daily-*.db")) - {stale}:
        first_run.unlink()  # 兩次執行落在同一天時，保留規則本來就會刪掉前一份：先拿掉，才只數得到那份過期的
    assert backup_db.main(["--db", str(src), "--dest", str(folder), "--tag", "daily", "--prune"]) == 0
    assert not stale.exists()
    assert "刪掉 1 份舊的每日備份" in capsys.readouterr().out
    with pytest.raises(SystemExit) as stop:  # 手動備份不能帶 --prune：parser.error 結束碼 2
        backup_db.main(["--db", str(src), "--dest", str(folder), "--prune"])
    assert stop.value.code == 2


def test_main_prune_that_cannot_delete_says_so_and_fails(tmp_path, capsys, monkeypatch):
    """舊檔被別的程式開著（以後放雲端同步資料夾，正在同步也一樣）刪不掉：新的備份已經做好，但要用白話講出刪舊失敗、結束碼不是 0（工作排程器才看得出來）。"""
    src = _live_db(tmp_path)
    folder = tmp_path / "backups"
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
    assert str(stale) in captured.err  # 哪一份沒刪掉，講出來
    assert stale.exists()


def test_restore_puts_the_backup_back_and_keeps_the_old_file(tmp_path):
    src = _live_db(tmp_path, names=("甲", "乙"))
    out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
    close_all()  # 模擬伺服器停掉
    db = open_database(src)  # 備份之後又玩了一段：多存一個角色
    CharacterStore(db).save(new_game_state(load_content(FIXTURE), "丙"))
    close_all()
    aside = restore_db.restore(out, src, now=NOW)
    assert aside is not None and aside.exists() and aside.name.startswith("tianxia.db.pre-restore-")
    assert backup_db.verify(src)["characters"] == 2  # 回到備份那一刻
    assert backup_db.verify(aside)["characters"] == 3  # 還原前的檔留著


def test_restore_moves_a_leftover_wal_with_the_old_file(tmp_path):
    """當機留下的 -wal 屬於舊檔：要跟著舊檔移走，不然 SQLite 會把它套進還原回來的檔（Review Focus 3）。"""
    src = _live_db(tmp_path)
    out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
    close_all()
    wal = src.with_name(src.name + "-wal")
    wal.write_bytes(b"leftover")
    aside = restore_db.restore(out, src, now=NOW)
    assert not wal.exists()
    assert aside.with_name(aside.name + "-wal").read_bytes() == b"leftover"


def test_restore_moves_orphan_sidecars_when_the_database_file_is_gone(tmp_path):
    """資料庫檔不見了、-wal 等殘留檔還在：照樣搬走，舊的 -wal 不能被套進還原回來的檔（審查必修 1）。
    實際做出一份有 500 筆江湖史的 -wal，備份卻是空的江湖史：套進去的話還原後會多出 500 筆。"""
    src = _live_db(tmp_path)
    out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
    close_all()
    writer = sqlite3.connect(src)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute("PRAGMA wal_autocheckpoint = 0")
    writer.executemany(
        "INSERT INTO chronicle (season, time, location, text) VALUES (1, ?, NULL, ?)",
        [(i, f"第{i}筆") for i in range(500)],
    )
    writer.commit()
    wal = src.with_name(src.name + "-wal")
    stale_wal = wal.read_bytes()  # 還沒做檢查點：這 500 筆只在 -wal 裡
    writer.close()
    src.unlink()  # 資料庫檔不見了，只剩殘留的 -wal（還有隨手留下的 -shm、-journal）
    wal.write_bytes(stale_wal)
    src.with_name(src.name + "-shm").write_bytes(b"leftover shm")
    src.with_name(src.name + "-journal").write_bytes(b"leftover journal")
    aside = restore_db.restore(out, src, now=NOW)
    assert aside is not None and not aside.exists()  # 資料庫檔本來就不在，所以只有殘留檔搬走了
    assert {p.name[len(aside.name):] for p in restore_db.aside_sidecars(aside)} == {"-wal", "-shm", "-journal"}
    assert [s for s in ("-wal", "-shm", "-journal") if src.with_name(src.name + s).exists()] == []
    assert backup_db.verify(src)["chronicle"] == 0  # 備份那一刻的樣子，沒有被舊的 -wal 改掉
    assert aside.with_name(aside.name + "-wal").read_bytes() == stale_wal


def test_restore_main_says_where_the_sidecars_went(tmp_path, capsys):
    """搬走了 -wal／-shm 就把路徑印出來；還原錯了要退回時，它們要跟資料庫檔一起改名回去（審查次要 4）。"""
    src = _live_db(tmp_path)
    out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
    close_all()
    wal = src.with_name(src.name + "-wal")
    wal.write_bytes(b"leftover")
    assert restore_db.main([str(out), "--db", str(src)]) == 0
    printed = capsys.readouterr().out
    (moved_wal,) = src.parent.glob("tianxia.db.pre-restore-*-wal")
    assert str(moved_wal) in printed  # 搬走的 -wal 的完整路徑
    assert "一起改名回去" in printed


@pytest.mark.skipif(sys.platform != "win32", reason="開著的檔改不了名是 Windows 的行為")
def test_restore_refuses_while_the_database_is_open(tmp_path):
    """伺服器開著（檔案被打開）時不還原（Review Focus 3）。"""
    src = _live_db(tmp_path)
    out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
    holder = sqlite3.connect(src)
    try:
        holder.execute("SELECT COUNT(*) FROM characters").fetchone()
        with pytest.raises(backup_db.BackupError, match="停掉伺服器"):
            restore_db.restore(out, src, now=NOW)
    finally:
        holder.close()
    assert backup_db.verify(src)["characters"] == 2  # 原檔沒被動到
    assert list(src.parent.glob("tianxia.db.*")) == []  # 也沒留下半途的檔或搬走的舊檔（-wal／-shm 是 tianxia.db- 開頭，不算）


def test_restore_refuses_a_bad_backup(tmp_path):
    src = _live_db(tmp_path)
    close_all()
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(backup_db.BackupError):
        restore_db.restore(junk, src, now=NOW)
    assert backup_db.verify(src)["characters"] == 2


def test_restore_that_cannot_copy_leaves_the_database_alone(tmp_path, monkeypatch):
    """磁碟滿了、複製到一半失敗：現在的資料庫一個字都沒動，也不留下半份檔。"""
    src = _live_db(tmp_path)
    out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
    close_all()

    def disk_full(*args, **kwargs):
        raise OSError("磁碟已滿")

    monkeypatch.setattr(restore_db.shutil, "copyfile", disk_full)
    with pytest.raises(backup_db.BackupError, match="複製"):
        restore_db.restore(out, src, now=NOW)
    assert backup_db.verify(src)["characters"] == 2
    assert [p.name for p in src.parent.iterdir() if not p.name.startswith("tianxia.db")] == []  # 沒有半份檔
    assert list(src.parent.glob("tianxia.db.*")) == []  # 也沒有搬走的舊檔：根本沒動到它


def test_restore_main(tmp_path, capsys):
    src = _live_db(tmp_path)
    out = backup_db.backup(src, tmp_path / "backups", tag="manual", now=NOW)
    close_all()
    assert restore_db.main([str(out), "--db", str(src)]) == 0
    assert "已還原" in capsys.readouterr().out
    assert restore_db.main([str(tmp_path / "nope.db"), "--db", str(src)]) == 1
    assert "找不到備份檔" in capsys.readouterr().err
