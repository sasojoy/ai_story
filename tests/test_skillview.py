import pytest

from tianxia import fusion, library, rules, skillview, team, traits
from tianxia.martial_arts import MartialArt, generate_from_name, historical_art, power_at
from tianxia.state import new_game_state


def test_rules_line():
    assert skillview.rules_line(None) == (
        "身上一門內功、一門武學：花心得練成，用意境修練衝品質；武學也能在「煉製」融意境衍生新武學，或兩門武學合成一門新的。"
    )


def test_member_card_before_learning_anything(state, content, world):
    card = skillview.member_card(state, content, world, "player")
    assert card == (
        "### 沈浪\n第 1 級　氣血 320/320\n內功　（尚未習得）\n武學　（尚未習得）"
    )


def test_the_players_card_reads_the_hp_cap_with_root_and_a_companions_reads_his_own(state, content, world):
    """根骨 15：本人的氣血上限 320 × 1.3 ＝ 416；同伴照他自己的根骨（韓鐵 6：320 × 1.03）。"""
    state.player.stats["con"] = 15
    assert "第 1 級　氣血 416/416" in skillview.member_card(state, content, world, "player")
    assert "氣血 330/330" in skillview.member_card(state, content, world, "mate")


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
    # FB-006：detail 改用功法卡，多了十格條、第一成／第十成兩個數字；本命武學沒有說明句，那一行整行省略。
    # 計畫六 Task 4：來源之後多一行功效（長拳屬剛、絕學 ×3：破甲 4%×3＝12%）
    assert text == (
        "【長拳】絕學・屬剛\n"
        "第1成 ●○○○○○○○○○，威力 50.0（下一成：57.8）\n"
        "第一成 50.0　第十成 120.0\n"
        "來源：本命武學\n"
        "功效：〔破甲〕對手強度當作低 12%"
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


PILL_LINE = "- 破境丹 ×2　衝擊絕學時可以服下，那一次的機會多幾分。"


def test_bag_text_lists_the_legend_item_and_is_not_empty_because_of_it(state, content):
    state.player.legend_items = 2
    text = skillview.bag_text(state, content)
    assert text.startswith("**背包**") and PILL_LINE in text.splitlines() and "還沒有東西" not in text
    assert "煉" not in text and "爐" not in text and "素材" not in text  # PM 用語：不叫人拿東西去爐裡


def test_the_legend_item_gets_its_own_heading_so_it_is_not_read_as_a_material(state, content):
    """材料那行標題寫「隨身帶著的材料，分凡品、靈品、天品三階」：破境丹不是材料，要有自己的小標題（空行隔開，
    不然 markdown 會把標題當成上一項的接續行）。"""
    state.player.materials = {"gang_1": 2}
    state.player.legend_items = 2
    lines = skillview.bag_text(state, content).splitlines()
    assert lines[0].startswith("**背包**") and "材料" in lines[0]
    assert lines[1].startswith("- 精鐵砂 ×2")
    assert lines[2:] == ["", "**傳奇道具**", PILL_LINE]


def test_the_legend_item_alone_sits_under_a_header_that_does_not_call_it_a_material(state, content):
    state.player.legend_items = 2
    assert skillview.bag_text(state, content).splitlines() == ["**背包**　隨身帶著的東西。", PILL_LINE]


def test_bag_text_says_it_is_empty_only_when_there_is_nothing_at_all(state, content):
    assert "還沒有東西" in skillview.bag_text(state, content)
    state.player.legend_items = 0
    state.player.materials = {"gang_1": 1}
    assert "還沒有東西" not in skillview.bag_text(state, content)


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


def test_forge_line_counts_against_the_cap_that_lore_widens(state, content, world):
    state.player.stats["lore"] = 8  # 比基準多 3 點：多 6 格
    assert "武學與意境 0/56" in skillview.forge_line(state, content, world, None, [])


def test_forge_line_shows_a_fuse(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 100
    line = skillview.forge_line(state, content, world, "basic_fist", ["feng"])
    assert "**合成**" in line and "【粗淺拳腳】＋「風」→ 一門新武學" in line and "屬快" in line
    # 第一成的下品底、基本意境：比普通搭配差一些，原因照分數大小寫兩個
    assert "品質看造化：下品 61%、中品 25%、上品 14%（火候還淺、底子尚淺）" in line
    assert "花 5 點心得、5 點體力（你有 100 點心得）" in line and "⚠" not in line


def test_forge_line_writes_this_pairings_odds_and_a_better_base_shows(state, content, world):
    """企劃者 2026-10-06：每一爐照搭配算自己的機率，說明寫這一爐的三個機率；底越好上品越容易，說明不寫「品質跟底一樣」。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 100
    lines = {}
    for quality in ("下品", "中品", "上品", "絕學"):
        state.player.art_quality["basic_fist"] = quality
        lines[quality] = skillview.forge_line(state, content, world, "basic_fist", ["feng"])
        assert "屬快" in lines[quality] and "一樣是" not in lines[quality] and "⚠" not in lines[quality]
    assert "上品 14%" in lines["下品"] and "上品 20%" in lines["中品"] and "上品 23%" in lines["上品"] and "上品 27%" in lines["絕學"]
    assert "底子厚實" in lines["絕學"]


# ── 武學＋武學（武學與成長設計 12.3）────────────────────────────────


def test_forge_line_shows_a_blend(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    state.player.stats["xinde"] = 100
    line = skillview.forge_line(state, content, world, "basic_fist", [], other_art="lake_kick")
    seed = fusion.recipe_seed(world, fusion.blend_key("basic_fist", "lake_kick"))[1]
    shape = fusion.blend_shape(
        team.resolve_art("basic_fist", content, world), team.resolve_art("lake_kick", content, world), seed,
    )
    assert "**合成**" in line and f"→ 一門新{shape.kind}（屬{shape.attribute}，品質看造化：下品 " in line
    assert "花 5 點心得、5 點體力（你有 100 點心得）" in line and "⚠" not in line
    assert "⚠ 要放兩門不同的武學。" in skillview.forge_line(state, content, world, "basic_fist", [], other_art="basic_fist")


def test_forge_line_when_idle_mentions_two_arts(state, content, world):
    line = skillview.forge_line(state, content, world, None, [])
    assert "放兩門武學" in line and "放一門武學和一個意境" in line and "放兩個意境" in line


def test_art_rows_name_the_parents_of_a_blended_art(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    state.player.stats["xinde"] = 100
    art, _ = fusion.blend(state, content, world, None, "basic_fist", "lake_kick")  # 沒有模型：退路字表取名
    rows = {row["id"]: row for row in skillview.art_rows(state, content, world)}
    assert "由【粗淺拳腳】與【湖邊腿法】衍生" in rows[art.id]["card"]
    assert "衍生" not in rows["basic_fist"]["card"] and "衍生" not in rows["lake_kick"]["card"]


def test_the_worn_slot_card_of_a_blended_art_names_both_parents(state, content, world):
    """身上那一欄的功法卡（detail）也寫「由…衍生」，不只清單裡的（art_rows）；穿的不是合成的就不寫。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    state.player.stats["xinde"] = 100
    art, _ = fusion.blend(state, content, world, None, "basic_fist", "lake_kick")
    assert "衍生" not in skillview.detail(state, content, world, "武學")  # 還穿著粗淺拳腳
    team.switch_art(state, content, world, art.id)
    assert art.kind == "武學" and "由【粗淺拳腳】與【湖邊腿法】衍生" in skillview.detail(state, content, world, "武學")


def test_parent_names_skip_a_source_that_is_gone_and_are_empty_for_other_arts(content, world):
    fist = team.resolve_art("basic_fist", content, world)
    assert skillview.parent_names(fist, content, world) == []
    art = generate_from_name("踏浪拳", "武學", "踏浪拳").model_copy(
        update={"origin": "fused", "parents": ["basic_fist", "ghost"]},
    )
    assert skillview.parent_names(art, content, world) == ["粗淺拳腳"]  # 找不到的那門不寫，card 只認剛好兩個


def test_the_card_of_a_blended_art_names_both_parents():
    art = generate_from_name("烈風腿", "武學", "烈風腿").model_copy(
        update={"origin": "fused", "creator": "甲", "parents": ["a", "b"]},
    )
    card = skillview.art_card(art, 1, None, ["旋風腿", "烈火拳"])
    assert card.split("\n")[3] == "來源：合成（甲 首創）　由【旋風腿】與【烈火拳】衍生"


# ── 武學的功效（武學與成長設計 13.6；計畫六 Task 4）：功法卡一行功效、爐子寫已知配方的功效 ──────────────


def test_the_art_card_lists_its_traits(state, content, world):
    art = generate_from_name("裂石拳", "武學", "裂石拳", attribute="剛").model_copy(
        update={"origin": "fused", "traits": ["剛", "快"], "special": "lianhuan"},
    )
    card = skillview.art_card(art, 1, None, None, traits.card_line(content, art))
    assert "功效：〔破甲〕" in card and "〔先手〕" in card and "〔連環〕" in card


def test_the_trait_line_sits_after_the_source_and_before_the_note(content):
    art = _crafted("以柔勁纏住兵刃，借力卸力。").model_copy(update={"origin": "fused"})
    lines = skillview.art_card(art, 3, None, None, traits.card_line(content, art)).split("\n")
    assert lines[3].startswith("來源：") and lines[4].startswith("功效：〔化勁〕") and lines[-1] == "以柔勁纏住兵刃，借力卸力。"
    assert len(lines) == 6  # 名字、成數、威力、來源、功效、說明


def test_a_card_without_a_trait_line_is_exactly_as_before():
    """沒給功效那一行（舊呼叫、內容沒有功效）：功法卡一個字不變，不留空行。"""
    art = _crafted("以柔勁纏住兵刃，借力卸力。")
    assert skillview.art_card(art, 3) == skillview.art_card(art, 3, None, None, "")
    assert len(skillview.art_card(art, 3).split("\n")) == 5


def test_the_worn_slot_cards_carry_the_traits_too(state, content, world):
    """F9：身上那一欄的功法卡（detail，網頁的 slot_cards）也有功效那一行，跟修練頁的清單（art_rows）一樣。"""
    state.player.member.wugong_id = "basic_fist"
    text = skillview.detail(state, content, world, "武學")
    assert "\n功效：〔厚〕帶傷時出手的下限高 5%" in text  # 基礎武學下品：一層、×1


def test_the_card_in_the_practice_list_follows_the_players_own_quality(state, content, world):
    """數字跟品質一起變：同一門武學修練到上品，功效的數字乘 2。"""
    state.player.member.wugong_id = "basic_fist"
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == "basic_fist"]
    assert "功效：〔厚〕帶傷時出手的下限高 5%" in row["card"]
    state.player.art_quality["basic_fist"] = "上品"
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == "basic_fist"]
    assert "功效：〔厚〕帶傷時出手的下限高 10%" in row["card"]


def test_the_card_of_a_fused_art_lists_every_trait_and_the_special(state, content, world):
    art = generate_from_name("裂石拳", "武學", "裂石拳", attribute="剛").model_copy(
        update={"origin": "fused", "traits": ["剛", "快", "剛"], "special": "wuzhao"},
    )
    world.claim_skill_name(art)
    state.player.arts = [art.id]
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == art.id]
    assert "〔破甲〕對手強度當作低 " in row["card"] and "〔先手〕" in row["card"] and "〔悟招〕打贏多拿 5 心得" in row["card"]


def test_the_furnace_shows_what_a_known_recipe_gives(state, content, world):
    """13.6：已知的配方說出合出來那一門與它的功效；沒人合過的寫「沒人合過」。"""
    state.player.member.wugong_id, state.player.insights = "basic_fist", ["feng"]
    state.player.stats["xinde"] = 100
    assert "沒人合過" in skillview.forge_line(state, content, world, "basic_fist", ["feng"])
    other = new_game_state(content, "乙")
    other.player.member.wugong_id, other.player.insights, other.player.stats["xinde"] = "basic_fist", ["feng"], 100
    made, _ = fusion.fuse(other, content, world, None, "basic_fist", "feng")
    line = skillview.forge_line(state, content, world, "basic_fist", ["feng"])
    assert f"會合出【{made.name}】" in line and "功效：〔先手〕" in line


def test_the_furnace_shows_a_known_blend_too_and_says_nothing_for_an_unknown_one(state, content, world):
    state.player.member.wugong_id, state.player.arts = "basic_fist", ["lake_kick"]
    state.player.stats["xinde"] = 100
    assert "沒人合過" in skillview.forge_line(state, content, world, "basic_fist", [], other_art="lake_kick")
    other = new_game_state(content, "乙")
    other.player.member.wugong_id, other.player.arts, other.player.stats["xinde"] = "basic_fist", ["lake_kick"], 100
    made, _ = fusion.blend(other, content, world, None, "basic_fist", "lake_kick")
    line = skillview.forge_line(state, content, world, "basic_fist", [], other_art="lake_kick")
    assert f"會合出【{made.name}】" in line and traits.card_line(content, made) in line and "沒人合過" not in line


def test_the_furnace_does_not_repeat_itself_for_an_art_you_already_have(state, content, world):
    """合出來的那一門你已經有了：下面的 ⚠ 本來就會說，不再寫「會合出」。"""
    state.player.member.wugong_id, state.player.insights = "basic_fist", ["feng"]
    state.player.stats["xinde"] = 100
    made, _ = fusion.fuse(state, content, world, None, "basic_fist", "feng")
    line = skillview.forge_line(state, content, world, "basic_fist", ["feng"])
    assert "你已經有了" in line and "會合出" not in line and "沒人合過" not in line
    assert made.id in state.player.arts


def test_the_furnace_does_not_peek_at_a_recipe_for_things_you_do_not_hold(state, content, world):
    """預覽不能拿來探：不是你的武學、還沒悟到的意境，一律先拒絕，不會透露別人合出了什麼（F8 沿用既有的把關）。"""
    other = new_game_state(content, "乙")
    other.player.member.wugong_id, other.player.insights, other.player.stats["xinde"] = "basic_fist", ["feng"], 100
    fusion.fuse(other, content, world, None, "basic_fist", "feng")
    state.player.member.wugong_id = "basic_fist"  # 沒有風這個意境
    line = skillview.forge_line(state, content, world, "basic_fist", ["feng"])
    assert line.startswith("⚠") and "會合出" not in line and "功效" not in line
