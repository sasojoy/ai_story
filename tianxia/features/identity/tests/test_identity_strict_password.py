"""identity 開著時全體密碼至少 12 字（帳號與客服第 209 批；企劃者 2026-11-09「1 不改，2 選 A」的 A）：
註冊、改密碼、補設密碼、忘記密碼、管理者重設、scripts/set_password.py 六條路都只看 identity 開沒開、不看名單，
名單上與名單外同一句（註冊頁試不出名單）；現有的短密碼照登入；identity 關著六條路照 base（PASSWORD_MIN）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_identity_bind import _pw
from test_identity_password import _phone_login, _set
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import bind, clock, error, on, phone_account, register  # noqa: F401

import server
from tianxia import accounts, database
from tianxia.accounts import AccountStore
from tianxia.core import identity_base

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
import set_password  # noqa: E402

ELEVEN = "abcdefghijk"
TWELVE = "abcdefghijkl"
LONG = "secret-pw-long"
HOUR = 3600


@pytest.fixture(autouse=True)
def _many_registers(monkeypatch):
    monkeypatch.setattr(server, "REGISTER_LIMIT", 50)  # 一條測試開好幾個帳號


def _register(login, pw):
    return TestClient(server.app).post("/api/register", json={"login": login, "password": pw, "again": pw})


def _change(pw, login="chg_01"):
    c = TestClient(server.app)
    register(c, login, LONG)
    return c.post("/api/password", json={"old": LONG, "new": pw, "again": pw}).json()["message"]


def _boss(monkeypatch):
    c = TestClient(server.app)
    register(c, "boss_01", LONG, name="段青山")
    monkeypatch.setattr(server.CONTENT.config, "admins", ["段青山"])
    return c


def _admin_reset(monkeypatch, pw, target="shen_01"):
    register(TestClient(server.app), target, LONG, name="沈青衫")
    return _boss(monkeypatch).post("/api/admin/reset_password", json={"target": target, "temp": pw}).json()["message"]


def _phone_set(pw):
    c = TestClient(server.app)
    phone_account(c, to="0922333444", name="李白衣")
    return c, _set(c, "set_01", new=pw)


def _reset_flow(clock, pw):
    c = TestClient(server.app)
    _pw(c, login="rst_01", name="王鐵心")
    bind(c, to="0933444555")
    clock.now += 73 * HOUR
    d = TestClient(server.app)
    from test_identity_session import send, verify
    assert send(d, to="0933444555", switch=True).status_code == 200
    assert verify(d).json()["stage"] == "game"
    return d.post("/api/identity/password/reset", json={"new": pw, "again": pw})


def _script(monkeypatch, tmp_path, pw, login="Rayal", on_=True):
    content = server.CONTENT
    if on_:
        key = tmp_path / "identity.json"
        key.write_text(json.dumps({"key": "k" * 32}), encoding="utf-8")
        monkeypatch.setattr(identity_base, "KEY_FILE", key)
    monkeypatch.setattr(set_password, "load_content", lambda *a, **k: content)
    monkeypatch.setattr(set_password.secrets, "token_urlsafe", lambda n: pw)
    return set_password.main([login, "--db", str(tmp_path / "s.db"), "--local-dir", str(tmp_path / "local")])


def test_six_paths_refuse_11_on(clock, monkeypatch, tmp_path, capsys):
    short = accounts.STRICT_SHORT_PASSWORD
    assert error(_register("reg_01", ELEVEN)) == short
    assert _change(ELEVEN) == short
    assert error(_phone_set(ELEVEN)[1]) == short
    assert error(_reset_flow(clock, ELEVEN)) == short
    assert _admin_reset(monkeypatch, ELEVEN) == short
    capsys.readouterr()
    assert _script(monkeypatch, tmp_path, ELEVEN, login="someone") == 1
    assert capsys.readouterr().out.strip() == short
    assert short == "密碼至少 12 字。"


def test_listed_and_unlisted_same_sentence(clock, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "admins", ["Rayal"])
    a = _register("rayal", ELEVEN)
    b = _register("plain_01", ELEVEN)
    assert (a.status_code, a.json()) == (b.status_code, b.json()) == (400, {"error": accounts.STRICT_SHORT_PASSWORD})


def test_twelve_passes_everywhere(clock, monkeypatch, tmp_path):
    assert _register("reg_01", TWELVE).status_code == 200
    assert _change(TWELVE) == "密碼已更新。"
    assert _phone_set(TWELVE)[1].status_code == 200
    assert _reset_flow(clock, TWELVE).status_code == 200
    assert _admin_reset(monkeypatch, TWELVE).startswith("已重設")
    assert _script(monkeypatch, tmp_path, TWELVE, login="someone") == 0


def test_off_eight_still_passes(monkeypatch, tmp_path, fresh_server):  # noqa: F811
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "g.db"))
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "g.db")
    assert server.CONTENT.config.identity.enabled is False
    eight = "abcdefgh"
    assert _register("reg_01", eight).status_code == 200
    assert _change(eight) == "密碼已更新。"
    assert _admin_reset(monkeypatch, eight).startswith("已重設")
    assert _script(monkeypatch, tmp_path, eight, on_=False) == 0
    assert error(_register("reg_02", "12345")) == accounts.SHORT_PASSWORD  # 關著照 base 那一句
    assert TestClient(server.app).post("/api/identity/password/set", json={}).status_code in (401, 404)


def test_short_password_still_logs_in(clock):
    store = AccountStore(database.open_database())
    store.register("old_01", "short-pw")  # 開 identity 之前設的 8 字
    r = TestClient(server.app).post("/api/login", json={"login": "old_01", "password": "short-pw"})
    assert r.status_code == 200
