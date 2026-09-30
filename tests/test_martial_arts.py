from tianxia.martial_arts import (
    ATTRIBUTES,
    QUALITIES,
    counters,
    generate_from_name,
    historical_art,
    power_at,
)


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
