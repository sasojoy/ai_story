"""事件分級（企劃者 2026-10-26，事件分級設計稿；tianxia/tiers.py）：第二、三階照五道門開，門沒開抽不到；開到第二、三階的人
抽事件先照 tier_mix 挑一階；第二、三階的檢定不吃第一階的放寬；子開關 event_tiers 關著時第二、三階一則都抽不到；
第一階的事件與檢定序列化一個鍵都不多。用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

import random
from types import SimpleNamespace
from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import renown, tiers
from tianxia.content import ContentError, stamp_tier, validate
from tianxia.events import event_candidates, pick_event
from tianxia.models import Event
from tianxia.rules import check_outlook

pytestmark = pytest.mark.slow

HERE = "yingshui"


def _event(eid: str, tier: int = 1, door: str | None = None, difficulty: int = 10) -> Event:
    ev = Event(id=eid, title=eid, text="（旁白）", locations=[HERE], tier=tier, door=door, weight=1000,
               choices=[{"text": "試試", "check": {"stat": "str", "difficulty": difficulty}}])
    stamp_tier(ev)
    return ev


def _add(game, *events: Event) -> None:
    for ev in events:
        game.content.events[ev.id] = ev


def _ids(game) -> set[str]:
    return {e.id for e in event_candidates(game.state, game.content, "explore")}


def test_the_martial_door_opens_by_level():
    game = ready(jianfa_game(), side="guan", loc=HERE, level=19)
    _add(game, _event("t2", 2, "武事"), _event("t3", 3, "武事"))
    assert tiers.door_tier(game.state, game.content, "武事") == 1 and not {"t2", "t3"} & _ids(game)
    game.state.player.member.level = 20
    assert tiers.door_tier(game.state, game.content, "武事") == 2 and "t2" in _ids(game) and "t3" not in _ids(game)
    game.state.player.member.level = 40
    assert tiers.top_tier(game.state, game.content) == 3 and {"t2", "t3"} <= _ids(game)


def test_the_arena_and_virtue_doors():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    s, c = game.state, game.content
    assert tiers.door_tier(s, c, "擂主") == 1
    entry = SimpleNamespace(rank=7)
    with mock.patch("tianxia.arena.entry_of", return_value=entry):
        assert tiers.door_tier(s, c, "擂主") == 2
        entry.rank = 1
        assert tiers.door_tier(s, c, "擂主") == 3
    with mock.patch.object(renown, "virtue_tier", return_value=2), mock.patch.object(renown, "path", return_value="寇"):
        assert tiers.door_tier(s, c, "綠林") == 2 and tiers.door_tier(s, c, "俠義") == 1


def test_a_tier_two_player_draws_tiers_six_to_four():
    game = ready(jianfa_game(), side="guan", loc=HERE, level=20)
    _add(game, _event("t1x"), _event("t2x", 2, "武事"))
    rng = random.Random(7)
    picks = [tiers.narrow(game.state, game.content, [game.content.events["t1x"], game.content.events["t2x"]], rng)[0].tier
             for _ in range(4000)]
    assert 0.37 < picks.count(2) / len(picks) < 0.43
    assert pick_event(game.state, game.content, "explore", random.Random(1)) is not None


def test_only_tier_one_checks_get_the_ease():
    game = ready(jianfa_game(), side="guan", loc=HERE, level=20)
    s, c = game.state, game.content
    low, high = _event("e1", difficulty=10), _event("e2", 2, "武事", difficulty=10)
    gap_low = check_outlook(low.choices[0].check, s, c, game.world).gap
    gap_high = check_outlook(high.choices[0].check, s, c, game.world).gap
    assert gap_low - gap_high == c.config.jianfa.event_ease


def test_switched_off_no_higher_tier_event_is_drawn():
    game = ready(jianfa_game(event_tiers=False), side="guan", loc=HERE, level=45)
    _add(game, _event("t2", 2, "武事"))
    assert "t2" not in _ids(game)
    assert tiers.top_tier(game.state, game.content) == 1


def test_tier_one_events_and_checks_serialize_as_before_and_doors_are_checked():
    ev = _event("plain")
    dumped = ev.model_dump()
    assert "tier" not in dumped and "door" not in dumped and "tier" not in dumped["choices"][0]["check"]
    high = _event("high", 2, "名流").model_dump()
    assert high["tier"] == 2 and high["door"] == "名流" and high["choices"][0]["check"]["tier"] == 2
    game = jianfa_game()
    game.content.events["nodoor"] = Event(id="nodoor", title="x", text="x", tier=2, choices=[{"text": "x"}])
    with pytest.raises(ContentError, match="nodoor"):
        validate(game.content)
    del game.content.events["nodoor"]
    game.content.events["easy"] = _event("easy", 2, "武事", difficulty=6)
    with pytest.raises(ContentError, match="9～12"):
        validate(game.content)
