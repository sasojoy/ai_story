from unittest import mock

import pytest

from tianxia import database, fusion, insights, landing, library, naming, skillview, team, traits
from tianxia.martial_arts import Insight, generate_from_name, power_at
from tianxia.sqlite_world import open_world
from tianxia.state import new_game_state


def named(name, description="一句話說明。"):
    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name=name, description=description)
    return client


def model_down():
    client = mock.Mock()
    client.chat_structured.side_effect = RuntimeError("連不上")
    return client


class AskedTheModel(BaseException):
    """naming._ask 把模型呼叫丟出的所有 Exception 當成「這次沒拿到」吞掉（連 AssertionError 也是），所以「不該叫模型」的假 client
    要丟 _ask 接不住的東西：BaseException 不是 Exception，會一路穿到測試、測試才會真的失敗。"""


def must_not_ask():
    client = mock.Mock()
    client.chat_structured.side_effect = AskedTheModel("配方已經有了，不該再叫模型")
    return client


@pytest.fixture
def ready(state):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    return state


def other_player(content, insights=("feng",)):
    other = new_game_state(content, "乙")
    other.player.member.wugong_id = "basic_fist"
    other.player.insights = list(insights)
    other.player.stats["xinde"] = 100
    return other


def test_fuse_keeps_the_base_and_adds_an_art_of_the_same_kind(ready, content, world):
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert (art.name, art.kind, art.attribute, art.insight, art.base) == ("旋風腿", "武學", "快", "feng", "basic_fist")
    assert ready.player.member.wugong_id == "basic_fist"  # 底留著
    assert ready.player.arts == ["旋風腿"]
    assert ready.player.stats["xinde"] == 95
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")).name == "旋風腿"
    assert "第一次" in msgs[0]


def test_a_fused_art_always_starts_at_the_lowest_quality_whatever_the_base_is(ready, content, world):
    """企劃者 2026-10-05（改了設計 3.4）：合出來的武學一律從下品起修，不繼承底的品質——底是中品也一樣。
    底的品質只留在底身上；新武學的底與威力曲線照配方登記的，從下品往上修練。"""
    fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.art_quality["旋風腿"] = "中品"
    art, msgs = fusion.fuse(ready, content, world, named("烈風腿"), "旋風腿", "huo")
    assert team.art_quality(ready, art) == "下品" and art.id not in ready.player.art_quality
    assert world.get_skill(art.id).quality == "下品"
    assert ready.player.art_quality["旋風腿"] == "中品"  # 底沒被動到
    assert "（下品・屬" in msgs[0] and "中品" not in msgs[0]


class Fixed:
    """rng.choices 永遠挑 pick 那一個（擲品質用）。"""

    def __init__(self, pick):
        self.pick, self.weights = pick, None

    def choices(self, population, weights):
        self.weights = dict(zip(population, weights))
        return [self.pick]


@pytest.mark.parametrize("quality", ["下品", "中品", "上品"])
def test_a_fused_art_rolls_its_own_quality(ready, content, world, quality):
    """企劃者 2026-10-06：合出來的武學自己那一份的品質照這一爐的機率擲；全服登記的照舊是下品，
    結果句寫擲到的品質，修練從擲到的那一品接著往上。"""
    rng = Fixed(quality)
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng", rng=rng)
    base, insight = team.player_art(ready, content, world, "basic_fist"), insights.resolve("feng", content, world)
    assert rng.weights == fusion.fuse_odds(ready, content, "basic_fist", base, insight).odds  # 照這一爐的搭配擲
    assert world.get_skill(art.id).quality == "下品"
    assert team.art_quality(ready, art) == quality
    assert f"（{quality}・屬" in msgs[0]
    if quality == "下品":
        assert art.id not in ready.player.art_quality and art.id not in ready.player.art_rolled
    else:
        assert ready.player.art_quality[art.id] == ready.player.art_rolled[art.id] == quality


def test_a_blended_art_rolls_its_own_quality_too(ready, content, world):
    ready.player.arts = ["lake_kick"]
    art, msgs = fusion.blend(ready, content, world, named("湖風拳"), "basic_fist", "lake_kick", rng=Fixed("上品"))
    assert team.art_quality(ready, art) == "上品" and "（上品・屬" in msgs[0]


def test_following_a_known_recipe_rolls_for_your_own_copy(ready, content, world):
    """照著別人合過的配方合（或合到舊的），拿到的是你還沒有的一門：一樣擲自己那一份。"""
    fusion.fuse(other_player(content), content, world, named("旋風腿"), "basic_fist", "feng", rng=Fixed("下品"))
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "basic_fist", "feng", rng=Fixed("中品"))
    assert team.art_quality(ready, art) == "中品" and "（中品・屬" in msgs[0]


def _fuse_odds(state, content, world, art_id, insight_id):
    return fusion.fuse_odds(
        state, content, art_id, team.player_art(state, content, world, art_id), insights.resolve(insight_id, content, world),
    )


def test_an_ordinary_pairing_gets_the_configured_average(content):
    """沒有任何因素加減分的一爐就是 Config.fuse_quality_odds（普通搭配的平均）。"""
    odds = fusion._points(content, [])
    assert odds.odds == {"下品": 50, "中品": 30, "上品": 20} and odds.reasons == ()


def test_odds_always_add_up_to_100_and_never_rule_anything_out(content):
    """企劃者 2026-10-06：不要有必出或必不出的組合——再好、再爛的搭配，上品與下品都夾在範圍裡。"""
    best = fusion._points(content, [("quality", 999)]).odds
    worst = fusion._points(content, [("quality", -999)]).odds
    assert best == {"下品": 15, "中品": 40, "上品": 45}
    assert worst == {"下品": 80, "中品": 15, "上品": 5}
    for odds in (best, worst):
        assert sum(odds.values()) == 100 and all(w > 0 for w in odds.values())


def test_a_better_base_gives_better_odds(ready, content, world):
    """回應企劃者「中品的底合出下品，那我幹嘛合成」：底的品質越好，上品越容易、下品越少。"""
    plain = _fuse_odds(ready, content, world, "basic_fist", "feng").odds
    ready.player.art_quality["basic_fist"] = "上品"
    good = _fuse_odds(ready, content, world, "basic_fist", "feng").odds
    assert good["上品"] > plain["上品"] and good["下品"] < plain["下品"]


def test_a_well_practised_base_gives_better_odds(ready, content, world):
    plain = _fuse_odds(ready, content, world, "basic_fist", "feng").odds
    ready.player.member.wugong_level = 10
    assert _fuse_odds(ready, content, world, "basic_fist", "feng").odds["上品"] > plain["上品"]


def test_matching_attributes_help_and_countering_ones_hurt(ready, content, world):
    """底屬快：融「風」（快）相投、融「山」（慢）相剋、融「火」（剛）不相干。"""
    ready.player.member.wugong_id = "lake_kick"
    ready.player.insights = ["feng", "huo", "shan"]
    same, plain, counter = (_fuse_odds(ready, content, world, "lake_kick", i) for i in ("feng", "huo", "shan"))
    assert same.odds["上品"] > plain.odds["上品"] > counter.odds["上品"]
    assert "兩股氣息相投" in same.reasons and "兩股氣息相衝" in counter.reasons


def test_an_uncommon_insight_helps(ready, content, world):
    """意境的來歷：內容寫好的基本意境不加分；善名惡名悟來的、合併出來的加分，自己首悟的再加。"""
    feng = insights.resolve("feng", content, world)
    haoran = insights.resolve("haoran", content, world)
    merged = Insight(id="颶火", name="颶火", attribute="剛", parents=["feng", "huo"], creator="乙")
    mine = merged.model_copy(update={"creator": ready.player.name})
    points = [fusion.insight_points(ready, content, i) for i in (feng, haoran, merged, mine)]
    assert points == sorted(points) and points[0] == 0 and len(set(points)) == 4


def test_a_sharper_mind_gives_better_odds(ready, content, world):
    plain = _fuse_odds(ready, content, world, "basic_fist", "feng").odds
    ready.player.stats["wis"] = 15
    assert _fuse_odds(ready, content, world, "basic_fist", "feng").odds["上品"] > plain["上品"]


def test_blend_odds_look_at_both_arts(ready, content, world):
    ready.player.arts = ["lake_kick"]
    a, b = (team.player_art(ready, content, world, x) for x in ("basic_fist", "lake_kick"))
    plain = fusion.blend_odds(ready, content, "basic_fist", a, "lake_kick", b).odds
    ready.player.art_quality["lake_kick"] = "上品"
    b = team.player_art(ready, content, world, "lake_kick")
    assert fusion.blend_odds(ready, content, "basic_fist", a, "lake_kick", b).odds["上品"] > plain["上品"]


def test_a_known_recipe_rolls_with_your_own_pairing(ready, content, world):
    """照別人合過的配方合：機率照你自己這一爐的組成（你的底、你的悟性），不是照首創者的。"""
    fusion.fuse(other_player(content), content, world, named("旋風腿"), "basic_fist", "feng", rng=Fixed("下品"))
    ready.player.art_quality["basic_fist"] = "上品"
    ready.player.stats["wis"] = 12
    rng = Fixed("中品")
    fusion.fuse(ready, content, world, must_not_ask(), "basic_fist", "feng", rng=rng)
    assert rng.weights == _fuse_odds(ready, content, world, "basic_fist", "feng").odds
    assert rng.weights["上品"] > 20


def test_quality_odds_text_writes_the_odds_and_why(content):
    assert fusion.quality_odds_text(fusion.QualityOdds({"下品": 50, "中品": 30, "上品": 20})) == "下品 50%、中品 30%、上品 20%"
    odds = fusion._points(content, [("attribute", 8), ("quality", 12), ("wis", 1)])
    assert fusion.quality_odds_text(odds) == "下品 29%、中品 41%、上品 30%（底子厚實、兩股氣息相投）"  # 分數小的不寫，最多兩個


def test_fusing_on_a_peerless_base_gives_a_lowest_quality_copy_with_the_lowest_power(ready, content, world):
    """設計 3.4 的舊寫法會讓絕學的底合出絕學的複本，馬上熔掉就賺 40 心得（金錢迴圈）。"""
    ready.player.art_quality["basic_fist"] = "絕學"
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    mine = team.player_art(ready, content, world, art.id)
    assert mine.quality == "下品" and art.id not in ready.player.art_quality
    assert power_at(mine, 1) == power_at(world.get_skill(art.id), 1)  # 威力也是下品的那一檔
    assert "（下品・屬" in msgs[0] and "絕學" not in msgs[0]
    assert ready.player.art_quality["basic_fist"] == "絕學"  # 底保有自己的品質


def test_fusing_over_and_over_and_melting_the_copy_never_makes_xinde(ready, content, world):
    """金錢迴圈關上了：絕學的底，合一爐（花心得）、立刻熔掉剛合出來的複本，每一輪心得只減不增。
    FB-068 起熔掉有基本值（melt_min_refund 4），但比合成的 5 少：每一輪淨虧 1。"""
    ready.player.art_quality["basic_fist"] = "絕學"
    ready.player.insights = ["feng", "huo", "shui"]
    price, floor = content.config.fuse_xinde, content.config.melt_min_refund
    xinde = ready.player.stats["xinde"]
    for name, insight in [("旋風腿", "feng"), ("烈火拳", "huo"), ("驚濤掌", "shui")]:
        art, _ = fusion.fuse(ready, content, world, named(name), "basic_fist", insight)
        assert ready.player.stats["xinde"] == xinde - price
        library.melt_art(ready, content, world, art.id)
        assert ready.player.stats["xinde"] == xinde - price + floor  # 下品、第一成：只退基本值
        xinde -= price - floor
    assert ready.player.stats["xinde"] == 100 - 3 * (price - floor) == 97


def test_a_second_player_gets_the_same_art_without_the_model(ready, content, world):
    first, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    second, msgs = fusion.fuse(other_player(content), content, world, must_not_ask(), "basic_fist", "feng")
    assert second.id == first.id and second.base_power == first.base_power
    assert "首創" in msgs[0]


def test_two_players_racing_for_a_new_recipe_end_up_with_one_registered_art(ready, content, world):
    """審查重點 3：兩個人都看見「這個配方還沒人合過」、各自請模型取了名字，登記只有第一個算數；
    第二個拿到第一個登記的那一門（同名、同數字），全服只有一筆。"""
    first, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    other = other_player(content)
    with mock.patch.object(world, "lookup_recipe", return_value=None):  # 乙看這一眼時，甲還沒登記
        second, msgs = fusion.fuse(other, content, world, named("疾風腿"), "basic_fist", "feng")
    assert (second.id, second.name) == (first.id, "旋風腿")
    assert (second.base_power, second.top_power) == (first.base_power, first.top_power)
    assert world.get_skill("疾風腿") is None  # 乙取的名字沒有登記
    assert other.player.arts == ["旋風腿"] and "首創" in msgs[0] and "第一次" not in msgs[0]


def test_fuse_is_refused_for_what_you_already_have(ready, content, world):
    fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert "已經有了" in fusion.fuse_problem(ready, content, world, "basic_fist", "feng")


def test_fuse_already_have_is_judged_by_the_art_id_not_its_display_name(ready, content, world):
    """全服第一個練成絕學的人會替它改名（Task 9）：改名之後顯示的名字跟 id 不一樣，「已經有了」仍然要認得出來。"""
    fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert world.rename_skill("旋風腿", "颯然腿")
    assert world.get_skill("旋風腿").name == "颯然腿"
    assert "已經有了" in fusion.fuse_problem(ready, content, world, "basic_fist", "feng")


@pytest.mark.parametrize(("change", "reason"), [
    (lambda s, c: s.player.insights.remove("feng"), "還沒悟到"),
    (lambda s, c: s.player.stats.update(xinde=0), "心得不足"),
    (lambda s, c: setattr(c.config, "holding_cap_base", 3), "滿了"),
])
def test_fuse_explains_why_it_is_refused(ready, content, world, change, reason):
    change(ready, content)
    assert reason in fusion.fuse_problem(ready, content, world, "basic_fist", "feng")


def test_the_full_check_for_a_fuse_follows_lore(ready, content, world):
    """持有上限含博聞（設計 6.3）：正好滿的時候多放一點博聞就能合成；博聞回到 5，又滿了，訊息寫的是同一個上限。"""
    content.config.holding_cap_base = 3  # 一門武學加兩個意境，正好滿
    assert "滿了" in fusion.fuse_problem(ready, content, world, "basic_fist", "feng")
    ready.player.stats["lore"] = 6  # 多 2 格
    assert fusion.fuse_problem(ready, content, world, "basic_fist", "feng") is None
    ready.player.stats["lore"] = 5
    assert "3/3" in fusion.fuse_problem(ready, content, world, "basic_fist", "feng")


def test_fuse_refuses_an_art_you_do_not_have(ready, content, world):
    assert "沒有這門武學" in fusion.fuse_problem(ready, content, world, "basic_breath", "feng")
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "basic_breath", "feng")
    assert art is None and "沒有這門武學" in msgs[0] and ready.player.stats["xinde"] == 100


def test_fuse_falls_back_to_the_word_table_when_the_model_is_down(ready, content, world):
    art, _ = fusion.fuse(ready, content, world, model_down(), "basic_fist", "feng")
    assert art.name == naming.fallback_name(content, fusion.fuse_key("basic_fist", "feng"), "武學", salt=0)


def test_a_bot_without_a_model_still_fuses_with_the_word_table(ready, content, world):
    art, _ = fusion.fuse(ready, content, world, None, "basic_fist", "feng")
    assert art.name == naming.fallback_name(content, fusion.fuse_key("basic_fist", "feng"), "武學", salt=0)


def test_a_name_taken_by_someone_else_is_replaced(ready, content, world):
    world.claim_skill_name(generate_from_name("旋風腿", "武學", "旋風腿"))
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert art.name != "旋風腿"


def test_a_failed_fuse_charges_nothing_and_registers_nothing(ready, content, world):
    with mock.patch.object(world, "claim_recipe", return_value=(None, False)):
        art, msgs = fusion.fuse(ready, content, world, model_down(), "basic_fist", "feng")
    assert art is None and "爐火熄了" in msgs[0]
    assert ready.player.stats["xinde"] == 100 and ready.player.arts == []


def test_a_recipe_registered_meanwhile_that_you_already_hold_is_refused_without_charging(ready, content, world):
    """配方被別人先登記、拿到的那一門剛好是自己已經有的：不收心得、不重複收進功法庫。"""
    first, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.stats["xinde"] = 100
    with mock.patch.object(world, "lookup_recipe", return_value=None), \
         mock.patch.object(fusion, "fuse_problem", return_value=None):
        art, msgs = fusion.fuse(ready, content, world, named("疾風腿"), "basic_fist", "feng")
    assert art is None and "已經有了" in msgs[0]
    assert ready.player.stats["xinde"] == 100 and ready.player.arts == [first.id]


def test_a_stale_reference_is_refused_instead_of_crashing(ready, content, world):
    ready.player.arts.append("ghost")  # 存檔裡記著、內容與全服登記裡都沒有
    assert "找不到" in fusion.fuse_problem(ready, content, world, "ghost", "feng")
    ready.player.insights.append("ghost_insight")
    assert "找不到" in fusion.fuse_problem(ready, content, world, "basic_fist", "ghost_insight")
    assert "找不到" in fusion.merge_problem(ready, content, world, "feng", "ghost_insight")


def test_merge_fire_and_wind_makes_a_shared_yang_insight(ready, content, world):
    insight, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert (insight.name, insight.attribute, insight.lean) == ("燎原", "陽", "無")
    assert ready.player.insights == ["feng", "huo", "燎原"]  # 兩個都留著
    assert ready.player.stats["xinde"] == 95
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")).name == "燎原"


def test_merging_an_insight_with_itself_is_allowed(ready, content, world):
    insight, _ = fusion.merge(ready, content, world, named("狂風"), "feng", "feng")
    assert insight.attribute == "快"


def test_merge_carries_the_lean(ready, content, world):
    ready.player.insights += ["haoran", "xuesha"]
    good, _ = fusion.merge(ready, content, world, named("正氣長風"), "haoran", "feng")
    plain, _ = fusion.merge(ready, content, world, named("陰陽一氣"), "haoran", "xuesha")
    assert (good.lean, plain.lean) == ("正", "無")


def test_merge_is_refused_for_an_insight_you_already_hold(ready, content, world):
    fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert "已經悟得" in fusion.merge_problem(ready, content, world, "feng", "huo")


@pytest.mark.parametrize(("change", "reason"), [
    (lambda s, c: s.player.insights.remove("feng"), "都要是你悟得的"),
    (lambda s, c: s.player.stats.update(xinde=0), "心得不足"),
    (lambda s, c: setattr(c.config, "holding_cap_base", 3), "滿了"),
])
def test_merge_explains_why_it_is_refused(ready, content, world, change, reason):
    change(ready, content)
    assert reason in fusion.merge_problem(ready, content, world, "feng", "huo")


def test_a_second_player_merges_into_the_same_insight_without_the_model(ready, content, world):
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    other = other_player(content, ("feng", "huo"))
    second, msgs = fusion.merge(other, content, world, must_not_ask(), "feng", "huo")
    assert (second.id, second.creator) == (first.id, "沈浪")
    assert other.player.insights == ["feng", "huo", "燎原"] and "首悟" in msgs[0]


def test_an_anonymous_first_fuser_is_shown_by_name(ready, content, world):
    """匿名行走只作用在地方傳聞（傳聞分層第七節，企劃者 2026-10-06）：首創寫給別人看的地方——後到的人那一句、
    功法卡（skillview）、換季的江湖史——一律寫名號。"""
    ready.player.anonymous = True
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    stored = world.get_skill(art.id)
    assert (stored.creator, stored.creator_shown) == ("沈浪", "沈浪")
    _, msgs = fusion.fuse(other_player(content), content, world, must_not_ask(), "basic_fist", "feng")
    assert "這一門由沈浪首創" in msgs[0] and "某位少俠" not in msgs[0]


def test_a_named_first_fuser_is_shown_by_name(ready, content, world):
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert world.get_skill(art.id).creator_shown == "沈浪"
    _, msgs = fusion.fuse(other_player(content), content, world, must_not_ask(), "basic_fist", "feng")
    assert "這一門由沈浪首創" in msgs[0]


def test_an_anonymous_first_merger_is_shown_by_name(ready, content, world):
    ready.player.anonymous = True
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert (first.creator, first.creator_shown) == ("沈浪", "沈浪")
    _, msgs = fusion.merge(other_player(content, ("feng", "huo")), content, world, must_not_ask(), "feng", "huo")
    assert "這個意境由沈浪首悟" in msgs[0] and "某位少俠" not in msgs[0]


def test_merge_falls_back_to_the_word_table_when_the_model_is_down(ready, content, world):
    insight, _ = fusion.merge(ready, content, world, model_down(), "huo", "feng")
    assert insight.name == naming.fallback_name(content, fusion.merge_key("huo", "feng"), "意境", salt=0)


def test_the_engine_forge_picks_fuse_or_merge(game):
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.insights = ["feng", "huo"]
    game.state.player.stats["xinde"] = 100
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", ["feng"])
        game.forge(None, ["feng", "huo"])
        msgs = game.forge(None, ["feng"])
    assert len(game.state.player.arts) == 1 and len(game.state.player.insights) == 3
    assert "放一門武學和一個意境" in msgs[0]


def test_the_engine_forge_is_titled_after_the_craft_tab_and_only_written_when_something_was_made(game):
    """FB-047：開爐的江湖紀錄標題是「煉製」（合成、合併都是）；被拒絕就只回一句話、不寫紀錄。"""
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.insights = ["feng", "huo"]
    game.state.player.stats["xinde"] = 100
    before = len(game.state.journal)
    game.forge("basic_fist", ["huo", "feng"])  # 一門武學配兩個意境：不是合成也不是合併
    assert len(game.state.journal) == before
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", ["feng"])
        fused = game.state.journal[0]
        game.forge(None, ["feng", "huo"])
        merged = game.state.journal[0]
    assert (fused.title, merged.title) == ("煉製", "煉製")
    assert fused.tag.startswith("合成【") and merged.tag.startswith("合併「")
    length = len(game.state.journal)
    game.forge(None, ["feng", "huo"])  # 已經悟得了：被拒絕
    assert len(game.state.journal) == length


def test_the_engine_fuse_then_melt_loop_on_a_peerless_base_only_ever_costs_xinde(game):
    """Task 13 的整季機器人踩到的洞（企劃者 2026-10-05 關掉）：走真的 Game.forge／Game.melt_art，
    絕學的底每一輪「合成、熔掉複本」心得只減不增，不再 100 → 135 → 170。FB-068 起熔掉退基本值 4、合成花 5：
    100 → 99 → 98 → 97。"""
    p = game.state.player
    p.member.wugong_id, p.art_quality["basic_fist"] = "basic_fist", "絕學"
    p.insights, p.stats["xinde"] = ["feng", "huo", "shui"], 100
    seen = [p.stats["xinde"]]
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        for insight in ("feng", "huo", "shui"):
            game.forge("basic_fist", [insight])
            (new,) = p.arts
            game.melt_art(new)
            seen.append(p.stats["xinde"])
    assert p.arts == [] and seen == [100, 99, 98, 97]


def test_fb068_fuse_then_melt_through_the_game_nets_minus_one_and_the_page_promised_it(game):
    """FB-068：合成花 5 心得，熔掉剛合出來的（下品、第一成）退基本值 4——一圈淨虧 1，沒有迴圈；
    修練頁的「退回心得 N」就是真的退的那個數。"""
    p = game.state.player
    p.member.wugong_id, p.insights, p.stats["xinde"] = "basic_fist", ["feng"], 100
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", ["feng"])
    (new,) = p.arts
    assert p.stats["xinde"] == 95
    (row,) = [r for r in game.art_rows() if r["id"] == new]
    assert row["melt"]["ok"] and row["melt"]["note"] == "退回心得 4"
    msgs = game.melt_art(new)
    assert p.stats["xinde"] == 99 and msgs[-1] == "心得 +4"
    assert "心得 +4" in game.state.journal[0].changes


# ── 設計 3.4、4.2 的規定，一條一條釘住 ───────────────────────────────


def test_a_neigong_base_stays_a_neigong(ready, content, world):
    """3.4：種類跟著底走，內功融意境還是內功；武學欄不受影響，新內功進功法庫。"""
    ready.player.member.neigong_id = "basic_breath"  # 柔
    art, _ = fusion.fuse(ready, content, world, named("雲水訣"), "basic_breath", "huo")
    assert (art.kind, art.attribute, art.base) == ("內功", "剛", "basic_breath")  # 屬性跟意境（火＝剛），不跟底（柔）
    assert ready.player.member.neigong_id == "basic_breath" and ready.player.member.wugong_id == "basic_fist"
    assert ready.player.arts == [art.id] and world.get_skill(art.id).kind == "內功"


def test_a_wugong_base_stays_a_wugong_even_when_the_neigong_slot_is_empty(ready, content, world):
    assert ready.player.member.neigong_id is None
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert art.kind == "武學"
    assert ready.player.member.neigong_id is None  # 新武學沒有誤上內功欄
    assert ready.player.arts == [art.id]


@pytest.mark.parametrize(("insight_id", "lean"), [("haoran", "正"), ("xuesha", "邪"), ("feng", "無")])
def test_the_fused_arts_lean_follows_the_insight(ready, content, world, insight_id, lean):
    """7.3：武學的正邪跟著它最後融的那個意境走；全服登記的那一筆與玩家拿到的是同一個。"""
    ready.player.insights += ["haoran", "xuesha"]
    art, _ = fusion.fuse(ready, content, world, named("某某勁"), "basic_fist", insight_id)
    assert art.lean == lean and art.insight == insight_id
    assert world.get_skill(art.id).lean == lean


def test_the_lean_is_the_last_insight_not_the_bases(ready, content, world):
    """融過好幾次就記最後那一個：正派的底再融一個沒有正邪的意境，新武學的正邪是「無」。"""
    ready.player.insights += ["haoran"]
    good, _ = fusion.fuse(ready, content, world, named("正氣腿"), "basic_fist", "haoran")
    plain, _ = fusion.fuse(ready, content, world, named("輕風腿"), good.id, "feng")
    assert (good.lean, plain.lean, plain.insight, plain.base) == ("正", "無", "feng", good.id)


def test_a_recipe_book_hit_still_costs_the_same_xinde(ready, content, world):
    """4.2：查表的老配方也照收（你是在「學」）；不看有沒有人首創、也不看要不要叫模型。"""
    fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    other = other_player(content)
    other_xinde = other.player.stats["xinde"]
    second, msgs = fusion.fuse(other, content, world, must_not_ask(), "basic_fist", "feng")
    assert second is not None and "首創" in msgs[0]
    assert other.player.stats["xinde"] == other_xinde - content.config.fuse_xinde == 95
    assert f"心得 -{content.config.fuse_xinde}" in msgs


def test_a_merge_recipe_book_hit_still_costs_the_same_xinde(ready, content, world):
    fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    other = other_player(content, ("feng", "huo"))
    second, msgs = fusion.merge(other, content, world, must_not_ask(), "feng", "huo")
    assert second is not None and "首悟" in msgs[0]
    assert other.player.stats["xinde"] == 100 - content.config.merge_xinde == 95
    assert f"心得 -{content.config.merge_xinde}" in msgs


def test_the_new_art_starts_at_the_first_level_even_when_the_base_is_far_along(ready, content, world):
    """3.4：新武學從第一成開始（品質也是下品起，見上面的測試）。底練到第七成，新武學不繼承；改練上身時也是第一成，底換回庫裡仍是第七成。"""
    ready.player.member.wugong_level = 7
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert ready.player.member.wugong_level == 7  # 底沒被動到
    assert ready.player.art_levels.get(art.id, 1) == 1
    team.switch_art(ready, content, world, art.id)
    assert (ready.player.member.wugong_id, ready.player.member.wugong_level) == (art.id, 1)
    assert ready.player.art_levels["basic_fist"] == 7


def test_the_new_art_starts_at_the_first_level_when_it_goes_straight_onto_an_empty_slot(ready, content, world):
    """底在功法庫裡、武學欄是空的：新武學直接上身，第一成。"""
    ready.player.member.wugong_id, ready.player.member.wugong_level = None, 0
    ready.player.arts = ["basic_fist"]
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert (ready.player.member.wugong_id, ready.player.member.wugong_level) == (art.id, 1)
    assert ready.player.arts == ["basic_fist"] and any("第一成" in m for m in msgs)


SWITCH_HINT = "到「修練」的功法庫把它改練上身。"  # W5：待 joy 潤


def test_a_forged_art_that_goes_into_the_library_says_where_to_switch_to_it(ready, content, world):
    """W5：結果說「收進功法庫」，卻沒人告訴玩家功法庫在哪、怎麼穿上——最後多一句指路。"""
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert art.id in ready.player.arts
    assert msgs[-1] == SWITCH_HINT and msgs[-3] == "【旋風腿】收進功法庫。"  # 中間是跟身上那門的比較（W6，見下面）
    assert library.SWITCH_HINT == SWITCH_HINT  # 句子只有一個出處


def test_the_forge_result_compares_the_new_art_with_the_worn_one_before_the_switch_hint(ready, content, world):
    """W6：合成的結果，收進功法庫之後、指路那句之前，多一句跟身上同一種那門的比較（第一成對第一成）；數字就是 team.compare_with_worn 的。"""
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    note = team.compare_with_worn(ready, content, world, art)
    assert note.startswith("比身上的【粗淺拳腳】：威力 ") and "（第一成）" in note
    assert msgs[-3:] == ["【旋風腿】收進功法庫。", note, SWITCH_HINT]


def test_the_forge_result_has_no_comparison_when_the_art_is_worn_at_once_or_it_is_a_merge(ready, content, world):
    ready.player.member.wugong_id, ready.player.member.wugong_level = None, 0
    ready.player.arts = ["basic_fist"]
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert ready.player.member.wugong_id == art.id and all("比身上的" not in m for m in msgs)  # 直接上身：沒有東西可比
    _, merged = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert all("比身上的" not in m for m in merged)


def test_a_blended_art_is_compared_with_the_slot_of_its_own_kind(ready, content, world):
    ready.player.member.neigong_id = "basic_breath"
    art, msgs = fusion.blend(ready, content, world, named("渾元手"), "basic_fist", "basic_breath")
    worn_name = "粗淺拳腳" if art.kind == "武學" else "粗淺吐納"
    assert msgs[-2].startswith(f"比身上的【{worn_name}】：威力 ") and msgs[-1] == SWITCH_HINT


def test_a_blended_art_that_goes_into_the_library_says_it_too(ready, content, world):
    ready.player.member.neigong_id = "basic_breath"
    art, msgs = fusion.blend(ready, content, world, named("渾元手"), "basic_fist", "basic_breath")
    assert art.id in ready.player.arts and msgs[-1] == SWITCH_HINT


def test_a_forged_art_that_is_worn_at_once_gets_no_switch_hint(ready, content, world):
    """武學欄空著：新武學直接上身，不在功法庫裡，也就沒有「去功法庫改練」這句。"""
    ready.player.member.wugong_id, ready.player.member.wugong_level = None, 0
    ready.player.arts = ["basic_fist"]
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert ready.player.member.wugong_id == art.id
    assert all(SWITCH_HINT not in m and "功法庫" not in m for m in msgs)


def test_a_merge_and_other_ways_of_storing_an_art_get_no_switch_hint(ready, content, world):
    """意境合併沒有放進功法庫；學藝、事件教的武學收進功法庫也不是「煉製」的結果，不加這句（只有合成、合成兩門才加）。"""
    _, msgs = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert all(SWITCH_HINT not in m for m in msgs)
    stored = library.store_art(ready, generate_from_name("甲乙丙", "武學", "甲乙丙", 0))
    assert stored == ["【甲乙丙】收進功法庫。"]


def test_two_players_racing_for_a_new_merge_end_up_with_one_registered_insight(ready, content, world):
    """合併版的審查重點 3：兩個人都看見「這個配方還沒人合過」、各自請模型取了名字，登記只有第一個算數；
    第二個拿到第一個登記的那一個意境（同名、同屬性），全服只有一筆。"""
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    other = other_player(content, ("feng", "huo"))
    with mock.patch.object(world, "lookup_insight_recipe", return_value=None):  # 乙看這一眼時，甲還沒登記
        second, msgs = fusion.merge(other, content, world, named("野火"), "feng", "huo")
    assert (second.id, second.name, second.attribute, second.creator) == (first.id, "燎原", first.attribute, "沈浪")
    assert world.get_insight("野火") is None  # 乙取的名字沒有登記
    assert other.player.insights == ["feng", "huo", "燎原"]
    assert "首悟" in msgs[0] and "第一次" not in msgs[0]
    assert other.player.stats["xinde"] == 95


# ── 首次取名移到行動鎖外（最終審查 Critical 1）：A 鎖內備料 → B 鎖外取名 → C 鎖內重驗、登記、收費 ──────────


def test_forge_request_hands_out_a_naming_slip_only_when_the_model_is_needed(ready, content, world):
    """A 段只讀：會被拒絕、配方已經登記過、放的不是一武學一意境或兩個意境，都不必叫模型（回 None）。"""
    before = ready.model_dump_json()
    fuse = fusion.forge_request(ready, content, world, "basic_fist", ["feng"])
    assert (fuse.kind, fuse.key, fuse.name_kind) == ("fuse", fusion.fuse_key("basic_fist", "feng"), "武學")
    base, feng = team.player_art(ready, content, world, "basic_fist"), fusion.insights.resolve("feng", content, world)
    note = traits.naming_note(
        content, traits.inherit_fuse(base, feng.attribute), traits.roll_special(content, fuse.key, world.read().tianji),
    )
    assert fuse.messages == fusion._fuse_messages(base, feng, note=note)
    merge = fusion.forge_request(ready, content, world, None, ["huo", "feng"])
    assert (merge.kind, merge.key, merge.name_kind) == ("merge", fusion.merge_key("huo", "feng"), "意境")
    assert ready.model_dump_json() == before  # 什麼都沒動
    assert fusion.forge_request(ready, content, world, "basic_breath", ["feng"]) is None  # 會被拒絕
    assert fusion.forge_request(ready, content, world, "basic_fist", ["feng", "huo"]) is None  # 形狀不對
    assert fusion.forge_request(ready, content, world, None, ["feng"]) is None
    fusion.fuse(other_player(content), content, world, named("旋風腿"), "basic_fist", "feng")
    assert fusion.forge_request(ready, content, world, "basic_fist", ["feng"]) is None  # 別人登記過了：查表就好


def test_a_proposed_name_is_used_without_asking_the_model(ready, content, world):
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "basic_fist", "feng", proposed=("「旋風腿」", "腿影如風。"))
    assert (art.name, art.note) == ("旋風腿", "腿影如風。") and "第一次" in msgs[0]
    insight, _ = fusion.merge(ready, content, world, must_not_ask(), "huo", "feng", proposed=("燎原", "野火燒原。"))
    assert (insight.name, insight.note) == ("燎原", "野火燒原。")


def test_no_proposed_name_falls_back_to_the_word_table_without_asking_the_model(ready, content, world):
    """C 段拿到 (None, "")（B 段叫不動、逾時、取壞了，或 A 段說不必叫）：鎖裡不叫模型，直接走退路字表。"""
    art, _ = fusion.fuse(ready, content, world, must_not_ask(), "basic_fist", "feng", proposed=(None, ""))
    assert art.name == naming.fallback_name(content, fusion.fuse_key("basic_fist", "feng"), "武學", salt=0)
    assert art.note == ""
    bad, _ = fusion.fuse(ready, content, world, must_not_ask(), "basic_fist", "huo", proposed=("九陰真經", "說明"))
    assert bad.name == naming.fallback_name(content, fusion.fuse_key("basic_fist", "huo"), "武學", salt=0)


def _brew_two_recipes_that_got_the_same_model_name(content, world, order):
    """同一個玩家、兩個不同的配方（底＋風、底＋火），模型碰巧給了同一個名字；照 order 的順序登記。"""
    state = new_game_state(content, "沈浪")
    state.player.member.wugong_id, state.player.insights, state.player.stats["xinde"] = "basic_fist", ["feng", "huo"], 100
    for insight in order:
        fusion.fuse(state, content, world, must_not_ask(), "basic_fist", insight, proposed=("旋風腿", "一句話。"))
    return {insight: world.lookup_recipe(fusion.fuse_key("basic_fist", insight)).name for insight in order}


def test_two_recipes_given_the_same_model_name_get_a_fallback_that_does_not_depend_on_who_came_first(content, tmp_path):
    """Infra 第 3 點：兩個不同的配方同時拿到同一個模型名字。先登記的拿到它；後到的換成退路字表的名字——
    種子是它自己的配方鍵＋這一季的天機、鹽從 0 起，所以換個順序再跑一次，後到的那一個拿到的退路名字一樣是它自己的那一個。"""
    from tianxia.sqlite_world import open_world

    names = {}
    for order in (("feng", "huo"), ("huo", "feng")):
        world = open_world(tmp_path / f"{order[0]}.db")
        world.mutate(lambda shared: setattr(shared, "tianji", 3))
        names[order] = _brew_two_recipes_that_got_the_same_model_name(content, world, order)
    fallback = {i: naming.fallback_name(content, fusion.fuse_key("basic_fist", i), "武學", tianji=3) for i in ("feng", "huo")}
    assert names[("feng", "huo")] == {"feng": "旋風腿", "huo": fallback["huo"]}
    assert names[("huo", "feng")] == {"huo": "旋風腿", "feng": fallback["feng"]}
    assert fallback["huo"] != naming.fallback_name(content, fusion.fuse_key("basic_fist", "huo"), "武學")  # 天機有算進去


def test_already_having_it_is_reported_before_what_it_would_cost(ready, content, world):
    """同一個人連按兩下（或開兩個分頁）：第二下在 C 段重驗時，告訴他真正變了的事——你已經有了——
    而不是第一下花掉之後才不夠的心得、體力或滿了的持有。"""
    fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    ready.player.stats["xinde"], ready.player.stamina = 0, 0
    assert "已經有了" in fusion.fuse_problem(ready, content, world, "basic_fist", "feng")
    assert "已經悟得" in fusion.merge_problem(ready, content, world, "feng", "huo")


def test_the_three_steps_run_without_a_server(game):
    """設計者 2026-10-05「假人也叫 AI 取名」：之後 bot_runner 不經過 HTTP 也要走同樣的三段。這裡只拿 Game 與它的全服儲存：
    A 在行動鎖裡（Game.forge_request）→ B 在鎖外（naming.generate）→ C 再進行動鎖（Game.forge(..., proposed=...)）。"""
    p = game.state.player
    p.member.wugong_id, p.insights, p.stats["xinde"] = "basic_fist", ["feng"], 100
    world = game.world
    with world.action_lock():
        request = game.forge_request("basic_fist", ["feng"])
    assert request is not None and request.kind == "fuse"
    model = mock.Mock(timeout=120)

    def reply(messages, response_model, **kwargs):
        assert not world.db.writing()  # B 段沒拿著寫入交易
        return naming.NameReply(name="旋風腿", description="腿影如風。")

    model.chat_structured.side_effect = reply
    proposed = naming.generate(model, game.content, request, budget=game.content.config.naming_budget_seconds)
    assert proposed == ("旋風腿", "腿影如風。")
    with world.action_lock():
        msgs = game.forge("basic_fist", ["feng"], proposed=proposed)
    assert "旋風腿" in p.arts and p.stats["xinde"] == 95 and "第一次" in msgs[0]
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")).note == "腿影如風。"


def test_forge_request_on_the_game_needs_a_model_client(game):
    p = game.state.player
    p.member.wugong_id, p.insights, p.stats["xinde"] = "basic_fist", ["feng"], 100
    assert game.forge_request("basic_fist", ["feng"]) is not None
    game.client = None  # 沒有 client（伺服器假人鎖內的 Game 就是這樣）：預設不開單；假人程式在鎖外自己叫模型，給 named_outside=True 才開
    assert game.forge_request("basic_fist", ["feng"]) is None


def test_the_naming_budget_fits_under_the_tunnels_cut(content):
    """trycloudflare 約 100 秒就切斷一個請求；取名的預算 60 秒，留下 A、C 兩段等行動鎖的餘裕（控制者 2026-10-05）。"""
    assert content.config.naming_budget_seconds == 60


# ── 合併要花體力（企劃者 2026-10-05：「意境合併要花體力，這樣的話她要拿心得就給他拿」）──────────
# 合併→熔掉→再合併，每一圈淨賺 5 點心得（merge_xinde 5、melt_insight_xinde 10）；企劃者的裁示不是擋重合、也不是
# 動熔的價，而是讓合併花體力：要賺就照著賺，只是每一圈都要付體力（FB-067 起 5 點，修練一次是 10）。合成（武學＋意境）維持不花體力。


def test_merge_stamina_is_half_a_cultivation_by_default(content):
    """FB-067（企劃者 2026-10-05）：合併的體力降到 5（原本 10，跟修練一次一樣）；修練（含衝絕學）維持 10。"""
    assert (content.config.merge_stamina, content.config.cultivate_stamina) == (5, 10)


def test_a_merge_costs_stamina_as_well_as_xinde(ready, content, world):
    before = ready.player.stamina
    insight, msgs = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert insight is not None
    assert ready.player.stamina == before - content.config.merge_stamina
    assert ready.player.stats["xinde"] == 100 - content.config.merge_xinde
    assert f"心得 -{content.config.merge_xinde}" in msgs and f"體力 -{content.config.merge_stamina}" in msgs


def test_a_merge_recipe_book_hit_costs_the_stamina_too(ready, content, world):
    fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    other = other_player(content, ("feng", "huo"))
    before = other.player.stamina
    second, msgs = fusion.merge(other, content, world, must_not_ask(), "feng", "huo")
    assert second is not None and other.player.stamina == before - content.config.merge_stamina
    assert f"體力 -{content.config.merge_stamina}" in msgs


def test_a_merge_without_enough_stamina_is_refused_and_changes_nothing(ready, content, world):
    ready.player.stamina = content.config.merge_stamina - 1
    assert fusion.merge_problem(ready, content, world, "feng", "huo") == f"體力不足：合併一次要 {content.config.merge_stamina}。"
    insight, msgs = fusion.merge(ready, content, world, named("燎原"), "feng", "huo")
    assert insight is None and msgs == [f"體力不足：合併一次要 {content.config.merge_stamina}。"]
    assert (ready.player.stamina, ready.player.stats["xinde"], ready.player.insights) == (
        content.config.merge_stamina - 1, 100, ["feng", "huo"],
    )
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")) is None  # 被拒絕的不登記配方


def test_a_merge_with_exactly_enough_stamina_goes_through_and_leaves_none(ready, content, world):
    ready.player.stamina = content.config.merge_stamina
    insight, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert insight is not None and ready.player.stamina == 0


def test_not_enough_xinde_is_still_reported_before_the_stamina(ready, content, world):
    ready.player.stamina, ready.player.stats["xinde"] = 0, 0
    assert "心得不足" in fusion.merge_problem(ready, content, world, "feng", "huo")


# ── 三種合成同一套價錢（武學與成長設計 12.1）──────────────────

def test_a_fuse_costs_stamina_as_well_as_xinde(ready, content, world):
    before = ready.player.stamina
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert art is not None and ready.player.stamina == before - content.config.fuse_stamina
    assert f"心得 -{content.config.fuse_xinde}" in msgs and f"體力 -{content.config.fuse_stamina}" in msgs


def test_a_fuse_without_enough_stamina_is_refused_and_changes_nothing(ready, content, world):
    ready.player.stamina = content.config.fuse_stamina - 1
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "basic_fist", "feng")
    assert art is None and msgs == [f"體力不足：合成一次要 {content.config.fuse_stamina}。"]
    assert ready.player.arts == [] and ready.player.stats["xinde"] == 100
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None


def test_not_enough_xinde_is_still_reported_before_the_stamina_for_a_fuse(ready, content, world):
    ready.player.stamina, ready.player.stats["xinde"] = 0, 0
    assert "心得不足" in fusion.fuse_problem(ready, content, world, "basic_fist", "feng")


def test_the_engine_merge_journal_entry_shows_both_the_xinde_and_the_stamina(game):
    p = game.state.player
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    before = p.stamina
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        msgs = game.forge(None, ["feng", "huo"])
    entry = game.state.journal[0]
    assert entry.title == "煉製" and entry.tag.startswith("合併「")
    assert "心得 -5" in entry.changes and "體力 -5" in entry.changes  # FB-067：合併 5 點體力
    assert p.stamina == before - 5 and "體力 -5" in msgs  # FB-067：合併 5 點體力


def test_the_engine_fuse_journal_entry_shows_both_the_xinde_and_the_stamina(game):
    p = game.state.player
    p.member.wugong_id, p.insights, p.stats["xinde"] = "basic_fist", ["feng"], 100
    before = p.stamina
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", ["feng"])
    entry = game.state.journal[0]
    stamina = game.content.config.fuse_stamina
    assert "心得 -5" in entry.changes and f"體力 -{stamina}" in entry.changes
    assert p.stamina == before - stamina


def test_the_engine_refused_merge_writes_no_journal_entry_and_spends_nothing(game):
    p = game.state.player
    p.insights, p.stats["xinde"], p.stamina = ["feng", "huo"], 100, 3
    length = len(game.state.journal)
    msgs = game.forge(None, ["feng", "huo"])
    assert any("體力不足" in m for m in msgs) and len(game.state.journal) == length
    assert (p.stamina, p.stats["xinde"], p.insights) == (3, 100, ["feng", "huo"])


def test_the_merge_melt_merge_loop_is_still_allowed_but_every_round_costs_stamina(game):
    """要拿心得就給他拿：合併（-5 心得、-10 體力）→ 熔掉那個意境（+10 心得）→ 再合同一組，沒有被擋；
    每一圈淨賺 5 點心得，也實實在在花掉 10 點體力。"""
    p = game.state.player
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    cfg = game.content.config
    stamina, xinde = p.stamina, p.stats["xinde"]
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        for round_ in range(1, 4):
            game.forge(None, ["feng", "huo"])
            (merged,) = [i for i in p.insights if i not in ("feng", "huo")]
            game.melt_insight(merged)
            assert p.insights == ["feng", "huo"]
            assert p.stamina == stamina - cfg.merge_stamina * round_
            assert p.stats["xinde"] == xinde + (cfg.melt_insight_xinde - cfg.merge_xinde) * round_


# ── 合到舊的（設計 12.2）────────────────────────────────────────

def landing_on(content):
    """這個測試裡，有候選就一定合到舊的。"""
    content.config.land_chance_per_candidate, content.config.land_chance_cap = 1.0, 1.0


def two_fast_arts(content, world):
    """乙先合出兩門「武學・快・無」：旋風腿（基礎拳腳＋風）、疾風腿（長拳＋風）。這時合到舊的還關著，兩門都是新的。"""
    other = other_player(content)
    other.player.arts = ["fist"]
    fusion.fuse(other, content, world, named("旋風腿"), "basic_fist", "feng")
    fusion.fuse(other, content, world, named("疾風腿"), "fist", "feng")
    return other


def test_a_first_fuse_can_land_on_an_art_someone_else_made(ready, content, world):
    other = other_player(content)
    made, _ = fusion.fuse(other, content, world, named("旋風腿"), "basic_fist", "feng")
    landing_on(content)
    ready.player.arts = ["lake_kick"]  # 湖邊腿法：武學・快，跟旋風腿同種類、同屬性、同正邪
    xinde, stamina = ready.player.stats["xinde"], ready.player.stamina
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng")  # 只有一個候選：不問模型
    assert art.id == made.id and art.id in ready.player.arts
    assert "合出來的竟是一門已有的武學【旋風腿】" in msgs[0] and "這一門由乙首創。" in msgs[0]
    assert "第一次" not in msgs[0]
    assert ready.player.stats["xinde"] == xinde - content.config.fuse_xinde
    assert ready.player.stamina == stamina - content.config.fuse_stamina
    assert world.lookup_recipe(fusion.fuse_key("lake_kick", "feng")).id == made.id
    assert world.get_skill(made.id).creator == "乙"  # 首創者照舊
    assert [a.id for a in world.fused_arts()] == [made.id]  # 沒有多登記一門


def test_landing_on_an_art_you_already_have_is_free_and_remembered(ready, content, world):
    made, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.arts.append("lake_kick")
    landing_on(content)
    xinde, stamina = ready.player.stats["xinde"], ready.player.stamina
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng")
    assert art is None and msgs == [  # FB-078：這一組是新摸清的練法，回話要講出來（不再只說「你已經有了」）
        "這一爐的路數，竟又歸到【旋風腿】——你多摸清了一條練法（【湖邊腿法】＋「風」）。不收心得、體力。",
    ]
    assert (ready.player.stats["xinde"], ready.player.stamina) == (xinde, stamina)
    assert world.lookup_recipe(fusion.fuse_key("lake_kick", "feng")).id == made.id  # 配方照樣記下來
    assert "你已經有了" in fusion.fuse_problem(ready, content, world, "lake_kick", "feng")  # 下一次按之前就知道


def test_a_new_combination_landing_on_your_own_art_registers_the_recipe_for_everyone(ready, content, world):
    """FB-078（企劃者裁決）：不同組合可以產出同一門，這組新組合合到你自己已經有的那門是對的——配方照樣登記（「這組→那門」），
    之後別人合同一組直接查表拿到那門，不再擲合到舊的、不叫模型；沒有人因為這一組多得到首創，也沒有人被收兩次錢。"""
    made, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.arts.append("lake_kick")
    landing_on(content)  # 唯一的候選是你的旋風腿：一定合到它
    key = fusion.fuse_key("lake_kick", "feng")
    assert world.lookup_recipe(key) is None
    xinde, stamina = ready.player.stats["xinde"], ready.player.stamina
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng")
    assert art is None and "多摸清了一條練法" in msgs[0]
    assert (ready.player.stats["xinde"], ready.player.stamina) == (xinde, stamina)  # 這一爐沒收錢
    assert world.lookup_recipe(key).id == made.id  # 登記了：「湖邊腿法＋風 → 旋風腿」
    assert world.get_skill(made.id).creator == "沈浪" and [a.id for a in world.fused_arts()] == [made.id]  # 首創照舊、沒多登記一門

    other = other_player(content)
    other.player.arts.append("lake_kick")
    other_xinde, other_stamina = other.player.stats["xinde"], other.player.stamina
    with mock.patch.object(landing, "lands", side_effect=AssertionError("配方已經登記：不該再擲合到舊的")):
        got, msgs = fusion.fuse(other, content, world, must_not_ask(), "lake_kick", "feng")
    assert got.id == made.id and made.id in other.player.arts  # 直接查表拿到那門
    assert other.player.stats["xinde"] == other_xinde - content.config.fuse_xinde  # 乙照常付一次
    assert other.player.stamina == other_stamina - content.config.fuse_stamina
    assert "第一次" not in msgs[0] and "這一門由沈浪首創" in msgs[0]  # 首創還是甲的：這一組沒有讓誰多得首創
    assert (ready.player.stats["xinde"], ready.player.stamina) == (xinde, stamina)  # 甲沒有被追加收費
    assert fusion.fuse_problem(other, content, world, "lake_kick", "feng").startswith("這一爐合出來還是【旋風腿】，你已經有了")


def test_the_reply_for_a_new_recipe_is_only_for_the_press_that_found_it(ready, content, world):
    """「多摸清了一條練法」只在這一爐真的把配方登記到你已經有的那門時說；第二次按同一組，按之前的檢查就攔下，說的還是「你已經有了」。"""
    made, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.arts.append("lake_kick")
    landing_on(content)
    first, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng")
    assert first is None and "多摸清了一條練法" in msgs[0]
    again, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng")
    assert again is None and msgs == ["這一爐合出來還是【旋風腿】，你已經有了——換一組試試吧。"]


def test_the_old_reply_stays_when_someone_else_registered_the_recipe_while_you_waited(ready, content, world):
    """C 段重驗時配方已經被別人登記、指到你有的那門：那一組不是你這一爐摸清的，說法照舊（link_recipe 回的 landed 是 False）。"""
    made, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.arts.append("lake_kick")
    landing_on(content)
    real_lookup = world.lookup_recipe
    key = fusion.fuse_key("lake_kick", "feng")
    calls = []

    def lookup(k):  # 第一次查（fuse_problem、fuse 開頭）看不到，之後就有人登記好了
        calls.append(k)
        if k == key and len(calls) <= 2:
            return None
        return real_lookup(k)

    world.link_recipe(key, made.id, "乙")  # 別人先登記了
    with mock.patch.object(world, "lookup_recipe", side_effect=lookup):
        art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng")
    assert art is None and msgs == ["這一爐合出來還是【旋風腿】，你已經有了——換一組試試吧。"]


def test_landing_twice_charges_once(ready, content, world):
    """Review Focus 1：同一爐合到舊的、連按兩下——第二下看見配方指向你剛拿到的那一門，什麼都不收。"""
    other = other_player(content)
    fusion.fuse(other, content, world, named("旋風腿"), "basic_fist", "feng")
    landing_on(content)
    ready.player.arts = ["lake_kick"]
    proposed = (None, "")  # 伺服器一律給 proposed；這一爐只有一個候選，A 段不開單
    first, _ = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng", proposed=proposed)
    xinde, stamina = ready.player.stats["xinde"], ready.player.stamina
    second, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng", proposed=proposed)
    assert first is not None and second is None and "你已經有了" in msgs[0]
    assert (ready.player.stats["xinde"], ready.player.stamina) == (xinde, stamina)


def test_landing_on_the_base_itself_is_free_and_stays_that_way(ready, content, world):
    """Review Focus 4（企劃者 2026-10-05：「旋風腿＋風」合出旋風腿可以接受；「一旦公式訂了就不能再變」）：
    旋風腿（快）＋一個私有的快意境本來會得到「武學・快・無」，唯一的候選是底自己——合到它：你本來就有，什麼都不收，
    配方照樣記下來；之後機會怎麼變都不重判。（旋風腿＋風本身現在被血統擋下，見 lineage_has。）"""
    made, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.own_insights["悟:1"] = Insight(id="悟:1", name="湖中影", attribute="快")
    ready.player.insights.append("悟:1")
    landing_on(content)
    xinde, stamina = ready.player.stats["xinde"], ready.player.stamina
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "旋風腿", "悟:1")
    assert art is None and msgs == [
        "這一爐的路數，竟又歸到【旋風腿】——你多摸清了一條練法（【旋風腿】＋「湖中影」）。不收心得、體力。",
    ]
    assert (ready.player.stats["xinde"], ready.player.stamina) == (xinde, stamina)
    key = fusion.fuse_key("旋風腿", "悟:1", "快")
    assert world.lookup_recipe(key).id == made.id
    content.config.land_chance_per_candidate = 0.0  # 機會改了也不重判：配方已經定了
    assert world.lookup_recipe(key).id == made.id
    assert "你已經有了" in fusion.fuse_problem(ready, content, world, "旋風腿", "悟:1")


def test_with_two_or_more_candidates_the_model_picks_one(ready, content, world):
    two_fast_arts(content, world)
    landing_on(content)
    ready.player.arts = ["lake_kick"]
    client = named("疾風腿")
    art, msgs = fusion.fuse(ready, content, world, client, "lake_kick", "feng")
    assert art.id == "疾風腿" and "竟是" in msgs[0]
    listing = client.chat_structured.call_args.args[0][-1]["content"].split("清單：")[1]
    assert "旋風腿" in listing and "疾風腿" in listing and "湖邊" not in listing  # 基礎武學不是合成物，不在清單上


@pytest.mark.parametrize(("client", "proposed"), [
    pytest.param(named("不在清單上"), None, id="model-names-something-off-the-list"),
    pytest.param(model_down(), None, id="model-down"),
    # Review Focus 2：C 段拿到的名字不在這時的候選裡（A 段之後情況變了）——改由規則挑，不叫模型
    pytest.param(must_not_ask(), ("亂取的名字", ""), id="proposed-name-is-no-candidate"),
])
def test_when_the_model_picks_nothing_on_the_list_the_rules_pick(ready, content, world, client, proposed):
    two_fast_arts(content, world)
    landing_on(content)
    ready.player.arts = ["lake_kick"]
    key = fusion.fuse_key("lake_kick", "feng")
    expected = landing.rule_pick(
        landing.art_candidates(world, "武學", "快", "無"), key, world.read().tianji,
    )
    art, _ = fusion.fuse(ready, content, world, client, "lake_kick", "feng", proposed=proposed)
    assert art.id == expected.id


def test_a_pick_that_turns_into_a_new_art_gets_a_fallback_name(ready, content, world):
    """Review Focus 2：A 段開的是「挑」的單（模型挑了疾風腿），C 段時這一爐翻成長新的——
    挑的名字已經被用掉，登記撞名就走退路字表，照常收一次錢。"""
    two_fast_arts(content, world)
    landing_on(content)
    ready.player.arts = ["lake_kick"]
    request = fusion.forge_request(ready, content, world, "lake_kick", ["feng"])
    assert request.choices == ("旋風腿", "疾風腿")
    content.config.land_chance_per_candidate = 0.0  # A 段之後情況變了
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng", proposed=("疾風腿", ""))
    key = fusion.fuse_key("lake_kick", "feng")
    assert art.name not in ("旋風腿", "疾風腿") and art.name == naming.fallback_name(content, key, "武學", tianji=world.read().tianji)
    assert ready.player.stats["xinde"] == 100 - content.config.fuse_xinde


def test_forge_request_opens_a_pick_only_with_two_or_more_candidates(ready, content, world):
    two_fast_arts(content, world)
    ready.player.arts = ["lake_kick"]
    plain = fusion.forge_request(ready, content, world, "lake_kick", ["feng"])  # 合到舊的還關著：取新名字
    assert plain.kind == "fuse" and plain.choices == ()
    landing_on(content)
    request = fusion.forge_request(ready, content, world, "lake_kick", ["feng"])
    assert request.kind == "fuse" and request.choices == ("旋風腿", "疾風腿")
    assert request.messages[0]["content"] == fusion.PICK_SYSTEM


def test_the_pick_prompt_lists_the_candidates_and_asks_for_the_bare_name():
    """清單每一行寫「名字（屬X）」，模型照抄會被 clean_name 變成「名字屬X」而對不上：提示要明講只回名字本身。"""
    arts = [generate_from_name(name, "武學", name) for name in ("旋風腿", "疾風腿")]
    messages = fusion._pick_messages("說明", arts)
    assert messages[0]["content"] == fusion.PICK_SYSTEM
    assert "- 旋風腿（屬" in messages[1]["content"] and "- 疾風腿（屬" in messages[1]["content"]
    assert "不要帶括號、屬性或說明" in messages[1]["content"]


def test_forge_request_needs_no_model_when_it_lands_on_the_only_candidate(ready, content, world):
    other = other_player(content)
    fusion.fuse(other, content, world, named("旋風腿"), "basic_fist", "feng")
    landing_on(content)
    ready.player.arts = ["lake_kick"]
    assert fusion.forge_request(ready, content, world, "lake_kick", ["feng"]) is None


def test_a_first_merge_can_land_on_a_known_insight(ready, content, world):
    """乙先合出燎原（火＋風＝陽）與狂風（風＋風＝快）；甲第一次合狂風＋火（快＋剛＝陽），合到燎原。"""
    other = other_player(content, insights=("feng", "huo"))
    fusion.merge(other, content, world, named("燎原"), "feng", "huo")
    fusion.merge(other, content, world, named("狂風"), "feng", "feng")
    landing_on(content)
    ready.player.insights = ["狂風", "huo"]
    stamina = ready.player.stamina
    insight, msgs = fusion.merge(ready, content, world, must_not_ask(), "狂風", "huo")
    assert insight.id == "燎原" and "燎原" in ready.player.insights
    assert "化成的竟是已有的「燎原」" in msgs[0] and "這個意境由乙首悟。" in msgs[0]
    assert ready.player.stamina == stamina - content.config.merge_stamina
    assert world.lookup_insight_recipe(fusion.merge_key("狂風", "huo")).id == "燎原"


def test_a_merged_insights_attribute_follows_the_recipe_not_the_name(ready, content, tmp_path, monkeypatch):
    """設計 12.6：火＋水是相剋的一對，屬性由配方加天機決定；模型取什麼名字都一樣。一個天機只翻一次硬幣、可能剛好兩邊一樣，
    所以每個天機各開一個新世界合一次：結果都要跟配方種子算的一樣，而且兩種屬性都要出現過（種子真的有在用）。"""
    seen = set()
    for tianji in range(12):
        monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / f"world{tianji}.db")
        world = open_world()
        world.mutate(lambda shared: setattr(shared, "tianji", tianji))
        ready.player.insights, ready.player.stats["xinde"], ready.player.stamina = ["huo", "shui"], 100, 100
        key = fusion.merge_key("huo", "shui")
        fire, water = (insights.resolve(i, content, world) for i in ("huo", "shui"))
        expected = insights.merged_attribute(fire, water, fusion.recipe_seed(world, key)[1])
        insight, _ = fusion.merge(ready, content, world, named(f"水火{tianji}"), "huo", "shui")
        assert insight.attribute == expected, tianji
        seen.add(insight.attribute)
    assert seen == {"剛", "柔"}


def two_yang_insights(world):
    """乙先合出兩個「陽・無」的意境（燎原、烈焰）：合到舊的還關著時直接登記，候選才有兩個。"""
    for i, name in enumerate(("燎原", "烈焰")):
        world.claim_insight_recipe(f"合|測試{i}", Insight(id=name, name=name, attribute="陽", creator="乙"))


def test_a_proposed_pick_beats_the_rules_pick(ready, content, world):
    """Task 4 審查：C 段拿到的「挑」要真的用上。挑規則不會挑的那一個——_picked 若不理 proposed，改由規則挑，這裡就會錯。"""
    two_fast_arts(content, world)
    landing_on(content)
    ready.player.arts = ["lake_kick"]
    key = fusion.fuse_key("lake_kick", "feng")
    candidates = landing.art_candidates(world, "武學", "快", "無")
    by_rule = landing.rule_pick(candidates, key, world.read().tianji)
    other = next(c for c in candidates if c.id != by_rule.id)
    art, _ = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng", proposed=(other.name, ""))
    assert art.id == other.id and art.id != by_rule.id
    assert world.lookup_recipe(key).id == other.id


def test_a_proposed_pick_beats_the_rules_pick_for_a_merge(ready, content, world):
    two_yang_insights(world)
    landing_on(content)
    key = fusion.merge_key("feng", "huo")
    candidates = landing.insight_candidates(world, "陽", "無")
    by_rule = landing.rule_pick(candidates, key, world.read().tianji)
    other = next(c for c in candidates if c.id != by_rule.id)
    insight, _ = fusion.merge(ready, content, world, must_not_ask(), "feng", "huo", proposed=(other.name, ""))
    assert insight.id == other.id and insight.id != by_rule.id
    assert world.lookup_insight_recipe(key).id == other.id


def test_the_model_picks_one_of_two_known_insights_too(ready, content, world):
    """沒給 proposed 時在這裡問模型（整季機器人、腳本）：挑到規則不會挑的那一個。"""
    two_yang_insights(world)
    landing_on(content)
    key = fusion.merge_key("feng", "huo")
    candidates = landing.insight_candidates(world, "陽", "無")
    by_rule = landing.rule_pick(candidates, key, world.read().tianji)
    other = next(c for c in candidates if c.id != by_rule.id)
    client = named(other.name)
    insight, msgs = fusion.merge(ready, content, world, client, "feng", "huo")
    assert insight.id == other.id and "化成的竟是已有的" in msgs[0]
    listing = client.chat_structured.call_args.args[0][-1]["content"].split("清單：")[1]
    assert "- 燎原（屬陽）" in listing and "- 烈焰（屬陽）" in listing
    assert "- 風（" not in listing and "- 火（" not in listing  # 基本意境不是合併得來的，不在清單上


def test_forge_request_opens_a_pick_for_a_merge_with_two_candidates(ready, content, world):
    two_yang_insights(world)
    plain = fusion.forge_request(ready, content, world, None, ["feng", "huo"])  # 合到舊的還關著：取新名字
    assert plain.kind == "merge" and plain.choices == ()
    landing_on(content)
    request = fusion.forge_request(ready, content, world, None, ["feng", "huo"])
    assert request.kind == "merge" and request.choices == ("燎原", "烈焰")
    assert request.messages[0]["content"] == fusion.PICK_SYSTEM


def test_forge_request_needs_no_model_when_a_merge_lands_on_the_only_candidate(ready, content, world):
    world.claim_insight_recipe("合|測試", Insight(id="燎原", name="燎原", attribute="陽", creator="乙"))
    landing_on(content)
    assert fusion.forge_request(ready, content, world, None, ["feng", "huo"]) is None


def test_landing_on_an_insight_you_already_hold_is_free(ready, content, world):
    """合出來的意境你已經悟得了：什麼都不收、不重複，配方照樣記下來（下一次按之前就知道）。"""
    fusion.merge(ready, content, world, named("燎原"), "feng", "huo")  # 陽
    fusion.merge(ready, content, world, named("狂風"), "feng", "feng")  # 快
    landing_on(content)
    xinde, stamina, held = ready.player.stats["xinde"], ready.player.stamina, list(ready.player.insights)
    result, msgs = fusion.merge(ready, content, world, must_not_ask(), "狂風", "huo")  # 快＋剛＝陽，唯一的候選是你的燎原
    assert result is None and msgs == [  # FB-078：這一組是新摸清的悟法，回話要講出來
        "這一爐的路數，竟又歸到「燎原」——你多摸清了一條悟法（「狂風」＋「火」）。不收心得、體力。",
    ]
    assert (ready.player.stats["xinde"], ready.player.stamina, ready.player.insights) == (xinde, stamina, held)
    assert world.lookup_insight_recipe(fusion.merge_key("狂風", "huo")).id == "燎原"
    assert "你已經悟得了" in fusion.merge_problem(ready, content, world, "狂風", "huo")  # 下一次按之前就知道，說法照舊
    other = other_player(content, ("feng", "huo"))  # 別人合同一組：直接查表拿到燎原，不擲合到舊的
    other.player.insights = ["狂風", "huo"]
    with mock.patch.object(landing, "lands", side_effect=AssertionError("配方已經登記：不該再擲合到舊的")):
        got, _ = fusion.merge(other, content, world, must_not_ask(), "狂風", "huo")
    assert got.id == "燎原" and "燎原" in other.player.insights


def test_landing_follows_the_registered_id_after_the_art_was_renamed(ready, content, world):
    """link_recipe 認登記的 id（skills 表的名字欄），不是現在顯示的名字：絕學的首位練成者替它改了名（world.rename_skill）
    之後兩個不一樣，合到它還是要成；模型挑的是清單上寫的名字（顯示的），也要對得回那一門。"""
    two_fast_arts(content, world)
    assert world.rename_skill("旋風腿", "颶風腿")
    landing_on(content)
    ready.player.arts = ["lake_kick"]
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng", proposed=("颶風腿", ""))
    assert art.id == "旋風腿" and art.name == "颶風腿" and "【颶風腿】" in msgs[0]
    assert world.lookup_recipe(fusion.fuse_key("lake_kick", "feng")).id == "旋風腿"
    assert "旋風腿" in ready.player.arts


# ── 武學＋武學（設計 12.3）────────────────────────────────────

def base_art(art_id, content, world):
    return team.resolve_art(art_id, content, world)


def test_blending_two_arts_keeps_both_and_adds_a_new_one(ready, content, world):
    ready.player.arts = ["lake_kick"]  # 粗淺拳腳（武學・實，身上）＋湖邊腿法（武學・快，功法庫）
    before = ready.player.stamina
    art, msgs = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert (art.name, art.kind, art.origin, art.quality) == ("踏浪拳", "武學", "fused", "下品")
    assert art.parents == ["basic_fist", "lake_kick"] and art.base is None
    assert art.attribute in ("實", "快") and art.insight is None  # 實＋快不在第一層的表裡；兩門都沒記意境
    assert {"basic_fist", "lake_kick", art.id} <= set(library.owned_arts(ready))  # 兩門都留著
    assert ready.player.stats["xinde"] == 100 - content.config.fuse_xinde
    assert ready.player.stamina == before - content.config.fuse_stamina
    assert world.lookup_recipe(fusion.blend_key("lake_kick", "basic_fist")).id == art.id  # 不分先後
    assert "你把【粗淺拳腳】與【湖邊腿法】合而為一" in msgs[0] and "第一次" in msgs[0]


def test_two_fused_arts_blend_by_the_pair_table_and_remember_one_parents_insight(ready, content, world):
    fast, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    hard, _ = fusion.fuse(ready, content, world, named("烈火拳"), "basic_fist", "huo")
    art, _ = fusion.blend(ready, content, world, named("烈風腿"), fast.id, hard.id)
    assert art.attribute == "陽" and art.kind == "武學" and art.lean == "無"  # 快＋剛＝陽
    shape = fusion.blend_shape(fast, hard, fusion.recipe_seed(world, fusion.blend_key(fast.id, hard.id))[1])
    assert art.insight == shape.insight and art.insight in ("feng", "huo")  # 兩門都不是陽：配方挑一門


def test_a_blended_art_inherits_the_insight_even_when_one_parent_is_basic(ready, content, world):
    """旋風腿（快、記風）＋湖邊腿法（快、沒記意境）：不管配方挑到哪一門，沒有意境的那門就改用另一門的。"""
    fast, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.arts.append("lake_kick")
    art, _ = fusion.blend(ready, content, world, named("踏浪腿"), fast.id, "lake_kick")
    assert art.attribute == "快" and art.insight == "feng"


def test_blend_shape_keeps_an_insight_whichever_way_the_recipe_leans(content, world):
    """兩門屬性一樣、只有一門記了意境：不管配方挑到哪一門，都用記了的那一個；兩門都記了才各有一半機會。"""
    kick = base_art("lake_kick", content, world)
    windy = kick.model_copy(update={"id": "windy", "insight": "feng"})
    fiery = kick.model_copy(update={"id": "fiery", "insight": "huo"})
    for i in range(40):
        assert fusion.blend_shape(windy, kick, f"0|兼|{i}").insight == "feng"
        assert fusion.blend_shape(kick, windy, f"0|兼|{i}").insight == "feng"
    assert {fusion.blend_shape(windy, fiery, f"0|兼|{i}").insight for i in range(40)} == {"feng", "huo"}


def test_blend_shape_gives_either_kind_for_an_inner_and_an_outer_art(content, world):
    breath, fist = base_art("basic_breath", content, world), base_art("basic_fist", content, world)
    assert {fusion.blend_shape(breath, fist, f"0|兼|{i}").kind for i in range(40)} == {"內功", "武學"}
    assert fusion.blend_shape(breath, fist, "0|兼|x") == fusion.blend_shape(fist, breath, "0|兼|x")  # 不分先後


def test_blend_shape_passes_the_lean_through_and_cancels_it(content, world):
    fist = base_art("basic_fist", content, world)
    good, evil = fist.model_copy(update={"id": "a", "lean": "正"}), fist.model_copy(update={"id": "b", "lean": "邪"})
    kick = base_art("lake_kick", content, world)
    assert fusion.blend_shape(good, kick, "0|兼|x").lean == "正"
    assert fusion.blend_shape(good, evil, "0|兼|x").lean == "無"


def test_an_inner_and_an_outer_art_blend_into_the_kind_the_recipe_fixes(ready, content, world):
    ready.player.member.neigong_id = "basic_breath"
    art, _ = fusion.blend(ready, content, world, named("吐納拳"), "basic_breath", "basic_fist")
    seed = fusion.recipe_seed(world, fusion.blend_key("basic_breath", "basic_fist"))[1]
    expected = fusion.blend_shape(base_art("basic_breath", content, world), base_art("basic_fist", content, world), seed)
    assert (art.kind, art.attribute) == (expected.kind, expected.attribute)


def test_blend_needs_two_different_arts_you_know(ready, content, world):
    assert fusion.blend_problem(ready, content, world, "basic_fist", "basic_fist") == "要放兩門不同的武學。"
    assert fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick") == "兩門都要是你會的武學。"
    ready.player.arts = ["lake_kick"]
    assert fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick") is None


def test_a_blend_costs_like_a_fuse_and_is_refused_without_stamina(ready, content, world):
    ready.player.arts = ["lake_kick"]
    ready.player.stamina = content.config.fuse_stamina - 1
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick")
    assert art is None and msgs == [f"體力不足：合成一次要 {content.config.fuse_stamina}。"]
    assert world.lookup_recipe(fusion.blend_key("basic_fist", "lake_kick")) is None


def test_a_known_blend_you_already_have_is_refused_before_paying(ready, content, world):
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    xinde = ready.player.stats["xinde"]
    assert fusion.blend_problem(ready, content, world, "lake_kick", "basic_fist") == (
        f"這兩門合出來還是【{art.name}】，你已經有了——換一門吧。"
    )
    again, _ = fusion.blend(ready, content, world, must_not_ask(), "lake_kick", "basic_fist")
    assert again is None and ready.player.stats["xinde"] == xinde


def test_blending_and_melting_the_result_never_makes_xinde(ready, content, world):
    """設計 12.4：合出來的下品、沒練過，熔掉退的比合成花的少，一圈只虧不賺。"""
    ready.player.arts = ["lake_kick"]
    xinde = ready.player.stats["xinde"]
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    library.melt_art(ready, content, world, art.id)
    assert ready.player.stats["xinde"] < xinde


def test_a_blend_can_land_on_one_of_its_own_arts(ready, content, world):
    """Review Focus 4：旋風腿（快）＋湖邊腿法（快）→ 快；唯一的候選是放進去的旋風腿自己——合到它（企劃者接受）：
    你本來就有，什麼都不收，配方照樣記下來。"""
    fast, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.arts.append("lake_kick")
    landing_on(content)
    xinde, stamina = ready.player.stats["xinde"], ready.player.stamina
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), fast.id, "lake_kick")
    assert art is None and msgs == [  # FB-078：兩門照 id 排（跟成功那句、功法卡同一個先後）
        "這一爐的路數，竟又歸到【旋風腿】——你多摸清了一條練法（【湖邊腿法】＋【旋風腿】）。不收心得、體力。",
    ]
    assert (ready.player.stats["xinde"], ready.player.stamina) == (xinde, stamina)
    assert world.lookup_recipe(fusion.blend_key(fast.id, "lake_kick")).id == fast.id
    assert "你已經有了" in fusion.blend_problem(ready, content, world, fast.id, "lake_kick")  # 下一次按之前就知道


def test_forge_request_for_a_blend(ready, content, world):
    ready.player.arts = ["lake_kick"]
    request = fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick")
    assert request.kind == "blend" and request.key == fusion.blend_key("basic_fist", "lake_kick")
    assert "兩門合而為一" in request.messages[-1]["content"]
    assert fusion.forge_request(ready, content, world, "basic_fist", ["feng"], other_art="lake_kick") is None


def test_the_engine_blends_two_arts_and_logs_it_under_the_furnace(game):
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id, p.stats["xinde"] = "basic_fist", "basic_breath", 100
    before = p.stamina
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", [], other_art="basic_breath")
    entry = game.state.journal[0]
    assert entry.title == "煉製" and entry.tag.startswith("合成【")
    assert p.stamina == before - game.content.config.fuse_stamina
    assert len(library.owned_arts(game.state)) == 3


def test_the_engine_refuses_a_furnace_that_is_none_of_the_three(game):
    msgs = game.forge("basic_fist", ["feng"], other_art="basic_breath")
    assert "放一門武學和一個意境" in msgs[0] and "兩門武學" in msgs[0]


def test_with_two_candidates_the_model_picks_one_for_a_blend_and_it_need_not_be_a_parent(ready, content, world):
    """旋風腿（快）＋湖邊腿法（快）→ 武學・快・無：候選是旋風腿（放進爐裡的）與乙合出的疾風腿；模型挑疾風腿——
    你還沒有它，照常收一次錢；同一爐反過來再按一次，看見配方指向你剛拿到的那一門，什麼都不收。"""
    two_fast_arts(content, world)
    fusion.fuse(ready, content, world, must_not_ask(), "basic_fist", "feng")  # 乙已經登記過：照表拿到旋風腿
    ready.player.arts.append("lake_kick")
    landing_on(content)
    request = fusion.forge_request(ready, content, world, "旋風腿", [], other_art="lake_kick")
    assert request.kind == "blend" and request.choices == ("旋風腿", "疾風腿")
    assert request.messages[0]["content"] == fusion.PICK_SYSTEM
    xinde, stamina = ready.player.stats["xinde"], ready.player.stamina
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), "旋風腿", "lake_kick", proposed=("疾風腿", ""))
    assert art.id == "疾風腿" and art.id in library.owned_arts(ready)
    assert "合出來的竟是一門已有的武學【疾風腿】" in msgs[0] and "這一門由乙首創。" in msgs[0]
    assert ready.player.stats["xinde"] == xinde - content.config.fuse_xinde
    assert ready.player.stamina == stamina - content.config.fuse_stamina
    key = fusion.blend_key("旋風腿", "lake_kick")
    assert world.lookup_recipe(key).id == "疾風腿" and art.parents == []  # 它本來的來源不改
    again, msgs = fusion.blend(ready, content, world, must_not_ask(), "lake_kick", "旋風腿", proposed=("疾風腿", ""))
    assert again is None and "你已經有了" in msgs[0]
    assert ready.player.stats["xinde"] == xinde - content.config.fuse_xinde  # 沒有再收


def test_a_blend_takes_the_proposed_name_and_note_without_asking_the_model(ready, content, world):
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick", proposed=("踏浪拳", "拳腳並用。"))
    assert art.name == "踏浪拳" and art.note == "拳腳並用。"
    assert world.lookup_recipe(fusion.blend_key("basic_fist", "lake_kick")).note == "拳腳並用。"


def test_a_blend_without_a_model_falls_back_to_the_word_table(ready, content, world):
    ready.player.arts = ["lake_kick"]
    key = fusion.blend_key("basic_fist", "lake_kick")
    art, _ = fusion.blend(ready, content, world, model_down(), "basic_fist", "lake_kick")
    shape = fusion.blend_shape(
        base_art("basic_fist", content, world), base_art("lake_kick", content, world), fusion.recipe_seed(world, key)[1],
    )
    assert art.name == naming.fallback_name(content, key, shape.kind, tianji=world.read().tianji)
    assert art.kind == shape.kind and art.attribute == shape.attribute and art.note == ""


def test_a_second_player_blends_into_the_same_art_without_the_model(ready, content, world):
    """配方全服共享（設計 12.3）：乙先合出來，甲照同樣兩門合（不管順序）拿到同一門，不問模型、不再登記。"""
    other = other_player(content)
    other.player.arts = ["lake_kick"]
    made, _ = fusion.blend(other, content, world, named("踏浪拳"), "lake_kick", "basic_fist")
    ready.player.arts = ["lake_kick"]
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick")
    assert art.id == made.id and "你照著合出了同一門" in msgs[0]
    assert [a.id for a in world.fused_arts()] == [made.id]


def test_the_three_steps_run_for_a_blend_too(game):
    """A（鎖內 Game.forge_request）→ B（鎖外 naming.generate）→ C（鎖內 Game.forge(..., proposed=, other_art=)）。"""
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id, p.stats["xinde"] = "basic_fist", "basic_breath", 100
    world = game.world
    with world.action_lock():
        request = game.forge_request("basic_fist", [], other_art="basic_breath")
    assert request is not None and request.kind == "blend"
    model = mock.Mock(timeout=120)
    model.chat_structured.return_value = naming.NameReply(name="吐納拳", description="一吐一納，拳隨氣走。")
    proposed = naming.generate(model, game.content, request, budget=game.content.config.naming_budget_seconds)
    assert proposed == ("吐納拳", "一吐一納，拳隨氣走。")
    with world.action_lock():
        msgs = game.forge("basic_fist", [], proposed=proposed, other_art="basic_breath")
    (made,) = p.arts
    assert world.get_skill(made).name == "吐納拳" and p.stats["xinde"] == 95 and "第一次" in msgs[0]
    assert world.lookup_recipe(fusion.blend_key("basic_fist", "basic_breath")).note == "一吐一納，拳隨氣走。"
    assert game.forge_request("basic_fist", [], other_art="basic_breath") is None  # 配方登記了：不必再問
    assert game.forge_request("basic_fist", [], other_art=made) is not None  # 另一組還沒人合過
    game.client = None  # 沒有 client（伺服器假人鎖內的 Game 就是這樣）：預設不開單；假人程式在鎖外自己叫模型，給 named_outside=True 才開
    assert game.forge_request("basic_fist", [], other_art=made) is None


# ── 武學＋武學：Task 5 審查補的測試 ───────────────────────────────

def test_blend_parents_are_sorted_whatever_the_order_you_put_them_in(ready, content, world):
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "lake_kick", "basic_fist")  # 反過來放
    assert art.parents == ["basic_fist", "lake_kick"]
    assert world.get_skill(art.id).parents == ["basic_fist", "lake_kick"]  # 登記的那一筆也是
    assert skillview.parent_names(art, content, world) == ["粗淺拳腳", "湖邊腿法"]  # 功法卡的先後照 id 排，不看你怎麼放


ART_ORDER = [("basic_fist", "lake_kick"), ("lake_kick", "basic_fist")]


@pytest.mark.parametrize(("a", "b"), ART_ORDER)
def test_the_blend_sentence_names_the_two_arts_in_the_order_of_the_art_card(ready, content, world, a, b):
    """FB-073：回話寫「你把【甲】與【乙】合而為一」、功法卡寫「由【甲】與【乙】衍生」，兩邊的先後要一樣——照 id 排
    （MartialArt.parents），不看玩家怎麼放。"""
    ready.player.arts = ["lake_kick"]
    art, msgs = fusion.blend(ready, content, world, named("踏浪拳"), a, b)
    first, second = skillview.parent_names(art, content, world)
    assert (first, second) == ("粗淺拳腳", "湖邊腿法")
    assert msgs[0].startswith(f"你把【{first}】與【{second}】合而為一，衍生出一門")
    assert f"由【{first}】與【{second}】衍生" in skillview.art_card(art, 1, parent_names=[first, second])


@pytest.mark.parametrize(("a", "b"), ART_ORDER)
def test_a_landed_blend_sentence_follows_the_same_order(ready, content, world, a, b):
    """武學＋武學也會合到一門已知的（候選拳，乙首創）：登記成這個配方、不叫模型；句子照功法卡的順序寫兩門，不管放進爐子的先後。"""
    ready.player.arts = ["lake_kick"]
    key = fusion.blend_key("basic_fist", "lake_kick")
    shape = fusion.blend_shape(
        base_art("basic_fist", content, world), base_art("lake_kick", content, world), fusion.recipe_seed(world, key)[1],
    )
    known = generate_from_name("候選拳", shape.kind, "候選拳").model_copy(update={
        "origin": "fused", "attribute": shape.attribute, "lean": shape.lean, "creator": "乙",
    })
    world.claim_recipe("融|測試", known)
    landing_on(content)
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), a, b)
    assert art.id == "候選拳" and "由乙首創" in msgs[0]
    assert msgs[0].startswith("你把【粗淺拳腳】與【湖邊腿法】合而為一，合出來的竟是一門已有的")
    assert world.lookup_recipe(key).id == "候選拳"


def test_a_blend_is_refused_when_the_holdings_are_full(ready, content, world):
    """持有上限含放進爐裡的兩門：一門武學加一門功法庫的加兩個意境＝4，上限 4 就是滿的。拒絕時什麼都不收、不登記、A 段也不開單。"""
    ready.player.arts = ["lake_kick"]
    content.config.holding_cap_base = 4
    xinde, stamina = ready.player.stats["xinde"], ready.player.stamina
    assert fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick") is None
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick")
    assert art is None and "滿了" in msgs[0] and "4/4" in msgs[0]
    assert (ready.player.stats["xinde"], ready.player.stamina) == (xinde, stamina)
    assert world.lookup_recipe(fusion.blend_key("basic_fist", "lake_kick")) is None
    assert ready.player.arts == ["lake_kick"]


def test_a_blend_still_goes_through_one_below_the_cap(ready, content, world):
    ready.player.arts = ["lake_kick"]
    content.config.holding_cap_base = 5  # 現在 4 個，差一個
    assert fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick") is None
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert art is not None and library.held_count(ready) == 5
    assert "5/5" in fusion.blend_problem(ready, content, world, "basic_fist", art.id)  # 合出來的也占一格，現在滿了


@pytest.mark.parametrize(("art", "other", "why"), [
    ("basic_fist", "basic_fist", "同一門放兩次"),
    ("basic_fist", "basic_breath", "另一門你不會"),
    ("basic_fist", "ghost", "找不到資料的"),
])
def test_forge_request_for_a_blend_that_would_be_refused_is_none(ready, content, world, art, other, why):
    ready.player.arts = ["lake_kick", "ghost"]
    assert fusion.blend_problem(ready, content, world, art, other) is not None, why
    assert fusion.forge_request(ready, content, world, art, [], other_art=other) is None, why


def test_forge_request_for_a_blend_with_enough_xinde_and_stamina_only(ready, content, world):
    ready.player.arts = ["lake_kick"]
    assert fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick") is not None
    ready.player.stats["xinde"] = content.config.fuse_xinde - 1
    assert fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick") is None
    ready.player.stats["xinde"] = 100
    ready.player.stamina = content.config.fuse_stamina - 1
    assert fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick") is None


def test_forge_request_for_a_blend_with_a_known_recipe_is_none_even_if_you_do_not_own_the_result(ready, content, world):
    """配方這一季已經有人登記：查表就好，不問模型（照 A 段的規矩）；你還沒有它，所以 blend_problem 不攔。"""
    other = other_player(content)
    other.player.arts = ["lake_kick"]
    fusion.blend(other, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    ready.player.arts = ["lake_kick"]
    assert fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick") is None
    assert fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick") is None


def test_a_blend_passes_a_good_parents_lean_to_the_new_art(ready, content, world):
    """設計 7.3：正＋無＝正；登記的那一筆與玩家拿到的是同一個。"""
    ready.player.insights += ["haoran"]
    good, _ = fusion.fuse(ready, content, world, named("正氣拳"), "basic_fist", "haoran")  # 屬陽、正
    assert good.lean == "正"
    ready.player.arts.append("lake_kick")  # 屬快、無
    art, _ = fusion.blend(ready, content, world, named("正氣腿"), good.id, "lake_kick")
    assert art.lean == "正" and world.get_skill(art.id).lean == "正"
    assert "正派" in skillview.art_card(art, 1)


def test_a_mixed_kind_blend_lands_among_arts_of_the_kind_the_recipe_fixes(ready, content, world):
    """一內一外的兩門合出哪一種由配方定：合到舊的時候選的是那一種的合成物（不是放進爐裡第一門的種類）。
    先放的那一門刻意是種類跟結果不一樣的；同屬性、同正邪但另一種類的合成物是誘餌，不能算候選。"""
    ready.player.member.neigong_id = "basic_breath"
    key = fusion.blend_key("basic_breath", "basic_fist")
    breath, fist = base_art("basic_breath", content, world), base_art("basic_fist", content, world)
    shape = fusion.blend_shape(breath, fist, fusion.recipe_seed(world, key)[1])
    first, second = ("basic_breath", "basic_fist") if breath.kind != shape.kind else ("basic_fist", "basic_breath")
    decoy_kind = "武學" if shape.kind == "內功" else "內功"
    for name, kind in (("甲功", shape.kind), ("乙功", shape.kind), ("誘餌功", decoy_kind)):
        known = generate_from_name(name, kind, name).model_copy(update={
            "origin": "fused", "attribute": shape.attribute, "lean": shape.lean, "creator": "丙",
        })
        assert world.claim_recipe(f"融|測試{name}", known)[1]
    landing_on(content)
    request = fusion.forge_request(ready, content, world, first, [], other_art=second)
    assert request.kind == "blend" and request.choices == ("甲功", "乙功")
    art, _ = fusion.blend(ready, content, world, must_not_ask(), first, second, proposed=("乙功", ""))
    assert art.id == "乙功" and art.kind == shape.kind
    assert world.lookup_recipe(key).id == "乙功"


def test_blend_shape_keeps_the_insight_of_the_one_parent_that_matches_the_result(content, world):
    """快與實不在對照表裡：結果的屬性由配方從兩門裡挑一個；只有一門的屬性跟結果一樣，就記那一門的意境（不看另一個擲骰）。"""
    kick = base_art("lake_kick", content, world).model_copy(update={"id": "windy", "insight": "feng"})  # 屬快
    fist = base_art("basic_fist", content, world).model_copy(update={"id": "hard", "insight": "huo"})  # 屬實
    seen = set()
    for i in range(40):
        shape = fusion.blend_shape(kick, fist, f"0|兼|{i}")
        assert shape.attribute in ("快", "實")
        assert shape.insight == ("feng" if shape.attribute == "快" else "huo"), i
        assert fusion.blend_shape(fist, kick, f"0|兼|{i}") == shape  # 不分先後
        seen.add(shape.attribute)
    assert seen == {"快", "實"}  # 兩邊都出現過，上面的判斷才不是巧合


# ── 武學的功效（武學與成長設計 13.3、13.4；計畫六 Task 2）：合成照來路帶一般功效、偶爾擲出特別功效 ──────────────


def test_a_fused_art_carries_its_lineage_traits(ready, content, world):
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert art.traits == ["快", "實"]  # 風的屬性在前，粗淺拳腳（實）傳下來
    assert world.get_skill(art.id).traits == ["快", "實"]  # 登記在全服的那一份也帶著
    again, _ = fusion.fuse(ready, content, world, named("烈風腿"), art.id, "huo")
    assert again.traits == ["剛", "快", "實"]


def test_a_fused_art_keeps_its_traits_when_the_model_is_down(ready, content, world):
    """取名走退路字表也一樣：功效是規則算的，跟名字哪來的無關。"""
    art, _ = fusion.fuse(ready, content, world, model_down(), "basic_fist", "feng")
    assert art.traits == ["快", "實"]


def test_a_blended_art_carries_both_parents_own_traits(ready, content, world):
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert art.traits[0] == art.attribute and sorted(art.traits[1:]) == ["實", "快"]
    assert world.get_skill(art.id).traits == art.traits


def test_a_new_art_may_roll_a_special(ready, content, world):
    content.config.special_trait_chance = 1.0
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert art.special in {t.id for t in content.traits.special if t.pool}
    assert world.get_skill(art.id).special == art.special


def test_a_blended_art_may_roll_a_special_too(ready, content, world):
    content.config.special_trait_chance = 1.0
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert art.special in {t.id for t in content.traits.special if t.pool}


def test_no_special_when_the_chance_is_zero(ready, content, world):
    content.config.special_trait_chance = 0.0
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert art.special is None and not any("江湖上傳開了" in m for m in msgs)
    assert ready.world.rumors == []


def test_the_special_does_not_pass_down_to_the_next_art(ready, content, world):
    """設計 13.4：拿它當底、或跟別的武學合，傳下去的只有一般功效；新武學照自己的配方擲。"""
    content.config.special_trait_chance = 1.0
    base, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert base.special is not None
    content.config.special_trait_chance = 0.0
    child, _ = fusion.fuse(ready, content, world, named("烈風腿"), base.id, "huo")
    assert child.special is None and child.traits == ["剛", "快", "實"]
    ready.player.arts.append("lake_kick")
    twin, _ = fusion.blend(ready, content, world, named("踏浪拳"), base.id, "lake_kick")
    assert twin.special is None


def test_the_same_recipe_in_the_same_season_always_rolls_the_same_special(content, world):
    """擲的是配方加這一季的天機：再合一次（別人、或重來）同一個配方同一個結果。"""
    content.config.special_trait_chance = 0.5
    tianji = world.read().tianji
    keys = [fusion.fuse_key("basic_fist", insight) for insight in ("feng", "huo", "shui", "shan", "haoran", "xuesha")]
    first = [traits.roll_special(content, key, tianji) for key in keys]
    assert first == [traits.roll_special(content, key, tianji) for key in keys]


def test_landing_keeps_the_known_arts_traits(ready, content, world):
    """Review Focus 5：合到舊的那一門維持原本的功效與特別功效，不重算、不重擲。"""
    content.config.special_trait_chance = 1.0  # 乙合的那一門帶特別功效
    other = other_player(content)
    made, _ = fusion.fuse(other, content, world, named("旋風腿"), "basic_fist", "feng")
    assert made.special is not None
    landing_on(content)
    content.config.special_trait_chance = 0.0  # 重擲的話這一次就會變成沒有
    ready.player.arts = ["lake_kick"]  # 重算功效的話是【快、快】
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "lake_kick", "feng")
    assert art.id == made.id and art.traits == made.traits == ["快", "實"] and art.special == made.special
    assert not any("江湖上傳開了" in m for m in msgs)  # 不是第一次合出來


def test_a_recipe_hit_does_not_recompute_the_traits(ready, content, world):
    content.config.special_trait_chance = 1.0
    made, _ = fusion.fuse(other_player(content), content, world, named("旋風腿"), "basic_fist", "feng")
    content.config.special_trait_chance = 0.0
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), "basic_fist", "feng")
    assert art.id == made.id and art.special == made.special and art.traits == made.traits
    assert not any("江湖上傳開了" in m for m in msgs)


def test_the_naming_prompt_shows_the_traits(ready, content, world):
    client = named("旋風腿")
    fusion.fuse(ready, content, world, client, "basic_fist", "feng")
    asked = client.chat_structured.call_args.args[0][-1]["content"]
    assert "先手" in asked and "厚" in asked
    assert asked.index("先手") < asked.index(naming.FORMAT_RULES)  # 提示寫在格式規則前面


def test_the_blend_naming_prompt_shows_the_traits_and_the_special(ready, content, world):
    content.config.special_trait_chance = 1.0
    ready.player.arts = ["lake_kick"]
    client = named("踏浪拳")
    art, _ = fusion.blend(ready, content, world, client, "basic_fist", "lake_kick")
    asked = client.chat_structured.call_args.args[0][-1]["content"]
    assert "厚" in asked and "先手" in asked and traits.special(content, art.special).name in asked


def test_the_naming_slip_is_exactly_the_prompt_the_fuse_sends(ready, content, world):
    """A 段開的單子、B 段送出去的、C 段（沒給 proposed 時）自己送的是同一份提示：同一個配方、同一季的天機，
    功效與特別功效算出來一樣（取名提示寫著功效，兩段對不上就會替另一門武學取名）。"""
    content.config.special_trait_chance = 0.5
    ready.player.insights = ["feng", "huo", "shui", "shan"]
    for insight, name in (("feng", "旋風腿"), ("huo", "烈火掌"), ("shui", "流水拳"), ("shan", "鎮山拳")):
        request = fusion.forge_request(ready, content, world, "basic_fist", [insight])
        client = named(name)
        fusion.fuse(ready, content, world, client, "basic_fist", insight)
        assert request.messages == client.chat_structured.call_args.args[0], insight


def test_the_blend_naming_slip_is_exactly_the_prompt_the_blend_sends(ready, content, world):
    content.config.special_trait_chance = 1.0
    ready.player.arts = ["lake_kick"]
    request = fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick")
    client = named("踏浪拳")
    fusion.blend(ready, content, world, client, "basic_fist", "lake_kick")
    assert request.messages == client.chat_structured.call_args.args[0]


def test_the_first_art_with_a_special_is_a_rumor_in_the_world(ready, content, world):
    """設計 13.4：第一次合出帶特別功效的武學，江湖上傳一句（不寫配方）；之後照著合的人不再傳。"""
    content.config.special_trait_chance = 1.0
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    special = traits.special(content, art.special)
    line = f"江湖上傳開了：沈浪合出一門帶〔{special.name}〕的【旋風腿】。"
    assert line in msgs
    (rumor,) = ready.world.rumors
    assert rumor.text == line and rumor.layer == "world" and rumor.named is True
    assert rumor.location is None  # 天下大事不釘在鑄功法的人此刻的位置（不然輿圖的 ✦ 會把他的行蹤送給每個陣營）
    assert "basic_fist" not in line and "feng" not in line  # 不寫配方
    again, again_msgs = fusion.fuse(other_player(content), content, world, must_not_ask(), "basic_fist", "feng")
    assert again.id == art.id and not any("江湖上傳開了" in m for m in again_msgs)


def test_the_special_rumor_names_the_maker_even_when_walking_anonymously(ready, content, world):
    content.config.special_trait_chance = 1.0
    ready.player.anonymous = True
    ready.player.arts = ["lake_kick"]
    art, msgs = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    special = traits.special(content, art.special)
    line = f"江湖上傳開了：沈浪合出一門帶〔{special.name}〕的【踏浪拳】。"
    assert line in msgs and "某位少俠" not in line
    (rumor,) = ready.world.rumors
    # 世界層的傳聞一律具名、寫真正的名號（只有地方傳聞才有不具名）；匿名行走的人也一樣
    assert rumor.text == line and rumor.named is True and rumor.layer == "world"
    assert art.creator_shown == "沈浪"  # 首創一律寫名號（傳聞分層第七節）：功法自己記的名號也不再照匿名改


def test_a_special_rumor_survives_the_engine_save(game):
    """F3：Game.forge 做成了就把共用賽季存回去——傳聞放在 state.world.rumors，不存的話下一次 sync 就被資料庫的賽季蓋掉。"""
    game.content.config.special_trait_chance = 1.0
    p = game.state.player
    p.member.wugong_id, p.insights, p.stats["xinde"] = "basic_fist", ["feng"], 100
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", ["feng"])
    (new,) = p.arts
    art = game.world.get_skill(new)
    special = traits.special(game.content, art.special)
    stored = [r.text for r in game.world.get_season().rumors]
    assert f"江湖上傳開了：沈浪合出一門帶〔{special.name}〕的【{art.name}】。" in stored


def test_a_rejected_forge_saves_no_rumor(game):
    game.content.config.special_trait_chance = 1.0
    game.state.player.insights = ["feng"]
    game.forge("basic_fist", ["feng"])  # 手上沒有那門武學：被拒絕
    assert not any("江湖上傳開了" in r.text for r in game.world.get_season().rumors)


# ── 師門配方（新手引導計畫一 Task 5）─────────────────────────

def a_newcomer(content, name="沈浪"):
    state = new_game_state(content, name)
    state.player.insights = ["feng"]
    return state


def test_preset_for_matches_the_base_and_the_insight_both(prologue_content):
    assert fusion.preset_for(prologue_content, "basic_fist", "feng").name == "穿林腿"
    assert fusion.preset_for(prologue_content, "basic_fist", "huo").name == "烈爐拳"
    assert fusion.preset_for(prologue_content, "basic_breath", "feng") is None  # 別的底
    assert fusion.preset_for(prologue_content, "basic_fist", "haoran") is None  # 別的意境


def test_preset_recipe_needs_no_model(prologue_content, world, monkeypatch):
    from tianxia.engine import Game
    from tianxia.ollama_client import OllamaClient

    def asked(self, *args, **kwargs):
        raise AskedTheModel("師門配方的名字寫好了，不該叫模型")

    monkeypatch.setattr(OllamaClient, "chat_structured", asked)
    game = Game.new(prologue_content, "沈浪", world=world)
    game.state.player.insights = ["feng"]
    assert game.forge_request("basic_fist", ["feng"]) is None  # 不開模型的單子
    msgs = game.forge("basic_fist", ["feng"])  # 沒給 proposed：照舊會在鎖內叫模型，這裡不會
    art = world.lookup_recipe(fusion.fuse_key("basic_fist", "feng"))
    assert art.name == "穿林腿" and art.note == "腿隨風走。" and art.attribute == "快" and art.origin == "fused"
    assert "師門傳下來的路數" in "\n".join(msgs)
    assert art.id in game.state.player.arts  # 武學欄有基本功，新得的收進功法庫


def test_preset_recipe_is_back_next_season(prologue_content, world):
    from conftest import next_season
    from tianxia.engine import Game

    game = Game.new(prologue_content, "沈浪", world=world)
    game.state.player.insights = ["feng"]
    game.forge("basic_fist", ["feng"], proposed=(None, ""))
    next_season(prologue_content, world, game)  # 配方每季清空（武學與成長 3.10）
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None
    game.state.player.insights = ["feng"]
    game.forge("basic_fist", ["feng"], proposed=(None, ""))
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")).name == "穿林腿"


def test_every_newcomer_gets_the_same_preset_art_and_the_master_line(prologue_content, world):
    first, msgs = fusion.fuse(a_newcomer(prologue_content), prologue_content, world, must_not_ask(), "basic_fist", "feng")
    second, again = fusion.fuse(a_newcomer(prologue_content, "乙"), prologue_content, world, must_not_ask(), "basic_fist", "feng")
    assert second.id == first.id and second.base_power == first.base_power
    for lines in (msgs, again):  # 後到的人也是師門傳下來的路數，不寫成「由先到的那個新人首創」
        assert "師門傳下來的路數" in "\n".join(lines) and "首創" not in "\n".join(lines)


def test_a_preset_art_has_the_inherited_traits_but_no_special_and_no_rumor(prologue_content, world):
    """配方的特別功效照這一季的天機擲：師門配方不帶（不在隱蔽的草廬裡傳出「江湖上傳開了」）；一般功效照來路。"""
    prologue_content.config.special_trait_chance = 1.0
    state = a_newcomer(prologue_content)
    base = team.player_art(state, prologue_content, world, "basic_fist")
    art, _ = fusion.fuse(state, prologue_content, world, must_not_ask(), "basic_fist", "feng")
    assert art.special is None
    assert art.traits == traits.inherit_fuse(base, art.attribute)
    assert not any("江湖上傳開了" in rumor.text for rumor in state.world.rumors)


def test_preset_recipe_never_lands_on_an_old_art(prologue_content, world):
    """合到舊的（計畫五）：師門配方不擲它，不然一個新人會拿到陌生人合出來的武學（師門傳下來的是同一門）。"""
    from tianxia.engine import Game
    from tianxia.martial_arts import generate_from_name

    prologue_content.config.land_chance_per_candidate = 1.0
    prologue_content.config.land_chance_cap = 1.0  # 有候選就一定合到舊的
    for name in ("風行拳", "追電拳"):  # 兩門別人合出來的 快・武學・無：長新的就不會是它們
        old = generate_from_name(name, "武學", name).model_copy(update={"origin": "fused", "attribute": "快", "lean": "無"})
        world.claim_recipe(f"融|{name}", old)
    game = Game.new(prologue_content, "沈浪", world=world)
    game.state.player.insights = ["feng"]
    assert game.forge_request("basic_fist", ["feng"]) is None  # 要是擲了合到舊的，這裡是「兩個候選挑一個」的單子
    game.forge("basic_fist", ["feng"], proposed=(None, ""))
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")).name == "穿林腿"
    assert prologue_content.config.land_chance_per_candidate == 1.0  # 其他配方照樣會合到舊的
    other, _ = fusion.fuse(a_newcomer(prologue_content, "乙"), prologue_content, world, named("不重要"), "basic_fist", "feng")
    assert other.name == "穿林腿"


def test_a_recipe_that_lands_on_a_preset_art_names_the_master_not_a_stranger(prologue_content, world):
    """T6 review M9：老手的另一個配方合到了一門師門功夫上：沒有首創者可寫，不能寫「由不知名的前人首創」，寫師門傳下來的。
    合併進去的句子（武學＋意境與武學＋武學）都一樣。"""
    preset, _ = fusion.fuse(a_newcomer(prologue_content), prologue_content, world, must_not_ask(), "basic_fist", "feng")
    assert preset.preset
    prologue_content.config.land_chance_per_candidate = prologue_content.config.land_chance_cap = 1.0
    veteran = new_game_state(prologue_content, "老手")
    veteran.player.arts, veteran.player.insights, veteran.player.stats["xinde"] = ["lake_kick"], ["feng"], 100
    art, msgs = fusion.fuse(veteran, prologue_content, world, must_not_ask(), "lake_kick", "feng")  # 同是快・武學・無：只有師門那一個候選
    assert art.id == preset.id
    assert "合出來的竟是一門已有的武學【穿林腿】" in msgs[0]
    assert "師門傳下來" in msgs[0] and "不知名" not in msgs[0] and "首創" not in msgs[0]


def test_a_taken_preset_name_falls_back_instead_of_failing(prologue_content, world):
    """名字被別的配方先登記走了：師門配方照舊登記，改走退路字表的名字（不卡住新人）。"""
    from tianxia.martial_arts import generate_from_name

    taken = generate_from_name("穿林腿", "武學", "穿林腿").model_copy(update={"origin": "fused", "attribute": "剛"})
    assert world.claim_recipe("融|別人的", taken)[0] is not None
    art, _ = fusion.fuse(a_newcomer(prologue_content), prologue_content, world, must_not_ask(), "basic_fist", "feng")
    assert art is not None and art.name != "穿林腿"
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")).id == art.id


def test_a_preset_name_that_is_a_characters_name_falls_back(prologue_content, world):
    """FB-069：玩家的名號不能跟武學撞。有人把角色取名叫穿林腿，師門配方這一季改走退路字表的名字（說明不帶），不卡住新人。"""
    from tianxia.characters import open_characters

    open_characters().save(new_game_state(prologue_content, "穿林腿"))
    assert world.is_character_name("穿林腿")
    art, msgs = fusion.fuse(a_newcomer(prologue_content, "新人乙"), prologue_content, world, must_not_ask(), "basic_fist", "feng")
    assert art is not None and art.preset and art.name != "穿林腿" and art.note == ""
    assert not world.is_character_name(art.name)


def test_models_and_players_cannot_take_a_preset_name(prologue_content):
    assert naming.name_problem("穿林腿", prologue_content) == naming.PRESET_CLASH
    assert naming.name_problem("追風腿", prologue_content) is None
    assert naming.recheck(prologue_content, ("穿林腿", "說明"))[0] is None  # 模型取了師門的名字：當作取壞了


# ── 師門的功夫不屬於哪個新人（review-t4-5 I1）─────────────────

def test_a_preset_art_credits_the_master_not_the_newcomer(prologue_content, world):
    """師門配方是寫好的、傳下來的：第一個合出來的新人不是它的首創者，功法卡、後到的人那一句、本季的首創名單都不寫他。"""
    from tianxia.martial_arts import shown_creator

    art, msgs = fusion.fuse(a_newcomer(prologue_content, "新人甲"), prologue_content, world, must_not_ask(), "basic_fist", "feng")
    assert art.preset and art.creator is None and shown_creator(art) is None
    assert "新人甲" not in "\n".join(msgs)
    card = skillview.art_card(art, 1)
    assert "來源：師門傳下來的功夫" in card and "新人甲" not in card and "首創" not in card
    assert world.get_skill(art.id).preset  # 登記在全服的那一份也標著
    later, _ = fusion.fuse(a_newcomer(prologue_content, "新人乙"), prologue_content, world, must_not_ask(), "basic_fist", "feng")
    assert later.id == art.id and "新人" not in skillview.art_card(later, 1)


def test_presets_stay_out_of_the_seasons_firsts_and_the_chronicle(prologue_content, world):
    """換季寫進江湖史的「合成首創」只列真的有人首創的：師門的功夫不列、也不算進「N 門」（江湖史跨季永遠留著）。"""
    from conftest import next_season
    from tianxia.engine import Game

    game = Game.new(prologue_content, "新人甲", world=world)
    game.state.player.insights = ["feng", "huo"]
    game.forge("basic_fist", ["feng"])  # 師門配方：穿林腿
    game.forge("basic_breath", ["huo"], proposed=("燎原功", "一句說明。"))  # 真的首創
    next_season(prologue_content, world, game)
    texts = [r.text for _, rumors in world.chronicle_before(2) for r in rumors]
    firsts = [t for t in texts if "合成首創" in t]
    assert len(firsts) == 1 and "1 門" in firsts[0] and "燎原功" in firsts[0] and "穿林腿" not in firsts[0]
    assert not any("穿林腿" in t for t in texts)


def test_a_season_of_only_presets_writes_no_firsts_line(prologue_content, world):
    from conftest import next_season
    from tianxia.engine import Game

    game = Game.new(prologue_content, "新人甲", world=world)
    game.state.player.insights = ["feng"]
    game.forge("basic_fist", ["feng"])
    next_season(prologue_content, world, game)
    assert not any("合成首創" in r.text for _, rumors in world.chronicle_before(2) for r in rumors)


# ── 血統裡融過的意境不能再融（企劃者 2026-10-06：「同一種意境合成後的產物無限合成上去」）────────


def test_a_fused_art_cannot_take_the_same_insight_again(ready, content, world):
    """武學＋風 → 乙；乙＋風 就被擋下（意境不會用掉，不擋就能一代一代往上疊）。"""
    b, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    problem = fusion.fuse_problem(ready, content, world, b.id, "feng")
    assert problem is not None and "早已融過「風」" in problem and "【旋風腿】" in problem
    art, msgs = fusion.fuse(ready, content, world, must_not_ask(), b.id, "feng")
    assert art is None and msgs == [problem]


def test_taking_turns_between_two_insights_is_still_blocked(ready, content, world):
    """A＋風 → 乙、乙＋火 → 丙、丙＋風：風在丙的血統裡（乙那一代融的），照樣擋；丙＋火也擋。"""
    b, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    c, _ = fusion.fuse(ready, content, world, named("烈風腿"), b.id, "huo")
    assert c is not None
    assert "早已融過「風」" in fusion.fuse_problem(ready, content, world, c.id, "feng")
    assert "早已融過「火」" in fusion.fuse_problem(ready, content, world, c.id, "huo")
    ready.player.insights.append("shui")
    assert fusion.fuse_problem(ready, content, world, c.id, "shui") is None  # 沒融過的意境照樣能融


def test_a_blend_carries_both_parents_lineage(ready, content, world):
    """武學＋武學合出來的那一門，兩門來源融過的意境都算在它的血統裡。"""
    ready.player.arts = ["lake_kick"]
    b, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    blended, _ = fusion.blend(ready, content, world, named("湖風拳"), b.id, "lake_kick")
    assert fusion.lineage_has(blended.id, insights.resolve("feng", content, world), content, world)
    assert not fusion.lineage_has(blended.id, insights.resolve("huo", content, world), content, world)


def test_a_private_insight_is_matched_by_its_attribute(ready, content, world):
    """私有意境（悟意境 0.2b）的 id 不進全服登記：融過一個私有的快意境，同一條血統就不能再融任何私有的快意境；
    全服的「風」（也屬快）是另一個意境，照 id 認，不受影響。"""
    for n, name in ((1, "湖中影"), (2, "掠水痕")):
        ready.player.own_insights[f"悟:{n}"] = Insight(id=f"悟:{n}", name=name, attribute="快")
        ready.player.insights.append(f"悟:{n}")
    b, _ = fusion.fuse(ready, content, world, named("影腿"), "basic_fist", "悟:1")
    assert b.insight is None and b.insight_attr == "快"
    assert "早已融過「掠水痕」" in fusion.fuse_problem(ready, content, world, b.id, "悟:2")
    assert fusion.fuse_problem(ready, content, world, b.id, "feng") is None


def test_the_scroll_card_skips_an_insight_already_in_the_lineage(ready, content, world):
    b, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.insights = ["feng"]
    row = next(r for r in skillview.art_rows(ready, content, world) if r["id"] == b.id)
    assert "forge_odds" not in row
