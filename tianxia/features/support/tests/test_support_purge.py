"""客服單到期刪除（隱私權條款第二條「客服單……結案後 1 年」；Config.support.purge_days 預設 365）：
結了、最後一筆動靜早於 purge_days 天的單整張刪掉（各表的列＋截圖資料夾）；沒結的、還沒到期的不動；旁檔不在不建檔；看守先刪一次、停得下來。"""
from __future__ import annotations

import contextlib
import sqlite3
import threading

from tianxia.core.tuning.support import SupportTuning
from tianxia.features.support import purge, rules, store

DAY = rules.DAY_SECONDS
YEAR = 365 * DAY
T0 = 1_000_000.0


def _ticket(sc: store.SupportStore, now: float, account_id: int = 1) -> int:
    return sc.add_ticket(account_id=account_id, account_created=1.0, login="x", character="沈青衫", version="v", category="account",
                         body="帳號登不進去", now=now, open_max=99, daily_max=99)


def _full(sc: store.SupportStore, files: object, now: float) -> int:
    """一張什麼都有的單：玩家回、客服回、內部註記、截圖一張（列＋檔）、找真人、查帳號一筆、待確認的紀錄一筆，然後結掉。"""
    tid = _ticket(sc, now)
    sc.staff_reply(tid, 2, "試試重登", "wait", now)
    sc.player_reply(tid, 1, 1.0, "還是不行", now)
    sc.add_human(tid, 1, 1.0, now)
    folder = files / str(tid)
    folder.mkdir(parents=True)
    part = folder / "x.part"
    part.write_bytes(b"png")
    sc.add_file(tid, 1, 1.0, "png", 3, "00", now, 3, part=part)
    sc.log_card(staff_account_id=2, ticket_id=tid, shown="sh***@g***", found=1, now=now)
    with contextlib.closing(sqlite3.connect(sc.path, isolation_level=None)) as conn:
        rid = conn.execute("SELECT MAX(id) FROM replies WHERE ticket_id = ?", (tid,)).fetchone()[0]
        conn.execute("INSERT INTO pending_notes (reply_id, ticket_id, at) VALUES (?, ?, ?)", (rid, tid, now))
    sc.close(tid, now)
    return tid


def _rows(sc: store.SupportStore, tid: int) -> dict[str, int]:
    with contextlib.closing(sqlite3.connect(sc.path)) as conn:
        out = {"tickets": conn.execute("SELECT COUNT(*) FROM tickets WHERE id = ?", (tid,)).fetchone()[0]}
        for table in ("replies", "files", "flags", "pending_notes", "lookups"):
            out[table] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE ticket_id = ?", (tid,)).fetchone()[0]  # noqa: S608
        return out


def test_purge_days_default_is_one_year():
    assert SupportTuning().purge_days == 365


def test_closed_ticket_older_than_a_year_is_gone_with_everything(tmp_path):
    db = tmp_path / "tianxia.db"
    sc = store.SupportStore(store.store_path(db))
    files = store.files_dir(db)
    old = _full(sc, files, T0)
    young = _full(sc, files, T0 + 10 * DAY)
    waiting = _ticket(sc, T0)  # 一年多沒動、但沒結：不刪
    assert all(n > 0 for n in _rows(sc, old).values())
    assert purge.purge_once(db, T0 + YEAR - 1, 365) == []  # 還差一秒
    assert purge.purge_once(db, T0 + YEAR + 1, 365) == [old]
    assert _rows(sc, old) == dict.fromkeys(("tickets", "replies", "files", "flags", "pending_notes", "lookups"), 0)
    assert not (files / str(old)).exists()  # 截圖資料夾一起刪
    assert all(n > 0 for n in _rows(sc, young).values()) and (files / str(young)).exists()
    assert sc.ticket(waiting)["status"] == rules.OPEN
    assert purge.purge_once(db, T0 + YEAR + 11 * DAY, 365) == [young]
    assert sc.ticket(waiting) is not None


def test_the_clock_starts_at_the_last_activity(tmp_path):
    """從最後一筆動靜（結單或之後的回覆，取晚的）起算：結案後客服又補一則，就從那一則起算。"""
    db = tmp_path / "tianxia.db"
    sc = store.SupportStore(store.store_path(db))
    tid = _ticket(sc, T0)
    sc.close(tid, T0 + 30 * DAY)
    assert purge.purge_once(db, T0 + YEAR + DAY, 365) == []  # 送單滿一年、結案未滿
    with contextlib.closing(sqlite3.connect(sc.path, isolation_level=None)) as conn:
        conn.execute("INSERT INTO replies (ticket_id, by_account_id, staff, internal, body, created) VALUES (?, 2, 1, 1, '補註', ?)",
                     (tid, T0 + 60 * DAY))
    assert purge.purge_once(db, T0 + 30 * DAY + YEAR + DAY, 365) == []
    assert purge.purge_once(db, T0 + 60 * DAY + YEAR + DAY, 365) == [tid]


def test_days_follow_the_setting(tmp_path):
    db = tmp_path / "tianxia.db"
    sc = store.SupportStore(store.store_path(db))
    tid = _ticket(sc, T0)
    sc.close(tid, T0)
    assert purge.purge_once(db, T0 + 31 * DAY, 365) == []
    assert purge.purge_once(db, T0 + 31 * DAY, 30) == [tid]


def test_no_sidecar_no_file(tmp_path):
    db = tmp_path / "tianxia.db"
    assert purge.purge_once(db, T0, 365) == []
    assert not store.store_path(db).exists()


def test_watcher_purges_at_start_and_stops(tmp_path):
    db = tmp_path / "tianxia.db"
    sc = store.SupportStore(store.store_path(db))
    tid = _ticket(sc, T0)
    sc.close(tid, T0)
    said: list[str] = []
    stop = threading.Event()
    thread = purge.start(lambda: db, lambda: T0 + 2 * YEAR, 365, interval=3600, stop=stop, warn=said.append)
    for _ in range(100):
        if said:
            break
        threading.Event().wait(0.05)
    stop.set()
    thread.join(5)
    assert not thread.is_alive()
    assert sc.ticket(tid) is None and said and "1 張" in said[0]


def test_watcher_survives_a_bad_round(tmp_path):
    said: list[str] = []
    stop = threading.Event()
    calls = []

    def clock():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        stop.set()
        return T0

    thread = purge.start(lambda: tmp_path / "tianxia.db", clock, 365, interval=0.01, stop=stop, warn=said.append)
    thread.join(5)
    assert not thread.is_alive() and len(calls) >= 2 and "失敗" in said[0]
