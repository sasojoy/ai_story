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


# ── 第 1 批補做（1b）：設計 3.1 列在批 1、跟著投靠點搬的那幾件 ─────────────────────

MOVED = ("huangfusong", "zhujun", "fuxie", "luzhi", "zhangmancheng", "zhaohong", "hanzhong")  # 設計 3.1 點名的七位
LUZHI_CAMP_FRAGMENTS = {  # 本來掛冀州、講盧植營裡的事的伏筆片段（監軍、營裡傳出來的話、盧植自己說的）
    ("fs_luzhi_guan", 0), ("fs_luzhi_guan", 1), ("fs_luzhi_huang", 0), ("fs_zhangjiao_guan", 1),
}


def _owner(c, rid: str) -> str | None:
    """這一州開季是誰的：州裡的區塊全是同一個陣營就是它（外圈）；中立的、混著的是 None。"""
    kinds = {b.kind for loc, b in conquest.blocks(c).items() if _region(c, loc) == rid}
    return next(iter(kinds)) if len(kinds) == 1 and conquest.NEUTRAL not in kinds else None


def _touching(c) -> set[frozenset[str]]:
    """有路直通的兩州（同 test_outer_ring_states_touch_along_the_ring）。"""
    out = set()
    for loc in c.locations.values():
        for other in loc.connections:
            a, b = _region(c, loc.id), _region(c, str(other))
            if a != b:
                out.add(frozenset((a, b)))
    return out


def _moves(c) -> list[tuple[str, str, str]]:
    """時刻表把人物調到某條線、某個地點的每一筆：(人物 id, 戰線, 地點)。「@commander」照當時的主將找人，這裡略過。"""
    out = []
    for event in c.timetable:
        for outcome in event.outcomes.values():
            for key, change in outcome.figures.items():
                fid = key.removeprefix("@人物:")
                if fid in c.figures and change.location is not None and change.front is not None:
                    out.append((fid, change.front, change.location))
    return out


def test_moved_figures_open_on_their_own_outer_ring():
    """設計 3.1：原本站在中原那幾個舊投靠點（長社、盧植營、南陽黃巾營）的七位，開季站在自家的外圈；
    求見的地方（talk_at）與常去的第一處（haunts[0]）跟著人走（content.validate 也守 talk_at）。"""
    c = real_content("season21")
    for fid in MOVED:
        fig = c.figures[fid]
        assert _owner(c, _region(c, fig.location)) == fig.faction, (fid, fig.location)
        ch = c.characters.get(fig.character) if fig.character else None
        if ch is not None:
            assert ch.talk_at == fig.location and (not ch.haunts or ch.haunts[0] == fig.location), fid


def test_promotions_summon_you_to_where_the_figure_stands():
    """晉升召見寫了出面的人物又寫了地點的，地點就是那位人物會站的地方（開季的所在、或時刻表調他去的地方）；
    人物搬了、召見沒跟著搬，主版就永遠演不到（ranks.presenter／_cast_ok 要人物正好在那裡）。"""
    c = real_content("season21")
    spots = {fid: {fig.location} for fid, fig in c.figures.items()}
    for fid, _front, loc in _moves(c):
        spots[fid].add(loc)
    for promo in c.promotions:
        if promo.figure is not None and promo.location and promo.location != "nearest_base":
            assert promo.location in spots[promo.figure], (promo.faction, promo.rank, promo.location)
        for leg in promo.legs:
            for cast in leg.casts:
                if cast.figure is not None and cast.at is not None:
                    assert cast.at in spots[cast.figure], (promo.faction, promo.rank, cast.event, cast.at)


def test_outer_ring_showdowns_keep_the_attackers_commanders_at_home():
    """宛城之戰（南陽，官軍的外圈）、廣宗決戰（冀州，黃巾的外圈）：攻進來的那一方，守這條線的人物、他們的接位鏈、
    時刻表調到這條線上的人，站的都是自家的外圈，而且那一州有路通到決戰的那一州（設計 3.1、3.7：打進對方家門）。"""
    c = real_content("season21")
    touching = _touching(c)
    showdowns = [b for b in c.battles.values() if b.timetable_event and b.front and _owner(c, b.region)]
    assert {b.timetable_event for b in showdowns} >= {"wancheng", "guangzong"}
    for battle in showdowns:
        home = _owner(c, battle.region)
        for side in (f.id for f in battle.factions if f.id != home):
            people = [fid for fid, fig in c.figures.items() if fig.faction == side and fig.front == battle.front]
            for fid in list(people):
                nxt = c.figures[fid].successor
                while nxt is not None and nxt not in people:
                    people.append(nxt)
                    nxt = c.figures[nxt].successor
            spots = [(fid, c.figures[fid].location) for fid in people]
            spots += [(fid, loc) for fid, front, loc in _moves(c) if front == battle.front and c.figures[fid].faction == side]
            assert spots, (battle.id, side)
            for fid, loc in spots:
                rid = _region(c, loc)
                assert _owner(c, rid) == side and frozenset((rid, battle.region)) in touching, (battle.id, fid, loc)


def test_luzhi_camp_fragments_follow_the_camp():
    """盧植營搬進東郡（批 1）：本來掛冀州、講盧植營裡的事的伏筆片段，掛到盧植營所在的大區；盧植自己說的每一片都在裡面。"""
    c = real_content("season21")
    chains = {ch.id: ch for ch in c.foreshadows.chains}
    camp = _region(c, "luzhi_camp")
    assert camp == "dongjun"
    for chain_id, i in sorted(LUZHI_CAMP_FRAGMENTS):
        assert chains[chain_id].fragments[i].region == camp, (chain_id, i)
    spoken = {(ch.id, i) for ch in chains.values() for i, f in enumerate(ch.fragments) if f.character == "luzhi"}
    assert spoken and spoken <= LUZHI_CAMP_FRAGMENTS


def test_tutorial_points_to_the_new_join_points():
    """序章出師那一步（師父）與初入江湖最後一步（老周）說三邊在哪裡收人：官軍、黃巾的投靠點全搬到外圈（設計 3.1），
    兩段都點得出每一處投靠點的名字，不再說長社、別部營寨在收人。"""
    c = real_content("season21")
    steps = {s.id: s.text for s in c.tutorial.steps}
    for step in ("p11_farewell", "e4_world"):
        text = steps[step]
        for side in _sides(c):
            for loc in c.scenario.faction(side).join_at:
                assert c.locations[loc].name in text, (step, loc)
        assert "長社" not in text and "別部營寨" not in text, step


def test_the_middle_line_is_called_zhongyuan():
    """中原一條線（企劃者 10/21「整個中原一個總值」）：id 照舊，畫面上的名字是「中原」；內容裡照名字指這條線的地方
    （三路並進的「還缺」、引薦人看戰局那一句）跟著改，不再寫「潁川汝南」。"""
    c = real_content("season21")
    line = next(b.line for b in conquest.blocks(c).values() if b.kind == conquest.NEUTRAL)
    names = {t.id: t.name for t in c.scenario.trends}
    assert names[line] == "中原"
    for opp in c.opportunities:
        for part in (opp.plot.parts if opp.plot else []):
            if part.front is not None:
                assert part.name == names[part.front], (opp.id, part.key)
    for side, rec in c.tutorial.enlist.recruiters.items():
        for text in (rec.briefing, *rec.allied.values()):
            assert "潁川汝南" not in text, side
