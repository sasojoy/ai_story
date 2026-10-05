from unittest import mock

import pytest

from tianxia import fusion, library, naming, team
from tianxia.martial_arts import generate_from_name, power_at
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


def test_an_anonymous_first_fuser_is_stored_by_name_but_shown_as_a_nameless_hero(ready, content, world):
    """匿名行走（最終審查 Important 2）：首創者的名號是身分（存著照舊），寫給別人看的地方——後到的人那一句、
    功法卡（skillview）、換季的江湖史——用登記當下的匿名規矩寫「某位少俠」（rules.display_name）。"""
    ready.player.anonymous = True
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    stored = world.get_skill(art.id)
    assert (stored.creator, stored.creator_shown) == ("沈浪", "某位少俠")
    _, msgs = fusion.fuse(other_player(content), content, world, must_not_ask(), "basic_fist", "feng")
    assert "這一門由某位少俠首創" in msgs[0] and "沈浪" not in msgs[0]


def test_a_named_first_fuser_is_shown_by_name(ready, content, world):
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert world.get_skill(art.id).creator_shown == "沈浪"
    _, msgs = fusion.fuse(other_player(content), content, world, must_not_ask(), "basic_fist", "feng")
    assert "這一門由沈浪首創" in msgs[0]


def test_an_anonymous_first_merger_is_shown_as_a_nameless_hero(ready, content, world):
    ready.player.anonymous = True
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert (first.creator, first.creator_shown) == ("沈浪", "某位少俠")
    _, msgs = fusion.merge(other_player(content, ("feng", "huo")), content, world, must_not_ask(), "feng", "huo")
    assert "這個意境由某位少俠首悟" in msgs[0] and "沈浪" not in msgs[0]


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
    assert row["melt"] == {"ok": True, "note": "退回心得 4"}
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
    assert fuse.messages == fusion._fuse_messages(team.player_art(ready, content, world, "basic_fist"),
                                                  fusion.insights.resolve("feng", content, world))
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
    game.client = None  # 伺服器假人（bot_runner 把 client 設成 None）：不叫模型，C 段走退路字表
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


def test_a_fuse_costs_no_stamina(ready, content, world):
    ready.player.stamina = 0
    art, msgs = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    assert art is not None and ready.player.stamina == 0
    assert not any("體力" in m for m in msgs)


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


def test_the_engine_fuse_journal_entry_has_no_stamina_line(game):
    p = game.state.player
    p.member.wugong_id, p.insights, p.stats["xinde"] = "basic_fist", ["feng"], 100
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", ["feng"])
    entry = game.state.journal[0]
    assert "心得 -5" in entry.changes and not any("體力" in c for c in entry.changes)


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
