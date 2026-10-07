"""第一季正式版・丁：第四階席次與每週輪替（計畫 2026-10-06-第一季正式版-丁）。

用真實內容（content/）：fixture real 在 tests/conftest.py（每個測試拿 real_content 的一份複本），開關在 on 裡才打開。
席次照人數上限換算：測試裡把人數上限調成 250（0.008 × 250 ＝ 2 席）。"""
from __future__ import annotations

import random

import pytest

from tianxia import factions, ranks, seats
from tianxia.engine import Game
from tianxia.state import WorldState


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 250
    return real


def _qualified(content, name, faction="guan", weeks=None, world=None):
    game = Game.new(content, name, rng=random.Random(0))
    game.client = None  # 沒有任何地方會叫模型
    if world is not None:
        game.state.world = world
    p = game.state.player
    p.faction, p.rank, p.qualified = faction, 3, True
    p.contrib_weeks = dict(weeks or {})
    return game


# ── Task 1：帳與補缺 ────────────────────────────────────────


def test_defaults_so_old_saves_load():
    w = WorldState()
    assert (w.seat_ledger, w.seats) == ({}, {})


def test_report_copies_the_weekly_contribution(on):
    assert factions.rank4_seats(on.config) == 2
    game = _qualified(on, "甲", weeks={1: 40, 2: 15})
    seats.report(game.state, on)
    assert game.state.world.seat_ledger == {"guan": {"甲": {1: 40, 2: 15}}}


def test_the_ledger_is_a_copy_that_the_next_report_replaces(on):
    game = _qualified(on, "甲", weeks={1: 7})
    seats.report(game.state, on)
    game.state.player.contrib_weeks[2] = 3  # 之後又記了一週的貢獻：帳要等下一次抄才換
    assert game.state.world.seat_ledger["guan"]["甲"] == {1: 7}
    seats.report(game.state, on)
    assert game.state.world.seat_ledger["guan"]["甲"] == {1: 7, 2: 3}


def test_the_ledger_keeps_the_order_in_which_they_qualified(on):
    """插入順序＝拿到資格的先後（同分時先拿到的優先）：再抄一次不改順序。"""
    w = WorldState(season_one=True)
    first, second = _qualified(on, "甲", world=w), _qualified(on, "乙", world=w)
    seats.report(first.state, on)
    seats.report(second.state, on)
    first.state.player.contrib_weeks = {1: 9}
    seats.report(first.state, on)
    assert list(w.seat_ledger["guan"]) == ["甲", "乙"]


def test_each_faction_has_its_own_ledger_and_seats(on):
    w = WorldState(season_one=True)
    for name in ("甲", "乙"):
        seats.report(_qualified(on, name, world=w).state, on)
    yellow = _qualified(on, "丙", faction="huang", world=w)
    assert seats.report(yellow.state, on) == ["你補上了大方渠帥的缺，到下週一為止。"]  # 官軍的席次坐滿了，不擋黃巾
    assert w.seats == {"guan": ["甲", "乙"], "huang": ["丙"]} and set(w.seat_ledger) == {"guan", "huang"}


def test_a_free_seat_is_filled_at_once(on):
    game = _qualified(on, "甲")
    before = len(game.state.world.rumors)
    msgs = seats.report(game.state, on)
    assert msgs == ["你補上了校尉的缺，到下週一為止。"] and seats.seated(game.state)
    note = game.state.world.rumors[before]
    assert (note.layer, note.faction, note.text) == ("faction", "guan", "甲補上了校尉的缺。")
    assert seats.report(game.state, on) == []  # 已經在任：不再說


def test_an_anonymous_member_is_named_in_the_faction_note(on):
    """陣營軍情一律寫本名（傳聞分層第七節）：匿名的人補上了缺，軍情照寫名號。"""
    game = _qualified(on, "甲")
    game.state.player.anonymous = True
    before = len(game.state.world.rumors)
    seats.report(game.state, on)
    assert game.state.world.rumors[before].text == "甲補上了校尉的缺。"


def test_the_note_names_the_title_of_the_faction(on):
    for faction, title in (("guan", "校尉"), ("huang", "大方渠帥"), ("haoqiang", "一方之主")):
        game = _qualified(on, f"甲{faction}", faction=faction)
        assert seats.report(game.state, on) == [f"你補上了{title}的缺，到下週一為止。"]


def test_no_seat_when_full(on):
    w = WorldState(season_one=True)
    for name in ("甲", "乙"):
        seats.report(_qualified(on, name, world=w).state, on)
    third = _qualified(on, "丙", world=w)
    assert seats.report(third.state, on) == [] and not seats.seated(third.state)
    assert list(w.seat_ledger["guan"]) == ["甲", "乙", "丙"]


def test_a_full_faction_still_keeps_the_ledger_of_the_others(on):
    """沒補上缺的人照樣在帳上（週一照帳排，下週他也有機會）。"""
    w = WorldState(season_one=True)
    for name in ("甲", "乙", "丙"):
        seats.report(_qualified(on, name, weeks={1: 5}, world=w).state, on)
    assert w.seats == {"guan": ["甲", "乙"]}
    assert w.seat_ledger["guan"]["丙"] == {1: 5}


def test_unqualified_members_are_not_on_the_ledger(on):
    game = _qualified(on, "甲")
    game.state.player.qualified = False
    seats.report(game.state, on)
    assert game.state.world.seat_ledger == {}


def test_a_drifter_is_not_on_the_ledger(on):
    game = _qualified(on, "甲")
    game.state.player.faction = None
    assert seats.report(game.state, on) == [] and game.state.world.seat_ledger == {}


def test_switch_off_no_ledger(real):
    game = _qualified(real, "甲")
    assert seats.report(game.state, real) == [] and game.state.world.seat_ledger == {}


def test_no_seat_after_the_season_ends(on):
    """季末那一刻的名單是之後頭銜（設計 13.3）要讀的：休季裡晚到的叛投、同步都不能再改它。"""
    game = _qualified(on, "甲")
    game.state.world.ended = True
    assert seats.report(game.state, on) == [] and game.state.world.seats == {} and game.state.world.seat_ledger == {}


def test_a_faction_without_titles_has_no_seats(on, monkeypatch):
    """_title 找不到第 4 階的頭銜（沒有這個陣營的頭銜表）：不排席次，不寫「你補上了的缺」。現在三個陣營都有，這只是底線。"""
    monkeypatch.setitem(ranks.TITLES, "guan", ["", "", "", "", ""])
    game = _qualified(on, "甲")
    assert seats.report(game.state, on) == [] and game.state.world.seats == {}


def test_a_sync_fills_the_seat_once_and_it_sticks(on):
    """伺服器的輪詢只同步、只存角色（server.poll_main → act_look）：同步補上的缺、抄的帳要存回共用賽季，下一次同步不再補一次。"""
    from tianxia.characters import open_characters

    game = _qualified(on, "甲", weeks={1: 7})
    open_characters().save(game.state)
    first = game.sync(1000.0)
    assert "你補上了校尉的缺，到下週一為止。" in first
    assert [e.title for e in game.state.journal if e.title == "席次"] == ["席次"]
    open_characters().save(game.state)
    again = Game(on, open_characters().load("甲"), random.Random(0))
    again.client = None
    assert again.state.world.seats == {"guan": ["甲"]} and again.state.world.seat_ledger["guan"]["甲"] == {1: 7}
    assert "你補上了校尉的缺，到下週一為止。" not in again.sync(1010.0)
    assert [e.title for e in again.state.journal if e.title == "席次"] == ["席次"]  # 紀錄裡也只有一則
    assert sum(r.text == "甲補上了校尉的缺。" for r in again.world.get_season().rumors) == 1


def test_a_sync_copies_the_ledger_of_a_seated_member_too(on):
    """已經在任的人同步時，只是帳多了新的一週的貢獻：照樣存回去（不然週一排名讀到舊帳）。"""
    from tianxia.characters import open_characters

    game = _qualified(on, "甲", weeks={1: 7})
    game.sync(1000.0)
    game.state.player.contrib_weeks[2] = 5
    game.sync(1010.0)
    open_characters().save(game.state)
    again = Game(on, open_characters().load("甲"), random.Random(0))
    assert again.state.world.seat_ledger["guan"]["甲"] == {1: 7, 2: 5}


def test_the_ledger_is_copied_when_an_action_ends(on):
    game = _qualified(on, "甲", weeks={1: 4})
    game.choose("act:explore")
    assert game.state.world.seat_ledger["guan"]["甲"] == {1: 4}


def test_the_ledger_is_copied_after_a_fast_trip(on):
    """疾行送到糧車也記貢獻（engine.travel 與 choose 一樣收在 check_summons 那一行）：travel 也要抄帳。"""
    game = _qualified(on, "甲", weeks={1: 4})
    here = on.locations[game.state.player.location]
    game.travel(str(here.connections[0]), "dash")
    assert game.state.world.seat_ledger["guan"]["甲"] == {1: 4}


def test_the_ledger_is_copied_after_a_free_text_answer(on):
    """隨口應對的效果也可能推大勢、記貢獻（六則真的事件有 trend）：answer_event 也要抄帳。"""
    game = _qualified(on, "甲", weeks={1: 4})
    game._present(on.events["jz_gz_deserter"])  # noqa: SLF001
    request = game.free_text_request("我把他押回去")
    assert request is not None
    game.answer_event(request, llm_rate=50)
    assert game.state.world.seat_ledger["guan"]["甲"] == {1: 4}
