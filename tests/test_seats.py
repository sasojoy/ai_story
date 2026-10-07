"""第一季正式版・丁：第四階席次與每週輪替（計畫 2026-10-06-第一季正式版-丁）。

用真實內容（content/）：fixture real 在 tests/conftest.py（每個測試拿 real_content 的一份複本），開關在 on 裡才打開。
席次照人數上限換算：測試裡把人數上限調成 250（0.008 × 250 ＝ 2 席）。"""
from __future__ import annotations

import random

import pytest

from tianxia import calendar, factions, push, ranks, seats
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


def test_a_season_saved_before_the_seat_fields_loads_with_empty_ones():
    old = WorldState(season_one=True).model_dump(mode="json")
    del old["seat_ledger"], old["seats"]  # 丁之前存的賽季：沒有這兩個鍵
    w = WorldState.model_validate(old)
    assert (w.seat_ledger, w.seats) == ({}, {}) and w.season_one


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


def test_a_season_opened_without_the_stamp_has_no_seats(on):
    """開關開著、可是這一季開季時沒蓋章（舊季還在跑）：規則看章，不只看設定（rules.season_one）。"""
    w = WorldState()  # season_one 預設 False：沒蓋章
    assert on.config.season_one and not w.season_one
    game = _qualified(on, "甲", world=w)
    assert seats.report(game.state, on) == [] and w.seats == {} and w.seat_ledger == {} and w.rumors == []


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


def _credit_inside(monkeypatch, name, points):
    """讓 Game.<name> 在做完它自己的事之後替這個人記 points 點第 1 週的貢獻（動作自己記的貢獻，推大勢、護糧、密謀都是這樣記的）。"""
    real = getattr(Game, name)

    def wrapped(self, *args, **kwargs):
        out = real(self, *args, **kwargs)
        push.add_contribution(self.state.player, 1, points)
        return out

    monkeypatch.setattr(Game, name, wrapped)


def _assert_ledger_is_the_new_total(game, total):
    assert game.state.player.contrib_weeks == {1: total}
    assert game.state.world.seat_ledger["guan"]["甲"] == {1: total}


def test_choose_copies_the_ledger_after_the_action_and_the_plots_credit_it(on, monkeypatch):
    """帳要抄動作自己記的貢獻（週一排名讀它）：抄的那一行排在動作與密謀結算之後，不是之前。"""
    _credit_inside(monkeypatch, "_act", 3)
    _credit_inside(monkeypatch, "_settle_plots", 2)
    game = _qualified(on, "甲", weeks={1: 4})
    game.choose("act:explore")
    _assert_ledger_is_the_new_total(game, 9)


def test_travel_copies_the_ledger_after_the_trip_credits_it(on, monkeypatch):
    """疾行送到糧車在 _depart 裡記貢獻：travel 抄帳要排在它之後。"""
    _credit_inside(monkeypatch, "_depart", 3)
    game = _qualified(on, "甲", weeks={1: 4})
    game.travel(str(on.locations[game.state.player.location].connections[0]), "dash")
    _assert_ledger_is_the_new_total(game, 7)


def test_answer_event_copies_the_ledger_after_the_effect_credits_it(on, monkeypatch):
    """隨口應對的效果推大勢、記貢獻（apply_effect）：answer_event 抄帳要排在效果之後。"""
    _credit_inside(monkeypatch, "_apply", 3)
    game = _qualified(on, "甲", weeks={1: 4})
    game._present(on.events["jz_gz_deserter"])  # noqa: SLF001
    request = game.free_text_request("我把他押回去")
    assert request is not None
    game.answer_event(request, llm_rate=50)
    assert game.state.player.contrib_weeks[1] >= 7  # 效果真的記了那 3 點（事件自己的效果也可能再記）
    assert game.state.world.seat_ledger["guan"]["甲"] == game.state.player.contrib_weeks


def test_sync_copies_the_ledger_after_arrivals_and_plots_credit_it(on, monkeypatch):
    """抵達（護糧送到）與密謀結算都在同步裡記貢獻：抄帳要排在它們之後，不然不在線時記的貢獻週一讀不到。"""
    _credit_inside(monkeypatch, "_arrivals", 3)
    _credit_inside(monkeypatch, "_settle_plots", 2)
    game = _qualified(on, "甲", weeks={1: 4})
    game.sync(1000.0)
    _assert_ledger_is_the_new_total(game, 9)


def test_a_sync_with_nothing_new_saves_the_season_zero_times(on, monkeypatch):
    """輪詢每 10 秒同步一次：帳與名單沒變就不存共用賽季（有變才存，才不會每次輪詢都整份重寫）。"""
    saves = []
    real_save = Game._save_season  # noqa: SLF001
    monkeypatch.setattr(Game, "_save_season", lambda self: saves.append(1) or real_save(self))
    game = _qualified(on, "甲", weeks={1: 4})
    game.sync(1000.0)  # 補上缺、抄帳：存一次
    assert len(saves) == 1
    game.sync(1010.0)
    game.sync(1020.0)
    assert len(saves) == 1  # 什麼都沒變：不存
    game.state.player.contrib_weeks[1] = 6
    game.sync(1030.0)
    assert len(saves) == 2  # 帳多了新的貢獻：存


def test_a_sync_of_someone_unqualified_never_saves_the_season(on, monkeypatch):
    saves = []
    real_save = Game._save_season  # noqa: SLF001
    monkeypatch.setattr(Game, "_save_season", lambda self: saves.append(1) or real_save(self))
    plain = Game.new(on, "丙", rng=random.Random(0))
    plain.client = None
    plain.state.player.faction = "guan"  # 有陣營、沒有資格
    plain.sync(1000.0)
    plain.sync(1010.0)
    assert saves == [] and plain.state.world.seat_ledger == {}

# ── Task 2：每週輪替、rank_of 與頭銜 ────────────────────────


def _season(ledger, faction="guan"):
    """一份共用賽季：帳照 ledger（名號 → 上一週第 1 週的貢獻）寫好。"""
    w = WorldState(season_one=True)
    for name, pts in ledger.items():
        w.seat_ledger.setdefault(faction, {})[name] = {1: pts}
    return w


def _notes(w, since=0):
    return [r.text for r in w.rumors[since:] if r.layer == "faction"]


def test_rotation_reads_the_ledger_not_the_saves(on):
    w = _season({"甲": 50, "乙": 10, "丙": 30})
    game = _qualified(on, "乙", world=w)
    before = len(w.rumors)
    assert seats.rotate(game.state, on, 2) == []  # 名單寫在陣營軍情裡，不上天下大事
    assert w.seats["guan"] == ["甲", "丙"]
    note = w.rumors[before]
    assert (note.layer, note.faction, note.text) == ("faction", "guan", "本週在任的校尉：甲、丙。")


def test_rotation_ranks_the_week_before_the_one_that_just_began(on):
    """第 week 週的週一排名讀第 week − 1 週的貢獻：別的週的點數不算。"""
    w = WorldState(season_one=True)
    w.seat_ledger["guan"] = {"甲": {1: 5, 2: 90}, "乙": {1: 30, 3: 90}, "丙": {1: 20}}
    game = _qualified(on, "甲", world=w)
    seats.rotate(game.state, on, 2)
    assert w.seats["guan"] == ["乙", "丙"]
    seats.rotate(game.state, on, 3)  # 第 3 週讀第 2 週：只有甲有
    assert w.seats["guan"] == ["甲", "乙"]  # 乙、丙第 2 週都是 0：同分照帳上的先後，乙在丙前面


def test_a_missing_week_counts_as_zero(on):
    w = WorldState(season_one=True)
    w.seat_ledger["guan"] = {"甲": {}, "乙": {1: 1}, "丙": {2: 99}}
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert w.seats["guan"] == ["乙", "甲"]


def test_tie_goes_to_the_earlier_qualifier(on):
    w = _season({"甲": 20, "乙": 20, "丙": 20})
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert w.seats["guan"] == ["甲", "乙"]


def test_the_seat_count_follows_the_server_size(on):
    w = _season({"甲": 9, "乙": 8, "丙": 7})
    on.config.server_max_players = 50  # 0.008 × 50 ＝ 0.4 席：至少留 1 席
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert w.seats["guan"] == ["甲"]


def test_vacancy_fill_lasts_until_monday(on):
    w = _season({"甲": 50, "乙": 40})
    w.seats["guan"] = ["甲"]
    third = _qualified(on, "丙", world=w)
    seats.report(third.state, on)  # 週三補上
    assert w.seats["guan"] == ["甲", "丙"]
    seats.rotate(third.state, on, 2)  # 週一照上週：甲 50、乙 40、丙 0
    assert w.seats["guan"] == ["甲", "乙"] and not seats.seated(third.state)


def test_the_filler_keeps_the_seat_when_last_weeks_work_was_enough(on):
    """補缺的人上週的功勞夠就留任（「到下週一為止」只是說下週一重排，不是一定下台）。"""
    w = _season({"甲": 50, "乙": 40})
    w.seats["guan"] = ["甲"]
    third = _qualified(on, "丙", weeks={1: 45}, world=w)
    seats.report(third.state, on)
    seats.rotate(third.state, on, 2)
    assert w.seats["guan"] == ["甲", "丙"] and seats.seated(third.state)


def test_each_faction_rotates_on_its_own_ledger(on):
    w = _season({"甲": 5, "乙": 9, "丙": 1})
    w.seat_ledger["huang"] = {"丁": {1: 3}, "戊": {1: 8}}
    before = len(w.rumors)
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert w.seats == {"guan": ["乙", "甲"], "huang": ["戊", "丁"]}
    notes = w.rumors[before:]
    assert [(r.faction, r.text) for r in notes] == [
        ("guan", "本週在任的校尉：乙、甲。"), ("huang", "本週在任的大方渠帥：戊、丁。"),
    ]


def test_no_note_when_the_list_is_unchanged(on):
    w = _season({"甲": 50, "乙": 40})
    w.seats["guan"] = ["甲", "乙"]
    before = len(w.rumors)
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert len(w.rumors) == before and w.seats["guan"] == ["甲", "乙"]


def test_a_reshuffle_of_the_same_people_posts_nothing(on):
    """名單有變指的是誰在任，不是排在前面還是後面：補缺的丙先坐進去，週一排完還是同一批人（排名順序變了）就不重發一遍。"""
    w = _season({"甲": 10, "乙": 60})
    w.seats["guan"] = ["甲", "乙"]
    before = len(w.rumors)
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert w.seats["guan"] == ["乙", "甲"]  # 名單照新的排名寫回
    assert len(w.rumors) == before


def test_a_changed_set_posts_one_note_even_when_only_one_seat_moves(on):
    w = _season({"甲": 50, "乙": 10, "丙": 40})
    w.seats["guan"] = ["甲", "乙"]
    before = len(w.rumors)
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert _notes(w, before) == ["本週在任的校尉：甲、丙。"]


def test_a_faction_whose_ledger_emptied_loses_its_seats_without_a_note(on):
    """帳上沒有人（叛投讓出席次之後的底線）：名單清空，不發「本週在任的校尉：。」這種空句。"""
    w = WorldState(season_one=True)
    w.seat_ledger["guan"] = {}
    w.seats["guan"] = ["甲"]
    before = len(w.rumors)
    seats.rotate(_qualified(on, "乙", world=w).state, on, 2)
    assert w.seats["guan"] == [] and len(w.rumors) == before


def test_a_faction_without_titles_is_left_alone_by_the_rotation(on, monkeypatch):
    """跟 report 一樣：找不到第 4 階的頭銜就不排、不發「本週在任的：…」這種缺了頭銜的句子。"""
    monkeypatch.setitem(ranks.TITLES, "guan", ["", "", "", "", ""])
    w = _season({"甲": 50, "乙": 40})
    w.seats["guan"] = ["乙"]
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert w.seats["guan"] == ["乙"] and w.rumors == []


def test_rotation_never_posts_to_the_world_news(on):
    """名單是陣營軍情，不上天下大事（傳聞分層 4.1）：公開的傳聞一則都沒多。"""
    w = _season({"甲": 50})
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert [r.layer for r in w.rumors] == ["faction"]


def test_rotation_does_nothing_with_the_switch_off_or_after_the_season(on):
    w = _season({"甲": 50})
    w.season_one = False  # 這一季開季時沒開：舊季照舊
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert w.seats == {} and w.rumors == []


def test_rotation_leaves_the_ended_season_alone(on):
    """季末那一刻的名單是之後頭銜要讀的（設計 13.3）：收季之後的週一不再排。"""
    w = _season({"甲": 50, "乙": 40})
    w.seats["guan"] = ["乙"]
    w.ended = True
    seats.rotate(_qualified(on, "甲", world=w).state, on, 2)
    assert w.seats["guan"] == ["乙"]


def test_rank_and_title_follow_the_seat(on):
    w = WorldState(season_one=True)
    game = _qualified(on, "甲", world=w)
    assert ranks.rank_of(game.state) == 3 and ranks.title(on, game.state) == "軍司馬（校尉候缺）"
    w.seats["guan"] = ["甲"]
    assert ranks.rank_of(game.state) == 4 and ranks.title(on, game.state) == "校尉"
    w.seats["guan"] = []  # 週一被擠下來：回到候缺
    assert ranks.rank_of(game.state) == 3 and ranks.title(on, game.state) == "軍司馬（校尉候缺）"


def test_the_title_of_a_seated_member_in_each_faction(on):
    for faction, title in (("guan", "校尉"), ("huang", "大方渠帥"), ("haoqiang", "一方之主")):
        w = WorldState(season_one=True)
        game = _qualified(on, f"甲{faction}", faction=faction, world=w)
        seats.report(game.state, on)
        assert (ranks.rank_of(game.state), ranks.title(on, game.state)) == (4, title)


def test_a_seat_in_another_faction_does_not_count(on):
    """在任看自己陣營的名單：別的陣營的名單上剛好有同名的人（叛投前的舊帳）不算。"""
    w = WorldState(season_one=True)
    w.seats["huang"] = ["甲"]
    game = _qualified(on, "甲", faction="guan", world=w)
    assert ranks.rank_of(game.state) == 3


def test_an_unqualified_name_on_the_list_is_still_rank_three_or_below(on):
    """rank_of 只有「有資格而且在任」才是 4：沒資格的人就算名號在名單上（不該發生）也不被抬成第 4 階。"""
    w = WorldState(season_one=True)
    game = _qualified(on, "甲", world=w)
    game.state.player.qualified = False
    w.seats["guan"] = ["甲"]
    assert ranks.rank_of(game.state) == 3 and ranks.title(on, game.state) == "軍司馬"


def test_a_drifter_is_rank_zero_whatever_the_list_says(on):
    w = WorldState(season_one=True)
    game = _qualified(on, "甲", world=w)
    game.state.player.faction = None
    w.seats["guan"] = ["甲"]
    assert ranks.rank_of(game.state) == 0


def test_the_stored_rank_stays_three_for_a_seated_member(on):
    """存檔的階（PlayerState.rank）不隨席次動：求見門檻、晉升都還讀它；第 4 階只是 rank_of 看的此刻。"""
    game = _qualified(on, "甲")
    seats.report(game.state, on)
    assert game.state.player.rank == 3 and ranks.rank_of(game.state) == 4
    assert ranks.next_rank_up(game.state, on) is None  # 沒有第 5 階：被打發時不會許諾「再升一階」


def test_the_defection_prompt_names_the_seat_title(on):
    from tianxia import defection

    game = _qualified(on, "甲")
    seats.report(game.state, on)
    text = defection.prompt(game.state, on, on.scenario.faction("huang"), "")
    assert "身份歸零（你現在是校尉）" in text


def test_the_status_line_shows_the_seat_title(on):
    game = _qualified(on, "甲")
    assert game.status_data()["affiliation"].endswith("軍司馬（校尉候缺）")
    seats.report(game.state, on)
    assert game.status_data()["affiliation"].endswith("校尉")


def test_the_week_hook_runs_the_rotation(on):
    from tianxia import world as world_mod

    w = _season({"甲": 50})
    w.hooked_week = 2  # 週一的掛鉤跑的時候 hooked_week 已經是剛跨進的那一週
    game = _qualified(on, "甲", world=w)
    world_mod.WEEK_HOOKS[0](game.state, on, random.Random(0))  # 排第一個：在軍令發令之前
    assert w.seats["guan"] == ["甲"]


def _real_seconds_to_week(content, game, week):
    """從開季算起，到第 week 週週一 00:00 要多少現實秒（世界秒 ÷ time_scale）。"""
    return calendar.week_start(week, content, game.state.world) / content.config.time_scale


def _two_challengers(game):
    """第 1 週：帳上多了兩個上一週比甲多做事的人（乙 50、丙 40），甲 7；席次兩席。第 1 週的掛鉤（開季那一刻）已經跑過了。"""
    def _apply(season):
        season.seat_ledger.update({"guan": {"乙": {1: 50}, "丙": {1: 40}, "甲": {1: 7}}})
        season.hooked_week = 1

    game.world.mutate_season(_apply)


def test_a_season_walking_into_week_two_rotates_the_seats_then_issues_the_orders(on, monkeypatch):
    """整條路：時間走進第 2 週，掛鉤先排席次、再發軍令（軍令之後要讀在任的人）；每週只排一次。"""
    from tianxia import orders

    game = _qualified(on, "甲", weeks={1: 7})
    _two_challengers(game)
    order_calls = []
    real_issue = orders.issue

    def spy(state, content, week, rng):
        order_calls.append(list(state.world.seats.get("guan", [])))  # 發令那一刻，席次已經排好了
        return real_issue(state, content, week, rng)

    monkeypatch.setattr(orders, "issue", spy)
    game.sync(1000.0)
    assert game.world.get_season().seats["guan"] == ["甲"]  # 週內：甲補上了缺（兩席還空一席）
    order_calls.clear()
    week_two = 1000.0 + _real_seconds_to_week(on, game, 2) + 5
    game.sync(week_two)
    season = game.world.get_season()
    assert season.seats["guan"] == ["乙", "丙"]
    assert order_calls == [["乙", "丙"]]
    assert _notes(season).count("本週在任的校尉：乙、丙。") == 1
    game.sync(week_two + 4)  # 同一週再同步：不再排、不再發
    assert _notes(game.world.get_season()).count("本週在任的校尉：乙、丙。") == 1


# ── N5：賽季時鐘暫停時凍結世界的變化 ─────────────────────


def _pause(game, now):
    assert game.world.pause_clock(now)


def _resume(game, now):
    from tianxia.world import resume_season_clock

    assert resume_season_clock(game.world, game.content, now, random.Random(0), "繼續。") is not None


def test_a_pause_holds_the_seat_fill_and_the_resume_fills_it_once(on):
    from tianxia.characters import open_characters

    game = _qualified(on, "甲", weeks={1: 7})
    _pause(game, 1000.0)
    msgs = game.sync(1100.0)
    assert "你補上了校尉的缺，到下週一為止。" not in msgs
    season = game.world.get_season()
    assert season.seats == {} and season.seat_ledger == {}  # 暫停中不補缺、帳也不動
    assert [r.text for r in season.rumors if "補上" in r.text] == []
    assert [e.title for e in game.state.journal if e.title == "席次"] == []
    _resume(game, 1200.0)
    assert "你補上了校尉的缺，到下週一為止。" in game.sync(1210.0)
    open_characters().save(game.state)
    season = game.world.get_season()
    assert season.seats == {"guan": ["甲"]} and season.seat_ledger["guan"]["甲"] == {1: 7}
    assert sum(r.text == "甲補上了校尉的缺。" for r in season.rumors) == 1
    assert "你補上了校尉的缺，到下週一為止。" not in game.sync(1220.0)
    assert [e.title for e in game.state.journal if e.title == "席次"] == ["席次"]


def test_an_action_during_a_pause_does_not_fill_a_seat(on):
    """伺服器本來就擋暫停中的動作；引擎自己也不在暫停中補缺。choose 與隨口應對在引擎裡本來就被擋（選單只剩一顆灰的、
    free_text_request 回 None），到不了抄帳那一行；travel 沒有這一層，直接叫它（測試與腳本的路）就靠 _report_seat 擋。"""
    game = _qualified(on, "甲", weeks={1: 7})
    _pause(game, 1000.0)
    assert game.choose("act:explore") == ["（此刻無法這麼做。）"]
    game.travel(str(on.locations[game.state.player.location].connections[0]), "dash")
    game._present(on.events["jz_gz_deserter"])  # noqa: SLF001
    assert game.free_text_request("我把他押回去") is None
    assert game.world.get_season().seats == {} and game.world.get_season().seat_ledger == {}
    _resume(game, 1500.0)
    assert "你補上了校尉的缺，到下週一為止。" in game.sync(1510.0)


def test_a_pause_holds_the_monday_rotation_and_the_resume_rotates_once(on):
    game = _qualified(on, "甲", weeks={1: 7})
    _two_challengers(game)
    game.sync(1000.0)  # 甲補上空著的缺
    store = game.world
    assert store.get_season().seats["guan"] == ["甲"]
    hooked = store.get_season().hooked_week
    week_two = _real_seconds_to_week(on, game, 2)
    _pause(game, 1001.0)
    game.sync(1000.0 + week_two + 100)  # 現實時間已經過了週一，可是賽季時鐘停著
    season = store.get_season()
    assert season.hooked_week == hooked and season.seats["guan"] == ["甲"]
    assert _notes(season).count("本週在任的校尉：乙、丙。") == 0
    resume_at = 1000.0 + week_two + 200
    _resume(game, resume_at)
    game.sync(resume_at + week_two)  # 繼續之後走過週一
    season = store.get_season()
    assert season.hooked_week == hooked + 1 and season.seats["guan"] == ["乙", "丙"]
    assert _notes(season).count("本週在任的校尉：乙、丙。") == 1
    game.sync(resume_at + week_two + 30)
    assert _notes(store.get_season()).count("本週在任的校尉：乙、丙。") == 1
    assert ranks.title(on, game.state) == "軍司馬（校尉候缺）"  # 甲被擠下來了：回到候缺
