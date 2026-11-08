"""LINE、Google 登入（帳號與客服第 202 批；設計 4.2）：假的登入服務（換掉 oauth.HTTP，回造好的 id_token）。
start 回授權網址、發 tx_oauth；回呼比對票與 cookie、驗 id_token；認得的身分直接登入，不認得的不開帳號、只留 pending；
建角色那一步才在同一筆交易開帳號、寫 logins、建角色，共用殼的註冊限制；名號不合格整筆退。關著四條路由 404。"""
from __future__ import annotations

import base64
import json
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

import server
from tianxia import database
from tianxia.accounts import NAME_TAKEN, AccountStore
from tianxia.characters import open_characters
from tianxia.core import identity_base
from tianxia.engine import Game
from tianxia.features.identity import oauth
from tianxia.features.identity import store as idstore
from tianxia.state import BotProfile

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def fresh_server(monkeypatch, tmp_path):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    cfg = server.CONTENT.config.identity
    for name, value in (("enabled", False), ("ways", []), ("redirect_base", ""), ("turnstile_site_key", "")):
        monkeypatch.setattr(cfg, name, value)
    monkeypatch.setattr(server.time, "time", lambda: NOW)
    path = tmp_path / "identity.json"
    path.write_text(json.dumps({"key": "k" * 32, "line": {"client_id": "cid-line", "client_secret": "sec-line"},
                                "google": {"client_id": "cid-google", "client_secret": "sec-google"}}), encoding="utf-8")
    monkeypatch.setattr(identity_base, "KEY_FILE", path)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES, server.REGISTRATIONS):
        store.clear()
    server.WORLD_GAME = None
    yield
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES, server.REGISTRATIONS):
        store.clear()
    server.WORLD_GAME = None


def _turn_on(monkeypatch):
    cfg = server.CONTENT.config.identity
    monkeypatch.setattr(cfg, "enabled", True)
    monkeypatch.setattr(cfg, "ways", ["line", "google"])
    monkeypatch.setattr(cfg, "redirect_base", "https://example.com")


def _token(claims: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJSUzI1NiJ9.{body}.sig"


def _fake_idp(monkeypatch, sub="U-1", **over):
    """假的登入服務：記下每次換 token 的請求，回一張帶這次 nonce 的 id_token（nonce 從授權網址讀，同真的登入服務）。"""
    seen = {"calls": [], "nonce": None, "provider": "line"}

    def post(url, data=None, timeout=None):
        seen["calls"].append((url, dict(data)))
        p = seen["provider"]
        claims = {"iss": oauth.PROVIDERS[p]["iss"][0], "aud": f"cid-{p}", "exp": NOW + 600, "nonce": seen["nonce"], "sub": sub}
        claims.update(over)
        return type("R", (), {"status_code": 200, "json": lambda self: {"id_token": _token(claims)}})()

    monkeypatch.setattr(oauth, "HTTP", post)
    return seen


def _start(c: TestClient, seen: dict, provider="line"):
    r = c.post("/api/identity/start", json={"provider": provider, "purpose": "login"})
    assert r.status_code == 200, r.text
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["url"]).query).items()}
    seen["nonce"], seen["provider"] = q["nonce"], provider
    return q


def _callback(c: TestClient, provider: str, **params):
    return c.get(f"/auth/{provider}/callback", params=params, follow_redirects=False)


def _counts() -> tuple[int, int]:
    with database.open_database().snapshot() as conn:
        return (conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], conn.execute("SELECT COUNT(*) FROM logins").fetchone()[0])


def _side_rows(table: str) -> int:
    with sqlite3.connect(idstore.default_side_path()) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608  表名是測試寫死的


def _pending_client(monkeypatch, sub="U-new", provider="line") -> TestClient:
    _turn_on(monkeypatch)
    seen = _fake_idp(monkeypatch, sub=sub)
    c = TestClient(server.app)
    q = _start(c, seen, provider)
    r = _callback(c, provider, code="c1", state=q["state"])
    assert r.headers["location"] == f"/?auth=new&via={provider}"
    return c


def test_login_key_finds_third_party_accounts_only():
    accounts = AccountStore(database.open_database())
    assert accounts.login_key("line", "U-1") is None
    key = accounts.create_without_password("line", "U-1", "LINE")
    assert accounts.login_key("line", "U-1") == key and accounts.login_key("line", "u-1") is None  # subject 分大小寫
    accounts.register("shen_01", "secret-pw")
    accounts.add_login("shen_01", "google", "G-1", "Google")
    assert accounts.login_key("google", "G-1") == "shen_01"  # 有密碼的帳號鍵照舊是小寫帳號
    assert accounts.login_key("password", "shen_01") is None  # 密碼不走這裡


def test_new_routes_404_while_closed(monkeypatch, tmp_path):
    seen = _fake_idp(monkeypatch)
    anon = TestClient(server.app)
    player = TestClient(server.app)
    player.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    for c in (anon, player):
        assert c.post("/api/identity/start", json={"provider": "line", "purpose": "login"}).status_code == 404
        assert _callback(c, "line", code="c", state="s").status_code == 404
    assert player.post("/api/identity/character", json={"name": "柳如煙"}).status_code == 404
    _turn_on(monkeypatch)
    monkeypatch.setattr(identity_base, "KEY_FILE", tmp_path / "missing.json")  # 開關開著、金鑰讀不到：一樣關著
    assert anon.post("/api/identity/start", json={"provider": "line", "purpose": "login"}).status_code == 404
    assert _callback(anon, "line", code="c", state="s").status_code == 404
    assert player.post("/api/identity/character", json={"name": "柳如煙"}).status_code == 404
    assert seen["calls"] == []


def test_start_returns_url_and_sets_browser_cookie(monkeypatch):
    _turn_on(monkeypatch)
    seen = _fake_idp(monkeypatch)
    c = TestClient(server.app)
    r = c.post("/api/identity/start", json={"provider": "google", "purpose": "login"})
    assert r.status_code == 200 and list(r.json()) == ["url"]
    url = urlsplit(r.json()["url"])
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == oauth.PROVIDERS["google"]["authorize"]
    assert q["client_id"] == "cid-google" and q["redirect_uri"] == "https://example.com/auth/google/callback"
    assert q["code_challenge_method"] == "S256" and q["scope"] == "openid"
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("tx_oauth=") and "HttpOnly" in cookie and "Path=/auth/" in cookie and "samesite=lax" in cookie.lower()
    assert "Max-Age=600" in cookie
    assert _side_rows("oauth_tickets") == 1 and seen["calls"] == []
    for bad in ({"provider": "email", "purpose": "login"}, {"provider": "line", "purpose": "bind"}, {"provider": "nope"}):
        assert c.post("/api/identity/start", json=bad).status_code == 404, bad
    monkeypatch.setattr(server.CONTENT.config.identity, "ways", ["google"])
    assert c.post("/api/identity/start", json={"provider": "line", "purpose": "login"}).status_code == 404  # 不在 ways


def test_start_refuses_when_logged_in(monkeypatch):
    _turn_on(monkeypatch)
    c = TestClient(server.app)
    c.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    r = c.post("/api/identity/start", json={"provider": "line", "purpose": "login"})
    assert r.status_code == 400 and r.json()["error"] == "你已經登入了，要換帳號請先登出"
    assert "set-cookie" not in r.headers


def test_start_throttled_per_ip(monkeypatch):
    _turn_on(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config.identity, "start_per_hour", 2)
    c = TestClient(server.app)
    replies = [c.post("/api/identity/start", json={"provider": "line", "purpose": "login"}) for _ in range(3)]
    assert [r.status_code for r in replies] == [200, 200, 400]
    assert replies[2].json()["error"] == "太頻繁了，請稍後再試"
    monkeypatch.setattr(server.time, "time", lambda: NOW + 3601)
    assert c.post("/api/identity/start", json={"provider": "line", "purpose": "login"}).status_code == 200


def test_callback_existing_login_starts_session(monkeypatch):
    _turn_on(monkeypatch)
    key = AccountStore(database.open_database()).create_without_password("line", "U-1", "LINE")
    server.create_character(key, "柳如煙")
    seen = _fake_idp(monkeypatch, sub="U-1")
    c = TestClient(server.app)
    q = _start(c, seen)
    r = _callback(c, "line", code="code-1", state=q["state"])
    assert r.status_code == 302 and r.headers["location"] == "/?auth=ok"
    url, data = seen["calls"][0]
    assert url == oauth.PROVIDERS["line"]["token"] and data["code"] == "code-1"
    assert data["redirect_uri"] == "https://example.com/auth/line/callback" and data["code_verifier"]
    me = c.get("/api/me").json()
    assert me["stage"] == "game" and me["main"]
    assert "tx_oauth" not in c.cookies


def test_callback_unknown_subject_makes_no_account(monkeypatch):
    before = _counts()
    c = _pending_client(monkeypatch)
    assert _counts() == before
    assert c.cookies.get("tx_pending") and _side_rows("pending") == 1
    assert c.get("/api/me").json()["stage"] == "login"  # 還沒有 session


def test_callback_bad_state_or_cookie_or_claims_fails(monkeypatch):
    _turn_on(monkeypatch)
    seen = _fake_idp(monkeypatch)
    c = TestClient(server.app)
    q = _start(c, seen)
    assert _callback(c, "line", code="c", state="wrong").headers["location"] == "/?auth=fail"
    assert _callback(c, "google", code="c", state=q["state"]).headers["location"] == "/?auth=fail"  # 票是 line 的
    assert _callback(c, "line", code="c", state=q["state"]).headers["location"] == "/?auth=fail"  # 上一次已經作廢
    other = TestClient(server.app)
    q = _start(c, seen)
    assert _callback(other, "line", code="c", state=q["state"]).headers["location"] == "/?auth=fail"  # 別的瀏覽器（沒有 tx_oauth）
    for over in ({"aud": "cid-x"}, {"iss": "https://evil.example"}, {"exp": NOW - 1}, {"nonce": "x"}, {"sub": ""}):
        bad = _fake_idp(monkeypatch, **over)
        q = _start(c, bad)
        assert _callback(c, "line", code="c", state=q["state"]).headers["location"] == "/?auth=fail", over
        assert len(bad["calls"]) == 1
    seen = _fake_idp(monkeypatch)
    q = _start(c, seen)
    monkeypatch.setattr(server.time, "time", lambda: NOW + 601)  # 票過期（ticket_seconds 600）
    assert _callback(c, "line", code="c", state=q["state"]).headers["location"] == "/?auth=fail" and seen["calls"] == []
    assert _counts() == (0, 0) and _side_rows("pending") == 0
    assert _callback(c, "nope", code="c", state="s").status_code == 404


def test_cancel_goes_back_with_auth_cancel(monkeypatch):
    _turn_on(monkeypatch)
    seen = _fake_idp(monkeypatch)
    c = TestClient(server.app)
    q = _start(c, seen)
    r = _callback(c, "line", error="access_denied", state=q["state"])
    assert r.headers["location"] == "/?auth=cancel" and seen["calls"] == []
    assert _side_rows("oauth_tickets") == 0  # 票照樣作廢


def test_character_opens_account_and_login_in_one_go(monkeypatch):
    c = _pending_client(monkeypatch, sub="U-77")
    r = c.post("/api/identity/character", json={"name": "柳如煙", "gender": "女"})
    assert r.status_code == 200 and r.json()["stage"] == "game"
    accounts = AccountStore(database.open_database())
    key = accounts.login_key("line", "U-77")
    assert key and key.startswith("id:") and accounts.owner_of("柳如煙") == key
    with database.open_database().snapshot() as conn:
        assert [tuple(r) for r in conn.execute("SELECT provider, subject, display FROM logins")] == [("line", "U-77", "LINE")]
    side = idstore.IdentityStore()
    want = identity_base.subject_hmac(b"k" * 32, "line", "U-77")
    assert side.verified_at(accounts.account_id(key), "line") == NOW
    with sqlite3.connect(side.path) as conn:
        assert conn.execute("SELECT subject_hmac FROM bindings_meta").fetchall() == [(want,)]
    assert _side_rows("pending") == 0 and "tx_pending" not in c.cookies
    assert c.get("/api/me").json()["stage"] == "game"
    assert server.game_for("柳如煙").state.player.gender == "女"


def test_character_bad_name_leaves_no_account(monkeypatch):
    c = _pending_client(monkeypatch)
    taken = TestClient(server.app)
    taken.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    taken.post("/api/character", json={"name": "沈青衫"})
    before = _counts()
    for name, why in (("沈青衫", NAME_TAKEN), ("", "請先輸入你的名號。"), ("id:9", NAME_TAKEN), ("客服", NAME_TAKEN)):
        r = c.post("/api/identity/character", json={"name": name})
        assert r.status_code == 400 and r.json()["error"] == why, name
        assert _counts() == before, name
    assert _side_rows("pending") == 1  # 還能再試
    assert c.post("/api/identity/character", json={"name": "柳如煙"}).json()["stage"] == "game"


def test_character_respects_register_limit(monkeypatch):
    for i in range(server.REGISTER_LIMIT):
        r = TestClient(server.app).post("/api/register", json={"login": f"shen_{i}x", "password": "secret-pw", "again": "secret-pw"})
        assert r.status_code == 200
    c = _pending_client(monkeypatch)
    before = _counts()
    r = c.post("/api/identity/character", json={"name": "柳如煙"})
    assert r.status_code == 400 and r.json()["error"] == server.TOO_MANY_REGISTERS and _counts() == before
    server.REGISTRATIONS.clear()
    for i in range(server.REGISTER_LIMIT - 1):
        TestClient(server.app).post("/api/register", json={"login": f"wei_{i}x", "password": "secret-pw", "again": "secret-pw"})
    assert c.post("/api/identity/character", json={"name": "柳如煙"}).status_code == 200  # 第五個是第三方開的
    r = TestClient(server.app).post("/api/register", json={"login": "late_1", "password": "secret-pw", "again": "secret-pw"})
    assert r.json()["error"] == server.TOO_MANY_REGISTERS  # 反過來也算


def test_character_without_pending_is_401_and_double_submit_is_idempotent(monkeypatch):
    _turn_on(monkeypatch)
    anon = TestClient(server.app)
    r = anon.post("/api/identity/character", json={"name": "柳如煙"})
    assert r.status_code == 401 and r.json()["detail"] == "請先登入。"
    anon.cookies.set("tx_pending", "forged", path="/api/identity/")
    assert anon.post("/api/identity/character", json={"name": "柳如煙"}).status_code == 401
    player = TestClient(server.app)
    player.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    r = player.post("/api/identity/character", json={"name": "柳如煙"})
    assert r.status_code == 401 and r.json()["detail"] == "請先登入。"
    c = _pending_client(monkeypatch, sub="U-9")
    pending = c.cookies.get("tx_pending")
    # 連按兩次的第二下：第一下已經開好帳號（身分查得到），pending 還在。不再開一個，直接登入
    key = AccountStore(database.open_database()).create_without_password("line", "U-9", "LINE")
    server.create_character(key, "柳如煙")
    before = _counts()
    r = c.post("/api/identity/character", json={"name": "別的名號"})
    assert r.status_code == 200 and r.json()["stage"] == "game" and _counts() == before
    again = TestClient(server.app)
    again.cookies.set("tx_pending", pending, path="/api/identity/")
    assert again.post("/api/identity/character", json={"name": "別的名號"}).status_code == 401  # 用過就作廢
    assert _counts() == before


def test_bot_name_and_human_name_refused_alike(monkeypatch):
    bot = Game.new(server.CONTENT, "周泰安")
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    open_characters().save(bot.state)
    human = TestClient(server.app)
    human.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    human.post("/api/character", json={"name": "沈青衫"})
    c = _pending_client(monkeypatch)
    a = c.post("/api/identity/character", json={"name": "周泰安"})
    b = c.post("/api/identity/character", json={"name": "沈青衫"})
    assert (a.status_code, a.content) == (b.status_code, b.content) and a.status_code == 400 and a.json() == {"error": NAME_TAKEN}


def test_me_has_identity_flag_only_when_open(monkeypatch):
    c = TestClient(server.app)
    off = [c.get("/api/me").content]
    c.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    off.append(c.get("/api/me").content)
    assert off == [b'{"stage":"login"}', b'{"stage":"create"}']  # 關著：跟第 201 批逐位元組一樣
    _turn_on(monkeypatch)
    assert c.get("/api/me").json() == {"stage": "create", "identity": True}
    assert TestClient(server.app).get("/api/me").json() == {"stage": "login", "identity": True}
    assert "identity" not in c.post("/api/character", json={"name": "沈青衫"}).json()  # 只有 /api/me 帶
