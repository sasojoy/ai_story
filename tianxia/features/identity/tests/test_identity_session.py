"""這次登入的方式與時間、近期驗證、重驗、換帳號先問一次（帳號與客服第 204 批；設計 4.3、4.4）；K 波修正輪留下的：
旁檔一個路徑只建一次表、驗證碼兩條照 shell.time、Turnstile 拿不到網域不過、fake_services 開著印警告、公開網址是正式網域才拒絕啟動（L 波）。"""
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


@pytest.fixture
def clock(on, monkeypatch):
    """shell 的時間（server.time）換成可以撥的鐘；起點是真的現在（登入狀態的 30 天照真的時鐘算，不會過期）。"""
    tick = Clock(real_time.time())
    monkeypatch.setattr(server, "time", tick)
    return tick


def register(c, login="shen_01", password="secret-pw", name=None):
    r = c.post("/api/register", json={"login": login, "password": password, "again": password})
    assert r.status_code == 200, r.text
    if name is not None:
        assert c.post("/api/character", json={"name": name}).status_code == 200
    return r


def send(c, to="0912345678", channel="phone", purpose=None, **extra):
    body = {"channel": channel, "to": to, "turnstile": "ok", **extra}
    if purpose is not None:
        body["purpose"] = purpose
    return c.post("/api/identity/code/send", json=body)


def verify(c, channel="phone"):
    return c.post("/api/identity/code/verify", json={"code": code_of(channel)})


def bind(c, to="0912345678", channel="phone"):
    """綁一種（要近期驗證）：寄碼、驗碼，回驗碼那一下的回應。"""
    r = send(c, to, channel, purpose="bind")
    assert r.status_code == 200, r.text
    return verify(c, channel)


def side_rows(sql: str, args=()) -> list:
    with sqlite3.connect(idstore.default_side_path()) as conn:
        return conn.execute(sql, args).fetchall()


def error(r) -> str:
    assert r.status_code == 400, (r.status_code, r.text)
    return r.json()["error"]


def subj(channel, value):
    return identity_base.subject_hmac(KEY, channel, value)


def account_id(key: str) -> int:
    return AccountStore(database.open_database()).account_id(key)


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


def test_fake_services_not_refused_by_content():
    """L 波 PM 定：season_one 開著（season21 的測試環境）也准開 fake_services，載入不擋（擋在啟動、看公開網址）。"""
    from types import SimpleNamespace

    for season_one in (True, False):
        found: list[str] = []
        content = SimpleNamespace(config=SimpleNamespace(season_one=season_one, identity=SimpleNamespace(fake_services=True)))
        FEATURE.check_content(content, lambda ok, message: None if ok else found.append(message))
        assert found == []


def test_password_login_records_session_auth(clock):
    c = TestClient(server.app)
    register(c)
    assert identity_base.session_auth(token_of(c)) == {"method": "password", "at": clock.now, "verified": None, "verified_by": None}
    clock.now += 5
    c.post("/api/logout")
    assert c.post("/api/login", json={"login": "SHEN_01", "password": "secret-pw"}).status_code == 200
    assert identity_base.session_auth(token_of(c))["at"] == clock.now and server.SESSIONS.get(token_of(c)) == "shen_01"


def test_oauth_and_code_login_record_their_method(clock):
    from tianxia.features.identity import routes

    assert not hasattr(routes, "_session_token")  # 不再從回應的 set-cookie 撈 token：殼的 _start_session 回 token、自己記
    c = TestClient(server.app)
    key = phone_account(c)
    assert key.startswith("id:") and identity_base.session_auth(token_of(c))["method"] == "phone"  # 建角色那一步
    c.post("/api/logout")
    clock.now += 61  # 同一個號碼 60 秒才能再寄
    assert send(c).status_code == 200 and verify(c).json()["stage"] == "game"
    assert identity_base.session_auth(token_of(c)) == {"method": "phone", "at": clock.now, "verified": None, "verified_by": None}


def test_session_auth_not_written_when_off(monkeypatch, key_file, tmp_path):  # noqa: F811
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "g.db")
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "g.db"))
    c = TestClient(server.app)
    register(c)
    assert not idstore.default_side_path().exists()


def test_unknown_session_is_not_recent(clock):
    from tianxia.features.identity import binding

    cfg = server.CONTENT.config.identity
    assert binding.recent(None, clock.now, cfg) is False
    c = TestClient(server.app)
    register(c, name="沈青衫")
    assert send(c, purpose="bind").status_code == 200  # 剛登入的 10 分鐘內算
    side_rows("DELETE FROM session_auth")
    assert error(send(c, purpose="bind")) == binding.NEED_RECENT  # 查不到就當沒驗過


def test_reauth_with_password_extends_recent(clock):
    from tianxia.features.identity import binding

    c = TestClient(server.app)
    register(c, name="沈青衫")
    clock.now += server.CONTENT.config.identity.recent_seconds + 1
    assert error(send(c, purpose="bind")) == binding.NEED_RECENT
    r = c.post("/api/identity/reauth", json={"password": "secret-pw"})
    assert r.status_code == 200 and "驗證好了" in r.json()["message"]
    auth = identity_base.session_auth(token_of(c))
    assert auth["method"] == "password" and auth["verified"] == clock.now and auth["verified_by"] == "password"
    assert send(c, purpose="bind").status_code == 200


def test_reauth_wrong_password_counts_toward_lockout(clock):
    c = TestClient(server.app)
    register(c, name="沈青衫")
    for _ in range(accounts.MAX_FAILURES):
        assert error(c.post("/api/identity/reauth", json={"password": "wrong-pw"})) == accounts.LOGIN_FAILED
    assert error(c.post("/api/identity/reauth", json={"password": "secret-pw"})) == accounts.TOO_MANY_TRIES  # 同一套擋猜
    assert identity_base.session_auth(token_of(c))["verified"] is None


def test_reauth_without_password_uses_a_bound_way(clock):
    from tianxia.features.identity import binding, codes

    c = TestClient(server.app)
    phone_account(c)
    clock.now += server.CONTENT.config.identity.recent_seconds + 1
    r = c.post("/api/identity/reauth", json={})
    assert r.json() == {"message": binding.REAUTH_WAYS, "ways": ["phone"]}
    assert error(send(c, to="0987654321", purpose="reauth")) == codes.NOT_THIS  # 不是這個帳號綁的那一支
    assert error(send(c, channel="email", to="a@b.co", purpose="reauth")) == binding.NO_SUCH_WAY
    assert send(c, purpose="reauth").status_code == 200
    assert "登入驗證碼" in senders.FAKES.sms.outbox[-1][1]  # 重驗用登入那一份字
    assert verify(c).status_code == 200
    auth = identity_base.session_auth(token_of(c))
    assert auth["verified"] == clock.now and auth["verified_by"] == "phone"
    assert binding.recent(auth, clock.now, server.CONTENT.config.identity)


def test_switch_account_asks_once(clock):
    from tianxia.features.identity import binding

    other = TestClient(server.app)
    key = phone_account(other)
    c = TestClient(server.app)
    register(c, name="李白衣")
    old = token_of(c)
    clock.now += 61  # 同一個號碼 60 秒才能再寄
    sent = len(senders.FAKES.sms.outbox)
    assert send(c).json() == {"ask": binding.SWITCH_ASK}  # 已登入：先問
    assert len(senders.FAKES.sms.outbox) == sent  # 問的那一下沒寄
    assert send(c, switch=True).status_code == 200
    assert verify(c).json()["stage"] == "game"
    assert server.SESSIONS.get(token_of(c)) == key and server.SESSIONS.get(old) is None  # 換過去、原本的登出


def test_fake_services_warns_at_start(monkeypatch, capsys):
    monkeypatch.delenv(server.PUBLIC_URL_ENV, raising=False)
    monkeypatch.setattr(server.CONTENT.config.identity, "fake_services", False)
    FEATURE.threads(server)
    assert capsys.readouterr().out == ""
    monkeypatch.setattr(server.CONTENT.config.identity, "fake_services", True)
    FEATURE.threads(server)  # 沒設公開網址：印警告、照常起
    assert "fake_services" in capsys.readouterr().out
    monkeypatch.setenv(server.PUBLIC_URL_ENV, "https://staging.example.test")
    FEATURE.threads(server)  # 不是正式網域：照常起
    assert "fake_services" in capsys.readouterr().out


def test_fake_services_refused_on_the_live_domain(monkeypatch, capsys):
    """公開網址是正式網域（tianxiadashi.com）又開 fake_services：印警告、拒絕啟動；關著照常起。"""
    monkeypatch.setenv(server.PUBLIC_URL_ENV, "https://TianxiaDashi.com")
    monkeypatch.setattr(server.CONTENT.config.identity, "fake_services", True)
    with pytest.raises(SystemExit) as stop:
        FEATURE.threads(server)
    assert str(stop.value) == FAKE_REFUSED
    assert "fake_services" in capsys.readouterr().out
    monkeypatch.setattr(server.CONTENT.config.identity, "fake_services", False)
    FEATURE.threads(server)
    assert capsys.readouterr().out == ""
