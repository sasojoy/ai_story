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


def test_choice_label_shows_who_acts_not_the_success_rate(state, content):
    drunk = content.events["drunk"]
    assert choice_label(drunk.choices[0], state, content) == "逼問（韓鐵出手）"  # 隊伍檢定：臂力最高的韓鐵
    assert choice_label(drunk.choices[1], state, content) == "摸走鐵牌"
    insight = content.events["insight"]
    assert choice_label(insight.choices[0], state, content) == "運氣衝關（本人）"  # 本人檢定
