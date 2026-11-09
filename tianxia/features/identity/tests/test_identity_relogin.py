"""「請用密碼重新登入」（帳號與客服第 209 批；設計 4.4 最後一條）：GET /api/identity/session 回 {"relogin": bool}，
只有這個帳號在名單上（identity_base.listed）而且這次 session 不夠格（admin_session_ok 假：驗證碼、第三方、密碼登入超過 staff_hours）才真；
名單外永遠假、同一個形狀（本人問自己的帳號，試不出別人）。先 401 再 gate（同 /api/identity/me）。"""
from __future__ import annotations

from fastapi.testclient import TestClient
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import clock, on, phone_account, register  # noqa: F401

import server
from tianxia import database
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.state import BotProfile

BOSS = "段青山"
PATH = "/api/identity/session"
HOURS = 7 * 3600


def _ask(c):
    r = c.get(PATH)
    assert r.status_code == 200, r.text
    return r.json()


def test_listed_code_session_relogin_true(clock, monkeypatch):
    c = TestClient(server.app)
    phone_account(c, name=BOSS)
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS])
    assert c.get("/api/main").json()["admin"] is False
    assert _ask(c) == {"relogin": True}


def test_listed_password_fresh_false(clock, monkeypatch):
    c = TestClient(server.app)
    register(c, "boss_01", "secret-pw-12", name=BOSS)
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS])
    assert _ask(c) == {"relogin": False}


def test_listed_password_7h_true(clock, monkeypatch):
    c = TestClient(server.app)
    register(c, "boss_01", "secret-pw-12", name=BOSS)
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS])
    clock.now += HOURS
    assert _ask(c) == {"relogin": True}
    assert c.post("/api/identity/reauth", json={"password": "secret-pw-12"}).status_code == 200
    assert _ask(c) == {"relogin": False}


def test_unlisted_always_false_same_shape(clock, monkeypatch):
    c = TestClient(server.app)
    phone_account(c, name="沈青衫")
    boss = TestClient(server.app)
    phone_account(boss, to="0987654321", name=BOSS)
    monkeypatch.setattr(server.CONTENT.config, "admins", [BOSS])  # 建好角色才列（玩家不能取管理者的名號）
    r = c.get(PATH)
    listed = boss.get(PATH)
    assert listed.json() == {"relogin": True}
    assert r.json() == {"relogin": False} and set(r.json()) == set(listed.json())
    assert r.headers["content-type"] == listed.headers["content-type"]


def test_session_route_401_then_404_off(fresh_server, key_file, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "off.db")
    assert TestClient(server.app).get(PATH).status_code == 401  # 沒登入先 401（關著也是，同 /api/identity/me）
    c = TestClient(server.app)
    register(c, "shen_01", name="沈青衫")
    assert c.get(PATH).status_code == 404  # 關著：登入了也 404


def test_bot_name_not_revealed(clock, monkeypatch):
    """假人沒有帳號：名單上寫假人的名號，也只有本人問自己的帳號，名單外的真人照樣同一個樣子。"""
    bot = Game.new(server.CONTENT, "botman")
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    CharacterStore(database.open_database()).save(bot.state)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["botman"])
    c = TestClient(server.app)
    phone_account(c, name="沈青衫")
    assert _ask(c) == {"relogin": False}
