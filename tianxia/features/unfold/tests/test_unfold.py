"""慢慢長出來（tianxia/features/unfold/）：新角色站在城門口開本、只看得到江湖與俠客的武學；選了路輿圖長出來，
升級長出屬性、拿到東西長出裝備；長出來的亮紅點、點開才滅、不收回；舊角色與開關關著一個鍵都不多。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from fastapi.testclient import TestClient

import server
from tianxia.engine import Game
from tianxia.features.unfold import rules


@pytest.fixture
def on():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.jianfa.enabled = True
    c.config.unfold.enabled = True
    return c


def _new(content, name="沈浪"):
    g = Game.new(content, name, rng=random.Random(0), prologue=True)
    g.sync(g.now + 1)
    return g


def test_a_new_player_at_the_gate_starts_with_everything_folded(on):
    g = _new(on)
    u = g.feature_status()["unfold"]
    assert set(u["hide"]) == set(rules.KEYS) and u["fresh"] == []


def test_choosing_a_road_grows_the_map_with_a_dot(on):
    g = _new(on)
    g.choose("choice:0")
    u = g.feature_status()["unfold"]
    assert "tab:map" not in u["hide"] and "tab:map" in u["fresh"]
    rules.seen(g.state.player.unfold, ["tab:map"])
    assert "tab:map" not in g.feature_status()["unfold"]["fresh"]


def test_grown_blocks_never_fold_back(on):
    g = _new(on)
    g.choose("choice:0")
    g.state.player.stat_points = 1
    g.sync(g.now + 1)
    assert "hero:attrs" in g.state.player.unfold.grown
    g.state.player.stat_points = 0
    g.sync(g.now + 1)
    assert "hero:attrs" not in g.feature_status()["unfold"]["hide"]


def test_old_characters_and_the_switch_off_keep_no_key(on):
    g = _new(on)
    g.choose("choice:0")
    g.state.player.unfold = None  # 舊角色：走過城門口才打開開關
    g.sync(g.now + 1)
    assert g.state.player.unfold is None and "unfold" not in g.feature_status()
    on.config.unfold.enabled = False
    assert "unfold" not in _new(on, "林三").feature_status()
    assert "unfold" not in g.state.player.model_dump()


@pytest.mark.smoke
def test_seen_route_clears_the_dot_and_is_404_when_off(tmp_path, monkeypatch):
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "t.db"))
    client = TestClient(server.app)
    monkeypatch.setattr(server.CONTENT.config.unfold, "enabled", False)
    assert client.post("/api/unfold/seen", json={"keys": []}).status_code in (401, 404)
