"""客服查帳號（帳號與客服第 212 批；設計 6.3）：只收完整帳號、Email、手機（比對 HMAC），要帶單號，每位客服每小時 lookup_hourly 次，
每次留紀錄（含查無；只存遮好的字），紀錄沒有路由改得到；看單時單上的帳號帶出帳號卡（不算次數、照樣留紀錄）；假人查起來跟沒有這個人一樣。"""
from __future__ import annotations

import contextlib
import json
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

from tianxia.accounts import AccountStore
from tianxia.characters import name_key, open_characters
from tianxia.core import identity_base
from tianxia.database import open_database
from tianxia.engine import Game
from tianxia.features.support import routes, rules
from tianxia.state import BotProfile
from tianxia.wallet import Wallet

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]

KEY = "k" * 24
EMAIL, PHONE = "Shen.Qing+game@Gmail.com", "0912-345-678"
BOT = "莫問天"


def _id_key_client(provider="line", subject="U-line-1", display="LINE 使用者") -> tuple[TestClient, str]:
    """沒有密碼列的帳號（第三方或驗證碼開的，帳號鍵 id:<n>），直接發一張登入狀態。"""
    key = AccountStore(open_database()).create_without_password(provider, subject, display)
    c = TestClient(server.app, raise_server_exceptions=False)
    c.cookies.set(server.COOKIE, server.SESSIONS.create(key))
    return c, key


@pytest.fixture
def keyed(monkeypatch, tmp_path):
    """identity 開著、金鑰在暫存檔：Email、手機才查得到。"""
    path = tmp_path / "identity.json"
    path.write_text(json.dumps({"key": KEY}), encoding="utf-8")
    monkeypatch.setattr(identity_base, "KEY_FILE", path)
    monkeypatch.setattr(server.CONTENT.config.identity, "enabled", True)
    return KEY.encode()


def _desk(monkeypatch):
    """沈青衫（shen_01）送了一張單；客服青衣（kefu_01）。回 (客服, 單號)。"""
    shen = player()
    tid = ticket(shen).json()["id"]
    return staffer(monkeypatch), tid


def _bind(key: bytes, provider: str, value: str, login="shen_01"):
    norm = identity_base.normalize_email(value) if provider == "email" else identity_base.normalize_phone(value)
    shown = identity_base.mask_email(norm) if provider == "email" else identity_base.mask_phone(norm)
    AccountStore(open_database()).add_login(login, provider, identity_base.subject_hmac(key, provider, norm), shown)


def _look(c, tid, kind, text):
    return c.post("/api/support/lookup", json={"id": tid, "kind": kind, "text": text})


def _log() -> list[dict]:
    with contextlib.closing(sqlite3.connect(sidecar())) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM lookups ORDER BY id")]


def test_id_key_account_sends_ticket():
    c, key = _id_key_client()
    r = ticket(c)
    assert r.status_code == 200, r.text
    mine = c.get("/api/support/mine").json()["tickets"]
    assert [t["id"] for t in mine] == [r.json()["id"]]


def test_lookup_by_full_login_brings_card(monkeypatch):
    s, tid = _desk(monkeypatch)
    w = Wallet(open_database())
    owner = name_key("沈青衫")
    w.post(owner, 3000, "grant", "grant:test:1", time=1_762_000_000.0, note="封測")
    w.post(owner, -300, "buy", "buy:test:1", time=1_762_100_000.0)
    r = _look(s, tid, "login", "  SHEN_01 ")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["found"] is True and out["message"] == "" and out["left"] == server.CONTENT.config.support.lookup_hourly - 1
    card = out["card"]
    assert card["login"] == "shen_01" and card["character"] == "沈青衫" and card["balance"] == 2700
    assert [(b["provider"], b["name"], b["shown"]) for b in card["binds"]] == [("password", "密碼", "")]
    assert [(e["delta"], e["reason"], e["note"]) for e in card["ledger"]] == [(-300, "購買", ""), (3000, "封測發放", "封測")]


def test_card_without_character_has_empty_ledger(monkeypatch):
    s, tid = _desk(monkeypatch)
    c = TestClient(server.app, raise_server_exceptions=False)
    c.post("/api/register", json={"login": "wu_09", "password": "secret-pw-12", "again": "secret-pw-12"})
    card = _look(s, tid, "login", "wu_09").json()["card"]
    assert card["character"] is None and card["ledger"] == [] and card["balance"] == 0


def test_lookup_takes_no_partial_name_or_id_key(monkeypatch):
    s, tid = _desk(monkeypatch)
    shen_id = AccountStore(open_database()).account_id("shen_01")
    for text in ("shen", "shen_0", "沈青衫", f"id:{shen_id}", "%", "shen_01%"):
        out = _look(s, tid, "login", text).json()
        assert out == {"found": False, "card": None, "left": out["left"], "message": rules.LOOKUP_NONE}, text
    assert [r["outcome"] for r in _log()] == ["none"] * 6


def test_lookup_by_email_matches_normalized_hmac(monkeypatch, keyed):
    s, tid = _desk(monkeypatch)
    _bind(keyed, "email", EMAIL)
    out = _look(s, tid, "email", "shenqing@googlemail.com").json()
    assert out["found"] is False  # 網域不同就是不同的 Email
    out = _look(s, tid, "email", " SHENQING+other@gmail.com ").json()
    assert out["found"] is True and out["card"]["login"] == "shen_01"
    assert ("email", "Email", "s*@gmail.com") in [(b["provider"], b["name"], b["shown"]) for b in out["card"]["binds"]]


def test_lookup_by_phone_matches_both_spellings(monkeypatch, keyed):
    s, tid = _desk(monkeypatch)
    _bind(keyed, "phone", PHONE)
    for text in ("0912345678", "+886 912 345 678"):
        out = _look(s, tid, "phone", text).json()
        assert out["found"] is True and out["card"]["character"] == "沈青衫", text
    assert ("phone", "手機", "09*****678") in [(b["provider"], b["name"], b["shown"]) for b in out["card"]["binds"]]


def test_email_phone_lookup_none_without_key(monkeypatch, keyed, tmp_path):
    s, tid = _desk(monkeypatch)
    _bind(keyed, "email", EMAIL)
    _bind(keyed, "phone", PHONE)
    monkeypatch.setattr(identity_base, "KEY_FILE", tmp_path / "missing.json")
    assert _look(s, tid, "email", EMAIL).json()["found"] is False
    assert _look(s, tid, "phone", PHONE).json()["found"] is False


def test_lookup_bad_input_not_counted(monkeypatch):
    s, tid = _desk(monkeypatch)
    for kind, text, why in (("login", "  ", rules.LOOKUP_EMPTY), ("email", "not-an-email", rules.LOOKUP_BAD_EMAIL),
                            ("phone", "02-2345-6789", rules.LOOKUP_BAD_PHONE), ("name", "沈青衫", rules.LOOKUP_BAD_KIND)):
        r = _look(s, tid, kind, text)
        assert r.status_code == 400 and r.json() == {"error": why}, kind
    assert _log() == []
    assert s.get("/api/support/queue").json()["lookups_left"] == server.CONTENT.config.support.lookup_hourly


def test_lookup_needs_an_existing_ticket(monkeypatch):
    s = staffer(monkeypatch)
    r = _look(s, 1, "login", "kefu_01")
    assert r.status_code == 404 and r.json() == {"detail": rules.NOT_FOUND}
    assert not sidecar().exists()
    tid = ticket(player()).json()["id"]
    for bad in (tid + 1, 0, "x", None):
        r = _look(s, bad, "login", "kefu_01")
        assert r.status_code == 404 and r.json() == {"detail": rules.NOT_FOUND}, bad
    assert _log() == []


def test_lookup_staff_only_404(monkeypatch):
    shen = player()
    tid = ticket(shen).json()["id"]
    nowhere = shen.get("/api/support-no-such-route")
    r = _look(shen, tid, "login", "shen_01")
    assert (r.status_code, r.content) == (404, nowhere.content)
    assert _log() == []


def test_hourly_limit_then_window_moves(monkeypatch):
    s, tid = _desk(monkeypatch)
    n = server.CONTENT.config.support.lookup_hourly
    t0 = server.time.time()
    monkeypatch.setattr(server.time, "time", lambda: t0)
    for i in range(n):
        assert _look(s, tid, "login", "shen_01" if i % 2 else "nobody_here").status_code == 200  # 查無也算一次
    r = _look(s, tid, "login", "shen_01")
    assert r.status_code == 400 and r.json() == {"error": rules.LOOKUP_LIMIT.format(n=n)}
    log = _log()
    assert [(e["outcome"], e["counted"]) for e in log[-2:]] == [("found", 1), ("limit", 0)]
    assert sum(e["counted"] for e in log) == n
    assert s.get("/api/support/queue").json()["lookups_left"] == 0
    monkeypatch.setattr(server.time, "time", lambda: t0 + rules.HOUR_SECONDS + 1)
    assert s.get("/api/support/queue").json()["lookups_left"] == n
    assert _look(s, tid, "login", "shen_01").json()["found"] is True


def test_every_lookup_is_logged_masked(monkeypatch, keyed):
    s, tid = _desk(monkeypatch)
    _bind(keyed, "email", EMAIL)
    _bind(keyed, "phone", PHONE)
    staff_id = AccountStore(open_database()).account_id("kefu_01")
    shen_id = AccountStore(open_database()).account_id("shen_01")
    _look(s, tid, "login", "Shen_01")
    _look(s, tid, "email", EMAIL)
    _look(s, tid, "phone", PHONE)
    _look(s, tid, "phone", "0987654321")
    rows = [(r["staff_account_id"], r["ticket_id"], r["kind"], r["shown"], r["found_account_id"], r["outcome"], r["counted"]) for r in _log()]
    assert rows == [
        (staff_id, tid, "login", "shen_01", shen_id, "found", 1),
        (staff_id, tid, "email", "s*@gmail.com", shen_id, "found", 1),
        (staff_id, tid, "phone", "09*****678", shen_id, "found", 1),
        (staff_id, tid, "phone", "09*****321", None, "none", 1),
    ]
    raw = b"".join(p.read_bytes() for p in sidecar().parent.glob(sidecar().name + "*"))
    for secret in ("shenqing", "912345678", "0987654321", "987654321"):
        assert secret.encode() not in raw, secret
    for provider, value in (("email", "shenqing@gmail.com"), ("phone", "+886912345678")):
        assert identity_base.subject_hmac(keyed, provider, value).encode() not in raw


def test_no_route_changes_the_log():
    """旁檔的 lookups 只有 store 的 INSERT 寫（沒有 UPDATE、DELETE）；路由只有查帳號與看單兩條會寫它（router 的路徑照清單比）。"""
    import inspect

    from tianxia.features.support import store

    src = inspect.getsource(store)
    assert "UPDATE lookups" not in src and "DELETE FROM lookups" not in src and src.count("INSERT INTO lookups") == 1
    paths = sorted((tuple(sorted(r.methods)), r.path) for r in routes.router(server).routes)
    assert paths == sorted([
        (("POST",), "/api/support/ticket"), (("GET",), "/api/support/mine"), (("POST",), "/api/support/reply"),
        (("GET",), "/api/support/queue"), (("GET",), "/api/support/ticket/{tid}"), (("POST",), "/api/support/answer"),
        (("POST",), "/api/support/close"), (("POST",), "/api/support/lookup"),
        (("GET",), "/api/support/mailbox"),  # 第 214 批：只回設定裡的信箱，不碰旁檔
        (("POST",), "/api/support/file"),  # 第 215 批：截圖只寫 files 表
    ])
    rsrc = inspect.getsource(routes)
    assert rsrc.count("sidecar.lookup(") == 1 and rsrc.count("sidecar.log_card(") == 1


def test_ticket_card_logged_not_counted(monkeypatch):
    s, tid = _desk(monkeypatch)
    n = server.CONTENT.config.support.lookup_hourly
    view = s.get(f"/api/support/ticket/{tid}").json()
    assert view["card"]["login"] == "shen_01" and view["card"]["character"] == "沈青衫"
    assert s.get("/api/support/queue").json()["lookups_left"] == n
    assert [(r["kind"], r["outcome"], r["counted"], r["ticket_id"], r["shown"]) for r in _log()] == [("card", "card", 0, tid, "shen_01")]
    answered = s.post("/api/support/answer", json={"id": tid, "body": "好了", "then": "wait"}).json()
    assert "card" not in answered and len(_log()) == 1


def test_ticket_card_gone_when_account_changed(monkeypatch):
    s, tid = _desk(monkeypatch)
    db = open_database()
    with db.transaction() as conn:
        conn.execute("UPDATE accounts SET created = created + 1 WHERE id = (SELECT account_id FROM logins WHERE subject = 'shen_01')")
    assert s.get(f"/api/support/ticket/{tid}").json()["card"] == {"gone": True}
    assert [(r["kind"], r["outcome"], r["found_account_id"]) for r in _log()] == [("card", "gone", None)]


def test_bot_names_look_like_nobody(monkeypatch):
    game = Game.new(server.CONTENT, BOT)
    game.state.player.bot = BotProfile(personality="普通", seed=7)
    open_characters().save(game.state)
    s, tid = _desk(monkeypatch)

    def shape(text):
        out = _look(s, tid, "login", text).json()
        out.pop("left")
        return out

    assert shape(BOT) == shape("亂打的字") == shape(name_key(BOT)) == {"found": False, "card": None, "message": rules.LOOKUP_NONE}


def test_queue_shows_lookups_left(monkeypatch):
    s = staffer(monkeypatch)
    n = server.CONTENT.config.support.lookup_hourly
    assert s.get("/api/support/queue").json()["lookups_left"] == n  # 還沒有旁檔
    tid = ticket(player()).json()["id"]
    _look(s, tid, "login", "shen_01")
    _look(s, tid, "login", "nobody")
    assert s.get("/api/support/queue").json()["lookups_left"] == n - 2
