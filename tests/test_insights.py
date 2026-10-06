from tianxia import insights, library
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


def test_explore_gives_is_the_pool_unless_the_insight_branch_is_off_there(content):
    """W3：探索在這裡真的悟得到什麼——輿圖詳情欄的「這裡能悟」與探索自己（Game._explore_can）共用這一個判斷。
    這類地點探索時「悟意境」那一支的比例是 0，就什麼也悟不到，不能照池子寫。"""
    from tianxia.models import ExploreMix

    lake = content.locations["lake"]
    assert sorted(insights.explore_gives(lake, content)) == ["feng", "shui"] == sorted(insights.explore_pool(lake, content))
    content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"insight": 0, "event": 1})]
    assert insights.explore_gives(lake, content) == [] and insights.explore_pool(lake, content)  # 池子還在，只是這一支關著
    lake.tags = ["湖畔"]  # 比例照地點類型挑（跟探索同一個 explore_mix_of）：只關湖畔這一類，別處照舊
    content.config.explore_mix = [
        ExploreMix(kind="lake", tags=["湖畔"], weights={"insight": 0, "wild": 1}),
        ExploreMix(kind="wild", tags=[], weights={"insight": 1}),
    ]
    town = content.locations["town"]
    assert insights.explore_gives(lake, content) == []
    assert sorted(insights.explore_gives(town, content)) == sorted(insights.explore_pool(town, content)) != []


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
    seed = "1|合|recipe"  # 配方種子（天機|配方鍵）；表裡有的組合不看它
    assert insights.merged_attribute(fire, wind, seed) == "陽"
    assert insights.merged_attribute(water, hill, seed) == "陰"
    assert insights.merged_attribute(wind, water, seed) == "虛"
    assert insights.merged_attribute(fire, hill, seed) == "實"
    assert insights.merged_attribute(wind, wind, seed) == "快"
    assert {insights.merged_attribute(fire, wind, f"{t}|合|recipe") for t in range(20)} == {"陽"}


def test_other_pairs_pick_one_parent_by_the_recipe_seed_whatever_the_order():
    """設計 12.6：「其他組合」的屬性由配方加天機決定（原本是新名字），要先知道屬性才找得到合到舊的候選。"""
    fire, water = Insight(id="huo", name="火", attribute="剛"), Insight(id="shui", name="水", attribute="柔")
    seed = "3|合|huo+shui"
    assert insights.merged_attribute(fire, water, seed) == insights.merged_attribute(water, fire, seed)
    assert {insights.merged_attribute(fire, water, f"{t}|合|huo+shui") for t in range(40)} == {"剛", "柔"}


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


# ── 名聲到門檻悟得浩然、血煞（武學與成長設計 7.2）──────────────────────────────


def test_good_name_at_the_threshold_grants_haoran_once(state, content, world):
    state.player.stats["good"] = 15
    state.player.stats["xinde"] = 0
    msgs = insights.grant_by_name(state, content, world)
    assert state.player.insights == ["haoran"] and any("浩然" in m for m in msgs)
    library.melt_insight(state, content, world, "haoran")  # 真的熔掉（熔意境那條路），不是直接清單子
    assert state.player.insights == []
    assert state.player.stats["xinde"] == content.config.melt_insight_xinde  # 熔了就是那一份心得
    assert insights.grant_by_name(state, content, world) == []  # 善名還在門檻上，也不再給：不然熔了又拿可以刷心得
    assert state.player.insights == []
    assert state.player.stats["xinde"] == content.config.melt_insight_xinde


def test_below_the_threshold_nothing_happens(state, content, world):
    state.player.stats["evil"] = 14
    assert insights.grant_by_name(state, content, world) == []
    assert state.player.insights == []


def test_each_name_grants_only_its_own_insight(state, content, world):
    state.player.stats["evil"] = 15
    msgs = insights.grant_by_name(state, content, world)
    assert state.player.insights == ["xuesha"] and any("血煞" in m for m in msgs)
    assert not any("浩然" in m for m in msgs)


def test_both_names_at_the_threshold_grant_both(state, content, world):
    state.player.stats["good"] = state.player.stats["evil"] = 20
    insights.grant_by_name(state, content, world)
    assert sorted(state.player.insights) == ["haoran", "xuesha"]


def test_the_grant_is_remembered_with_a_flag_so_a_second_call_adds_nothing(state, content, world):
    state.player.stats["good"] = 15
    insights.grant_by_name(state, content, world)
    assert "悟得:haoran" in state.player.flags
    assert insights.grant_by_name(state, content, world) == []
    assert state.player.insights == ["haoran"]


def test_an_insight_already_known_turns_into_xinde_but_is_still_counted_as_granted(state, content, world):
    state.player.insights = ["haoran"]  # 例如別條路已經悟過
    state.player.stats["good"] = 15
    state.player.stats["xinde"] = 0
    msgs = insights.grant_by_name(state, content, world)
    assert state.player.insights == ["haoran"] and state.player.stats["xinde"] == content.config.duplicate_insight_xinde
    assert insights.grant_by_name(state, content, world) == []  # 旗標記下了，不會每次加名聲都再化一次心得
    assert state.player.stats["xinde"] == content.config.duplicate_insight_xinde and msgs

