"""客服單的截圖（客服自動受理第 215 批；設計 5.1、5.5）：檔頭認種類、旁檔的 files 表、上傳（串流累計、超過就停）、看圖（主人與客服，其他人 404 同一句）。"""
from __future__ import annotations

import sqlite3

import pytest

from tianxia.features.support import rules, store

PNG = b"\x89PNG\r\n\x1a\n"
JPG = b"\xff\xd8\xff\xe0"
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 "


def test_image_kind_by_magic():
    assert rules.image_kind(PNG + b"rest") == "png"
    assert rules.image_kind(JPG + b"rest") == "jpg"
    assert rules.image_kind(WEBP + b"rest") == "webp"
    assert rules.image_kind(b"GIF89a" + b"\x00" * 10) is None
    assert rules.image_kind(b"") is None
    assert rules.image_kind(b"RIFF\x10\x00\x00\x00WAVE") is None
    assert rules.image_kind(b"MZ\x90\x00" + PNG) is None
    # 只看前 12 位元組：WebP 的標記落在第 12 個位元組之後就不算
    assert rules.image_kind(b"RIFF\x10\x00\x00\x00\x00WEBP") is None
    assert set(rules.CONTENT_TYPES) == {"png", "jpg", "webp"}
    assert rules.CONTENT_TYPES["png"] == "image/png" and rules.CONTENT_TYPES["jpg"] == "image/jpeg" and rules.CONTENT_TYPES["webp"] == "image/webp"


def test_file_strings_have_placeholders():
    assert "{mb}" in rules.FILE_TOO_BIG and "3" in rules.FILE_TOO_BIG.format(mb=3)
    assert "{n}" in rules.FILES_FULL and "3" in rules.FILES_FULL.format(n=3)
    assert rules.FILE_NOT_IMAGE and "{" not in rules.FILE_NOT_IMAGE


# ── 旁檔的 files 表（task 2）──
OLD_SCHEMA = store.SCHEMA[:8]  # 第 214 批的形狀：四張表與四個索引（files 表之前的那八句）


def _new_ticket(s, account_id=1, created=100.0):
    return s.add_ticket(account_id=account_id, account_created=created, login="a", character="甲", version="", category="game", body="x",
                        now=1000.0, open_max=3, daily_max=5)


def _add(s, tid, *, account_id=1, created=100.0, files_max=3, part=None):
    return s.add_file(tid, account_id, created, "png", 10, "0" * 64, 2000.0, files_max, part=part)


def test_add_file_numbers_and_limits(tmp_path):
    path = tmp_path / "x-support.sqlite"
    conn = sqlite3.connect(path)
    for sql in OLD_SCHEMA:
        conn.execute(sql)
    conn.commit()
    old = dict(conn.execute("SELECT name, sql FROM sqlite_master").fetchall())
    conn.close()
    assert "files" not in old and {"tickets", "replies", "lookups", "pending_notes"} <= set(old)
    s = store.SupportStore(path)
    conn = sqlite3.connect(path)
    now = dict(conn.execute("SELECT name, sql FROM sqlite_master").fetchall())
    conn.close()
    assert "files" in now and {k: v for k, v in now.items() if k in old} == old  # 舊存檔照讀：舊表一個字不變
    tid = _new_ticket(s)
    rows = [_add(s, tid) for _ in range(3)]
    assert [r["seq"] for r in rows] == [1, 2, 3] and rows[0]["ticket_id"] == tid and rows[0]["kind"] == "png"
    with pytest.raises(store.Refused) as e:
        _add(s, tid)
    assert str(e.value) == rules.FILES_FULL.format(n=3)
    assert [f["seq"] for f in s.files(tid)] == [1, 2, 3]
    other = _new_ticket(s, account_id=2)
    for who in ({"account_id": 1}, {"created": 99.0}):
        with pytest.raises(store.Refused) as e:
            _add(s, other, **who)
        assert str(e.value) == rules.NOT_FOUND
    with pytest.raises(store.Refused) as e:
        _add(s, 999)
    assert str(e.value) == rules.NOT_FOUND
    third = _new_ticket(s)
    s.close(third, 3000.0)
    with pytest.raises(store.Refused) as e:
        _add(s, third)
    assert str(e.value) == rules.CLOSED_ALREADY
    zero = _new_ticket(s, account_id=3)
    with pytest.raises(store.Refused):
        _add(s, zero, account_id=3, files_max=0)  # 主機把截圖關成 0 張
    assert s.files(other) == [] and s.queue_extras([tid, other]) == {tid: {"file_count": 3}, other: {"file_count": 0}}
    # .part 在交易裡換成 <seq>.<kind>；replace 丟錯就 rollback、不留列
    assert store.files_dir(tmp_path / "x.db") == tmp_path / "x-support-files"
    folder = store.files_dir(tmp_path / "x.db") / str(zero)
    folder.mkdir(parents=True)
    part = folder / ".upload-abc.part"
    part.write_bytes(PNG)
    row = _add(s, zero, account_id=3, part=part)
    assert (folder / "1.png").read_bytes() == PNG and not part.exists() and row["seq"] == 1
    with pytest.raises(OSError):
        _add(s, zero, account_id=3, part=folder / ".upload-gone.part")
    assert [f["seq"] for f in s.files(zero)] == [1]
