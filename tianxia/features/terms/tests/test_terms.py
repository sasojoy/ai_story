"""條款：誰要按同意（規則）、同意紀錄只加不刪（小檔）、/api/terms 與 /api/terms/agree（伺服器）、網頁那一層（node）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server
from tianxia.features.terms import routes as terms_routes
from tianxia.features.terms import rules
from tianxia.features.terms.store import ConsentStore

DATA = {"version": "v2", "published": "2026-11-08"}
DAY = 86400


def test_need_must_for_a_new_account_and_none_once_agreed():
    now = rules.published_at(DATA) + 1
    assert rules.need(None, DATA, now, 15) == rules.MUST
    assert rules.need("v2", DATA, now, 15) == rules.NONE


def test_an_old_consent_is_asked_inside_the_grace_days_and_deemed_accepted_after():
    start = rules.published_at(DATA)
    assert rules.need("v1", DATA, start + 14 * DAY, 15) == rules.ASK
    assert rules.need("v1", DATA, start + 15 * DAY, 15) == rules.NONE
    assert rules.need(None, DATA, start + 99 * DAY, 15) == rules.MUST  # 沒同意過任何一版：一直要按


def test_the_store_only_appends(tmp_path):
    store = ConsentStore(tmp_path / "t-terms.sqlite")
    assert store.latest("ab") is None
    store.record("ab", "v1", "register", 1.0)
    store.record("ab", "v2", "update", 2.0)
    assert store.latest("ab") == "v2"
    assert [h["version"] for h in store.history("ab")] == ["v1", "v2"]
    with pytest.raises(ValueError):
        store.record("ab", "v2", "nowhere", 3.0)


def test_check_catches_a_missing_company_field_and_an_unknown_placeholder():
    data = rules.load()
    broken = {**data, "company": {**data["company"], "email": ""}}
    assert any("email" in p for p in rules.check(broken))
    docs = {**data["docs"], "terms": {**data["docs"]["terms"], "sections": [{"h": "x", "p": ["{nope}"]}]}}
    assert any("nope" in p for p in rules.check({**data, "docs": docs}))


@pytest.fixture
def client(monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", True)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None
    c = TestClient(server.app)
    c.post("/api/register", json={"login": "terms_01", "password": "secret-pw", "again": "secret-pw"})
    yield c
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None


def test_api_asks_until_agreed_then_stays_quiet(client):
    assert TestClient(server.app).get("/api/terms").status_code == 401
    got = client.get("/api/terms").json()
    assert got["need"] == "must" and got["summary"] and got["email"] == "wormholecreativity@gmail.com"
    assert client.post("/api/terms/agree", json={"version": "old"}).status_code == 409
    done = client.post("/api/terms/agree", json={"version": got["version"]}).json()
    assert done["need"] == ""
    assert terms_routes.consent_store(server).history("terms_01")[0]["source"] == "gate"


def test_switch_off_never_asks(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", False)
    assert client.get("/api/terms").json()["need"] == ""


def test_record_consent_for_the_register_side(client):
    version = rules.load()["version"]
    with pytest.raises(ValueError):
        terms_routes.record_consent(server, "terms_01", "old")
    terms_routes.record_consent(server, "terms_01", version)
    assert client.get("/api/terms").json()["need"] == ""
    assert terms_routes.consent_store(server).history("terms_01")[-1]["source"] == "register"
