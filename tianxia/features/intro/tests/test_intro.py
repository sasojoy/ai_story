"""開局前導畫本（tianxia/features/intro/）：新角色站到城門口、還沒選路時要先看（status.intro.pending），看過就不再；
選了路的、開關關著的都不出聲；內容檔過得了檢查、加起來不超過 60 秒；兩條路由關著 404、開著給七幕、記看過。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from fastapi.testclient import TestClient

import server
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.features.intro import rules


@pytest.fixture
def on():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.jianfa.enabled = True
    c.config.intro.enabled = True
    return c


def _new(content, name="沈浪"):
    return Game.new(content, name, rng=random.Random(0), prologue=True)


@pytest.mark.smoke
def test_a_new_player_at_the_gate_sees_the_book_once(on):
    g = _new(on)
    assert g.status_data()["intro"] == {"pending": True}
    assert [o.id for o in g.options()] == ["choice:0", "choice:1", "choice:2"]  # 畫本不加選項，城門口三選一照舊
    rules.mark_seen(g)
    assert g.status_data()["intro"] == {"pending": False}


def test_after_choosing_a_road_it_is_not_pending(on):
    g = _new(on)
    g.choose("choice:0")
    assert g.status_data()["intro"] == {"pending": False}


def test_switch_off_leaves_no_key(on):
    on.config.intro.enabled = False
    g = _new(on)
    assert "intro" not in g.status_data()
    assert next(f for f in FEATURES if f.name == "intro").enabled(g) is False


def test_the_real_book_checks_clean_and_stays_under_a_minute(on):
    assert rules.check(on) == []
    book = rules.book(on)
    assert len(book["scenes"]) == 7 and sum(s["seconds"] for s in book["scenes"]) <= 60
    names = {f["name"] for s in book["scenes"] for f in s["figures"]}
    assert names == {"張角", "皇甫嵩", "朱儁", "波才"}
    assert all(s["image"].startswith("/static/img/") for s in book["scenes"])


def test_check_catches_a_missing_image_too_long_and_a_figure_without_a_portrait(on):
    data = rules.load()
    bad = {**data, "scenes": [{**data["scenes"][0], "image": "events/nope.webp", "seconds": 61,
                               "figures": [{"id": "nobody", "side": "x", "tag": "誰"}, {"id": "zhangjiao", "side": "r", "tag": "黃巾之首"}]}]}
    problems = " ".join(rules.check(on, bad))
    assert "找不到圖" in problems and "超過 60 秒" in problems and "nobody 沒有立繪" in problems and "side" in problems


@pytest.fixture
def client(monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None
    c = TestClient(server.app)
    c.post("/api/register", json={"login": "intro_01", "password": "secret-pw", "again": "secret-pw"})
    c.post("/api/character", json={"name": "沈青衫"})
    yield c
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None


def test_routes_are_closed_by_default_then_serve_the_book_and_record_seen(client, monkeypatch):
    assert client.get("/api/intro").status_code == 404
    assert client.post("/api/intro/seen").status_code == 404
    monkeypatch.setattr(server.CONTENT.config.intro, "enabled", True)
    assert TestClient(server.app).get("/api/intro").status_code == 401
    book = client.get("/api/intro").json()
    assert len(book["scenes"]) == 7 and book["skip"] and book["replay"]
    got = client.post("/api/intro/seen").json()
    assert got["main"]["status"]["intro"] == {"pending": False}
    game = next(iter(server.GAMES.values()))
    assert rules.SEEN in game.state.player.flags
