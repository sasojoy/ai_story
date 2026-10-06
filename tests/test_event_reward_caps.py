"""補寫事件的獎勵上限：三份補寫的事件池共用這一個檢查（以前三個檔各寫一份）。
- 探索補寫：content/events/explore_<大區>.json（tests/test_explore_variety.py）；
- 城鎮交友補寫：content/events/social_<大區>.json（tests/test_socialize_variety.py）；
- 四個新大區的探索事件：content/events/<大區>.json（tests/test_events_new_regions.py）。
每個選項結果（effect、fail_effect 各自）都要在上限之內；各池子的上限照原本各檔寫的，不全一樣（POOLS）。
選項幾個、檢定的屬性與難度、要不要 fail_effect、傳聞幾則這些結構上的檢查留在各自的檔案。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tianxia.content import load_content

CONTENT_DIR = Path(__file__).parent.parent / "content"
EVENTS = CONTENT_DIR / "events"
ATTRS = ("str", "agi", "con", "wis")
BASE_KEYS = {"silver", "good", "evil", "fame", *ATTRS}
ADDED = ("flags_add", "world_flags_add", "next_event", "recruit", "join_sect")  # 補寫的事件不能接劇情、不能招人、不能入門派

# 池子 →（檔案, 檢查哪些上限）。xinde：心得最多給多少（None＝心得不能給）；trend、materials：要不要檢查大勢與素材；
# banned：不能出現的效果；free_text：隨口應對的結果也算進去
POOLS = {
    "explore": ([*sorted(EVENTS.glob("explore_*.json"))], {
        "xinde": 15, "trend": True, "materials": True, "banned": (*ADDED, "learn_skills"), "free_text": False,
    }),
    "social": ([*sorted(EVENTS.glob("social_*.json"))], {
        "xinde": 12, "trend": False, "materials": False, "banned": (*ADDED, "learn_skills", "marks"), "free_text": True,
    }),
    "region": ([EVENTS / f"{r}.json" for r in ("youzhou", "jizhou", "luoyang", "nanyang")], {
        "xinde": None, "trend": True, "materials": True, "banned": ADDED, "free_text": False,
    }),
}
CASES = [(pool, path) for pool, (paths, _) in POOLS.items() for path in paths]


@pytest.fixture(scope="module")
def content():
    return load_content(CONTENT_DIR)


@pytest.mark.parametrize(("pool", "path"), CASES, ids=[f"{pool}-{path.stem}" for pool, path in CASES])
def test_added_event_rewards_stay_within_the_caps(content, pool, path):
    caps = POOLS[pool][1]
    stat_keys = BASE_KEYS | ({"xinde"} if caps["xinde"] is not None else set())
    events = json.loads(path.read_text(encoding="utf-8"))
    assert events
    for e in events:
        results = [*e["choices"], *([e["free_text"]] if caps["free_text"] and "free_text" in e else [])]
        for c in results:
            for key in ("effect", "fail_effect"):
                eff = c.get(key, {})
                stats = eff.get("stats", {})
                assert set(stats) <= stat_keys, e["id"]
                assert -40 <= stats.get("silver", 0) <= 40, e["id"]
                if caps["xinde"] is not None:
                    assert stats.get("xinde", 0) <= caps["xinde"], e["id"]
                assert all(-3 <= stats.get(k, 0) <= 3 for k in ("fame", "good", "evil")), e["id"]
                assert all(stats.get(k, 0) <= 1 for k in ATTRS), e["id"]
                if caps["trend"]:
                    assert set(eff.get("trend", {})) <= {"front"}, e["id"]
                    assert all(1 <= abs(v) <= 3 for v in eff.get("trend", {}).values()), e["id"]
                if caps["materials"]:
                    assert sum(eff.get("materials", {}).values()) <= 1, e["id"]
                    assert all(content.materials[m].tier <= 2 for m in eff.get("materials", {})), e["id"]
                for banned in caps["banned"]:
                    assert not eff.get(banned), (e["id"], banned)
