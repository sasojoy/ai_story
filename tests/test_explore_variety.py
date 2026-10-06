"""探索不能每次都抽到同一則事件、同一個判定（2026-10-03 試玩回饋：「一個地區的探索都只會有一種劇情，判定的基準完全一樣」）。

補寫的事件放在 content/events/explore_<大區>.json；這裡檢查的是整份內容，不分檔案。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tianxia.content import load_content
from tianxia.events import event_matches_location
from tianxia.models import Condition

CONTENT_DIR = Path(__file__).parent.parent / "content"
EXPLORE_FILES = sorted((CONTENT_DIR / "events").glob("explore_*.json"))
STAT_KEYS = {"silver", "good", "evil", "fame", "str", "agi", "con", "wis", "xinde"}


@pytest.fixture(scope="module")
def content():
    return load_content(CONTENT_DIR)


def _places(content):
    """探索得到事件的地點：序章的草廬（Location.prologue_only）不算，那裡的探索是師父安排好的草廬四景。"""
    return [loc_id for loc_id, loc in content.locations.items() if not loc.prologue_only]


def _always_available(content, loc_id):
    """沒有條件、不是一次性的探索事件：任何玩家在這裡探索都可能抽到。"""
    location = content.locations[loc_id]
    return [
        e for e in content.events.values()
        if "explore" in e.actions and event_matches_location(e, location)
        and e.condition == Condition() and not e.once
    ]


def test_every_location_has_at_least_four_explore_events_and_three_of_its_own(content):
    thin = {}
    for loc_id in _places(content):
        events = _always_available(content, loc_id)
        own = [e for e in events if loc_id in e.locations]
        if len(events) < 4 or len(own) < 3:
            thin[loc_id] = (len(events), len(own))
    assert not thin, thin


def test_every_location_offers_checks_on_at_least_three_different_stats(content):
    narrow = {}
    for loc_id in _places(content):
        stats = {c.check.stat for e in _always_available(content, loc_id) for c in e.choices if c.check}
        if len(stats) < 3:
            narrow[loc_id] = stats
    assert not narrow, narrow


@pytest.mark.parametrize("path", EXPLORE_FILES, ids=[p.stem for p in EXPLORE_FILES])
def test_added_events_vary_their_checks_and_stay_within_limits(content, path):
    events = json.loads(path.read_text(encoding="utf-8"))
    assert events
    rumors = 0
    for e in events:
        assert len(e["locations"]) == 1 and "condition" not in e and "actions" not in e, e["id"]
        assert 2 <= len(e["choices"]) <= 4, e["id"]
        checks = [c["check"] for c in e["choices"] if "check" in c]
        assert len({ck["stat"] for ck in checks}) >= 2, e["id"]  # 不同長處的人有不同的路
        for c in e["choices"]:
            if "check" in c:
                assert c["check"]["stat"] in {"str", "agi", "con", "wis"} and 3 <= c["check"]["difficulty"] <= 8, e["id"]  # 難度帶另見 test_real_content.py::DIFFICULTY_BANDS
            if "check" in c or "combat" in c:
                assert "fail_effect" in c, e["id"]
            if "combat" in c:
                assert c["combat"] in content.locations[e["locations"][0]].enemies, e["id"]
            for key in ("effect", "fail_effect"):
                eff = c.get(key, {})
                stats = eff.get("stats", {})
                assert set(stats) <= STAT_KEYS, e["id"]
                assert -40 <= stats.get("silver", 0) <= 40 and stats.get("xinde", 0) <= 15, e["id"]
                assert all(-3 <= stats.get(k, 0) <= 3 for k in ("fame", "good", "evil")), e["id"]
                assert all(stats.get(k, 0) <= 1 for k in ("str", "agi", "con", "wis")), e["id"]
                assert set(eff.get("trend", {})) <= {"front"}, e["id"]
                assert all(1 <= abs(v) <= 3 for v in eff.get("trend", {}).values()), e["id"]
                assert sum(eff.get("materials", {}).values()) <= 1, e["id"]
                assert all(content.materials[m].tier <= 2 for m in eff.get("materials", {})), e["id"]
                for banned in ("flags_add", "world_flags_add", "next_event", "recruit", "join_sect", "learn_skills"):
                    assert not eff.get(banned), (e["id"], banned)
                rumors += bool(eff.get("rumor"))
    assert rumors <= 2


def test_every_location_has_one_free_text_explore_event(content):
    """隨口應對每個地點先開 1 則（探索的多人與 LLM 玩法設計第五節）。"""
    counts = {
        loc_id: sum(1 for e in _always_available(content, loc_id) if e.free_text and loc_id in e.locations)
        for loc_id in _places(content)
    }
    assert all(n == 1 for n in counts.values()), counts


def test_location_traces_lead_somewhere(content):
    """地方痕跡：至少 8 條，每條都有 marks_min 條件的後果事件。"""
    readers = {k for e in content.events.values() for k in e.condition.marks_min}
    assert len({k.split(":")[0] for k in readers}) >= 8
