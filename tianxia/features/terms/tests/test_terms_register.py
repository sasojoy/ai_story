"""註冊兩個勾選、建帳號記版本（帳號與客服第 206 批；設計第五節）：殼的 /api/register 開帳號之前查 age_ok、terms_agree、
terms_version（經核心 terms_base，terms 包掛路由時登記 hook），建好記一筆 source=register，進遊戲同意層不再跳。
/api/terms/version 不用登入、關著 404。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server
from tianxia.core import terms_base
from tianxia.features.terms import routes as terms_routes
from tianxia.features.terms import rules


@pytest.fixture
def fresh(monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", True)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES, server.REGISTRATIONS):
        store.clear()
    server.WORLD_GAME = None
    yield
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES, server.REGISTRATIONS):
        store.clear()
    server.WORLD_GAME = None


def _ticks(**over):
    out = {"age_ok": True, "terms_agree": True, "terms_version": rules.load()["version"]}
    out.update(over)
    return out


def _reg(c, login, **extra):
    return c.post("/api/register", json={"login": login, "password": "secret-pw", "again": "secret-pw", **extra})


def test_terms_version_route(fresh, monkeypatch):
    c = TestClient(server.app)
    r = c.get("/api/terms/version")
    assert r.status_code == 200 and r.json() == {"version": rules.load()["version"]}  # 沒 cookie 也拿得到
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", False)
    assert c.get("/api/terms/version").status_code == 404


def test_router_registers_the_hook(fresh):
    TestClient(server.app)
    hook = terms_base._HOOK
    assert hook is not None and hook.version() == rules.load()["version"]


def test_register_refused_without_ticks_and_no_account_made(fresh):
    c = TestClient(server.app)
    said = set()
    for extra in ({}, {"age_ok": True, "terms_version": rules.load()["version"]},
                  {"terms_agree": True, "terms_version": rules.load()["version"]}, _ticks(terms_version="old")):
        r = _reg(c, "tick_01", **extra)
        assert r.status_code == 400, r.text
        said.add(r.json()["error"])
    assert said == {terms_base.REGISTER_NEED}
    assert server.account_store().get("tick_01") is None
    assert terms_routes.consent_store(server).history("tick_01") == []
    assert not any(server.REGISTRATIONS.values())  # 被勾選擋下的不算一次註冊


def test_register_with_ticks_records_register_and_no_layer(fresh):
    c = TestClient(server.app)
    r = _reg(c, "tick_02", **_ticks())
    assert r.status_code == 200, r.text
    history = terms_routes.consent_store(server).history("tick_02")
    assert [(h["version"], h["source"]) for h in history] == [(rules.load()["version"], "register")]
    assert c.get("/api/terms").json()["need"] == ""  # 同意層不再跳


def test_register_form_strings_count_as_ticks(fresh):
    c = TestClient(server.app)
    r = _reg(c, "tick_03", **_ticks(age_ok="on", terms_agree="on"))
    assert r.status_code == 200, r.text
    assert terms_routes.consent_store(server).history("tick_03")[0]["source"] == "register"


def test_register_refusal_reads_the_same_for_taken_and_new_names(fresh, monkeypatch):
    c = TestClient(server.app)
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", False)
    assert _reg(c, "tick_04").status_code == 200
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", True)
    c2 = TestClient(server.app)
    taken, new = _reg(c2, "tick_04"), _reg(c2, "tick_05")
    assert taken.status_code == new.status_code == 400
    assert taken.json() == new.json() == {"error": terms_base.REGISTER_NEED}
