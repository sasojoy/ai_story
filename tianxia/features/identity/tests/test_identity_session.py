"""這次登入的方式與時間、近期驗證、重驗、換帳號先問一次（帳號與客服第 204 批；設計 4.3、4.4）；K 波修正輪留下的：
旁檔一個路徑只建一次表、驗證碼兩條照 shell.time、Turnstile 拿不到網域不過、fake_services 正式設定擋。"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import time as real_time

import pytest
from fastapi.testclient import TestClient
from test_identity_server import _turn_on, fresh_server, key_file  # noqa: F401  同一份伺服器 fixture

import server
from tianxia import accounts, database
from tianxia.accounts import AccountStore
from tianxia.core import identity_base
from tianxia.features.identity import FEATURE, FAKE_REFUSED, senders
from tianxia.features.identity import store as idstore

KEY = b"k" * 32  # key_file 寫的那一把


@pytest.fixture
def on(monkeypatch, key_file, tmp_path):  # noqa: F811
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "g.db"))
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "g.db")
    _turn_on(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config.identity, "fake_services", True)
    for box in (senders.FAKES.sms.outbox, senders.FAKES.mail.outbox, senders.FAKES.mail.subjects):
        box.clear()
    senders.FAKES.sms.fail = senders.FAKES.mail.fail = False
    return tmp_path


class Clock:
    """換掉 server.time：time() 回 self.now，其他照真的 time 模組（shell.time.time() 讀它）。"""

    def __init__(self, now: float):
        self.now = now

    def time(self) -> float:
        return self.now

    def __getattr__(self, name):
        return getattr(real_time, name)


def register(c, login="shen_01", password="secret-pw"):
    r = c.post("/api/register", json={"login": login, "password": password, "again": password})
    assert r.status_code == 200, r.text
    return r


def token_of(c) -> str:
    return c.cookies.get(server.COOKIE)


def code_of(channel="phone") -> str:
    box = senders.FAKES.sms.outbox if channel == "phone" else senders.FAKES.mail.outbox
    return re.search(r"\d{6}", box[-1][1]).group(0)


def phone_account(c, to="0912345678", name="沈青衫"):
    """用手機驗證碼開一個沒有密碼的帳號（建角色那一步），回帳號鍵。"""
    assert c.post("/api/identity/code/send", json={"channel": "phone", "to": to, "turnstile": "ok"}).status_code == 200
    assert c.post("/api/identity/code/verify", json={"code": code_of()}).json() == {"stage": "create", "pending": True}
    r = c.post("/api/identity/character", json={"name": name})
    assert r.status_code == 200, r.text
    return server.SESSIONS.get(token_of(c))


# ── ⓪ K 波修正輪 ─────────────────────────────────────


def test_store_opens_schema_once(tmp_path, monkeypatch):
    path = tmp_path / "x-identity.sqlite"
    idstore.IdentityStore(path)
    monkeypatch.setattr(idstore, "TABLES", ("THIS IS NOT SQL",))  # 第二次還跑 DDL 就會炸
    s = idstore.IdentityStore(path)
    assert s.count_and_record("b", 60, 1, 1.0) is True
    path.unlink()  # 檔被刪了（sb 的 _wipe_db）：下一次要重建
    for extra in ("-wal", "-shm"):
        (tmp_path / f"x-identity.sqlite{extra}").unlink(missing_ok=True)
    monkeypatch.undo()
    assert idstore.IdentityStore(path).count_and_record("b", 60, 1, 1.0) is True


def test_k_wave_side_file_gets_new_columns(tmp_path):
    path = tmp_path / "old-identity.sqlite"
    with sqlite3.connect(path) as conn:  # 第 201 批的 session_auth、bindings_meta、oauth_tickets 沒有第 204 批的欄
        conn.execute("CREATE TABLE session_auth (token_hash TEXT PRIMARY KEY, method TEXT NOT NULL, at REAL NOT NULL)")
        conn.execute("CREATE TABLE bindings_meta (account_id INTEGER NOT NULL, provider TEXT NOT NULL, subject_hmac TEXT NOT NULL, "
                     "verified_at REAL NOT NULL, PRIMARY KEY (account_id, provider))")
        conn.execute("INSERT INTO session_auth VALUES ('t', 'password', 5.0)")
    s = idstore.IdentityStore(path)
    s.mark_bound(1, "phone", "h", 10.0)
    assert s.meta(1)["phone"]["bound_at"] == 10.0
    assert identity_base.record_reauth("x", "password", 1.0, path) is False  # 沒有這個 token
    with sqlite3.connect(path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(session_auth)")}
    assert {"verified", "verified_by"} <= cols


def test_code_routes_read_shell_time(on, monkeypatch):
    from tianxia.features.identity import routes

    assert not hasattr(routes, "time")  # 不自己 import time
    monkeypatch.setattr(server, "time", Clock(1_000_000.0))
    c = TestClient(server.app)
    assert c.post("/api/identity/code/send", json={"channel": "phone", "to": "0912345678", "turnstile": "ok"}).status_code == 200
    with sqlite3.connect(idstore.default_side_path()) as conn:
        assert conn.execute("SELECT created, expires FROM challenges").fetchone() == (1_000_000.0, 1_000_300.0)
    server.time.now += 301  # shell 的時間過了 5 分鐘：碼過期
    assert c.post("/api/identity/code/verify", json={"code": code_of()}).status_code == 400


def test_turnstile_none_hostname_fails():
    good = {"success": True, "hostname": "example.com", "action": "identity_code"}
    opener = lambda req, timeout: io.BytesIO(json.dumps(good).encode())  # noqa: E731
    v = senders.CloudflareTurnstile("sec", "identity_code", urlopen=opener)
    assert v.verify("tok", "", "example.com") is True
    assert v.verify("tok", "", None) is False  # 拿不到自己的網域不再跳過比對


def test_fake_services_refused_on_serving_profiles():
    """正式設定兩種都開 season_one（讀覆寫檔，不整份載入：省時間）；season_one 開著又開 fake_services 就擋。"""
    from types import SimpleNamespace

    from tianxia.content import REAL_ROOT

    for profile in ("season21", "week7"):
        assert json.loads((REAL_ROOT / "profiles" / f"{profile}.json").read_text(encoding="utf-8"))["season_one"] is True
    for season_one, fake, want in ((True, True, [FAKE_REFUSED]), (True, False, []), (False, True, [])):
        found: list[str] = []
        content = SimpleNamespace(config=SimpleNamespace(season_one=season_one, identity=SimpleNamespace(fake_services=fake)))
        FEATURE.check_content(content, lambda ok, message: None if ok else found.append(message))
        assert found == want


def test_fake_services_warns_at_start(monkeypatch, capsys):
    monkeypatch.setattr(server.CONTENT.config.identity, "fake_services", False)
    FEATURE.threads(server)
    assert capsys.readouterr().out == ""
    monkeypatch.setattr(server.CONTENT.config.identity, "fake_services", True)
    FEATURE.threads(server)
    assert "fake_services" in capsys.readouterr().out
