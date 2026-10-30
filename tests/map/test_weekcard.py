"""江湖頁的本週卡、三方卡與事件選項的樣子（減法季批 1，整合設計 6.1、3.4、6.4；tianxia/weekcard.py、Game.event_option_view）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import foreshadow, weekcard
from tianxia.engine import Game


@pytest.fixture
def on():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.season_one, c.config.season_days, c.config.server_max_players = True, 2.5, 2
    return c


def _game(content, name="甲"):
    return Game.new(content, name, rng=random.Random(0))


@pytest.mark.smoke
def test_phase_cuts_the_season_in_three():
    assert [weekcard.phase(w, 3) for w in (1, 2, 3)] == [0, 1, 2]
    assert [weekcard.phase(w, 12) for w in (1, 4, 5, 8, 9, 12)] == [0, 0, 1, 1, 2, 2]
    assert weekcard.phase(99, 3) == 2 and weekcard.phase(0, 3) == 0


def test_week_card_has_theme_sides_and_ends_with_join_for_a_loner(on):
    g = _game(on)
    status = g.status_data()
    card = weekcard.week_card(g, status, g.orders_view())
    assert card is not None
    assert card["theme"] == on.scenario.week_themes[0]
    assert set(card["sides"]) == {"guan", "huang"}
    assert card["label"] in ("本週", "這一段")
    assert card["steps"] and card["steps"][-1]["kind"] == "join"
    assert "先投一方" in card["steps"][-1]["text"]


def test_steps_follow_the_order_errand_order_bounty_newbie_join(on):
    g = _game(on)
    status = dict(g.status_data())
    status["bounties"] = [{"title": "甲榜", "how": "去做", "have": False},
                          {"title": "託付", "how": "送信", "commission": True, "issuer": "某人"}]
    status["newbie"] = {"rows": [{"text": "新手一"}]}
    orders = [{"title": "軍令", "text": "打", "how": "去打", "done": False}, {"title": "做完", "text": "x", "done": True}]
    kinds = [s["kind"] for s in weekcard.week_card(g, status, orders)["steps"]]
    assert kinds[:3] == ["errand", "order", "bounty"]
    assert kinds[-2:] == ["newbie", "join"]
    assert "做完" not in "".join(s["text"] for s in weekcard.week_card(g, status, orders)["steps"])


def test_sides_card_writes_two_armies_when_the_four_wins_rule_is_off(on):
    g = _game(on)
    sc = weekcard.sides_card(g)
    ids = [col["id"] for col in sc["cols"]]
    assert ids[:2] == ["guan", "huang"] or set(ids) >= {"guan", "huang"}
    assert sc["joined"] is False and sc["lean"] is None
    for col in sc["cols"]:
        assert col["goal"] and col["where"] and col["mine"] is False
        assert col["gives"] == weekcard.WIN_GIVES_OLD


def test_sides_card_adds_the_gentry_when_four_wins_is_on(on):
    on.config.jianfa.enabled = True
    g = _game(on)
    sc = weekcard.sides_card(g)
    assert any(col["goal"] == weekcard.HAOQIANG_GOAL for col in sc["cols"])
    assert {col["id"] for col in sc["cols"] if col["id"] in ("guan", "huang")} == {"guan", "huang"}


def test_no_cards_without_factions(content):
    g = _game(content)
    if not content.scenario.factions:
        assert weekcard.sides_card(g) is None


def test_foreshadow_next_step_is_none_for_a_fresh_player(on):
    g = _game(on)
    assert foreshadow.next_step(g.state, on) is None


def test_event_option_view_keeps_the_action_and_tags_each_choice(on):
    g = _game(on)
    assert g.event_option_view() is None
    g.state.pending_event = "jz_altar_roster"
    view = g.event_option_view()
    ev = on.events["jz_altar_roster"]
    assert view and all(k.startswith("choice:") for k in view)
    kinds = {v["kind"] for v in view.values()}
    assert "fight" in kinds
    for key, v in view.items():
        ch = ev.choices[int(key.split(":")[1])]
        assert v["act"].startswith(ch.text)
        assert v["kind"] == ("fight" if ch.combat else ch.check.stat if ch.check else "")
        if ch.combat:
            assert v["worry"].startswith("對手：") and isinstance(v["sure"], bool)  # 每一顆都寫（Joy 2026-10-27）
        elif ch.check:
            assert v["worry"].startswith(on.config.stat_names[ch.check.stat]) and "：" in v["worry"]
        else:
            assert v["worry"] == "" and v["sure"] is True
