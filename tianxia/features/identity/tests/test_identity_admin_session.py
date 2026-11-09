"""管理者這一半的 session 與名單上的帳號 12 字（帳號與客服第 207 批；設計 4.4 最後一條、第七節第 207 批那兩列）：
名單上的角色用驗證碼或第三方進來的 session、或密碼登入超過 staff_hours 沒重驗的，/api/main 的 admin 是假、管理者的路都拒（跟不是管理者同一句）；
重驗之後回來；identity 關著一個字不變。名單上的帳號開著時註冊、改密碼、管理者重設、scripts/set_password.py 都要 12 字；舊的短密碼照登入。"""
from __future__ import annotations

import re

from fastapi.testclient import TestClient
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import (  # noqa: F401
    Clock, clock, code_of, error, on, phone_account, register, send, token_of, verify,
)

import server
from tianxia import accounts, database
from tianxia.accounts import AccountStore
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.state import BotProfile

BOSS = "段青山"
NOT_ADMIN = "只有管理者能這麼做。"
NO_RESET = "（只有管理者能重設密碼。）"
HOURS = 7 * 3600


def _say(r) -> str:
    """/api/do 回的 message 是 md 轉過的 HTML：拿掉標籤。"""
    return re.sub(r"<[^>]+>", "", r.json()["message"]).strip()


def _boss(monkeypatch, password="secret-pw-12"):
    """密碼登入的管理者（建好角色才列：玩家不能取管理者的名號）。"""
    c = TestClient(server.app)
    register(c, "boss_01", password, name=BOSS)
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS])
    return c


def _answers(c) -> dict:
    """管理者的每一條路各打一次，回應攤成可以逐字比的樣子。"""
    out = {
        "main_admin": c.get("/api/main").json()["admin"],
        "admin": c.get("/api/admin").status_code,
        "player": c.post("/api/admin/player", json={"name": "沈青衫"}).status_code,
        "accounts": c.post("/api/admin/accounts", json={"q": "boss"}).status_code,
        "reset": c.post("/api/admin/reset_password", json={"target": "shen_01", "temp": "temp-pass-123"}).json()["message"],
        "id_accounts": c.post("/api/identity/admin/accounts", json={"q": "boss"}).status_code,
    }
    for op in ("pause_clock", "identity_view", "identity_unbind", "identity_delete"):
        r = c.post(f"/api/do/{op}", json={"target": "shen_01", "provider": "phone"})
        out[op] = (r.status_code, r.json().get("error"))
    return out


REFUSED = {
    "main_admin": False, "admin": 403, "player": 403, "accounts": 403, "reset": NO_RESET, "id_accounts": 403,
    "pause_clock": (400, NOT_ADMIN), "identity_view": (400, NOT_ADMIN), "identity_unbind": (400, NOT_ADMIN),
    "identity_delete": (400, NOT_ADMIN),
}


def _player(c):
    register(c, "shen_01", name="沈青衫")


# ── 驗證碼進來的管理者 ─────────────────────────────


def test_code_login_admin_flag_false(clock, monkeypatch):
    c = TestClient(server.app)
    phone_account(c, name=BOSS)
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS])
    assert c.get("/api/main").json()["admin"] is False
    assert c.get("/api/me").json()["main"]["admin"] is False
    c.post("/api/logout")
    clock.now += 61  # 同一個號碼 60 秒才能再寄
    assert send(c).status_code == 200
    r = verify(c)
    assert r.json()["stage"] == "game" and r.json()["main"]["admin"] is False


def test_code_login_admin_refused_everywhere(clock, monkeypatch):
    _player(TestClient(server.app))
    c = TestClient(server.app)
    phone_account(c, to="0987654321", name=BOSS)
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS])
    got = _answers(c)
    plain = TestClient(server.app)
    register(plain, "ma_01", name="馬伯庸")
    assert got == REFUSED == _answers(plain)  # 跟不是管理者逐字一樣
    assert accounts.AccountStore(database.open_database()).authenticate("shen_01", "secret-pw-12") is not None  # 沒被重設


# ── 密碼登入的管理者 ───────────────────────────────


def test_password_login_admin_flag_true_on_first_screen(clock, monkeypatch):
    c = _boss(monkeypatch)
    c.post("/api/logout")
    r = c.post("/api/login", json={"login": "boss_01", "password": "secret-pw-12"})
    assert r.json()["main"]["admin"] is True  # 登入回應不經 _game：_start_session 那一下要設好 token
    assert c.get("/api/me").json()["main"]["admin"] is True
    assert c.get("/api/main").json()["admin"] is True
    assert c.get("/api/admin").status_code == 200
    assert c.post("/api/do/pause_clock", json={}).status_code == 200


def test_password_login_7h_old_refused_then_reauth_restores(clock, monkeypatch):
    _player(TestClient(server.app))
    c = _boss(monkeypatch)
    clock.now += HOURS
    assert _answers(c) == REFUSED
    r = c.post("/api/identity/reauth", json={"password": "secret-pw-12"})
    assert r.status_code == 200, r.text
    assert c.get("/api/main").json()["admin"] is True
    assert c.get("/api/admin").status_code == 200
    assert c.post("/api/identity/admin/accounts", json={"q": "boss"}).status_code == 200
    assert c.post("/api/do/identity_view", json={"target": "shen_01"}).status_code == 200
    assert c.post("/api/admin/reset_password", json={"target": "shen_01", "temp": "temp-pass-123"}).json()["message"] != NO_RESET


def test_admin_off_bytes_unchanged(monkeypatch, key_file, tmp_path):  # noqa: F811
    """identity 關著：驗證碼的路 404；密碼登入 7 小時前的管理者照舊是管理者（不看 session 的時間）。"""
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "g.db")
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "g.db"))
    tick = Clock(server.time.time())
    monkeypatch.setattr(server, "time", tick)
    _player(TestClient(server.app))
    c = _boss(monkeypatch)
    tick.now += HOURS
    assert send(c).status_code == 404
    assert c.get("/api/main").json()["admin"] is True
    assert c.get("/api/me").json()["main"]["admin"] is True
    assert c.get("/api/admin").status_code == 200
    assert c.post("/api/admin/accounts", json={"q": "boss"}).status_code == 200
    assert c.post("/api/do/pause_clock", json={}).status_code == 200
    assert c.post("/api/admin/reset_password", json={"target": "shen_01", "temp": "temp-pass"}).json()["message"].startswith("已重設")
    assert c.post("/api/password", json={"old": "secret-pw-12", "new": "short-1", "again": "short-1"}).json()["message"] == "密碼已更新。"
    r = TestClient(server.app).post("/api/register", json={"login": BOSS_LOGIN, "password": "secret-pw", "again": "secret-pw"})
    assert r.status_code == 200  # 關著：名單上的帳號名 9 字照註冊
    assert not (tmp_path / "g-identity.sqlite").exists()


# ── 12 字（第 207 批只對名單上的帳號；第 209 批起 identity 開著全體：名單上與名單外同一句）──

BOSS_LOGIN = "Rayal"


def test_register_listed_login_needs_12(clock, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS_LOGIN])
    c = TestClient(server.app)
    r = c.post("/api/register", json={"login": "rayal", "password": "secret-pw-1", "again": "secret-pw-1"})
    assert error(r) == accounts.STRICT_SHORT_PASSWORD
    r = c.post("/api/register", json={"login": "shen_01", "password": "secret-pw-1", "again": "secret-pw-1"})
    assert error(r) == accounts.STRICT_SHORT_PASSWORD  # 第 209 批：名單外同一句
    r = TestClient(server.app).post("/api/register", json={"login": "rayal", "password": "a-long-password", "again": "a-long-password"})
    assert r.status_code == 200


def test_change_password_listed_needs_12(clock, monkeypatch):
    c = _boss(monkeypatch)
    out = c.post("/api/password", json={"old": "secret-pw-12", "new": "other-pw-1", "again": "other-pw-1"}).json()["message"]
    assert out == accounts.STRICT_SHORT_PASSWORD
    out = c.post("/api/password", json={"old": "secret-pw-12", "new": "a-long-password", "again": "a-long-password"}).json()["message"]
    assert out == "密碼已更新。"
    p = TestClient(server.app)
    _player(p)
    assert p.post("/api/password", json={"old": "secret-pw-12", "new": "other-pw-1", "again": "other-pw-1"}).json()["message"] == \
        accounts.STRICT_SHORT_PASSWORD  # 第 209 批：名單外同一句


def test_admin_reset_listed_needs_12(clock, monkeypatch):
    other = TestClient(server.app)
    register(other, "boss_02", name="段紅袖")
    _player(TestClient(server.app))
    c = _boss(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS, "段紅袖"])
    assert c.post("/api/admin/reset_password", json={"target": "boss_02", "temp": "temp-pass"}).json()["message"] == \
        accounts.STRICT_SHORT_PASSWORD
    assert c.post("/api/admin/reset_password", json={"target": "段紅袖", "temp": "temp-pass-1234"}).json()["message"].startswith("已重設")
    assert c.post("/api/admin/reset_password", json={"target": "shen_01", "temp": "temp-pass"}).json()["message"] == \
        accounts.STRICT_SHORT_PASSWORD  # 第 209 批：名單外同一句


def test_listed_short_password_still_logs_in(clock, monkeypatch):
    AccountStore(database.open_database()).register("boss_01", "secret-pw")  # 9 字（開 identity、列進名單之前設的）
    monkeypatch.setattr(server.CONTENT.config, "admins", ["boss_01"])
    r = TestClient(server.app).post("/api/login", json={"login": "boss_01", "password": "secret-pw"})
    assert r.status_code == 200


def test_bot_names_not_revealed_by_password_rule(clock):
    bot = Game.new(server.CONTENT, "botman")
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    CharacterStore(database.open_database()).save(bot.state)
    a = TestClient(server.app).post("/api/register", json={"login": "botman", "password": "secret-pw-12", "again": "secret-pw-12"})
    b = TestClient(server.app).post("/api/register", json={"login": "plain_1", "password": "secret-pw-12", "again": "secret-pw-12"})
    assert (a.status_code, a.json()) == (b.status_code, b.json()) == (200, {"stage": "create"})


# ── M 波：商城、形象那兩條唯讀的管理者頁也問 admin_session_ok（第 207 批留下）──


def _shop_admin(c) -> tuple[int, int]:
    return (c.post("/api/admin/mall", json={"name": "沈青衫"}).status_code, c.get("/api/admin/looks").status_code)


def _mall_on(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.mall, "enabled", True)
    assert server.CONTENT.looks  # 形象的頁要內容裡至少一套


def test_code_login_admin_refused_on_mall_and_looks(clock, monkeypatch):
    _mall_on(monkeypatch)
    _player(TestClient(server.app))
    c = TestClient(server.app)
    phone_account(c, to="0987654321", name=BOSS)
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS])
    plain = TestClient(server.app)
    register(plain, "ma_01", name="馬伯庸")
    assert _shop_admin(c) == (403, 403) == _shop_admin(plain)
    boss = TestClient(server.app)
    register(boss, "boss_09", "a-long-password", name="段紅袖")
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS, "段紅袖"])
    assert _shop_admin(boss) == (200, 200)  # 密碼登入、剛登入的照舊進得去
    clock.now += HOURS
    assert _shop_admin(boss) == (403, 403)


def test_mall_and_looks_admin_off_unchanged(monkeypatch, key_file, tmp_path):  # noqa: F811
    """identity 關著：密碼登入 7 小時前的管理者照舊看得到商城與形象的管理頁。"""
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "g.db")
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "g.db"))
    tick = Clock(server.time.time())
    monkeypatch.setattr(server, "time", tick)
    _mall_on(monkeypatch)
    _player(TestClient(server.app))
    c = _boss(monkeypatch)
    tick.now += HOURS
    assert _shop_admin(c) == (200, 200)
    assert not (tmp_path / "g-identity.sqlite").exists()
