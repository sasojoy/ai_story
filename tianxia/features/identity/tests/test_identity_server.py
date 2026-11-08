"""帳號綁定的伺服器那一側（帳號與客服第 201 批）：/api/identity/gate 關著 404、開著回設定；舊的帳號密碼流程逐字不變；
沒有密碼的帳號（id:<n>）建得了角色、進得了遊戲；開著時擋客服與 id: 開頭的名號，回同一句。"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import server
from tianxia import database
from tianxia.accounts import NAME_TAKEN, AccountStore
from tianxia.core import identity_base


@pytest.fixture(autouse=True)
def fresh_server(monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})  # 這裡測的不是密碼
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config.identity, "enabled", False)
    monkeypatch.setattr(server.CONTENT.config.identity, "ways", [])
    monkeypatch.setattr(server.CONTENT.config.identity, "redirect_base", "")
    monkeypatch.setattr(server.CONTENT.config.identity, "turnstile_site_key", "")
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES, server.REGISTRATIONS):
        store.clear()
    server.WORLD_GAME = None
    yield
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES, server.REGISTRATIONS):
        store.clear()
    server.WORLD_GAME = None


@pytest.fixture
def key_file(tmp_path, monkeypatch):
    path = tmp_path / "identity.json"
    path.write_text(json.dumps({"key": "k" * 32, "line": {"client_id": "cid-line", "client_secret": "sec-line"}}), encoding="utf-8")
    monkeypatch.setattr(identity_base, "KEY_FILE", path)
    return path


def _turn_on(monkeypatch):
    cfg = server.CONTENT.config.identity
    monkeypatch.setattr(cfg, "enabled", True)
    monkeypatch.setattr(cfg, "ways", ["line", "google", "email", "phone"])
    monkeypatch.setattr(cfg, "redirect_base", "https://example.com")
    monkeypatch.setattr(cfg, "turnstile_site_key", "0x4AAA")


def test_gate_is_404_while_closed(key_file):
    assert TestClient(server.app).get("/api/identity/gate").status_code == 404


def test_gate_is_404_without_the_key(monkeypatch, tmp_path):
    _turn_on(monkeypatch)
    monkeypatch.setattr(identity_base, "KEY_FILE", tmp_path / "missing.json")
    assert TestClient(server.app).get("/api/identity/gate").status_code == 404


def test_gate_lists_ready_ways_and_turnstile(monkeypatch, key_file):
    """line、google 要備好（oauth.ready：金鑰兩欄、redirect_base）才列；email、phone 照設定列（按了照舊尚未開放）。不帶客服信箱（第 202 批）。"""
    _turn_on(monkeypatch)
    want = {"ways": ["line", "email", "phone"], "turnstile": "0x4AAA"}  # google 的金鑰沒寫
    anon = TestClient(server.app).get("/api/identity/gate")
    assert anon.status_code == 200 and anon.json() == want
    player = TestClient(server.app)
    player.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    assert player.get("/api/identity/gate").content == anon.content  # 跟誰來問無關


def _flow() -> list[tuple[int, str]]:
    """註冊、看自己、錯密碼、登入、改密碼、登出：每一步的狀態碼與回應原文。"""
    c = TestClient(server.app)
    out = []
    for method, path, body in (
        ("get", "/api/me", None),
        ("post", "/api/register", {"login": "Shen_01", "password": "secret-pw", "again": "secret-pw"}),
        ("get", "/api/me", None),
        ("post", "/api/password", {"old": "nope-nope", "new": "new-secret", "again": "new-secret"}),
        ("post", "/api/password", {"old": "secret-pw", "new": "new-secret", "again": "new-secret"}),
        ("post", "/api/logout", None),
        ("post", "/api/login", {"login": "shen_01", "password": "secret-pw"}),
        ("post", "/api/login", {"login": "id:1", "password": "secret-pw"}),
        ("post", "/api/login", {"login": "SHEN_01", "password": "new-secret"}),
        ("get", "/api/me", None),
        ("post", "/api/register", {"login": "shen_01", "password": "secret-pw", "again": "secret-pw"}),
    ):
        r = c.get(path) if method == "get" else c.post(path, json=body or {})
        out.append((r.status_code, r.text))
    return out


def test_old_password_flows_are_byte_identical(monkeypatch, key_file, tmp_path):
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "off.db")
    off = _flow()
    for store in (server.LOGIN_FAILURES, server.REGISTRATIONS):
        store.clear()
    _turn_on(monkeypatch)
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "on.db")
    on = _flow()
    assert on == off
    assert off[0] == (200, '{"stage":"login"}') and off[2] == (200, '{"stage":"create"}')
    assert json.loads(off[6][1])["error"] == "帳號或密碼不對。"
    assert json.loads(off[7][1])["error"] == "帳號或密碼不對。"
    assert json.loads(off[3][1])["message"] == "舊密碼不對。"


def test_switch_off_routes_404_and_pages_do_not_move(monkeypatch, key_file):
    """關著：這一包的路由 404；/、/api/me、/api/main 跟開著時逐位元組一樣（開關只管 /api/identity/*）。/ 上這一包只多 script 與 link 兩行。"""
    import time

    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)
    c = TestClient(server.app)
    c.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    c.post("/api/character", json={"name": "沈青衫"})
    paths = [p for p in server.app.openapi()["paths"] if p.startswith("/api/identity")]
    assert paths == ["/api/identity/gate"]
    off = [c.get(p) for p in ("/", "/api/me", "/api/main")]
    assert all(c.get(p).status_code == 404 for p in paths)
    _turn_on(monkeypatch)
    on = [c.get(p) for p in ("/", "/api/me", "/api/main")]
    assert [r.content for r in on] == [r.content for r in off] and all(r.status_code == 200 for r in off)
    page = off[0].text
    assert [ln.strip() for ln in page.splitlines() if "identity" in ln] == [
        '<link rel="stylesheet" href="/static/identity.css?v=' + server.asset_version("/static/identity.css") + '">',
        '<script src="/static/identity.js?v=' + server.asset_version("/static/identity.js") + '"></script>',
    ]


def test_old_saves_load_and_the_package_claims_no_fields(game):
    from tianxia.characters import CharacterStore
    from tianxia.features.identity import FEATURE

    assert FEATURE.player_fields == () and FEATURE.carried == () and FEATURE.prefix is None
    store = CharacterStore(game.world.db)
    store.save(game.state)
    assert store.load(game.state.player.name).model_dump() == game.state.model_dump()


def _passwordless_client() -> tuple[TestClient, str]:
    key = AccountStore(database.open_database()).create_without_password("line", "U-test-1", "LINE")
    c = TestClient(server.app)
    c.cookies.set(server.COOKIE, server.SESSIONS.create(key))
    return c, key


def test_id_account_reaches_main():
    c, key = _passwordless_client()
    assert c.get("/api/me").json() == {"stage": "create"}
    r = c.post("/api/character", json={"name": "柳如煙"})
    assert r.status_code == 200 and r.json()["stage"] == "game"
    assert c.get("/api/main").status_code == 200
    assert AccountStore(database.open_database()).owner_of("柳如煙") == key


def test_staff_and_id_names_blocked_only_when_on(monkeypatch, key_file):
    names = ("客服", "GM", "id:3")
    for name in names:
        assert not server.name_taken(name), name  # 關著照舊能取
    _turn_on(monkeypatch)
    for i, name in enumerate(names):
        c = TestClient(server.app)
        c.post("/api/register", json={"login": f"shen_{i}x", "password": "secret-pw", "again": "secret-pw"})
        r = c.post("/api/character", json={"name": name})
        assert r.status_code == 400 and r.json()["error"] == NAME_TAKEN, name
    taken = TestClient(server.app)
    taken.post("/api/register", json={"login": "shen_9x", "password": "secret-pw", "again": "secret-pw"})
    taken.post("/api/character", json={"name": "沈青衫"})
    again = TestClient(server.app)
    again.post("/api/register", json={"login": "shen_8x", "password": "secret-pw", "again": "secret-pw"})
    assert again.post("/api/character", json={"name": "沈青衫"}).json()["error"] == NAME_TAKEN  # 同一句
