"""/api/travel、/api/party/leave（移動包的 routes.py，全部拆包第 47、48 批）：回的鍵與順序、走不成時留在輿圖寫原因、不認得的走法與地方、舊的趕路被拒。
整段的移動規則在 tests/core/test_engine.py、tests/server/test_server.py（混合檔，見 README）。"""
from __future__ import annotations

from test_mall_server import _player, fresh_server  # noqa: F401  fresh_server 是 autouse 的 fixture

import server


def _nearby(client) -> list[str]:
    return [o["id"][5:] for o in client.get("/api/main").json()["options"] if o["id"].startswith("move:") and o["enabled"]]


def test_a_departure_answers_main_and_arrived_only():
    client = _player()
    out = client.post("/api/travel", json={"place": _nearby(client)[0]}).json()
    assert list(out) == ["main", "arrived"] and out["arrived"] is True


def test_a_refusal_stays_on_the_map_and_says_why():
    client = _player()
    here = server.game_for("沈青衫").state.player.location
    out = client.post("/api/travel", json={"place": here, "layer": "situation"}).json()
    assert list(out) == ["main", "arrived", "reason", "map"]
    assert out["arrived"] is False and out["reason"] and out["map"]["selected"] == here


def test_unknown_places_walking_modes_and_the_old_hurry_are_refused_the_same_way():
    client = _player()
    place = _nearby(client)[0]
    for body in ({"place": "nowhere"}, {"place": place, "mode": "gallop"}, {"place": place, "mode": "hurry"}):
        out = client.post("/api/travel", json=body).json()
        assert out["arrived"] is False and out["reason"] == "無法安排前往這裡", body
    assert server.game_for("沈青衫").state.player.journey is None  # 什麼都沒變


def test_party_leave_answers_main_and_message_even_when_following_no_one():
    """/api/party/leave（全部拆包第 48 批搬進移動包）：回的鍵與順序是 main、message；沒跟著誰時也按得下去，回「你沒有跟著誰」。"""
    client = _player()
    out = client.post("/api/party/leave").json()
    assert list(out) == ["main", "message"] and "你沒有跟著誰" in out["message"]
