from tianxia import rules, skillview, team
from tianxia.martial_arts import MartialArt, historical_art, power_at


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


def test_detail_of_a_self_created_skill_says_so(state, content, world):
    art, msg = team.create_skill(state, content, world, "龍吟九霄", "武學")
    assert art is not None
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


def test_practice_hint_calls_the_pages_by_their_tab_names(state, content):
    """FB-047：門下頁拆成「修練」「煉製」兩個分頁之後，提示照分頁的名字寫，不再寫「門下」。"""
    from tianxia import materials

    state.player.stats["xinde"] = 500
    hint = skillview.practice_hint(state, content)
    assert hint == "💡 你已攢下 500 點心得。去「修練」鍛鍊內功、武學（不花一分一毫）。"
    materials.grant(state, content, "gang_1", 2)
    hint = skillview.practice_hint(state, content)
    assert hint == "💡 你已攢下 500 點心得。去「修練」鍛鍊內功、武學（不花一分一毫），或到「煉製」拿素材煉製新功法。"


def test_practice_hint_stays_quiet_while_the_season_rests(state, content):
    """FB-047：休季時什麼都不能做，提示不出現。"""
    state.player.stats["xinde"] = 500
    state.world.ended = True
    assert skillview.practice_hint(state, content) is None


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
    line = skillview.craft_line(state, content, [])
    assert "選 2 樣素材" in line and "目前心得 0" in line
    assert "凡品配方不花心得" in line and "閉關" in line  # 告訴玩家心得從哪裡來


def test_craft_line_shows_the_cost_and_what_you_have(state, content):
    from tianxia import materials

    materials.grant(state, content, "gang_3", 2)
    state.player.stats["xinde"] = 100
    line = skillview.craft_line(state, content, ["gang_3", "gang_3"])
    assert "隕鐵膽＋隕鐵膽 → 一門功法" in line and "開爐才知道" in line and "你有 100 點" in line
    assert "⚠" not in line


def test_craft_line_says_a_common_recipe_is_free(state, content):
    from tianxia import materials

    materials.grant(state, content, "gang_1", 2)
    line = skillview.craft_line(state, content, ["gang_1", "gang_1"])
    assert "精鐵砂＋精鐵砂 → 一門功法" in line and "不花心得" in line
    assert "⚠" not in line


def test_craft_line_explains_why_it_cannot_be_done(state, content):
    from tianxia import materials

    materials.grant(state, content, "gang_3", 2)
    state.player.stats["xinde"] = 0
    line = skillview.craft_line(state, content, ["gang_3", "gang_3"])
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
