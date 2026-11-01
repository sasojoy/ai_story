"""豪強兩本帳與「此刻幫誰」的純規則（減法季整合設計 3.2；計畫第五節 Task 3c-1、5.0 第 8～10 條）。

「此刻幫誰」就是 PlayerState.ally（豪強分屬兩軍的季投靠時挑的那一軍）：wins.lean_of 讀它、wins.set_lean 寫它；
換邊不算叛投、帳不清。這裡只測 wins 的函式與存檔的鍵；兩本帳要四勝利開著（減法季 Config.jianfa＋開季的章，ON），
引擎的接線另見 tests/test_four_wins_wiring.py。
用正式內容（season21：豪強分屬兩軍、劇本有三個陣營），載入超過一秒，整個檔標 slow。"""
from __future__ import annotations

import json

import pytest

from conftest import real_content
from tianxia import wins
from tianxia.models import LEAN_DEFAULT_BY_JOIN, JianfaRules
from tianxia.state import QUIET_DEFAULTS, GameState, WorldState, new_game_state

pytestmark = pytest.mark.slow

ON = WorldState(jianfa_on=True)  # 這一季開季時蓋了減法季的章（season21 的設定本來就開著）


@pytest.fixture(scope="module")
def content():
    return real_content("season21")


def _player(content, name="甲客", faction=None, ally=None):
    p = new_game_state(content, name).player
    p.faction, p.ally = faction, ally
    return p


def test_only_the_gentry_keep_two_books(content):
    assert wins.is_gentry(_player(content, faction="haoqiang", ally="guan"), content)
    assert not wins.is_gentry(_player(content, faction="guan"), content)
    assert not wins.is_gentry(_player(content, faction="huang"), content)
    assert not wins.is_gentry(_player(content), content)  # 散人


def test_army_credit_goes_to_contrib_only(content):
    p = _player(content, faction="guan")
    wins.credit(p, content, ON, 2, 7)
    assert (p.contrib, p.contrib_weeks, p.ledgers) == (7, {2: 7}, {})


def test_gentry_credit_goes_to_the_lean_book_and_contrib(content):
    p = _player(content, faction="haoqiang", ally="guan")
    wins.credit(p, content, ON, 1, 5)
    wins.credit(p, content, ON, 2, 3)
    assert p.ledgers == {"guan": 8}
    assert (p.contrib, p.contrib_weeks) == (8, {1: 5, 2: 3})  # 軍階、席次、榜照舊讀 contrib


def test_gentry_credit_can_name_the_side(content):
    """決戰的戰功記參戰那一刻那一邊（計畫 5.0 第 12 條）：side 蓋過此刻的傾向。"""
    p = _player(content, faction="haoqiang", ally="guan")
    wins.credit(p, content, ON, 1, 4, side="huang")
    assert p.ledgers == {"huang": 4}
    assert p.contrib == 4


def test_side_that_is_not_one_of_the_gentry_allies_keeps_no_book(content):
    p = _player(content, faction="haoqiang", ally="guan")
    wins.credit(p, content, ON, 1, 4, side="haoqiang")
    assert p.ledgers == {}
    assert p.contrib == 4


def test_gentry_without_a_lean_only_adds_contrib(content):
    p = _player(content, faction="haoqiang")
    wins.credit(p, content, ON, 1, 4)
    assert (p.contrib, p.ledgers) == (4, {})


def test_off_season_credit_only_adds_contrib(content):
    """四勝利關著（沒蓋減法季章的季）：照舊只記 contrib，豪強也不記帳（一個字都不變）。"""
    p = _player(content, faction="haoqiang", ally="guan")
    wins.credit(p, content, WorldState(), 1, 5)
    assert (p.contrib, p.contrib_weeks, p.ledgers) == (5, {1: 5}, {})
    assert wins.on(content, ON) and not wins.on(content, WorldState())


def test_zero_points_record_nothing(content):
    p = _player(content, faction="haoqiang", ally="guan")
    wins.credit(p, content, ON, 1, 0)
    assert (p.contrib, p.contrib_weeks, p.ledgers) == (0, {}, {})


def test_switching_lean_keeps_both_books_and_is_not_a_defection(content):
    p = _player(content, faction="haoqiang", ally="guan")
    wins.credit(p, content, ON, 1, 10)
    assert wins.lean_problem(p, content, "huang") == ""
    assert wins.set_lean(p, content, "huang")
    assert wins.lean_of(p, content) == "huang" and p.ally == "huang"
    assert p.lean_changed == 1
    assert (p.defected, p.contrib, p.ledgers) == (False, 10, {"guan": 10})  # 帳不清、不算叛投
    wins.credit(p, content, ON, 1, 6)
    assert p.ledgers == {"guan": 10, "huang": 6}
    assert p.contrib == 16
    assert wins.set_lean(p, content, "guan")
    assert p.lean_changed == 2
    assert p.ledgers == {"guan": 10, "huang": 6}


def test_lean_problems(content):
    gentry = _player(content, faction="haoqiang", ally="guan")
    assert wins.lean_problem(gentry, content, "guan") == wins.LEAN_SAME.format(side="官軍")
    assert wins.lean_problem(gentry, content, "haoqiang") == wins.LEAN_BAD
    assert wins.lean_problem(_player(content, faction="guan"), content, "huang") == wins.LEAN_NOT_GENTRY
    assert wins.lean_problem(_player(content), content, "huang") == wins.LEAN_NOT_GENTRY
    army = _player(content, faction="guan")
    assert not wins.set_lean(army, content, "huang")
    assert (army.ally, army.lean_changed) == (None, 0)
    assert not wins.set_lean(gentry, content, "guan")  # 本來就幫官軍：不算換一次
    assert gentry.lean_changed == 0


def test_first_lean_is_not_counted_as_a_switch(content):
    """還沒有傾向（投靠那一下由接線照投靠點預設給）：第一次給不算換邊。"""
    p = _player(content, faction="haoqiang")
    assert wins.set_lean(p, content, "huang")
    assert (p.ally, p.lean_changed) == ("huang", 0)


def test_lean_of_is_none_for_armies_even_with_a_stale_ally(content):
    p = _player(content, faction="guan", ally="huang")
    assert wins.lean_of(p, content) is None


def test_ledger_view(content):
    p = _player(content, faction="haoqiang", ally="guan")
    assert wins.ledger_view(p, content) == {"guan": 0, "huang": 0}
    wins.credit(p, content, ON, 1, 120)
    wins.credit(p, content, ON, 1, 40, side="huang")
    assert wins.ledger_view(p, content) == {"guan": 120, "huang": 40}
    assert wins.ledger_view(_player(content, faction="guan"), content) is None
    assert wins.ledger_view(_player(content), content) is None


def test_default_lean_by_join_point_matches_the_scenario(content):
    """企劃者 2026-10-24（計畫第十一節第 6 件）：鄉里結社、曹氏莊院幫官軍，豪族塢堡幫黃巾；豪強每個投靠點都有預設、都是它能幫的那一軍。"""
    assert LEAN_DEFAULT_BY_JOIN == {"zhuo_militia_hall": "guan", "cao_manor": "guan", "haozu_fort": "huang"}
    rules = JianfaRules()
    gentry = content.scenario.faction("haoqiang")
    assert {loc: wins.lean_default(content, loc, rules) for loc in gentry.join_at} == LEAN_DEFAULT_BY_JOIN
    assert wins.check(content, rules) == []
    assert wins.lean_default(content, "changshe", rules) is None  # 官軍的投靠點：不是豪強的


def test_check_reports_a_bad_default(content):
    rules = JianfaRules(lean_default_by_join={"cao_manor": "haoqiang", "changshe": "guan"})
    problems = wins.check(content, rules)
    assert len(problems) == 3  # cao_manor 給了不能幫的一方；changshe 不是豪強的投靠點；兩處投靠點沒寫預設（算一條）
    assert any("cao_manor" in line for line in problems)
    assert any("changshe" in line for line in problems)
    assert any("zhuo_militia_hall" in line and "haozu_fort" in line for line in problems)


def _keys(state: GameState) -> set[str]:
    return set(json.loads(state.model_dump_json())["player"])


def test_new_fields_add_no_keys_until_used(content):
    """存檔 JSON（CharacterStore.save 用 model_dump_json）：兩本帳空的、沒換過邊時不多一個鍵；舊存檔讀得進來。"""
    state = new_game_state(content, "甲客")
    keys = _keys(state)
    assert "ledgers" not in keys and "lean_changed" not in keys
    # 別的批也往 QUIET_DEFAULTS 加欄位（批 4 的 deed_day、deed_today；批 2 的 fights_today 這些，tests/test_jianfa_switch.py 測）：
    # 照整份清單扣，不寫死這兩個
    assert keys == set(type(state.player).model_fields) - set(QUIET_DEFAULTS) - _excluded(state)
    p = state.player
    p.faction, p.ally = "haoqiang", "guan"
    wins.credit(p, content, ON, 1, 9)
    wins.set_lean(p, content, "huang")
    data = json.loads(state.model_dump_json())["player"]
    assert data["ledgers"] == {"guan": 9} and data["lean_changed"] == 1
    back = GameState.model_validate_json(state.model_dump_json())
    assert (back.player.ledgers, back.player.lean_changed) == ({"guan": 9}, 1)
    old = json.loads(new_game_state(content, "乙客").model_dump_json())
    old["player"].pop("ledgers", None)
    old["player"].pop("lean_changed", None)
    loaded = GameState.model_validate(old)
    assert (loaded.player.ledgers, loaded.player.lean_changed) == ({}, 0)


def _excluded(state: GameState) -> set[str]:
    """本來就不進存檔的欄位（Field(exclude=True)）。"""
    return {name for name, field in type(state.player).model_fields.items() if field.exclude}
