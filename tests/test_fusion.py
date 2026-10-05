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
    """金錢迴圈關上了：絕學的底，合一爐（花心得）、立刻熔掉剛合出來的複本，每一輪心得只減不增。"""
    ready.player.art_quality["basic_fist"] = "絕學"
    ready.player.insights = ["feng", "huo", "shui"]
    price = content.config.fuse_xinde
    xinde = ready.player.stats["xinde"]
    for name, insight in [("旋風腿", "feng"), ("烈火拳", "huo"), ("驚濤掌", "shui")]:
        art, _ = fusion.fuse(ready, content, world, named(name), "basic_fist", insight)
        assert ready.player.stats["xinde"] == xinde - price
        library.melt_art(ready, content, world, art.id)
        assert ready.player.stats["xinde"] == xinde - price  # 熔掉一毛不退（下品、第一成）
        xinde -= price
    assert ready.player.stats["xinde"] == 100 - 3 * price


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


def test_the_engine_fuse_then_melt_loop_on_a_peerless_base_only_ever_costs_xinde(game):
    """Task 13 的整季機器人踩到的洞（企劃者 2026-10-05 關掉）：走真的 Game.forge／Game.melt_art，
    絕學的底每一輪「合成、熔掉複本」心得 100 → 95 → 90 → 85，不再 100 → 135 → 170。"""
    p = game.state.player
    p.member.wugong_id, p.art_quality["basic_fist"] = "basic_fist", "絕學"
    p.insights, p.stats["xinde"] = ["feng", "huo", "shui"], 100
    price = game.content.config.fuse_xinde
    seen = [p.stats["xinde"]]
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        for insight in ("feng", "huo", "shui"):
            game.forge("basic_fist", [insight])
            (new,) = p.arts
            game.melt_art(new)
            seen.append(p.stats["xinde"])
    assert p.arts == [] and seen == [100 - price * n for n in range(4)]


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


# ── 合併要花體力（企劃者 2026-10-05：「意境合併要花體力，這樣的話她要拿心得就給他拿」）──────────
# 合併→熔掉→再合併，每一圈淨賺 5 點心得（merge_xinde 5、melt_insight_xinde 10）；企劃者的裁示不是擋重合、也不是
# 動熔的價，而是讓合併花體力：要賺就照著賺，只是每一圈都要花一次修練那麼多的體力。合成（武學＋意境）維持不花體力。


def test_merge_stamina_is_one_cultivation_by_default(content):
    assert content.config.merge_stamina == content.config.cultivate_stamina == 10


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
    assert "心得 -5" in entry.changes and "體力 -10" in entry.changes
    assert p.stamina == before - 10 and "體力 -10" in msgs


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
