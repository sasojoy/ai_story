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
