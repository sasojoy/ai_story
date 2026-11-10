"""親衛隊長（features/guard）第五批：成長期三段（初來、相熟、長成）與每天教他（Joy 2026-11-10 設計稿 GzVzRd…「好」）。測試內容、沒有模型。"""
from __future__ import annotations

import pytest

from tianxia import rules as core_rules
from tianxia.features.guard import actions, bots, rules, texts


@pytest.fixture
def kid(game):
    t = game.content.config.guard
    t.enabled = True
    game.state.player.member.level = t.meet_level
    game.client = None
    game.sync(game.now)
    actions.meet_on_explore(game, game.state.player.location)
    game.choose("guard:save")
    game.choose("guard:adopt:男")
    return game


def _next_day(game):
    game.sync(game.now + core_rules.day_seconds(game.content, game.state.world))


def _clear(game):
    """答掉眼前那一件（第一個做法），回它是什麼種類。"""
    b = game.state.player.guard
    if b.event is None:
        return ""
    kind = b.event.kind
    game.choose("guard:open")
    game.choose("guard:pick:0")
    return kind


def test_a_child_starts_wary_and_cannot_be_sent_to_study_yet(kid):
    b = kid.state.player.guard
    st = actions.status(kid)["guard"]
    assert b.phase == 0 and st["stage_text"].startswith("初來") and "十二三歲" in st["stage_text"]
    assert not st["can_study"] and st["grow"]["phase"] == "初來"
    kid.state.player.member.level = 99  # 等級再高也一樣
    assert not actions.status(kid)["guard"]["can_study"]


def test_teaching_once_a_day_pushes_his_tags_and_counts_as_a_thing_together(kid):
    b, t = kid.state.player.guard, kid.content.config.guard
    st = actions.status(kid)["guard"]
    assert {x["id"] for x in st["lessons"]} == {f"guard:teach:{k}" for k in texts.LESSONS}
    msgs = kid.choose("guard:teach:read")
    assert msgs and b.tags.get("謀") == 1 and b.phase_n == 1 and "讀書" in b.log[-1].text
    assert actions.status(kid)["guard"]["lessons"] == []  # 今天教過了
    assert any("教過" in m for m in kid.choose("guard:teach:fist")) and b.tags.get("勇") is None
    _next_day(kid)
    assert actions.status(kid)["guard"]["lessons"]
    assert actions.status(kid)["guard"]["look"] == "愛讀書"
    assert t.lessons["play"]["qing"] == 1


def test_three_phases_each_end_with_a_big_event_then_he_wants_to_study(kid):
    b, t = kid.state.player.guard, kid.content.config.guard
    t.phase_days, t.phase_events = 1, 3  # 測試內容的季只有十四天：數字縮小，走法一樣
    seen = []
    for _ in range(40):
        if b.phase >= 3:
            break
        kid.choose("guard:teach:fist") if actions._can_teach(kid, b) else None
        kind = _clear(kid)
        if kind == "milestone":
            seen.append(b.phase)
        _next_day(kid)
    assert seen == [1, 2, 3]
    assert b.phase == 3 and b.stage == "grow"
    st = actions.status(kid)["guard"]
    assert st["can_study"] and st["grow"] is None and st["lessons"] == []
    assert any("發燒" in e.text for e in b.log) and any("爹娘" in e.text for e in b.log)


def test_the_big_event_waits_for_both_the_days_and_the_things(kid):
    b, t = kid.state.player.guard, kid.content.config.guard
    b.phase_n = t.phase_events  # 件數夠了、日子不夠
    _clear(kid)
    kid.sync(kid.now)
    assert b.event is None or b.event.kind != "milestone"
    b.phase_days = t.phase_days
    _clear(kid)
    kid.sync(kid.now)
    assert b.event is not None and b.event.kind == "milestone" and b.event.fixed == "fever"


def test_the_wish_names_what_he_leans_to(kid):
    b, t = kid.state.player.guard, kid.content.config.guard
    b.phase, b.tags = 2, {"仁": 5, "勇": 1}
    ev = rules.fixed_event(t, b, "milestone", 1, "x")
    assert texts.WANTS["仁"] in ev.text and len(ev.choices) == 3


def test_his_face_follows_the_phase(kid):
    b, t = kid.state.player.guard, kid.content.config.guard
    assert rules.art(t, b)["face"].endswith("child/m-saved.webp")
    b.phase = 1
    assert rules.art(t, b)["face"].endswith("child/m-grown.webp")
    b.phase = 2
    assert rules.art(t, b)["face"].endswith(("child/m-teen.webp", "child/m-grown.webp"))


def test_a_new_season_keeps_how_far_he_has_grown(kid):
    b = kid.state.player.guard
    b.phase, b.phase_days, b.phase_n, b.teach_day = 1, 2, 3, 5
    actions.on_season_start(kid, None)
    assert (b.phase, b.phase_days, b.phase_n, b.teach_day, b.phase_day) == (1, 2, 3, 0, 0)


def test_bots_teach_him_from_the_menu(kid):
    kid.state.player.bot = "test"
    ids = [o.id for o in kid.options(odds=False)]
    teach = [i for i in ids if i.startswith("guard:teach:")]
    assert len(teach) == len(texts.LESSONS)
    scores = {i: bots.score(kid, next(o for o in kid.options(odds=False) if o.id == i)) for i in teach}
    assert max(scores.values()) > min(scores.values())
