from unittest import mock

import pytest

from tianxia import fusion, naming
from tianxia.martial_arts import generate_from_name
from tianxia.state import new_game_state


def named(name, description="一句話說明。"):
    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name=name, description=description)
    return client


def model_down():
    client = mock.Mock()
    client.chat_structured.side_effect = RuntimeError("連不上")
    return client


def must_not_ask():
    client = mock.Mock()
    client.chat_structured.side_effect = AssertionError("配方已經有了，不該再叫模型")
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


def test_the_new_art_takes_the_players_quality_of_the_base(ready, content, world):
    fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ready.player.art_quality["旋風腿"] = "中品"
    art, _ = fusion.fuse(ready, content, world, named("烈風腿"), "旋風腿", "huo")
    assert ready.player.art_quality[art.id] == "中品"
    assert world.get_skill(art.id).quality == "下品"  # 全服那一筆是中性的


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
