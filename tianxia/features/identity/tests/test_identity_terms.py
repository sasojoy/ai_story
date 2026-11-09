"""建角色那一步才開帳號（第三方、驗證碼第一次進來）：terms 開著時同樣要兩個勾選與現行版號，建好記 source=register（帳號與客服第 206 批；
設計第五節「驗身分 → 建角色頁的勾選 → 建帳號記版本 → 進遊戲」）。identity 不 import terms 包，經核心 terms_base。
terms 關著：不帶三欄照舊開得了、不建 -terms.sqlite（殼的註冊與這裡同一條，「每個開關只留一條」）。"""
from __future__ import annotations

from fastapi.testclient import TestClient

import server
from tianxia import database
from tianxia.accounts import AccountStore
from tianxia.core import terms_base
from tianxia.features.terms import routes as terms_routes  # 測試讀 terms 的旁檔；包本身不 import terms
from tianxia.features.terms import rules

from test_identity_login import _pending_client, _side_rows, fresh_server  # noqa: F401  fresh_server 是 autouse


def _ticks(**over):
    out = {"age_ok": True, "terms_agree": True, "terms_version": rules.load()["version"]}
    out.update(over)
    return out


def _terms_on(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", True)


def test_character_refused_without_ticks_keeps_pending(monkeypatch):
    _terms_on(monkeypatch)
    c = _pending_client(monkeypatch, sub="U-t1")
    said = set()
    for extra in ({}, {"age_ok": True, "terms_version": rules.load()["version"]},
                  {"terms_agree": "on", "terms_version": rules.load()["version"]}, _ticks(terms_version="old")):
        r = c.post("/api/identity/character", json={"name": "柳如煙", "gender": "女", **extra})
        assert r.status_code == 400, r.text
        said.add(r.json()["error"])
    assert said == {terms_base.REGISTER_NEED}
    assert AccountStore(database.open_database()).login_key("line", "U-t1") is None
    assert _side_rows("pending") == 1 and "tx_pending" in c.cookies  # 可以再送
    assert not any(server.REGISTRATIONS.values())


def test_character_with_ticks_records_register_and_no_layer(monkeypatch):
    _terms_on(monkeypatch)
    c = _pending_client(monkeypatch, sub="U-t2")
    r = c.post("/api/identity/character", json={"name": "柳如煙", "gender": "女", **_ticks(age_ok="on", terms_agree="on")})
    assert r.status_code == 200 and r.json()["stage"] == "game", r.text
    key = AccountStore(database.open_database()).login_key("line", "U-t2")
    history = terms_routes.consent_store(server).history(key)
    assert [(h["version"], h["source"]) for h in history] == [(rules.load()["version"], "register")]
    assert c.get("/api/terms").json()["need"] == ""  # 進遊戲同意層不跳


def test_terms_off_register_and_character_unchanged(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", False)
    assert TestClient(server.app).get("/api/terms/version").status_code == 404
    plain = TestClient(server.app).post("/api/register", json={"login": "off_01", "password": "secret-pw-long", "again": "secret-pw-long"})
    ticked = TestClient(server.app).post("/api/register", json={"login": "off_02", "password": "secret-pw-long",
                                                                  "again": "secret-pw-long", **_ticks()})
    assert plain.status_code == ticked.status_code == 200
    assert plain.json().keys() == ticked.json().keys()
    c = _pending_client(monkeypatch, sub="U-t4")
    r = c.post("/api/identity/character", json={"name": "柳如煙", "gender": "女"})
    assert r.status_code == 200 and r.json()["stage"] == "game"
    assert not terms_routes.store_path(server).exists()  # 關著不建旁檔
