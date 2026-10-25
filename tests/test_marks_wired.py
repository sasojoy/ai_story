"""減法季批 4 接線（主機側計畫 Task 4-3、6.5 的勾選清單；整合設計 5.2；PM 2026-10-25 交接第四節之四第 4 件）：痕跡看得見——
動作存季之前、同步、排程的一下都看有沒有痕跡過門檻（marks.fire_due，只發一次）：那一刻發地方傳聞、世界層一句（〈天下形勢〉照它多一句）、
地點描寫換段；**江湖史在季末**（每個地點挑最高的那一條寫一句）；跨過門檻那一刻出過力的人（WorldState.mark_helpers）各記一則行狀。
用 tests/outcomes_kit.py 的「醉漢」（town）與它的四條痕跡規則；關著（總開關或子開關 marks_visible）一個字都不變。"""
from __future__ import annotations

import pytest

from conftest import FixedRandom
from outcomes_kit import RULES, answer, branch_game
from tianxia import annals, xingshi
from tianxia.characters import CharacterStore
from tianxia.rules import add_marks
from tianxia.state import WorldState
from tianxia.world import end_season

TALK_MARK = "town:勸醒"
RULE = next(r for r in RULES if r.mark == TALK_MARK)


def _ready(g, at=19, helpers=("乙",)):
    """季上這個痕跡已經 at 筆、這幾個人出過力（直接存回共用的季，不經 Game._save_season：那一下就會發）。"""
    w = g.state.world
    w.marks[TALK_MARK] = at
    if helpers:
        w.mark_helpers[TALK_MARK] = list(helpers)
    g.world.save_season(w)


def test_crossing_the_threshold_in_an_action_fires_once(content, world):
    g = branch_game(content, world, rng=FixedRandom(0.0))
    _ready(g)
    chronicle = len(g.world.get_season().chronicle)
    answer(g, "我好言勸他回家", "talk")
    season = g.world.get_season()
    assert season.marks[TALK_MARK] == 20 and TALK_MARK in season.marks_fired
    local, wide = season.rumors[-2:]
    assert (local.text, local.layer, local.location, local.named) == (RULE.rumor, "local", "town", False)  # 不列名字
    assert (wide.text, wide.layer, wide.named) == (RULE.rumor, "world", False)  # 世界層一句（xingshi 沒寫照傳聞那一句）
    assert len(season.chronicle) == chronicle  # 江湖史在季末才寫（PM 第 4 件）
    rumors = len(season.rumors)
    h = branch_game(content, world, name="丙", rng=FixedRandom(0.0))
    answer(h, "我好言勸他回家", "talk")
    assert len(h.world.get_season().rumors) == rumors  # 只發一次


def test_the_helpers_each_get_an_annal_at_their_next_sync(content, world):
    """跨過門檻那一刻出過力的人（乙之前記過一筆、甲這一下跨過去）各在下一次同步記一則行狀，記完把名號拿掉；沒出過力的丙沒有。"""
    yi = branch_game(content, world, name="乙", rng=FixedRandom(0.0))
    CharacterStore(world.db).save(yi.state)
    jia = branch_game(content, world, name="甲", rng=FixedRandom(0.0))
    _ready(jia, helpers=("乙",))
    answer(jia, "我好言勸他回家", "talk")
    assert world.get_season().mark_helpers[TALK_MARK] == ["乙", "甲"]  # 甲這一下也算出過力；還沒有人記行狀
    for g in (jia, yi):
        g.sync(g.now)
        notes = [a for a in g.state.player.annals if a.kind == annals.MARK]
        assert len(notes) == 1 and RULE.rumor in notes[0].text and notes[0].place == content.locations["town"].name
        assert notes[0].quote == ""
    assert TALK_MARK not in world.get_season().mark_helpers  # 都記過了：鍵拿掉
    bing = branch_game(content, world, name="丙")
    bing.sync(bing.now)
    assert not [a for a in bing.state.player.annals if a.kind == annals.MARK]
    jia.sync(jia.now)
    assert len([a for a in jia.state.player.annals if a.kind == annals.MARK]) == 1  # 只記一次


def test_marks_past_the_threshold_record_no_new_helpers(content, world):
    g = branch_game(content, world)
    w = g.state.world
    add_marks({TALK_MARK: 1}, g.state, content)
    assert w.mark_helpers == {TALK_MARK: ["甲"]}
    g.state.player.mark_days.clear()
    add_marks({"town:沒有規則": 1}, g.state, content)
    assert "town:沒有規則" not in w.mark_helpers  # 沒有痕跡規則的痕跡（事件條件讀的那些）不記
    w.marks_fired["town:扭送"] = 1.0
    add_marks({"town:扭送": 1}, g.state, content)
    assert "town:扭送" not in w.mark_helpers  # 過了門檻之後出力的不算「跨過門檻那一刻有出過力的人」


@pytest.mark.parametrize("parts", [None, {"marks_visible": False}], ids=["off", "sub-switch-off"])
def test_nothing_fires_or_is_recorded_when_off(content, world, parts):
    g = branch_game(content, world, on=parts is not None, parts=parts, rng=FixedRandom(0.0))
    _ready(g, helpers=())
    rumors = len(g.world.get_season().rumors)
    g.state.player.mark_days.clear()
    add_marks({TALK_MARK: 1}, g.state, content)
    g._save_season()
    g.sync(g.now)
    g.world_tick(g.now)
    season = g.world.get_season()
    assert season.marks[TALK_MARK] == 20 and not season.marks_fired and not season.mark_helpers
    assert len(season.rumors) == rumors
    assert "marks_fired" not in season.model_dump() and "mark_helpers" not in season.model_dump()


def test_the_place_reads_differently_past_the_threshold_when_on(content, world):
    g = branch_game(content, world)
    g.state.player.location = "town"
    loc = content.locations["town"]
    plain = g.location_text()
    _ready(g, at=20, helpers=())
    assert g.location_text() == f"{plain}\n\n{RULE.describe}"
    off = branch_game(content, world, name="乙", on=True, parts={"marks_visible": False})
    off.state.player.location = "town"
    assert off.location_text() == f"【{loc.name}】危險 {'★' * loc.danger}\n\n{loc.describe(off.state.world.flags)}"


def test_the_scheduler_fires_without_crediting_anyone(content, world):
    g = branch_game(content, world)
    _ready(g, at=20, helpers=("乙",))
    assert not g.world.get_season().marks_fired
    g.world_tick(g.now)
    season = g.world.get_season()
    assert TALK_MARK in season.marks_fired
    assert season.mark_helpers == {TALK_MARK: ["乙"]}  # 排程那一份 Game 不替任何人記行狀
    assert not [a for a in g.state.player.annals if a.kind == annals.MARK]


@pytest.mark.parametrize("counts, top_mark", [
    ({TALK_MARK: 25, "town:扭送": 31, "town:周濟": 5}, "town:扭送"),
    ({TALK_MARK: 31, "town:扭送": 25, "town:周濟": 40, "town:搜身": 3}, "town:周濟"),
    ({TALK_MARK: 31, "town:扭送": 25}, TALK_MARK),
])
def test_the_season_end_writes_the_top_mark_of_each_place(content, world, counts, top_mark):
    """PM 2026-10-25 第 4 件（照整合設計 5.2）：季末每個地點挑最高的那一條痕跡（過了門檻、人數最多）寫一句進江湖史。"""
    g = branch_game(content, world)
    w = g.state.world
    w.marks.update(counts)
    end_season(g.state, content)
    lines = [e.text for e in w.chronicle]
    top = next(r for r in RULES if r.mark == top_mark)
    assert top.rumor in lines  # 一個地點一句：人數最多的那一條
    assert not any(r.rumor in lines for r in RULES if r is not top)


def test_the_season_end_writes_nothing_when_off(content, world):
    g = branch_game(content, world, on=True, parts={"marks_visible": False})
    w = g.state.world
    w.marks.update({TALK_MARK: 25, "town:扭送": 31})
    end_season(g.state, content)
    assert not any(r.rumor in e.text for e in w.chronicle for r in RULES)


def test_the_xingshi_gets_a_fact_for_each_mark_fired_since_the_last_essay(content, world, monkeypatch):
    monkeypatch.setattr(xingshi, "lines", lambda c: {"fact": {"line": "{line}{lean}{move}"}})  # 測試內容沒有形勢的句型；這裡只看痕跡那一類
    g = branch_game(content, world)
    w = g.state.world
    w.time = 500.0
    w.marks[TALK_MARK] = 20
    g._save_season()
    w = g.state.world
    skip = len(w.rumors)  # 只看痕跡那一類（傳聞那一類照 rumors_from 讀，這裡全部跳過）
    facts = xingshi.facts(w, content, [], {}, skip, marks_since=0.0)
    assert RULE.rumor in facts
    assert RULE.rumor not in xingshi.facts(w, content, [], {}, skip, marks_since=600.0)  # 上一篇之後才過門檻的才寫
    assert xingshi.facts(w, content, [], {}, 0, marks_since=0.0).count(RULE.rumor) == 1  # 世界層那一句與痕跡那一類不寫兩次
    off = branch_game(content, world, name="乙", on=True, parts={"marks_visible": False})
    assert RULE.rumor not in xingshi.facts(off.state.world, content, [], {}, len(off.state.world.rumors), marks_since=0.0)


def test_mark_helpers_add_no_key_until_used():
    world = WorldState()
    assert "mark_helpers" not in world.model_dump() and "mark_helpers" not in world.model_dump_json()
    world.mark_helpers[TALK_MARK] = ["甲"]
    assert WorldState.model_validate_json(world.model_dump_json()).mark_helpers == {TALK_MARK: ["甲"]}
