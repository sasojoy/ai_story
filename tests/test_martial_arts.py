from tianxia.martial_arts import (
    ATTRIBUTES,
    QUALITIES,
    counters,
    generate_from_name,
    historical_art,
    power_at,
)
from tianxia.world_state import WorldStateStore


def test_generate_from_name_is_deterministic():
    a = generate_from_name("烈日decompose拳", "武學", "created:烈日拳")
    b = generate_from_name("烈日decompose拳", "武學", "created:烈日拳")
    assert a.attribute == b.attribute
    assert a.quality == b.quality
    assert a.base_power == b.base_power
    assert a.top_power == b.top_power


def test_generate_from_name_uses_valid_attribute_and_quality():
    art = generate_from_name("驚鴻一瞥", "武學", "created:驚鴻一瞥")
    assert art.attribute in ATTRIBUTES
    assert art.quality in QUALITIES
    assert art.origin == "created"


def test_different_names_can_produce_different_results():
    names = [f"武學{i}" for i in range(30)]
    results = {generate_from_name(n, "武學", n).quality for n in names}
    # 30 個不同名字裡不該全部都是同一個品質（下品機率最高，但不該吃下全部樣本）。
    assert len(results) > 1


def test_legendary_quality_is_rare_but_reachable():
    names = [f"探索{i}" for i in range(4000)]
    qualities = [generate_from_name(n, "武學", n).quality for n in names]
    legendary_ratio = qualities.count("絕學") / len(qualities)
    # 機率設計上是極小（CREATED_QUALITY_WEIGHTS 裡 0.5%），允許統計誤差，但不該是 0 也不該常見。
    assert 0 < legendary_ratio < 0.05


def test_historical_art_is_always_legendary():
    art = historical_art("zhangfei_snake_spear", "丈八蛇矛", "武學", "剛")
    assert art.quality == "絕學"
    assert art.origin == "historical"


def test_power_at_interpolates_linearly_between_first_and_tenth_level():
    art = historical_art("id", "測試武學", "武學", "陽")
    assert power_at(art, 1) == art.base_power
    assert power_at(art, 10) == art.top_power
    mid = power_at(art, 5)
    assert art.base_power < mid < art.top_power


def test_power_at_clamps_out_of_range_levels():
    art = historical_art("id", "測試武學", "武學", "陽")
    assert power_at(art, 0) == art.base_power
    assert power_at(art, 99) == art.top_power


def test_attribute_counters_are_symmetric_pairs():
    for attacker, defender in [("陽", "陰"), ("剛", "柔"), ("快", "慢"), ("實", "虛")]:
        assert counters(attacker, defender)
        assert counters(defender, attacker)
        assert not counters(attacker, attacker)


def test_tianji_zero_matches_the_original_recipe():
    """天機 0 必須沿用換季機制出現前的配方：直接拿名字本身的雜湊算，不加任何前綴。"""
    import hashlib

    from tianxia.martial_arts import ATTRIBUTES

    art = generate_from_name("驚雷掌", "武學", "x", tianji=0)
    digest = hashlib.sha256("驚雷掌".encode("utf-8")).digest()
    assert art.attribute == ATTRIBUTES[digest[0] % len(ATTRIBUTES)]
    assert art == generate_from_name("驚雷掌", "武學", "x")


def test_the_same_name_is_stable_within_one_tianji():
    assert generate_from_name("流雲劍", "武學", "x", tianji=2) == generate_from_name("流雲劍", "武學", "x", tianji=2)


def test_the_same_names_reshuffle_when_the_tianji_changes():
    names = ["驚雷掌", "流雲劍", "寒江訣", "斷岳刀", "回風步"]
    before = [generate_from_name(n, "武學", n, tianji=0) for n in names]
    after = [generate_from_name(n, "武學", n, tianji=1) for n in names]
    assert [(a.attribute, a.quality, a.base_power) for a in before] != [
        (a.attribute, a.quality, a.base_power) for a in after
    ]


def test_create_skill_uses_the_current_tianji(content, tmp_path):
    from tianxia import team
    from tianxia.state import new_game_state

    store = WorldStateStore(tmp_path / "world.json")
    store.mutate(lambda state: setattr(state, "tianji", 3))
    state = new_game_state(content, "甲")
    art, _ = team.create_skill(state, content, store, "驚雷掌", "武學")
    assert art == generate_from_name("驚雷掌", "武學", "驚雷掌", tianji=3)
