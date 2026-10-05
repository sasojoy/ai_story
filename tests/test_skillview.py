from tianxia import rules, skillview
from tianxia.martial_arts import MartialArt, generate_from_name, historical_art, power_at


def test_rules_line():
    assert skillview.rules_line(None) == (
        "身上一門內功、一門武學：花心得練成，用意境修練衝品質；武學也能在「煉製」融意境衍生新武學。"
    )


def test_member_card_before_learning_anything(state, content, world):
    card = skillview.member_card(state, content, world, "player")
    assert card == (
        "### 沈浪\n第 1 級　氣血 320/320\n內功　（尚未習得）\n武學　（尚未習得）"
    )


def test_member_card_after_learning_a_historical_skill(state, content, world):
    rules.learn_skill(state, content, "fist")
    card = skillview.member_card(state, content, world, "player")
    assert "武學　長拳（絕學・屬剛）第1成" in card


def test_member_card_for_a_companion_reads_the_shared_world_state(state, content, world):
    world.update_companion("mate", lambda p: setattr(p, "level", 3))
    card = skillview.member_card(state, content, world, "mate")
    assert card.startswith("### 韓鐵\n第 3 級")


def test_library_is_empty_until_something_is_learned(state, content, world):
    assert skillview.library(state, content, world) == []
    rules.learn_skill(state, content, "fist")
    assert skillview.library(state, content, world) == [
        ("武學　長拳（絕學・屬剛）第1成 ●○○○○○○○○○", "武學"),  # 熟練度十格條，見 skillview.level_bar
    ]
    rules.learn_skill(state, content, "breath")
    assert ("內功　吐納法（絕學・屬陰）第1成 ●○○○○○○○○○", "內功") in skillview.library(state, content, world)


def test_detail_before_learning_says_so(state, content, world):
    assert skillview.detail(state, content, world, "武學") == "你還沒有武學。"
    assert skillview.detail(state, content, world, "內功") == "你還沒有內功。"


def test_detail_of_a_historical_skill(state, content, world):
    rules.learn_skill(state, content, "fist")
    text = skillview.detail(state, content, world, "武學")
    # FB-006：detail 改用功法卡，多了十格條、第一成／第十成兩個數字；本命武學沒有說明句，那一行整行省略
    assert text == (
        "【長拳】絕學・屬剛\n"
        "第1成 ●○○○○○○○○○，威力 50.0（下一成：57.8）\n"
        "第一成 50.0　第十成 120.0\n"
        "來源：本命武學"
    )


def test_detail_at_the_tenth_level_has_no_next_tier(state, content, world):
    rules.learn_skill(state, content, "fist")
    state.player.member.wugong_level = 10
    text = skillview.detail(state, content, world, "武學")
    assert "已達第十成" in text and "威力 120.0" in text


def test_detail_of_an_old_self_created_skill_says_so(state, content, world):
    """自創已經作廢，但以前登記在世界裡的自創功法還在（資料庫沒清）：功法說明照舊寫「來源：自創」。"""
    art = generate_from_name("龍吟九霄", "武學", "龍吟九霄", world.read().tianji)
    assert world.claim_skill_name(art)
    state.player.member.wugong_id = art.id
    text = skillview.detail(state, content, world, "武學")
    assert text.startswith("【龍吟九霄】") and "來源：自創" in text


def test_detail_of_a_missing_skill_reference_is_a_placeholder(state, content, world):
    state.player.member.wugong_id = "ghost"
    assert skillview.detail(state, content, world, "武學") == "（找不到武學資料：ghost）"


# ── 功法卡（FB-006：看得到威力與模型寫的那句說明）──────────────


def _crafted(note: str) -> MartialArt:
    """一門煉出來的功法：origin 是 crafted、creator 是第一個煉出這個配方的人（FB-017）。"""
    return MartialArt(
        id="沉柳纏勁", name="沉柳纏勁", kind="武學", quality="上品", attribute="柔",
        base_power=28.0, top_power=72.0, origin="crafted", creator="沈浪", note=note,
    )


def test_an_art_card_ends_with_the_models_note():
    card = skillview.art_card(_crafted("以柔勁纏住兵刃，借力卸力。"), 3)
    lines = card.split("\n")
    assert lines[0] == "【沉柳纏勁】上品・屬柔"
    assert lines[1].startswith("第3成 ●●●○○○○○○○，威力 ")
    assert lines[3] == "來源：煉製（沈浪 首創）"
    assert lines[-1] == "以柔勁纏住兵刃，借力卸力。"


def test_an_art_card_says_where_the_art_came_from():
    """FB-017：煉出來的寫「煉製（首創者 首創）」，取名自創的寫「自創（取名者 所創）」，其他是本命武學。"""
    def source(art: MartialArt) -> str:
        return skillview.art_card(art, 1).split("\n")[3]

    crafted = _crafted("")
    assert source(crafted) == "來源：煉製（沈浪 首創）"
    assert source(crafted.model_copy(update={"creator": None})) == "來源：煉製"
    assert source(crafted.model_copy(update={"origin": "created"})) == "來源：自創（沈浪 所創）"
    assert source(historical_art("龍吟九霄", "龍吟九霄", "武學", "剛")) == "來源：本命武學"


def test_an_art_card_without_a_note_drops_the_whole_line():
    """退路字表取名的功法沒有說明句：不留空行、不出現 None，整行省略（FB-006 驗收）。"""
    with_note = skillview.art_card(_crafted("以柔勁纏住兵刃，借力卸力。"), 3)
    for blank in ("", "   "):
        card = skillview.art_card(_crafted(blank), 3)
        assert "None" not in card
        assert all(line.strip() for line in card.split("\n"))
        assert not card.endswith("\n")
        assert len(card.split("\n")) == len(with_note.split("\n")) - 1


def test_an_art_card_shows_the_first_and_tenth_level_power():
    art = _crafted("")
    card = skillview.art_card(art, 3)
    assert f"第一成 {power_at(art, 1):.1f}　第十成 {power_at(art, 10):.1f}" in card.split("\n")
    assert f"威力 {power_at(art, 3):.1f}（下一成：{power_at(art, 4):.1f}）" in card
    assert "（下一成：已達第十成）" in skillview.art_card(art, 10)


# ── 練功提示（練成花心得：心得的去處是練成與合成）──────────────


def test_practice_hint_is_quiet_below_the_threshold(state, content):
    state.player.member.wugong_id = "basic_fist"
    state.player.stats["xinde"] = content.config.xinde_hint_threshold - 1
    assert skillview.practice_hint(state, content) is None


def test_practice_hint_lists_the_slots_it_can_afford(state, content):
    state.player.member.wugong_id = "basic_fist"
    state.player.member.neigong_id = "basic_breath"
    state.player.member.neigong_level = 10
    state.player.stats["xinde"] = 60
    hint = skillview.practice_hint(state, content)
    assert "練成武學" in hint and "內功" not in hint


def test_practice_hint_names_both_slots_when_both_can_be_practised(state, content):
    state.player.member.wugong_id = "basic_fist"
    state.player.member.neigong_id = "basic_breath"
    state.player.stats["xinde"] = content.config.xinde_hint_threshold
    hint = skillview.practice_hint(state, content)
    assert "練成內功、武學" in hint and str(content.config.xinde_hint_threshold) in hint


def test_practice_hint_skips_a_slot_whose_next_level_it_cannot_pay(state, content):
    """價錢是下一成的價錢：付不起的那一門不列，不然玩家照著提示去按只會挨一句「心得不足」。"""
    content.config.practice_xinde_per_level = 10
    state.player.member.wugong_id, state.player.member.wugong_level = "basic_fist", 2  # 要 20 點
    state.player.member.neigong_id, state.player.member.neigong_level = "basic_breath", 9  # 要 90 點
    state.player.stats["xinde"] = 60
    hint = skillview.practice_hint(state, content)
    assert "練成武學" in hint and "內功" not in hint


def test_practice_hint_points_at_the_furnace_when_holding_an_insight(state, content):
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 60
    assert "煉製" in skillview.practice_hint(state, content)


def test_practice_hint_only_mentions_the_furnace_when_a_forge_is_possible_and_affordable(state, content):
    """Task 5 審查留下的：光是手上有意境不算，要持有沒滿、付得起一次合成或合併才提煉製。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.member.wugong_level = 10  # 練成那一半不會出聲，只看煉製那一半
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 60
    assert "煉製" in skillview.practice_hint(state, content)
    content.config.fuse_xinde = content.config.merge_xinde = 999  # 付不起
    assert skillview.practice_hint(state, content) is None
    content.config.fuse_xinde = content.config.merge_xinde = 5
    content.config.holding_cap_base = 2  # 持有滿了（一門武學加一個意境）
    assert skillview.practice_hint(state, content) is None


def test_practice_hint_needs_an_art_to_fuse_but_not_to_merge(state, content):
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 60
    content.config.fuse_xinde, content.config.merge_xinde = 5, 999
    assert skillview.practice_hint(state, content) is None  # 沒有武學：合成不了，合併付不起
    state.player.member.wugong_id, state.player.member.wugong_level = "basic_fist", 10
    assert "煉製" in skillview.practice_hint(state, content)  # 有了武學，合成付得起
    content.config.fuse_xinde, content.config.merge_xinde = 999, 5
    assert "煉製" in skillview.practice_hint(state, content)  # 合併付得起（自己跟自己也能合）


def test_practice_hint_calls_the_pages_by_their_tab_names(state, content):
    """FB-047：門下頁拆成「修練」「煉製」兩個分頁之後，提示照分頁的名字寫，不再寫「門下」。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.stats["xinde"] = 60
    assert skillview.practice_hint(state, content) == "💡 你已攢下 60 點心得。去「修練」練成武學。"
    state.player.insights = ["feng"]
    assert skillview.practice_hint(state, content) == (
        "💡 你已攢下 60 點心得。去「修練」練成武學，或去「煉製」拿意境合成新武學。"
    )


def test_practice_hint_never_sends_you_to_the_furnace_with_materials(state, content):
    """審查裁示（企劃者的用語）：任何提示都不能叫玩家拿素材去煉製。"""
    from tianxia import materials

    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng"]
    materials.grant(state, content, "gang_1", 2)
    state.player.stats["xinde"] = 500
    hint = skillview.practice_hint(state, content)
    assert "煉製" in hint and "素材" not in hint


def test_practice_hint_is_quiet_when_there_is_nothing_to_do(state, content):
    state.player.stats["xinde"] = 60
    assert skillview.practice_hint(state, content) is None


def test_practice_hint_stays_quiet_while_the_season_rests(state, content):
    """FB-047：休季時什麼都不能做，提示不出現。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 500
    state.world.ended = True
    assert skillview.practice_hint(state, content) is None


def test_practice_hint_goes_away_once_everything_is_at_the_tenth_level(state, content, world):
    state.player.stats["xinde"] = 9999
    state.player.member.wugong_id, state.player.member.neigong_id = "fist", "breath"
    state.player.member.wugong_level = state.player.member.neigong_level = 10
    assert skillview.practice_hint(state, content) is None


# ── 背包（素材不再拿去煉製，企劃者的用語：任何文字都不能叫玩家拿素材去爐裡）──────────────


def test_bag_text_when_empty_says_where_things_come_from(state, content):
    """探索改悟意境之後不再撿素材（武學與成長計畫一 Task 7）：提示不能再叫玩家去探索找素材；
    素材也不再煉製（Task 8），標題與說明都不能提煉製、爐。"""
    text = skillview.bag_text(state, content)
    assert text.startswith("**背包**")
    assert "打贏對手" in text and "探索" not in text and "煉" not in text and "爐" not in text


def test_bag_text_never_mentions_the_furnace(state, content):
    state.player.materials = {"gang_1": 1}
    text = skillview.bag_text(state, content)
    assert text.startswith("**背包**") and "煉" not in text and "爐" not in text


def test_bag_text_lists_what_you_hold_high_tier_first(state, content):
    state.player.materials = {"gang_1": 2, "gang_3": 1}
    lines = skillview.bag_text(state, content).splitlines()
    assert lines[1].startswith("- 隕鐵膽 ×1　天品・屬剛")
    assert lines[2].startswith("- 精鐵砂 ×2　凡品・屬剛")


# ── 煉製那一塊的說明與功法庫 ────────────────────────────────


def test_forge_line_asks_for_an_art_and_an_insight_first(state, content, world):
    line = skillview.forge_line(state, content, world, None, [])
    assert "放一門武學和一個意境" in line and "放兩個意境" in line and "素材" not in line
    assert "武學與意境 0/50" in line


def test_forge_line_shows_a_fuse(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 100
    line = skillview.forge_line(state, content, world, "basic_fist", ["feng"])
    assert "**合成**" in line and "【粗淺拳腳】＋「風」→ 一門新武學" in line and "屬快" in line
    assert "品質跟【粗淺拳腳】一樣是下品" in line and "花 5 點心得（你有 100 點）" in line and "⚠" not in line


def test_forge_line_shows_a_merge(state, content, world):
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    line = skillview.forge_line(state, content, world, None, ["feng", "huo"])
    assert "**合併**" in line and "「風」＋「火」→ 一個新的意境" in line and "花 5 點心得" in line and "⚠" not in line


def test_forge_line_explains_why_it_cannot_be_done(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 0
    assert "⚠ 心得不足" in skillview.forge_line(state, content, world, "basic_fist", ["feng"])
    assert "⚠ 心得不足" in skillview.forge_line(state, content, world, None, ["feng", "feng"])
    assert "⚠ 你還沒悟到" in skillview.forge_line(state, content, world, "basic_fist", ["huo"])


def test_forge_line_survives_something_that_does_not_exist(state, content, world):
    assert "不存在" in skillview.forge_line(state, content, world, "ghost", ["feng"])
    assert "不存在" in skillview.forge_line(state, content, world, None, ["feng", "ghost"])


def test_forge_line_never_sends_you_to_the_furnace_with_materials(state, content, world):
    for art_id, picked in ((None, []), ("basic_fist", ["feng"]), (None, ["feng", "huo"])):
        assert "素材" not in skillview.forge_line(state, content, world, art_id, picked)


def test_the_art_library_is_empty_at_first(state, content, world):
    assert skillview.art_library(state, content, world) == []


def test_the_art_library_lists_each_art_with_its_own_level(state, content, world):
    art = _whirlwind(world)
    state.player.arts.append(art.id)
    state.player.art_levels[art.id] = 4
    label, art_id = skillview.art_library(state, content, world)[0]
    assert art_id == art.id and "第4成" in label and "武學" in label


def test_the_level_bar_reads_at_a_glance():
    """手機上「第4成」要讀過才知道練到哪，十格條一眼就看得出還剩多少可練。"""
    assert skillview.level_bar(0) == "○" * 10
    assert skillview.level_bar(4) == "●●●●○○○○○○"
    assert skillview.level_bar(10) == "●" * 10
    assert skillview.level_bar(99) == "●" * 10  # 夾住，不會長出第 11 格


# ── 武學與成長 Task 3：顯示玩家自己那一份的品質 ─────────────────────────


def _whirlwind(world) -> MartialArt:
    from tianxia.martial_arts import generate_from_name

    art = generate_from_name("旋風腿", "武學", "旋風腿", weights={"下品": 100, "中品": 0, "上品": 0, "絕學": 0})
    assert world.claim_skill_name(art)
    return art


def test_the_players_card_library_and_detail_show_the_players_own_quality(state, content, world):
    art = _whirlwind(world)
    state.player.member.wugong_id = "旋風腿"
    state.player.art_quality["旋風腿"] = "上品"
    label = f"旋風腿（上品・屬{art.attribute}）第1成"
    assert f"武學　{label}" in skillview.member_card(state, content, world, "player")
    assert skillview.library(state, content, world)[0][0].startswith(f"武學　{label}")
    text = skillview.detail(state, content, world, "武學")
    assert text.startswith(f"【旋風腿】上品・屬{art.attribute}")
    assert f"第一成 {28 * art.base_power / 8:.1f}" in text  # 威力也照自己的品質（上品區間，保留這門的微調）


def test_the_art_library_shows_the_players_own_quality(state, content, world):
    art = _whirlwind(world)
    state.player.arts = ["旋風腿"]
    assert skillview.art_library(state, content, world) == [(f"武學　旋風腿（下品・屬{art.attribute}）第1成", "旋風腿")]
    state.player.art_quality["旋風腿"] = "中品"
    assert skillview.art_library(state, content, world) == [(f"武學　旋風腿（中品・屬{art.attribute}）第1成", "旋風腿")]


def test_a_companions_card_ignores_the_players_own_quality(state, content, world):
    """玩家自己修練出來的品質只屬於玩家：同伴那門同 id 的武學照全服登記的（內容的）品質。"""
    world.update_companion("mate", lambda p: setattr(p, "wugong_id", "fist"))
    state.player.art_quality["fist"] = "下品"
    assert "武學　長拳（絕學・屬剛）第1成" in skillview.member_card(state, content, world, "mate")


# ── 修練與煉製頁的資料列（武學與成長計畫 T11）──────────────────


def test_art_rows_list_worn_arts_first_with_what_can_be_done(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    rows = skillview.art_rows(state, content, world)
    assert [r["id"] for r in rows] == ["basic_fist", "lake_kick"]
    assert rows[0]["worn"] and not rows[0]["melt"]["ok"]
    assert rows[1]["melt"]["ok"] and "退回心得" in rows[1]["melt"]["note"]
    assert not rows[0]["cultivate"]["ok"] and "沒有融過意境" in rows[0]["cultivate"]["note"]


def test_art_rows_carry_what_the_pages_draw(state, content, world):
    state.player.member.wugong_id, state.player.member.wugong_level = "basic_fist", 6
    state.player.arts = ["lake_kick"]
    state.player.art_levels["lake_kick"] = 3
    worn, stored = skillview.art_rows(state, content, world)
    assert (worn["name"], worn["kind"], worn["quality"], worn["attribute"], worn["level"]) == ("粗淺拳腳", "武學", "下品", "實", 6)
    assert (stored["level"], stored["worn"], stored["insight"]) == (3, False, None)
    assert "第6成" in worn["card"] and "基礎武學" in worn["card"]  # 功法卡跟著那一份的熟練度


def test_art_rows_of_an_art_with_an_insight_say_the_odds_and_the_cost(state, content, world):
    art = generate_from_name("旋風腿", "武學", "旋風腿", weights={"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}).model_copy(
        update={"origin": "fused", "insight": "feng", "lean": "無"},
    )
    assert world.claim_skill_name(art)
    state.player.arts = ["旋風腿"]
    state.player.insights = ["feng"]
    state.player.art_mastery["旋風腿"] = 2
    (row,) = skillview.art_rows(state, content, world)
    first, step = content.config.cultivate_odds["中品"]
    assert row["insight"] == "風" and row["cultivate"]["ok"]
    assert row["cultivate"]["note"] == f"{first + 2 * step}% 晉為中品・體力 {content.config.cultivate_stamina}"
    assert "意境：「風」" in row["card"] and "合成" in row["card"]
    state.player.insights = []  # 意境熔掉了：修練的按鈕講原因，不再說機率
    assert not skillview.art_rows(state, content, world)[0]["cultivate"]["ok"]


def test_the_art_awaiting_its_name_sits_in_the_library_but_cannot_be_melted(state, content, world):
    """審查（Task 9）：練成絕學、等著定名的那門在功法庫裡，熔煉鈕要跟動作一樣擋住，並講原因。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick", "basic_breath"]
    state.player.naming = "lake_kick"
    rows = {r["id"]: r for r in skillview.art_rows(state, content, world)}
    assert rows["lake_kick"]["melt"]["ok"] is False and "先替它定名" in rows["lake_kick"]["melt"]["note"]
    assert rows["basic_breath"]["melt"]["ok"] is True  # 其他庫裡的照樣能熔


def test_art_rows_skip_an_art_nobody_can_find(state, content, world):
    state.player.arts = ["ghost", "lake_kick"]
    assert [r["id"] for r in skillview.art_rows(state, content, world)] == ["lake_kick"]


def test_insight_rows_carry_name_attribute_and_melt_value(state, content, world):
    state.player.insights = ["haoran"]
    (row,) = skillview.insight_rows(state, content, world)
    assert (row["name"], row["attribute"], row["lean"], row["melt"]) == ("浩然", "陽", "正", 10)
    assert row["id"] == "haoran" and row["note"]


def test_insight_rows_keep_the_order_they_were_learned_and_skip_unknown_ones(state, content, world):
    state.player.insights = ["huo", "ghost", "feng"]
    assert [r["id"] for r in skillview.insight_rows(state, content, world)] == ["huo", "feng"]


def test_an_art_card_names_fused_and_basic_sources_and_the_insight():
    fused = MartialArt(
        id="旋風腿", name="旋風腿", kind="武學", quality="下品", attribute="快", base_power=10.0, top_power=30.0,
        origin="fused", creator="沈浪", insight="feng", lean="正",
    )
    card = skillview.art_card(fused, 2, "風")
    lines = card.split("\n")
    assert lines[0] == "【旋風腿】下品・屬快・正派"
    assert lines[3] == "來源：合成（沈浪 首創）　意境：「風」"
    assert skillview.art_card(fused.model_copy(update={"creator": None}), 2).split("\n")[3] == "來源：合成"
    basic = fused.model_copy(update={"origin": "basic", "lean": "無"})
    assert skillview.art_card(basic, 1).split("\n")[3] == "來源：基礎武學"
    assert skillview.art_card(basic, 1).split("\n")[0] == "【旋風腿】下品・屬快"  # 沒有傾向就不寫「無派」
