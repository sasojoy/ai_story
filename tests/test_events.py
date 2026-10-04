import random

from tianxia.events import (
    choice_label, event_matches_location, has_events_here, pick_event, visible_choices,
)


def test_location_matching(content):
    town, lake = content.locations["town"], content.locations["lake"]
    assert event_matches_location(content.events["drunk"], town)
    assert not event_matches_location(content.events["drunk"], lake)


def test_pick_event_filters_by_action_and_location(state, content):
    rng = random.Random(0)
    assert {pick_event(state, content, "explore", rng).id for _ in range(20)} == {"drunk"}
    assert pick_event(state, content, "socialize", rng).id == "join"
    assert pick_event(state, content, "train", rng) is None


def test_pick_event_skips_seen_once_events(state, content):
    state.player.location = "lake"
    rng = random.Random(0)
    assert pick_event(state, content, "explore", rng).id == "scroll"
    state.player.seen_events.add("scroll")
    assert pick_event(state, content, "explore", rng) is None


def test_the_common_pool_never_holds_once_or_qiyu_events(state, content):
    """探索三選一：事件那一支只從可重複的事件抽，一次性與奇遇只走奇遇那一步（探索三選一設計 4.3）。"""
    state.player.location = "lake"  # 湖邊的探索事件只有殘卷（一次性＋奇遇）
    rng = random.Random(0)
    assert pick_event(state, content, "explore", rng, pool="common") is None
    assert pick_event(state, content, "explore", rng, pool="rare").id == "scroll"
    assert pick_event(state, content, "explore", rng).id == "scroll"  # 不指定池子＝照舊（遊歷、交友用）
    content.events["scroll"].once = False  # 只是奇遇、不是一次性：一樣不進可重複的池子
    assert pick_event(state, content, "explore", rng, pool="common") is None
    content.events["scroll"].once, content.events["scroll"].qiyu = True, False  # 只是一次性
    assert pick_event(state, content, "explore", rng, pool="common") is None
    state.player.location = "town"
    assert {pick_event(state, content, "explore", rng, pool="common").id for _ in range(20)} == {"drunk"}
    assert pick_event(state, content, "explore", rng, pool="rare") is None


def test_a_seen_qiyu_stays_in_the_rare_pool_but_a_seen_once_event_does_not(state, content):
    """企劃者 2026-10-03 改：奇遇看過之後還能再遇到；標了 once 的照舊只有一次。"""
    state.player.location = "lake"
    rng = random.Random(0)
    content.events["scroll"].once = False
    state.player.seen_events.add("scroll")
    assert pick_event(state, content, "explore", rng, pool="rare").id == "scroll"
    content.events["scroll"].once = True
    assert pick_event(state, content, "explore", rng, pool="rare") is None


def test_pick_event_respects_condition(state, content):
    state.player.sect = "cloud"
    assert pick_event(state, content, "socialize", random.Random(0)) is None


def test_chain_only_events_never_picked(state, content):
    state.player.location = "lake"
    rng = random.Random(0)
    picks = {pick_event(state, content, "train", rng).id for _ in range(20)}
    assert picks == {"chain_a"}


def test_visible_choices_hide_conditional(state, content):
    ev = content.events["drunk"]
    assert [i for i, _ in visible_choices(ev, state)] == [0, 1]
    state.player.stats["evil"] = 5
    assert [i for i, _ in visible_choices(ev, state)] == [0, 1, 2]


def test_has_events_here(content):
    assert has_events_here(content, content.locations["town"], "socialize")
    assert not has_events_here(content, content.locations["cave"], "socialize")


def test_choice_label_shows_who_acts_not_the_success_rate(state, content, world):
    drunk = content.events["drunk"]
    assert choice_label(drunk.choices[0], state, content, world) == "逼問（本人出手）"  # 空隊伍時只有本人
    state.player.team.append("mate")  # 韓鐵臂力比本人高
    assert choice_label(drunk.choices[0], state, content, world) == "逼問（韓鐵出手）"
    assert choice_label(drunk.choices[1], state, content, world) == "摸走鐵牌"
    insight = content.events["insight"]
    assert choice_label(insight.choices[0], state, content, world) == "運氣衝關（本人）"  # 本人檢定
