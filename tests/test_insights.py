from tianxia import insights
from tianxia.martial_arts import Insight


def test_learning_a_new_insight_keeps_it_for_good(state, content, world):
    msgs = insights.learn(state, content, world, "feng")
    assert state.player.insights == ["feng"] and "風" in msgs[0]


def test_learning_it_again_turns_into_xinde(state, content, world):
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 0
    msgs = insights.learn(state, content, world, "feng")
    assert state.player.insights == ["feng"] and state.player.stats["xinde"] == 10
    assert "心得 +10" in msgs


def test_an_insight_is_learned_even_when_the_library_is_full(state, content, world):
    content.config.holding_cap_base = 0
    insights.learn(state, content, world, "huo")
    assert state.player.insights == ["huo"]


def test_an_unknown_insight_teaches_nothing(state, content, world):
    assert insights.learn(state, content, world, None) == []
    assert insights.learn(state, content, world, "nope") == []
    assert state.player.insights == []


def test_the_explore_pool_follows_the_location(content):
    assert sorted(insights.explore_pool(content.locations["lake"], content)) == ["feng", "shui"]
    content.locations["lake"].insights = []
    assert sorted(insights.explore_pool(content.locations["lake"], content)) == ["feng", "huo", "shan", "shui"]


def test_fame_insights_are_never_in_the_explore_pool(content):
    content.locations["lake"].insights = ["haoran", "xuesha"]  # 載入檢查會擋，這裡只看規則本身
    pool = insights.explore_pool(content.locations["lake"], content)
    assert "haoran" not in pool and "xuesha" not in pool and sorted(pool) == ["feng", "huo", "shan", "shui"]


def test_rolling_picks_from_the_pool(content):
    import random

    rng = random.Random(3)
    got = {insights.roll_explore(content.locations["lake"], content, rng) for _ in range(40)}
    assert got == {"feng", "shui"}


def test_merged_attributes_follow_the_pair_table():
    fire, wind = Insight(id="huo", name="火", attribute="剛"), Insight(id="feng", name="風", attribute="快")
    water, hill = Insight(id="shui", name="水", attribute="柔"), Insight(id="shan", name="山", attribute="慢")
    assert insights.merged_attribute(fire, wind, "燎原") == "陽"
    assert insights.merged_attribute(water, hill, "幽谷") == "陰"
    assert insights.merged_attribute(wind, water, "雲霧") == "虛"
    assert insights.merged_attribute(fire, hill, "熔岩") == "實"
    assert insights.merged_attribute(wind, wind, "狂風") == "快"


def test_other_pairs_pick_one_parent_by_the_name():
    fire, water = Insight(id="huo", name="火", attribute="剛"), Insight(id="shui", name="水", attribute="柔")
    got = insights.merged_attribute(fire, water, "水火")
    assert got in ("剛", "柔") and got == insights.merged_attribute(water, fire, "水火")


def test_a_merge_key_ignores_the_order():
    assert insights.merge_key("shui", "huo") == insights.merge_key("huo", "shui") == "huo+shui"
    assert insights.merge_key("feng", "feng") == "feng+feng"


def test_lean_passes_through_and_cancels():
    good = Insight(id="haoran", name="浩然", attribute="陽", lean="正")
    evil = Insight(id="xuesha", name="血煞", attribute="陰", lean="邪")
    plain = Insight(id="feng", name="風", attribute="快")
    assert insights.merged_lean(good, plain) == "正"
    assert insights.merged_lean(evil, evil) == "邪"
    assert insights.merged_lean(good, evil) == "無"
    assert insights.merged_lean(plain, plain) == "無"
