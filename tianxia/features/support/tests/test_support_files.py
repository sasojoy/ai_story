"""客服單的截圖（客服自動受理第 215 批；設計 5.1、5.5）：檔頭認種類、旁檔的 files 表、上傳（串流累計、超過就停）、看圖（主人與客服，其他人 404 同一句）。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3

import pytest
import server
from fastapi.testclient import TestClient
# autouse 的 fixture 要明列（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import player, sidecar, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.features.support import routes, rules, store

pytestmark = pytest.mark.whole_content

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
    none = {"human": False, "last_by": None}  # 第 216 批多的兩鍵
    assert s.files(other) == [] and s.queue_extras([tid, other]) == {tid: {"file_count": 3, **none}, other: {"file_count": 0, **none}}
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


# ── 上傳（task 3）：POST /api/support/file?id=<單號>，內文就是圖的位元組 ──
NOWHERE = "/api/support-no-such-route"


def _up(c, tid, data: bytes, content_type="image/png", **headers):
    return c.post(f"/api/support/file?id={tid}", content=data, headers={"Content-Type": content_type, **headers})


def _folder(tid=None):
    base = routes.files_path()
    return base if tid is None else base / str(tid)


def test_upload_png_jpg_webp_lands_on_disk(support_on):
    c = player()
    tid = ticket(c).json()["id"]
    sent = []
    for head, ext in ((PNG, "png"), (JPG, "jpg"), (WEBP, "webp")):
        data = head + os.urandom(200)
        r = _up(c, tid, data)
        assert r.status_code == 200, r.text
        out = r.json()
        sent.append(data)
        assert (out["id"], out["seq"], out["kind"], out["bytes"]) == (tid, len(sent), ext, len(data))
        assert len(out["files"]) == len(sent)
        assert (_folder(tid) / f"{len(sent)}.{ext}").read_bytes() == data
    rows = store.open_store(sidecar(), create=False).files(tid)
    assert [r["sha256"] for r in rows] == [hashlib.sha256(d).hexdigest() for d in sent]
    assert not list(_folder(tid).glob("*.part")) and not list(_folder(tid).glob(".upload-*"))
    mine = c.get("/api/support/mine").json()["tickets"][0]
    assert mine["files"] == [{"seq": i + 1, "kind": k, "bytes": len(d)} for i, (k, d) in enumerate(zip(("png", "jpg", "webp"), sent))]
    r = _up(c, tid, PNG + b"4")
    assert r.status_code == 400 and r.json() == {"error": rules.FILES_FULL.format(n=3)}
    assert not list(_folder(tid).glob(".upload-*"))  # 滿了：.part 刪掉


def test_file_too_big_is_refused_by_real_size(support_on, monkeypatch):
    """Review Focus 1：Content-Length 說 1、實際送 17 位元組（上限 16）：照實際累計拒絕，檔不落地、files 表不多列。"""
    monkeypatch.setattr(server.CONTENT.config.support, "file_bytes_max", 16)
    c = player()
    tid = ticket(c).json()["id"]
    r = _up(c, tid, PNG + b"x" * 9, **{"Content-Length": "1"})
    assert r.status_code == 400 and r.json() == {"error": rules.FILE_TOO_BIG.format(mb=routes._mb(16))}
    assert not _folder().exists() and store.open_store(sidecar(), create=False).files(tid) == []
    told = _up(c, tid, PNG, **{"Content-Length": "17"})  # 說超過的：不讀就拒
    assert told.status_code == 400 and told.json() == r.json()
    ok = _up(c, tid, PNG + b"x" * 8)  # 剛好 16：收
    assert ok.status_code == 200 and ok.json()["bytes"] == 16


def test_oversized_upload_stops_reading_early(support_on, monkeypatch):
    """Review Focus 1：沒有 Content-Length、一塊一塊送：累到超過就停止讀（第 3 塊不會被要）。TestClient 會先把整個內文讀完，所以直接打 ASGI。"""
    chunk = 9
    monkeypatch.setattr(server.CONTENT.config.support, "file_bytes_max", 2 * chunk - 1)
    c = player()
    tid = ticket(c).json()["id"]
    cookie = c.cookies.get(server.COOKIE)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http", "path": "/api/support/file",
             "raw_path": b"/api/support/file", "root_path": "", "query_string": f"id={tid}".encode(), "server": ("testserver", 80),
             "client": ("testclient", 50000),
             "headers": [(b"host", b"testserver"), (b"content-type", b"image/png"), (b"cookie", f"{server.COOKIE}={cookie}".encode())]}
    pulls, sent = [], []

    async def receive():
        pulls.append(1)
        if len(pulls) >= 3:
            raise AssertionError("第 3 塊被要了")
        return {"type": "http.request", "body": (PNG + b"x")[:chunk], "more_body": True}

    async def send(message):
        sent.append(message)

    asyncio.run(server.app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    assert start["status"] == 400 and json.loads(body) == {"error": rules.FILE_TOO_BIG.format(mb=routes._mb(2 * chunk - 1))}
    assert len(pulls) == 2 and not _folder().exists()


def test_kind_is_by_magic_bytes_only(support_on):
    """Review Focus 2：照檔頭，不照 Content-Type。MZ（執行檔）說是 image/png → 不收；PNG 檔頭說是 text/plain → 收、存成 png。"""
    c = player()
    tid = ticket(c).json()["id"]
    r = _up(c, tid, b"MZ\x90\x00" + os.urandom(64), "image/png")
    assert r.status_code == 400 and r.json() == {"error": rules.FILE_NOT_IMAGE}
    assert not _folder().exists()
    data = PNG + b"not really an image"
    r = _up(c, tid, data, "text/plain")
    assert r.status_code == 200 and r.json()["kind"] == "png"
    assert (_folder(tid) / "1.png").read_bytes() == data
    seen = c.get(f"/api/support/file/{tid}/1")
    assert seen.status_code == 200 and seen.headers["content-type"] == "image/png" and seen.content == data
    assert seen.headers["x-content-type-options"] == "nosniff"  # 全站已有：檔頭是 PNG、內容不是圖，瀏覽器只會畫成破圖


# ── 看圖（task 4）：GET /api/support/file/{tid}/{seq} ──

def test_view_file_owner_staff_and_nobody_else(support_on, monkeypatch):
    c = player()
    tid = ticket(c).json()["id"]
    data = JPG + os.urandom(50)
    assert _up(c, tid, data, "image/jpeg").status_code == 200
    mine = c.get(f"/api/support/file/{tid}/1")
    assert (mine.status_code, mine.content, mine.headers["content-type"]) == (200, data, "image/jpeg")
    assert mine.headers["content-disposition"] == "inline"
    s = staffer(monkeypatch)
    desk = s.get(f"/api/support/file/{tid}/1")
    assert (desk.status_code, desk.content, desk.headers["content-type"]) == (200, data, "image/jpeg")
    assert s.get(f"/api/support/ticket/{tid}").json()["files"] == [{"seq": 1, "kind": "jpg", "bytes": len(data)}]
    assert s.get("/api/support/queue").json()["tickets"][0]["file_count"] == 1
    other = player("li_02", "李白衣")
    replies = [other.get(f"/api/support/file/{tid}/1"), c.get(f"/api/support/file/{tid}/2"), c.get(f"/api/support/file/{tid + 9}/1"),
               c.get(f"/api/support/file/{tid}/x"), c.get("/api/support/file/abc/1"), s.get(f"/api/support/file/{tid}/7")]
    assert {(r.status_code, r.content) for r in replies} == {(404, replies[0].content)}
    assert replies[0].json() == {"detail": rules.NOT_FOUND}
    anon = TestClient(server.app, raise_server_exceptions=False)
    assert anon.get(f"/api/support/file/{tid}/1").status_code == 401


def test_file_response_says_nosniff(support_on, monkeypatch):
    """第 219 批：看圖的回應帶 X-Content-Type-Options: nosniff（瀏覽器不准猜種類），inline 照舊。
    全站 middleware（第 209 批的 SECURITY_HEADERS）本來就加；這裡把它清空，確認路由自己也帶（middleware 哪天改了也還在）。"""
    monkeypatch.setattr(server, "SECURITY_HEADERS", {})
    c = player()
    tid = ticket(c).json()["id"]
    assert _up(c, tid, PNG + os.urandom(30)).status_code == 200
    r = c.get(f"/api/support/file/{tid}/1")
    assert r.status_code == 200
    assert (r.headers.get("x-content-type-options"), r.headers["content-disposition"]) == ("nosniff", "inline")


def test_missing_file_on_disk_is_404_not_500(support_on):
    c = player()
    tid = ticket(c).json()["id"]
    assert _up(c, tid, WEBP + b"zz").status_code == 200
    (_folder(tid) / "1.webp").unlink()
    r = c.get(f"/api/support/file/{tid}/1")
    assert r.status_code == 404 and r.json() == {"detail": rules.NOT_FOUND}


def test_upload_needs_owner_and_open_ticket(support_on, monkeypatch):
    c = player()
    tid = ticket(c).json()["id"]
    other = player("li_02", "李白衣")
    stranger, missing = _up(other, tid, PNG), _up(other, tid + 50, PNG)
    assert (stranger.status_code, stranger.content) == (missing.status_code, missing.content) == (404, missing.content)
    assert missing.json() == {"detail": rules.NOT_FOUND}
    assert _up(c, "abc", PNG).json() == {"detail": rules.NOT_FOUND}
    s = staffer(monkeypatch)
    assert s.post("/api/support/close", json={"id": tid}).status_code == 200
    r = _up(c, tid, PNG)
    assert r.status_code == 400 and r.json() == {"error": rules.CLOSED_ALREADY}
    anon = TestClient(server.app, raise_server_exceptions=False)
    assert _up(anon, tid, PNG).status_code == 401
    assert not _folder().exists()


def test_off_file_routes_404_before_login(monkeypatch):
    """關著：兩條都跟沒有這條路逐位元組一樣（沒登入、壞單號、超大 Content-Length 都一樣），不建資料夾、不建旁檔。"""
    anon = TestClient(server.app, raise_server_exceptions=False)
    nowhere = anon.get(NOWHERE)
    c = player()
    for who in (anon, c):
        for r in (_up(who, 1, PNG), _up(who, "abc", PNG), _up(who, 1, b"MZ"), _up(who, 1, PNG, **{"Content-Length": "999999999"}),
                  who.get("/api/support/file/1/1"), who.get("/api/support/file/abc/x")):
            assert (r.status_code, r.content) == (404, nowhere.content)
    assert not _folder().exists() and not sidecar().exists()
