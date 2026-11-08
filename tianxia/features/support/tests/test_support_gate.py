"""客服包的 gate（帳號與客服第 212 批；計畫「J 波落地時 PM 加的」第 1 條）：關著時每一條 /api/support/* 一律 404 {"detail":"Not Found"}，
而且 gate 先於登入與參數解析（沒登入、壞 JSON、單號不是數字都一樣 404，跟沒有這條路逐位元組同一個回應）；開著沒登入照舊 401；
開著時單號不是數字回 404「找不到這張單。」、壞 JSON 回 422。關著時 /api/me、/api/main 一個位元組都不多。"""
from __future__ import annotations

import pytest
import server
from fastapi.testclient import TestClient
# autouse 的 fixture 要明列（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import ROUTES, hit, player, sidecar, staffer, support_isolated, support_on  # noqa: F401

from tianxia.features import support as package
from tianxia.features.support import rules

pytestmark = pytest.mark.whole_content

POSTS = [(m, p) for m, p, _ in ROUTES if m == "POST"]
NOWHERE = "/api/support-no-such-route"  # 沒有這條路：關著時每一條都要跟它逐位元組一樣


def _bad_json(c: TestClient, path: str):
    return c.post(path, content=b"{not json", headers={"content-type": "application/json"})


def test_off_every_route_404_before_login_and_parsing():
    anon = TestClient(server.app, raise_server_exceptions=False)
    nowhere = anon.get(NOWHERE)
    assert nowhere.status_code == 404 and nowhere.json() == {"detail": "Not Found"}
    c = player()
    for who in (anon, c):
        for method, path, body in ROUTES:
            r = hit(who, method, path, body)
            assert (r.status_code, r.content) == (404, nowhere.content), (method, path)
        for _, path in POSTS:
            r = _bad_json(who, path)
            assert (r.status_code, r.content) == (404, nowhere.content), path
            r = who.post(path, json=[1, 2])
            assert (r.status_code, r.content) == (404, nowhere.content), path
        r = who.get("/api/support/ticket/abc")
        assert (r.status_code, r.content) == (404, nowhere.content)
    assert not sidecar().exists()


def test_off_me_and_main_same_bytes_as_without_the_package(monkeypatch):
    """關著時 /api/me、/api/main、登入頁跟這一包的表外格、on_own_turn 全拿掉時逐位元組一樣。"""
    c = player()
    anon = TestClient(server.app, raise_server_exceptions=False)
    monkeypatch.setattr(server.time, "time", lambda: 1_762_581_600.0)
    now = (c.get("/api/me").content, c.get("/api/main").content, anon.get("/").content)
    monkeypatch.setattr(package.SupportFeature, "status_slots", lambda self: ())
    monkeypatch.setattr(package.SupportFeature, "on_own_turn", lambda self, ctx: None)
    without = (c.get("/api/me").content, c.get("/api/main").content, anon.get("/").content)
    assert now == without


def test_on_without_login_401(support_on):
    """取代第 211 批的 test_routes_401_without_login_either_way：關著是 404（上一條），開著沒登入才是 401。"""
    anon = TestClient(server.app, raise_server_exceptions=False)
    assert {path: hit(anon, method, path, body).status_code for method, path, body in ROUTES} == {path: 401 for _, path, _ in ROUTES}


def test_on_bad_ticket_id_404_and_bad_json_422(support_on, monkeypatch):
    s = staffer(monkeypatch)
    r = s.get("/api/support/ticket/abc")
    assert r.status_code == 404 and r.json() == {"detail": rules.NOT_FOUND}
    for _, path in POSTS:
        assert _bad_json(s, path).status_code == 422, path
        assert s.post(path, json=[1, 2]).status_code == 422, path
    assert not sidecar().exists()


# ── 登入頁的客服信箱（帳號與客服第 214 批）：GET /api/support/mailbox 不用登入；關著 404 跟沒有這條路一樣 ──
MAILBOX = "/api/support/mailbox"


def test_mailbox_off_404_like_nowhere():
    anon = TestClient(server.app, raise_server_exceptions=False)
    nowhere = anon.get(NOWHERE)
    for who in (anon, player()):
        r = who.get(MAILBOX)
        assert (r.status_code, r.content) == (404, nowhere.content)
    assert not sidecar().exists()


def test_mailbox_on_without_login(support_on):
    anon = TestClient(server.app, raise_server_exceptions=False)
    r = anon.get(MAILBOX)
    config = server.CONTENT.config
    assert r.status_code == 200
    assert r.json() == {"mailbox": config.support.mailbox, "line": package.FEATURE.gate_slot(config)}
    assert config.support.mailbox in r.json()["line"]
    assert "set-cookie" not in r.headers
    assert not sidecar().exists()


def test_mailbox_same_for_everyone(support_on, monkeypatch):
    """不因人而異：沒登入、玩家、客服、帶壞 cookie 的回應逐位元組一樣（名號、帳號不出現；假人沒有帳號，也看不出來）。"""
    anon = TestClient(server.app, raise_server_exceptions=False)
    forged = TestClient(server.app, raise_server_exceptions=False)
    forged.cookies.set(server.COOKIE, "not-a-real-session")
    replies = [c.get(MAILBOX) for c in (anon, player(), staffer(monkeypatch), forged)]
    assert {(r.status_code, r.content) for r in replies} == {(200, replies[0].content)}
    for name in ("沈青衫", "青衣", "shen_01", "kefu_01"):
        assert name not in replies[0].text
    assert not sidecar().exists()


def test_mailbox_follows_config(support_on, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.support, "mailbox", "help@example.org")
    body = TestClient(server.app, raise_server_exceptions=False).get(MAILBOX).json()
    assert body["mailbox"] == "help@example.org" and "help@example.org" in body["line"]
