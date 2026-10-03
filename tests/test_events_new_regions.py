"""四個新大區（幽州、冀州、洛陽、南陽）新地點的探索事件（地圖擴充設計第七節；計畫 Task 5～8）。
事件檔是 content/events/<大區>.json，事件 id 以「<大區>_」開頭；每個大區一列參數，各自的 commit 才加上自己那一列。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tianxia.content import load_content

CONTENT_DIR = Path(__file__).parent.parent / "content"
STAT_KEYS = {"silver", "good", "evil", "fame", "str", "agi", "con", "wis"}
REGIONS = [  # （大區, 新地點, 最少事件數, 最多事件數）
    ("youzhou", {"loushang_village", "zhuo_militia_hall", "juma_river", "yanshan_foot"}, 5, 7),
    ("jizhou", {"julu_altar", "guangzong", "luzhi_camp", "xiaquyang", "haozu_fort", "baima_ford"}, 7, 9),
]
REGION_IDS = [row[0] for row in REGIONS]


@pytest.fixture(scope="module")
def content():
    return load_content(CONTENT_DIR)


def _events(region: str) -> list[dict]:
    return json.loads((CONTENT_DIR / "events" / f"{region}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("region, locations, low, high", REGIONS, ids=REGION_IDS)
def test_every_new_location_has_one_or_two_explore_events(content, region, locations, low, high):
    events = _events(region)
    assert low <= len(events) <= high
    per_place = {loc: 0 for loc in locations}
    for e in events:
        assert e["id"].startswith(f"{region}_"), e["id"]
        assert e.get("actions", ["explore"]) == ["explore"], e["id"]
        assert content.events[e["id"]].locations == e["locations"], e["id"]  # 事件真的載入了，地點照檔案寫的
        (loc,) = e["locations"]
        assert loc in per_place, e["id"]
        per_place[loc] += 1
    assert all(1 <= n <= 2 for n in per_place.values()), per_place


@pytest.mark.parametrize("region", REGION_IDS)
def test_events_stay_within_the_reward_limits(content, region):
    """每個上限都是每個選項結果（effect、fail_effect 各自）的上限；同一則事件的選項互斥。"""
    events = _events(region)
    risky = 0
    rumors = 0
    for e in events:
        assert 2 <= len(e["choices"]) <= 3, e["id"]
        if any("check" in c or "combat" in c for c in e["choices"]):
            risky += 1
        for c in e["choices"]:
            if "check" in c or "combat" in c:
                assert "fail_effect" in c, e["id"]
            if "check" in c:
                assert c["check"]["stat"] in {"str", "agi", "con", "wis"} and 5 <= c["check"]["difficulty"] <= 8, e["id"]
            for key in ("effect", "fail_effect"):
                eff = c.get(key, {})
                stats = eff.get("stats", {})
                assert set(stats) <= STAT_KEYS, e["id"]
                assert -40 <= stats.get("silver", 0) <= 40 and -3 <= stats.get("fame", 0) <= 3, e["id"]
                assert -3 <= stats.get("good", 0) <= 3 and -3 <= stats.get("evil", 0) <= 3, e["id"]
                assert all(stats.get(k, 0) <= 1 for k in ("str", "agi", "con", "wis")), e["id"]
                assert set(eff.get("trend", {})) <= {"huangjin"} and all(1 <= abs(v) <= 3 for v in eff.get("trend", {}).values()), e["id"]
                assert sum(eff.get("materials", {}).values()) <= 1, e["id"]
                assert all(content.materials[m].tier <= 2 for m in eff.get("materials", {})), e["id"]
                assert not eff.get("flags_add") and not eff.get("world_flags_add"), e["id"]
                assert not eff.get("next_event") and not eff.get("recruit") and not eff.get("join_sect"), e["id"]
                rumors += bool(eff.get("rumor"))
    assert risky * 2 >= len(events)
    assert rumors <= 2
