"""四個新大區（幽州、冀州、洛陽、南陽）新地點的探索事件（地圖擴充設計第七節；計畫 Task 5～8）。
事件檔是 content/events/<大區>.json，事件 id 以「<大區>_」開頭；每個大區一列參數，各自的 commit 才加上自己那一列。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tianxia.content import load_content

CONTENT_DIR = Path(__file__).parent.parent / "content"
REGIONS = [  # （大區, 新地點, 最少事件數, 最多事件數）
    ("youzhou", {"loushang_village", "zhuo_militia_hall", "juma_river", "yanshan_foot"}, 5, 7),
    ("jizhou", {"julu_altar", "guangzong", "luzhi_camp", "xiaquyang", "haozu_fort", "baima_ford"}, 7, 9),
    ("luoyang", {"luoyang_palace", "dajiangjun_fu", "beimang_hill", "mengjin_ford"}, 5, 7),
    ("nanyang", {"nanyang_huangjin_camp", "yu_river", "xinye", "nanyang_wilds"}, 5, 7),
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


def _shown_to(cond: dict, faction: str | None) -> bool:
    if cond.get("factions") and faction not in cond["factions"]:
        return False
    return faction is None or faction not in cond.get("factions_none", [])


@pytest.mark.parametrize("region", REGION_IDS)
def test_events_stay_within_the_reward_limits(content, region):
    """同一則事件的選項互斥；一半以上的事件要冒險（檢定或動手），傳聞最多兩則。每個選項結果的獎勵上限
    （effect、fail_effect 各自）跟另外兩份補寫事件共用一個檢查：tests/test_event_reward_caps.py（region-<大區>）。"""
    events = _events(region)
    risky = 0
    rumors = 0
    for e in events:
        for faction in (None, "guan", "huang", "haoqiang"):  # 選項照陣營分邊（2026-10-08）：每一種身分看得到的都是 2～3 個
            shown = [c for c in e["choices"] if _shown_to(c.get("condition", {}), faction)]
            assert 2 <= len(shown) <= 3, (e["id"], faction)
        if any("check" in c or "combat" in c for c in e["choices"]):
            risky += 1
        for c in e["choices"]:
            if "check" in c or "combat" in c:
                assert "fail_effect" in c, e["id"]
            if "check" in c:
                assert c["check"]["stat"] in {"str", "agi", "con", "wis"} and 3 <= c["check"]["difficulty"] <= 8, e["id"]  # 難度帶另見 test_real_content.py::DIFFICULTY_BANDS
            rumors += sum(bool(c.get(key, {}).get("rumor")) for key in ("effect", "fail_effect"))
    assert risky * 2 >= len(events)
    assert rumors <= 2
