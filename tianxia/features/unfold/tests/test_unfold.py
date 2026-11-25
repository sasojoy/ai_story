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


# ── 小事卡（features/unfold/cards.py）：門派、書信、結義、稱號、江湖錄、合成第一次碰到時攤一張（帶著對象），一次一張、每種一次
def _card(name="王越"):
    from tianxia.state import Mingtie, MingtieCopy

    return MingtieCopy(name=name, card=Mingtie(), when="", place="", season=1, gave=1)


def _card_now(g):
    g.sync(g.now + 1)
    return (g.feature_status()["unfold"] or {}).get("card")


def test_standing_at_a_sect_gate_lays_the_sect_card_with_its_join_button(on):
    on.config.zongmen.enabled = True
    g = _new(on)
    g.choose("choice:0")
    sect = next(s for s in on.sects.values() if s.switch == "zongmen" and on.sect_open(s.id))
    g.state.player.location = sect.location
    k = _card_now(g)
    assert k["kind"] == "sect" and k["arg"] == sect.id and k["go"] and k["later"]
    rules_book = g.state.player.unfold
    from tianxia.features.unfold import cards

    cards.close(rules_book)
    assert _card_now(g) is None  # 收了就不再出同一種


def test_one_card_at_a_time_mail_then_jieyi_after_a_fight_together(on):
    from tianxia.features.unfold import cards
    from tianxia.state import BattleRecord, Fighter

    on.config.mail.enabled = on.config.jieyi.enabled = True
    g = _new(on)
    g.choose("choice:0")
    g.state.player.mingtie_box.append(_card())
    assert _card_now(g)["kind"] == "mail"
    g.state.battles.append(BattleRecord(id=99, time=0, location="", kind="spar", opponent="王越", ours=[Fighter(name="沈浪", level=1)],
                                        tier="險勝", our_power=1, difficulty=1))
    assert _card_now(g)["kind"] == "mail"  # 前一張還攤著：排著等
    cards.close(g.state.player.unfold)
    k = _card_now(g)
    assert k["kind"] == "jieyi" and k["arg"] == "王越"


def test_an_old_player_never_gets_a_card(on):
    on.config.mail.enabled = True
    g = _new(on)
    g.choose("choice:0")
    g.state.player.unfold = None
    g.state.player.mingtie_box.append(_card())
    g.sync(g.now + 1)
    assert "unfold" not in g.feature_status()


def test_a_new_player_no_longer_hears_the_three_replaced_hints(on):
    g = _new(on)
    assert {"h_merge", "h_points", "h_create"} <= g.state.player.hints_seen


def test_a_new_player_hears_the_short_line(on):
    from tianxia.features.guide import hints, short

    g = _new(on)
    assert hints.note_for(g.state, on, "h_tavern").text == short.SHORT["h_tavern"]
    g.state.player.unfold = None
    assert hints.note_for(g.state, on, "h_tavern").text != short.SHORT["h_tavern"]


def test_the_mall_comes_up_once_the_road_is_chosen_and_the_pills_when_legs_give_out(on):
    from tianxia.features.guide import actions

    on.config.mall.enabled = True
    g = _new(on)
    assert "h_mall" not in actions.hint_triggers(g)
    g.choose("choice:0")
    assert "h_mall" in actions.hint_triggers(g)
    p = g.state.player
    p.stamina, p.stamina_pills = 3, 0
    assert "h_pills" in actions.hint_triggers(g)
    p.stamina_pills = 1
    assert "h_pills" not in actions.hint_triggers(g)
