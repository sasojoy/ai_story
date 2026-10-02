from tianxia import rules, skillview, team


def test_rules_line():
    assert skillview.rules_line(None) == (
        "每人最多學一門內功、一門武學：自創功法（取名決定屬性/威力/成長性）或鍛鍊已知武學。"
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
    assert text == "【長拳】絕學・屬剛\n第1成，威力 50.0（下一成：57.8）\n來源：本命武學"


def test_detail_at_the_tenth_level_has_no_next_tier(state, content, world):
    rules.learn_skill(state, content, "fist")
    state.player.member.wugong_level = 10
    text = skillview.detail(state, content, world, "武學")
    assert "已達第十成" in text and "威力 120.0" in text


def test_detail_of_a_self_created_skill_says_so(state, content, world):
    art, msg = team.create_skill(state, content, world, "龍吟九霄", "武學")
    assert art is not None
    text = skillview.detail(state, content, world, "武學")
    assert text.startswith("【龍吟九霄】") and "來源：自創" in text


def test_detail_of_a_missing_skill_reference_is_a_placeholder(state, content, world):
    state.player.member.wugong_id = "ghost"
    assert skillview.detail(state, content, world, "武學") == "（找不到武學資料：ghost）"


# ── 練功提示（心得目前沒有用途，提示把它接回門下）──────────────


def test_practice_hint_stays_quiet_below_the_threshold(state, content):
    state.player.stats["xinde"] = content.config.xinde_hint_threshold - 1
    assert skillview.practice_hint(state, content) is None


def test_practice_hint_names_both_kinds_when_nothing_is_learned(state, content):
    state.player.stats["xinde"] = content.config.xinde_hint_threshold
    hint = skillview.practice_hint(state, content)
    assert hint is not None
    assert "內功、武學" in hint and str(content.config.xinde_hint_threshold) in hint


def test_practice_hint_names_only_what_is_left_to_train(state, content, world):
    state.player.stats["xinde"] = 500
    team.create_skill(state, content, world, "龍吟九霄", "武學")
    state.player.member.wugong_level = 10
    hint = skillview.practice_hint(state, content)
    assert hint is not None and "內功" in hint and "武學" not in hint


def test_practice_hint_goes_away_once_everything_is_at_the_tenth_level(state, content, world):
    state.player.stats["xinde"] = 9999
    team.create_skill(state, content, world, "龍吟九霄", "武學")
    team.create_skill(state, content, world, "太虛吐納", "內功")
    state.player.member.wugong_level = state.player.member.neigong_level = 10
    assert skillview.practice_hint(state, content) is None


# ── 煉製素材（門下頁的背包）────────────────────────────────


def test_bag_text_when_empty_says_where_materials_come_from(state, content):
    text = skillview.bag_text(state, content)
    assert text.startswith("**煉製素材**")
    assert "打贏對手" in text and "探索" in text


def test_bag_text_lists_what_you_hold_high_tier_first(state, content):
    state.player.materials = {"gang_1": 2, "gang_3": 1}
    lines = skillview.bag_text(state, content).splitlines()
    assert lines[1].startswith("- 隕鐵膽 ×1　天品・屬剛")
    assert lines[2].startswith("- 精鐵砂 ×2　凡品・屬剛")


# ── 煉製那一塊的說明與功法庫 ────────────────────────────────


def test_craft_line_asks_for_two_materials_first(state, content):
    line = skillview.craft_line(state, content, [], "武學")
    assert "選 2 樣素材" in line and "目前心得 0" in line
    assert "凡品配方不花心得" in line and "閉關" in line  # 告訴玩家心得從哪裡來


def test_craft_line_shows_the_cost_and_what_you_have(state, content):
    from tianxia import materials

    materials.grant(state, content, "gang_3", 2)
    state.player.stats["xinde"] = 100
    line = skillview.craft_line(state, content, ["gang_3", "gang_3"], "武學")
    assert "隕鐵膽＋隕鐵膽 → 一門武學" in line and "你有 100 點" in line
    assert "⚠" not in line


def test_craft_line_says_a_common_recipe_is_free(state, content):
    from tianxia import materials

    materials.grant(state, content, "gang_1", 2)
    line = skillview.craft_line(state, content, ["gang_1", "gang_1"], "武學")
    assert "精鐵砂＋精鐵砂 → 一門武學" in line and "不花心得" in line
    assert "⚠" not in line


def test_craft_line_explains_why_it_cannot_be_done(state, content):
    from tianxia import materials

    materials.grant(state, content, "gang_3", 2)
    state.player.stats["xinde"] = 0
    line = skillview.craft_line(state, content, ["gang_3", "gang_3"], "武學")
    assert "⚠" in line and "心得不足" in line


def test_the_art_library_is_empty_at_first(state, content, world):
    assert skillview.art_library(state, content, world) == []


def test_the_art_library_lists_each_art_with_its_own_level(state, content, world):
    team.create_skill(state, content, world, "龍吟九霄", "武學")
    state.player.arts.append("龍吟九霄")
    state.player.art_levels["龍吟九霄"] = 4
    label, art_id = skillview.art_library(state, content, world)[0]
    assert art_id == "龍吟九霄" and "第4成" in label and "武學" in label


# ── 練功提示（煉製之後文案改寫）──────────────────────────────


def test_the_hint_mentions_crafting_once_you_can_afford_a_furnace(state, content):
    from tianxia import materials

    state.player.stats["xinde"] = 500
    materials.grant(state, content, "gang_1", 2)
    hint = skillview.practice_hint(state, content)
    assert hint is not None and "煉製" in hint


def test_the_hint_says_nothing_about_crafting_without_materials(state, content):
    state.player.stats["xinde"] = 500
    hint = skillview.practice_hint(state, content)
    assert hint is not None and "煉製" not in hint


def test_the_hint_goes_quiet_when_everything_is_maxed_and_nothing_can_be_crafted(state, content, world):
    state.player.stats["xinde"] = 500
    team.create_skill(state, content, world, "龍吟九霄", "武學")
    team.create_skill(state, content, world, "太虛吐納", "內功")
    state.player.member.wugong_level = state.player.member.neigong_level = 10
    assert skillview.practice_hint(state, content) is None


def test_the_level_bar_reads_at_a_glance():
    """手機上「第4成」要讀過才知道練到哪，十格條一眼就看得出還剩多少可練。"""
    assert skillview.level_bar(0) == "○" * 10
    assert skillview.level_bar(4) == "●●●●○○○○○○"
    assert skillview.level_bar(10) == "●" * 10
    assert skillview.level_bar(99) == "●" * 10  # 夾住，不會長出第 11 格
