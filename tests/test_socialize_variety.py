"""城鎮的交友不能每次都抽到「茶館說書」（2026-10-03：一季重複約 22 次，因為城鎮除了它沒有別的無條件交友事件）。

補寫的事件放在 content/events/social_<大區>.json；說書人轉述地方痕跡的段子放在 content/events/tales.json。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tianxia.content import load_content
from tianxia.events import event_matches_location
from tianxia.models import Condition

CONTENT_DIR = Path(__file__).parent.parent / "content"
SOCIAL_FILES = sorted((CONTENT_DIR / "events").glob("social_*.json"))
STAT_KEYS = {"silver", "good", "evil", "fame", "str", "agi", "con", "wis", "xinde"}


@pytest.fixture(scope="module")
def content():
    return load_content(CONTENT_DIR)


def _always_available(content, loc_id):
    """沒有條件、不是一次性的交友事件：任何玩家在這裡交友都可能抽到。"""
    location = content.locations[loc_id]
    return [
        e for e in content.events.values()
        if "socialize" in e.actions and event_matches_location(e, location)
        and e.condition == Condition() and not e.once
    ]


def _towns(content):
    return [loc_id for loc_id, loc in content.locations.items() if "城鎮" in loc.tags]


def test_every_town_has_three_socialize_events_of_its_own_besides_the_teahouse(content):
    thin = {}
    for loc_id in _towns(content):
        events = _always_available(content, loc_id)
        own = [e for e in events if loc_id in e.locations]
        if len(events) < 4 or len(own) < 3:
            thin[loc_id] = (len(events), len(own))
    assert not thin, thin


def test_every_town_has_one_free_text_socialize_event(content):
    counts = {
        loc_id: sum(1 for e in _always_available(content, loc_id) if e.free_text and loc_id in e.locations)
        for loc_id in _towns(content)
    }
    assert all(n == 1 for n in counts.values()), counts


def test_storytellers_retell_every_location_trace(content):
    """每條地方痕跡都有一則城鎮交友的說書段子在轉述（多人同服：別人做過的事會在城裡傳開）。"""
    told = set()
    for e in content.events.values():
        if "socialize" in e.actions:
            for sub in e.condition.any_of:
                told |= set(sub.marks_min)
    written = {k for e in content.events.values() for c in e.choices for k in c.effect.marks}
    assert written and written <= told, written - told


@pytest.mark.parametrize("path", SOCIAL_FILES, ids=[p.stem for p in SOCIAL_FILES])
def test_added_socialize_events_vary_their_checks_and_stay_within_limits(content, path):
    events = json.loads(path.read_text(encoding="utf-8"))
    assert events
    for e in events:
        assert e["actions"] == ["socialize"] and len(e["locations"]) == 1 and "condition" not in e, e["id"]
        assert 2 <= len(e["choices"]) <= 4, e["id"]
        checks = [c["check"] for c in e["choices"] if "check" in c]
        assert len({ck["stat"] for ck in checks}) >= 2, e["id"]
        for c in [*e["choices"], *([e["free_text"]] if "free_text" in e else [])]:
            assert "combat" not in c, e["id"]
            if "check" in c:
                assert c["check"]["stat"] in {"str", "agi", "con", "wis"} and 4 <= c["check"]["difficulty"] <= 7, e["id"]
                assert "fail_effect" in c, e["id"]
            for key in ("effect", "fail_effect"):
                eff = c.get(key, {})
                stats = eff.get("stats", {})
                assert set(stats) <= STAT_KEYS, e["id"]
                assert -40 <= stats.get("silver", 0) <= 40 and stats.get("xinde", 0) <= 12, e["id"]
                assert all(-3 <= stats.get(k, 0) <= 3 for k in ("fame", "good", "evil")), e["id"]
                assert all(stats.get(k, 0) <= 1 for k in ("str", "agi", "con", "wis")), e["id"]
                for banned in ("flags_add", "world_flags_add", "next_event", "recruit", "join_sect", "learn_skills", "marks"):
                    assert not eff.get(banned), (e["id"], banned)
