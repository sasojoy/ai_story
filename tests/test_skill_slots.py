"""武學技能分檔（Joy 2026-10-17；tianxia/skill_slots.py）：品質決定亮幾格技能、擲不擲得到高階，層數照舊。"""
from __future__ import annotations

import collections

import pytest

from tianxia import skill_slots, skillview, traits
from tianxia.content import load_content
from tianxia.martial_arts import MartialArt


@pytest.fixture(scope="module")
def content():
    return load_content("content")


def art(**kw) -> MartialArt:
    base = dict(id="x", name="裂雲劍", kind="武學", quality="下品", attribute="剛", base_power=10, top_power=50, origin="fused",
                traits=["剛", "剛", "剛", "快", "慢"], special="lianhuan")
    base.update(kw)
    return MartialArt(**base)


def test_slot_counts_follow_quality(content):
    seen = collections.defaultdict(set)
    for i in range(400):
        for q in ("下品", "中品", "上品", "絕學"):
            seen[q].add(skill_slots.slot_count(content, f"p{i}", "x", q))
    assert seen["下品"] == {1, 2}
    assert seen["中品"] == {2, 3}
    assert seen["上品"] == {3, 4}
    assert seen["絕學"] == {3, 4}


def test_mastered_keeps_the_superior_slot_count(content):
    for i in range(50):
        assert skill_slots.slot_count(content, f"p{i}", "x", "絕學") == skill_slots.slot_count(content, f"p{i}", "x", "上品")


def test_high_rate_follows_the_rolled_quality(content):
    n = 4000
    hits = {q: sum(skill_slots.high_of(content, f"p{i}", art(), q, q) is not None for i in range(n)) / n for q in ("下品", "中品", "上品")}
    assert hits["下品"] < 0.04
    assert 0.05 < hits["中品"] < 0.11
    assert 0.16 < hits["上品"] < 0.24


def test_cultivating_up_keeps_the_high_skill_and_lights_more(content):
    a = art()
    for i in range(300):
        low = skill_slots.layout(content, f"p{i}", a, "下品", "下品")
        up = skill_slots.layout(content, f"p{i}", a, "上品", "下品")
        if any(k == "h" for k, _ in low.lit):
            assert any(k == "h" for k, _ in up.lit)
        assert len(up.lit) >= len(low.lit)
        assert low.lit[0] == ("g", "剛")  # 層數最多的那個一定在第一格


def test_layout_is_deterministic_and_fills_from_the_lineage_first(content):
    a = art()
    one = skill_slots.layout(content, "甲", a, "中品", "中品")
    assert one == skill_slots.layout(content, "甲", a, "中品", "中品")
    lineage = [("g", "剛"), ("s", "lianhuan"), ("g", "快"), ("g", "慢")]
    plain = [x for x in one.lit if x[0] != "h"]
    assert plain == lineage[: len(plain)]
    assert one.dormant == lineage[len(plain):]


def test_empty_slots_roll_mid_or_low_without_duplicates(content):
    thin = art(traits=["剛"], special=None)
    for i in range(200):
        lay = skill_slots.layout(content, f"p{i}", thin, "上品", "上品")
        assert len(lay.lit) == lay.slots
        assert len(set(lay.lit)) == len(lay.lit)
        assert "剛" not in lay.extra_traits


def test_apply_only_touches_fused_arts(content):
    state = None  # 內容寫的武學不看是誰
    sid = next(iter(content.skills))
    s = content.skills[sid]
    native = MartialArt(id=sid, name=s.name, kind=s.kind, quality=s.quality, attribute=s.attribute, base_power=1, top_power=1)
    assert skill_slots.apply(state, content, native) is native


def test_card_line_shows_high_and_dormant(content):
    a = art(quality="下品", dormant=["慢"], high="bengshan", traits=["剛", "剛", "剛"], special=None)
    line = traits.card_line(content, a)
    assert "〔高階・崩山〕" in line
    assert "未開：穩" in line


def test_tier_numbers_match_the_ui(content):
    assert skill_slots.TIERS == {"low": 1, "mid": 2, "high": 3, "top": 4}
    assert skillview.melt_judge  # 介面區照 traits[].tier 畫凡、良、精、極


def test_compare_names_only_lit_slots(content):
    """開爐結果那一句「多了〔…〕」只算亮了的格子，跟卡上「未開」對得上。"""
    from types import SimpleNamespace

    from tianxia import team

    a = art(id="fused_x")
    for i in range(200):
        state = SimpleNamespace(player=SimpleNamespace(name=f"p{i}", art_rolled={"fused_x": "下品"}))
        shown = skill_slots.apply(state, content, a)
        if shown.dormant:
            break
    names = team._trait_names(content, shown)
    dormant = traits.dormant_names(content, shown)
    assert dormant and not set(dormant) & set(names)
    assert len(names) == skill_slots.layout(content, state.player.name, a, "下品", "下品").slots


def test_mastered_lights_every_lineage_trait(content):
    """練到絕學，來路的功效全部亮起，不再有「未開」（Joy 2026-10-17）。"""
    many = art(traits=["剛", "剛", "剛", "快", "慢", "柔", "陽"])
    for i in range(200):
        lay = skill_slots.layout(content, f"p{i}", many, "絕學", "下品")
        assert lay.dormant == []
        assert {a for k, a in lay.lit if k == "g"} >= {"剛", "快", "慢", "柔", "陽"}
        assert ("s", "lianhuan") in lay.lit
