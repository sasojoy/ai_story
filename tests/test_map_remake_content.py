"""輿圖重製第 1 批：內容——新天下（設計 docs/superpowers/specs/2026-10-20-輿圖簡化-design.md 第三章；計畫
docs/superpowers/plans/2026-10-20-輿圖重製-1.md）。三圈天下：外圈出生州是陣營領地、內圈中原與核心開季中立；州＝引擎的大區；
大勢值整個中原一條線（企劃者 2026-10-21）。陣營從劇本讀（設計 3.6）：判斷不寫死「官軍、黃巾」，只有釘名單的那一條寫這一季的內容。"""
from __future__ import annotations

from collections import deque

import pytest

from conftest import real_content
from conquest_kit import conquest_game
from tianxia import atlas, conquest, territory

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

INNER = {"yingchuan", "dongjun", "chenliu", "runan"}  # 內圈中原四郡（設計 3.1）
CORE = "core"


def _sides(c) -> list[str]:
    """開季持有領地的陣營：區塊表裡出現過的陣營種類（照劇本陣營的順序）。"""
    kinds = {b.kind for b in conquest.blocks(c).values()}
    return [f.id for f in c.scenario.factions if f.id in kinds]


def _region(c, loc_id: str) -> str:
    return atlas.region_of(c, loc_id).id


def test_nine_regions_one_per_state():
    """州＝引擎的大區一對一（設計 3.3）：外圈四個出生州、內圈四郡、核心自己一區。"""
    c = real_content("season21")
    assert sorted(r.id for r in c.map.regions) == sorted(["luoyang", "nanyang", "jizhou", "qingzhou", *INNER, CORE])
    for loc_id in c.locations:
        assert atlas.region_of(c, loc_id) is not None, loc_id


def test_outer_ring_is_faction_land_and_the_middle_is_neutral():
    """外圈出生州整州是一個陣營的領地，內圈中原與核心開季全是中立（設計 3.1、3.7）。"""
    c = real_content("season21")
    by_region: dict[str, set[str]] = {}
    for loc_id, block in conquest.blocks(c).items():
        by_region.setdefault(_region(c, loc_id), set()).add(block.kind)
    for rid, kinds in by_region.items():
        if rid in INNER or rid == CORE:
            assert kinds == {conquest.NEUTRAL}, rid
        else:
            assert len(kinds) == 1 and conquest.NEUTRAL not in kinds, (rid, kinds)
    assert {k for rid, ks in by_region.items() if rid not in INNER and rid != CORE for k in ks} == set(_sides(c))


def test_join_points_are_only_on_the_outer_ring_two_states_per_side():
    """投靠點只在外圈（企劃者）：每個陣營兩個出生州各一處，所在的州開季就是自家。"""
    c = real_content("season21")
    for side in _sides(c):
        bases = c.scenario.faction(side).join_at
        regions = [_region(c, loc) for loc in bases]
        assert len(bases) == 2 and len(set(regions)) == 2, (side, regions)
        for loc in bases:
            assert conquest.blocks(c)[loc].kind == side, loc
    for loc in ("changshe", "huangjin_camp", "luzhi_camp", "nanyang_huangjin_camp"):  # 改成中原的高級資源地／前哨舊址
        assert conquest.blocks(c)[loc].kind == conquest.NEUTRAL and _region(c, loc) in INNER, loc


def test_the_middle_is_one_line():
    """大勢值整個中原一個總值（企劃者 2026-10-21）：中原與核心的中立區塊都算進同一條線，外圈不算進任何一條；
    舊拔河（territory.lines）也只剩這一條。"""
    c = real_content("season21")
    blocks = conquest.blocks(c)
    lines = {b.line for b in blocks.values() if b.kind == conquest.NEUTRAL}
    assert len(lines) == 1 and None not in lines
    line = lines.pop()
    assert all(b.line is None for b in blocks.values() if b.kind != conquest.NEUTRAL)
    assert list(c.scenario.territory.lines) == [line]
    for loc in c.scenario.territory.lines[line]:
        assert blocks[loc].kind == conquest.NEUTRAL and territory.line_of(c, loc) == line, loc


def test_every_neutral_block_is_reachable_from_each_sides_land():
    """領地爭奪裁決第 2 條、設計第十一章：每一個中立區塊，每一方都有一條路從自家開季持有的領地走得到——
    路上只經過中立區塊（不必先打進對方的領地），照 conquest.adjacent（不穿過不是區塊的地點）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    blocks = conquest.blocks(c)
    neutral = {loc for loc in blocks if conquest.start_kind(w, c, loc) == conquest.NEUTRAL}
    assert len(neutral) >= 20
    for side in _sides(c):
        own = {loc for loc in blocks if conquest.holder(w, c, loc) == side}
        seen = {loc for loc in neutral if any(x in own for x in conquest.adjacent(c, loc))}
        queue = deque(seen)
        while queue:
            for nxt in conquest.adjacent(c, queue.popleft()):
                if nxt in neutral and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        assert seen == neutral, (side, sorted(neutral - seen))


def test_opening_reach_is_balanced():
    """開季兩邊碰得到的中立區塊數相近（裁決 2）：差不超過 1。現在各 5 塊（數字寫進計畫給 PM 對）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    reach = {
        side: sorted(loc for loc in conquest.targets(w, c, side) if conquest.start_kind(w, c, loc) == conquest.NEUTRAL)
        for side in _sides(c)
    }
    counts = [len(v) for v in reach.values()]
    assert min(counts) >= 1 and max(counts) - min(counts) <= 1, reach
    assert reach == {
        "guan": ["baima_ford", "guan_camp", "hilltop_wilds", "nanyang_huangjin_camp", "yingchuan"],
        "huang": ["baima_ford", "guandu", "jiwu", "luzhi_camp", "qiao_county"],
    }


def test_outer_ring_states_touch_along_the_ring():
    """外環路（企劃者「也要讓出生區直接相連」）：相鄰的出生州之間有路直通（不一定是區塊，豪族塢堡也算路）。"""
    c = real_content("season21")
    touching = set()
    for loc in c.locations.values():
        a = _region(c, loc.id)
        for other in loc.connections:
            b = _region(c, str(other))
            if a != b:
                touching.add(frozenset((a, b)))
    for pair in (("luoyang", "jizhou"), ("jizhou", "qingzhou"), ("qingzhou", "nanyang"), ("nanyang", "luoyang")):
        assert frozenset(pair) in touching, pair
    for rid in INNER:  # 每個內圈郡一條往核心
        assert frozenset((rid, CORE)) in touching, rid
