import pytest

from tianxia import arts as arts_mod, cultivation, library, rules, skillview, team, traits
from tianxia.martial_arts import Insight, MartialArt, generate_from_name, historical_art, power_at
from tianxia.state import InsightFx
from test_cultivation import STRONG


@pytest.mark.smoke
def test_rules_line():
    # 武學重構：意境就是技能、裝進槽；煉製頁只剩武學＋武學、意境揣摩與自創
    assert skillview.rules_line(None) == (
        "身上一門內功、一門武學：花心得練成；意境就是技能，裝進武學的意境槽（收得下的屬性才裝得進去）；"
        "在「煉製」兩門武學合成一門新的、意境揣摩得更深，或用心得自創一門。"
    )


def test_the_attribute_note_says_what_the_code_does(content):
    """W2：屬性的說明一句話——同屬性、相剋、克對手三條，數字與哪幾對相剋都讀自程式（team.pairing 的設定、
    martial_arts.ATTRIBUTE_COUNTERS、encounter.COUNTER_BONUS），不另外寫死一份。句子待 joy 潤。"""
    assert skillview.attribute_line(content) == (  # FB-089：開頭先說清楚這是武學的屬性（剛柔快慢陰陽虛實），不是升級配點的那五項
        "武學的屬性（剛柔快慢陰陽虛實）：內功與武學同屬，威力 +20%；兩門相剋（陰陽、剛柔、快慢、虛實）威力 −20%；"
        "武學克住對手的屬性，威力 ×1.3。"
    )


def test_the_word_attribute_names_the_arts_side_only_where_it_is_qualified(content):
    """FB-089：「屬性」有兩個意思——升級配的五項（臂力身法根骨悟性博聞）與武學的剛柔快慢陰陽虛實。武學這一邊的說明都冠上
    「武學的屬性（…）」，配點那一邊維持「屬性」；「屬X」那種卡片上的短標籤不動。"""
    note = skillview.attribute_line(content)
    assert note.startswith("武學的屬性（剛柔快慢陰陽虛實）：")
    from tianxia import martial_arts

    assert sorted(skillview.ARTS_ATTRIBUTES) == sorted(martial_arts.ATTRIBUTES)  # 八個字一個不少（只是寫給玩家看的順序不同）
    assert "同屬性" not in note and "臂力" not in note  # 沒有資格詞的「同屬性」換成「同屬」；說明裡不夾配點那五項
    names = [name for name, _ in skillview.stat_uses(content)]
    assert names == ["臂力", "身法", "根骨", "悟性", "博聞"]  # 配點那一邊照舊（狀態列「點名號展開的屬性」）


def test_the_attribute_note_follows_the_numbers_it_reads(content, monkeypatch):
    from tianxia import encounter, martial_arts

    content.config.pairing_bonus, content.config.pairing_penalty = 0.35, 0.1
    monkeypatch.setattr(encounter, "COUNTER_BONUS", 1.5)
    monkeypatch.setattr(martial_arts, "ATTRIBUTE_COUNTERS", {"剛": "柔", "柔": "剛"})
    note = skillview.attribute_line(content)
    assert "威力 +35%" in note and "威力 −10%" in note and "威力 ×1.5" in note
    assert "兩門相剋（剛柔）威力" in note and "陰陽、" not in note  # 相剋的一對照表列，每一對只寫一次（開頭那八個字是屬性的名單）


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


def test_detail_before_learning_says_so(state, content, world):
    assert skillview.detail(state, content, world, "武學") == "你還沒有武學。"
    assert skillview.detail(state, content, world, "內功") == "你還沒有內功。"


def test_detail_of_a_historical_skill(state, content, world):
    rules.learn_skill(state, content, "fist")
    text = skillview.detail(state, content, world, "武學")
    # FB-006：detail 改用功法卡，多了十格條、第一成／第十成兩個數字；本命武學沒有說明句，那一行整行省略。
    # 計畫六 Task 4：來源之後多一行功效（長拳屬剛、絕學 ×3：破甲 10%×3＝30%）
    assert text == (
        "【長拳】絕學・屬剛\n"
        "第1成 ●○○○○○○○○○，威力 50.0（下一成 57.8・第十成 120.0）\n"  # W1：威力只寫一行
        "來源：本命武學\n"
        "功效：〔破甲〕強攻剋中對手時，有 30% 的機會讓他下一回合的固守與借力落空"
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
    assert lines[2] == "來源：煉製（沈浪 首創）"
    assert lines[-1] == "以柔勁纏住兵刃，借力卸力。"


def test_an_art_card_says_where_the_art_came_from():
    """FB-017：煉出來的寫「煉製（首創者 首創）」，取名自創的寫「自創（取名者 所創）」，其他是本命武學。"""
    def source(art: MartialArt) -> str:
        return skillview.art_card(art, 1).split("\n")[2]

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


def test_an_art_card_says_the_power_on_one_line_with_the_next_level_and_the_tenth():
    """W1：威力只在一行裡說——現在這一成、下一成、第十成；不再另起一行寫「第一成 …　第十成 …」。"""
    art = _crafted("")
    card = skillview.art_card(art, 3)
    assert f"第3成 ●●●○○○○○○○，威力 {power_at(art, 3):.1f}（下一成 {power_at(art, 4):.1f}・第十成 {power_at(art, 10):.1f}）" in card.split("\n")
    assert "第一成" not in card and "　第十成" not in card  # 舊的那一行不在了
    assert sum(line.count("威力") for line in card.split("\n")) == 1  # 威力整張卡只出現一次（功效那一行說的是別的）


def test_an_art_card_at_the_ninth_and_tenth_level_does_not_repeat_itself():
    """第九成的下一成就是第十成，不寫兩個一樣的數字；第十成沒有下一成。"""
    art = _crafted("")
    ninth = skillview.art_card(art, 9).split("\n")[1]
    assert ninth.endswith(f"威力 {power_at(art, 9):.1f}（下一成即第十成 {power_at(art, 10):.1f}）")  # 待 joy 潤
    tenth = skillview.art_card(art, 10).split("\n")[1]
    assert tenth.endswith(f"威力 {power_at(art, 10):.1f}（已達第十成）")  # 待 joy 潤


# ── 練功提示（練成花心得：心得的去處是練成與合成）──────────────


def test_practice_hint_is_quiet_below_the_threshold(state, content):
    state.player.member.wugong_id = "basic_fist"
    content.config.xinde_hint_threshold = 50  # 設定還留著這個下限（explain-2 起預設 0）：設了就照它
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
    state.player.stats["xinde"] = team.practice_price(content, 1)  # 兩門都還在第一成：付得起第二成就兩門都能練
    hint = skillview.practice_hint(state, content)
    assert "練成內功、武學" in hint and f"你已攢下 {team.practice_price(content, 1)} 點心得" in hint


def test_practice_hint_skips_a_slot_whose_next_level_it_cannot_pay(state, content):
    """價錢是下一成的價錢：付不起的那一門不列，不然玩家照著提示去按只會挨一句「心得不足」。"""
    content.config.practice_xinde_per_level = 10
    state.player.member.wugong_id, state.player.member.wugong_level = "basic_fist", 2  # 要 20 點
    state.player.member.neigong_id, state.player.member.neigong_level = "basic_breath", 9  # 要 90 點
    state.player.stats["xinde"] = 60
    hint = skillview.practice_hint(state, content)
    assert "練成武學" in hint and "內功" not in hint


def test_practice_hint_points_at_the_furnace_when_holding_an_insight(state, content):
    state.player.insights = ["feng", "huo"]  # 合併要兩個意境
    state.player.stats["xinde"] = 60
    assert "煉製" in skillview.practice_hint(state, content)


def test_practice_hint_only_mentions_the_furnace_when_a_forge_is_possible_and_affordable(state, content):
    """Task 5 審查留下的：光是手上有意境不算，要持有沒滿、付得起一次合成或合併才提煉製。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.member.wugong_level = 10  # 練成那一半不會出聲，只看煉製那一半
    state.player.insights = ["feng", "huo"]  # 合併要兩個意境
    state.player.stats["xinde"] = 60
    assert "煉製" in skillview.practice_hint(state, content)
    content.config.fuse_xinde = content.config.merge_xinde = 999  # 付不起
    assert skillview.practice_hint(state, content) is None
    content.config.fuse_xinde = content.config.merge_xinde = 5
    content.config.holding_cap_base = 2  # 持有滿了（一門武學加一個意境）
    assert skillview.practice_hint(state, content) is None


def test_practice_hint_calls_the_pages_by_their_tab_names(state, content):
    """FB-047：門下頁拆成「修練」「煉製」兩個分頁之後，提示照分頁的名字寫，不再寫「門下」。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.stats["xinde"] = 60
    assert skillview.practice_hint(state, content) == "💡 你已攢下 60 點心得。點上面身上的武學練成武學。"
    state.player.insights = ["feng", "huo"]  # 合併要兩個意境
    assert skillview.practice_hint(state, content) == (
        "💡 你已攢下 60 點心得。點上面身上的武學練成武學，或去「煉製」把兩個意境合成新的。"
    )


def test_practice_hint_never_sends_you_to_the_furnace_with_materials(state, content):
    """審查裁示（企劃者的用語）：任何提示都不能叫玩家拿素材去煉製。"""
    from tianxia import materials

    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]  # 合併要兩個意境
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
    state.player.insights = ["feng", "huo"]  # 合併要兩個意境
    state.player.stats["xinde"] = 500
    state.world.ended = True
    assert skillview.practice_hint(state, content) is None


def test_practice_hint_goes_away_once_everything_is_at_the_tenth_level(state, content, world):
    state.player.stats["xinde"] = 9999
    state.player.member.wugong_id, state.player.member.wugong_level = "fist", 10
    state.player.member.neigong_id, state.player.member.neigong_level = "breath", 10
    assert skillview.practice_hint(state, content) is None  # 兩門都滿了、沒有意境：爐裡只合意境，也沒得合
    state.player.insights = ["feng", "huo"]  # 合併要兩個意境
    assert "煉製" in skillview.practice_hint(state, content)  # 有意境還能拿去煉製


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


def test_forge_line_asks_for_two_insights_first(state, content, world):
    line = skillview.forge_line(state, content, world, [])
    assert skillview.FORGE_EMPTY in line and "放兩個意境" in line and "素材" not in line
    assert "武學與意境 0/50" in line


def test_forge_line_with_one_insight_in_the_furnace_says_what_is_missing(state, content, world):
    """W4：爐裡只放了一個意境——說還缺什麼，不再是放什麼都一樣的總說明。句子待 joy 潤。"""
    state.player.insights = ["feng"]
    line = skillview.forge_line(state, content, world, ["feng"])
    assert skillview.FORGE_ONE_INSIGHT in line and "再放一個意境" in line and "武學與意境 1/50" in line
    assert "放兩個意境" not in line  # 總說明那一長句不重複
    assert "「風」" not in line  # 不點名：放的東西爐子上已經畫了


def test_forge_line_one_item_hint_leaks_nothing_about_an_insight_you_do_not_have(state, content, world):
    """預覽不能拿來探：放的不是你的意境，提示也只有「再放…」，不寫名字、屬性。"""
    line = skillview.forge_line(state, content, world, ["shui"])
    assert skillview.FORGE_ONE_INSIGHT in line and "水" not in line and "屬" not in line


def test_forge_line_counts_against_the_cap_that_lore_widens(state, content, world):
    state.player.stats["lore"] = 8  # 比基準多 3 點：多 6 格
    assert "武學與意境 0/56" in skillview.forge_line(state, content, world, [])


def test_forge_line_shows_a_merge(state, content, world):
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    line = skillview.forge_line(state, content, world, ["feng", "huo"])
    assert "**合併**" in line and "「風」＋「火」→ 一個新的意境" in line and "花 5 點心得" in line and "⚠" not in line


def test_forge_line_explains_why_it_cannot_be_done(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 0
    assert "⚠ 揣摩要同一種意境的兩份" in skillview.forge_line(state, content, world, ["feng", "feng"])  # 同一份放兩次
    state.player.insights.append("feng~2")
    assert "⚠ 心得不足" in skillview.forge_line(state, content, world, ["feng", "feng~2"])  # 揣摩也花心得


def test_forge_line_survives_something_that_does_not_exist(state, content, world):
    """存檔裡記著、內容與登記裡都沒有的（失效的引用）：說「不存在」；你根本沒有的，見下面那條。"""
    state.player.insights = ["feng", "ghost"]
    assert "不存在" in skillview.forge_line(state, content, world, ["feng", "ghost"])


def test_forge_line_says_nothing_about_an_insight_you_do_not_have(state, content, world):
    """沒有的東西（還沒悟到的意境）只回拒絕那一句：不寫名字、屬性，不能拿預覽來探。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    for picked in (["feng", "shui"], ["shui", "feng"]):
        line = skillview.forge_line(state, content, world, picked)
        assert "兩個意境都要是你悟得的" in line and line.startswith("⚠"), line
        assert "水" not in line and "屬" not in line and "→" not in line, line


def test_forge_line_never_sends_you_to_the_furnace_with_materials(state, content, world):
    for picked in ([], ["feng"], ["feng", "huo"]):
        assert "素材" not in skillview.forge_line(state, content, world, picked)


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
    art = art.model_copy(update={"affinity": [art.attribute]})  # 武學重構：武學的屬性＝相容屬性的第一個；沒寫相容屬性是兼容並蓄、沒有屬性
    assert world.claim_skill_name(art)
    return art


def test_the_players_card_and_detail_show_the_players_own_quality(state, content, world):
    art = _whirlwind(world)
    state.player.member.wugong_id = "旋風腿"
    state.player.art_quality["旋風腿"] = "上品"
    label = f"旋風腿（上品・屬{art.attribute}）第1成"
    assert f"武學　{label}" in skillview.member_card(state, content, world, "player")
    text = skillview.detail(state, content, world, "武學")
    assert text.startswith(f"【旋風腿】上品・屬{art.attribute}")
    assert f"第1成 ●○○○○○○○○○，威力 {28 * art.base_power / 8:.1f}（" in text  # 威力也照自己的品質（上品區間，保留這門的微調）


def test_the_art_rows_show_the_players_own_quality_and_level(state, content, world):
    art = _whirlwind(world)
    state.player.arts = ["旋風腿"]
    state.player.art_levels["旋風腿"] = 4

    def stored():
        return next(r for r in skillview.art_rows(state, content, world) if r["id"] == "旋風腿")

    assert (stored()["quality"], stored()["attribute"], stored()["level"]) == ("下品", art.attribute, 4)
    state.player.art_quality["旋風腿"] = "中品"
    assert stored()["quality"] == "中品" and "中品" in stored()["card"]


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
    assert rows[1]["melt"]["ok"] and rows[1]["melt"]["note"] == "沒有心得，只空出一格"  # 第一成的湖邊腿法熔了退 0（W9）
    assert not rows[0]["cultivate"]["ok"] and rows[0]["cultivate"]["note"] == cultivation.NO_RANK_LINE  # 武學重構：下品不靠修練衝品級


def test_art_rows_carry_the_melt_confirm_the_button_asks(state, content, world):
    """W9：確認框問什麼由伺服器寫好（library.melt_confirm）放在每一列的 melt.confirm，網頁照放。"""
    content.config.starter_skills = ["basic_fist"]
    state.player.member.wugong_id = "lake_kick"
    state.player.arts = ["basic_fist", "旋風腿"]
    _whirlwind(world)
    rows = {r["id"]: r for r in skillview.art_rows(state, content, world)}
    assert rows["basic_fist"]["melt"]["confirm"] == (  # arts-polish-2：W9 的直話＋去哪裡重學（只說一次）
        "把【粗淺拳腳】熔掉？這門熔了沒有心得，只空出一格。熔了還能免費重學：這裡就是城鎮，到江湖頁「此地還能做」找「學粗淺拳腳」。"
    )
    refund = rows["旋風腿"]["melt"]["note"].removeprefix("退回心得 ")
    assert rows["旋風腿"]["melt"]["confirm"] == f"把【旋風腿】熔成心得？退回心得 {refund}。熔掉就沒了。"  # 合成的有基本值，不是 0
    assert rows["旋風腿"]["melt"]["note"].startswith("退回心得 ")
    assert rows["lake_kick"]["melt"]["confirm"] == ""  # 身上正在練的不能熔：沒有確認框要問


def _refund_the_row_promises(state, content, world, art_id):
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == art_id]
    assert row["melt"]["ok"]
    return int(row["melt"]["note"].removeprefix("退回心得 "))


def test_the_melt_note_is_what_melting_really_pays_for_a_fused_art_you_cultivated(state, content, world):
    """修練頁寫的「退回心得 N」跟 library.melt_art 真的退的是同一個數（共用 melt_refund 與登記的品質）。"""
    _whirlwind(world)
    state.player.arts = ["旋風腿"]
    state.player.art_levels["旋風腿"] = 5
    for quality in ("下品", "中品", "上品", "絕學"):
        state.player.art_quality["旋風腿"] = quality
        promised = _refund_the_row_promises(state, content, world, "旋風腿")
        before = state.player.stats["xinde"]
        arts, levels, qualities = list(state.player.arts), dict(state.player.art_levels), dict(state.player.art_quality)
        library.melt_art(state, content, world, "旋風腿")
        assert state.player.stats["xinde"] - before == promised
        # 武學重構：中品、上品是合成帶來的品級（不是修練上去的），不給加給；只有絕學（契機那一階）照領
        assert promised == 8 + (content.config.melt_quality_bonus["絕學"] if quality == "絕學" else 0)
        state.player.arts, state.player.art_levels, state.player.art_quality = arts, levels, qualities


def test_the_melt_note_is_what_melting_really_pays_for_a_content_peerless_art(state, content, world):
    """登記就是絕學的內容武學（沒修練過）：頁面寫的、真的退的都不含 +40。"""
    state.player.arts = ["fist"]
    state.player.art_levels["fist"] = 5
    promised = _refund_the_row_promises(state, content, world, "fist")
    before = state.player.stats["xinde"]
    library.melt_art(state, content, world, "fist")
    assert state.player.stats["xinde"] - before == promised == 8


def test_art_rows_carry_what_the_pages_draw(state, content, world):
    state.player.member.wugong_id, state.player.member.wugong_level = "basic_fist", 6
    state.player.arts = ["lake_kick"]
    state.player.art_levels["lake_kick"] = 3
    worn, stored = skillview.art_rows(state, content, world)
    # 武學重構：基礎武學兼容並蓄、沒有屬性（attribute 是空字串）；「融的意境」沒有了（insight 一律 None，槽裡裝的在 slots）
    assert (worn["name"], worn["kind"], worn["quality"], worn["attribute"], worn["level"]) == ("粗淺拳腳", "武學", "下品", "", 6)
    assert (stored["level"], stored["worn"], stored["insight"]) == (3, False, None)
    assert worn["affinity"] == "兼容並蓄" and worn["slots"] == [None, None] and stored["gen"] == ""
    assert "第6成" in worn["card"] and "基礎武學" in worn["card"]  # 功法卡跟著那一份的熟練度


def test_art_rows_of_an_art_with_a_slotted_insight_say_the_skill_and_no_longer_any_odds(state, content, world):
    """武學重構：沒有「融的意境」與修練機率了——意境裝在槽裡（slots 每格一招），修練那一顆下品一律寫品級不靠修練。"""
    art = generate_from_name("旋風腿", "武學", "旋風腿", weights={"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}).model_copy(
        update={"origin": "fused", "affinity": ["快"]},
    )
    assert world.claim_skill_name(art)
    state.player.arts = ["旋風腿"]
    state.player.insights = ["feng"]
    assert arts_mod.slot(state, content, world, "旋風腿", "feng") == [arts_mod.SLOTTED_LINE.format(insight="風", art="旋風腿", i=1)]
    (row,) = skillview.art_rows(state, content, world)
    assert row["insight"] is None and row["affinity"] == "快" and row["attribute"] == "快"
    assert [s and s["name"] for s in row["slots"]] == ["風", None]
    assert row["slots"][0]["skill"] == "先手一重" and row["slots"][0]["mark"] == "一重" and row["slots"][0]["strength"] == 1
    assert row["slots"][0]["quality"] == "中品" and row["slots"][0]["fx"][0]["name"] == "先手"  # 這一版之前悟到的：照舊的樣子、中品
    assert not row["cultivate"]["ok"] and row["cultivate"]["note"] == cultivation.NO_RANK_LINE and row["cultivate"]["xinde"] is None
    assert "功效：〔先手〕" in row["card"] and "合成" in row["card"] and "意境：" not in row["card"]
    assert "forge_odds" not in row and "forge_with" not in row and "forge_fixed" not in row


def _wind_kick(world, state, quality="下品", content=None, level=1, filled=0):
    """一門全服登記的下品武學（兼容並蓄），自己那一份的品級、成數與槽裡裝幾個意境照參數（裝槽要 content）。"""
    art = generate_from_name("旋風腿", "武學", "旋風腿", weights={"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}).model_copy(
        update={"origin": "fused", "lean": "無"},
    )
    if world.get_skill("旋風腿") is None:  # 同一個測試裡叫第二次（先一般、再到極處）：登記過就不再登記
        assert world.claim_skill_name(art)
    state.player.arts, state.player.insights = ["旋風腿"], ["feng", "huo", "shui", "shan"]
    state.player.art_quality["旋風腿"] = quality
    state.player.art_levels["旋風腿"] = level
    for insight_id in state.player.insights[:filled]:
        assert arts_mod.slot_problem(state, content, world, "旋風腿", insight_id) is None
        arts_mod.slot(state, content, world, "旋風腿", insight_id)


def _cultivate_row(state, content, world):
    return skillview.art_rows(state, content, world)[0]["cultivate"]


def _ripe(world, state, content, quality="上品"):
    """上品、第十成、槽（3 格）裝滿：到了衝絕學的門檻（cultivation.ready）。"""
    _wind_kick(world, state, quality, content, level=10, filled=3)
    for insight_id, fx in STRONG.items():  # 評分（第三批）：每一份三重加一重，四格 128 過一百
        state.player.insight_fx[insight_id] = InsightFx(quality="上品", general=dict(fx))


def test_the_peerless_step_note_says_to_wait_for_a_chance_or_take_the_pill(state, content, world):
    """武學重構：上品到了極處（第十成）那一步不在練功房裡——沒有丹時那一顆灰掉、寫等契機或服丹；
    還沒到極處寫差在哪（第幾成、槽幾格）；不是上品一律寫品級不靠修練。"""
    _wind_kick(world, state, "上品")
    row = _cultivate_row(state, content, world)
    assert row["ok"] is False and row["note"] == cultivation.NOT_RIPE_LINE.format(name="旋風腿", level=1, need=100, score=0)
    assert row["legend"] is None
    _ripe(world, state, content)
    row = _cultivate_row(state, content, world)
    assert row["ok"] is False and row["note"] == cultivation.CHANCE_LINE.format(name="旋風腿", pill="破境丹") and row["legend"] is None
    for step in ("中品", "下品"):  # 下一步不是絕學：品級不靠修練
        state.player.art_quality["旋風腿"] = step
        row = _cultivate_row(state, content, world)
        assert row["ok"] is False and row["note"] == cultivation.NO_RANK_LINE and row["legend"] is None, step


def test_the_row_offers_the_pill_only_at_the_peak_and_only_when_one_is_held(state, content, world):
    _ripe(world, state, content)
    assert _cultivate_row(state, content, world)["legend"] is None  # 手上沒有丹
    state.player.legend_items = 2
    row = _cultivate_row(state, content, world)
    odds = cultivation.force_odds(state, content, world, "旋風腿")  # 強行衝關的機會：legend_item_bonus × 悟性（15 × 1.0）
    assert odds == 15 and row["ok"] is True and "等一場硬仗的契機" in row["note"]
    assert row["legend"] == {
        "count": 2, "bonus": 15, "label": "服下破境丹強行衝關（剩 2 枚）", "note": "約 15% 衝開・體力 10",
    }


def test_the_pill_note_follows_the_players_wisdom(state, content, world):
    """頁面上寫的就是擲的：悟性 15 時 15% × 1.3 ≈ 20%（cultivation.force_odds）。"""
    _ripe(world, state, content)
    state.player.stats["wis"] = 15
    state.player.legend_items = 1
    row = _cultivate_row(state, content, world)
    assert cultivation.force_odds(state, content, world, "旋風腿") == 20
    assert row["legend"]["bonus"] == 20 and row["legend"]["note"] == "約 20% 衝開・體力 10"


def test_a_refused_row_has_no_pill_choice(state, content, world):
    _ripe(world, state, content)
    state.player.legend_items = 1
    state.player.stamina = 5  # 體力不足：按鈕講原因，不再提丹
    row = _cultivate_row(state, content, world)
    assert row["ok"] is False and "體力不足" in row["note"] and row["legend"] is None


def test_the_row_follows_the_pill_name_and_bonus_in_the_config(state, content, world):
    content.config.legend_item_name, content.config.legend_item_bonus = "天機丹", 20
    _ripe(world, state, content)
    state.player.legend_items = 1
    legend = _cultivate_row(state, content, world)["legend"]
    assert legend["label"] == "服下天機丹強行衝關（剩 1 枚）" and legend["note"] == "約 20% 衝開・體力 10"
    state.player.legend_items = 0
    assert _cultivate_row(state, content, world)["note"] == cultivation.CHANCE_LINE.format(name="旋風腿", pill="天機丹")


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
    assert lines[2] == "來源：合成（沈浪 首創）　意境：「風」"
    assert skillview.art_card(fused.model_copy(update={"creator": None}), 2).split("\n")[2] == "來源：合成"
    basic = fused.model_copy(update={"origin": "basic", "lean": "無"})
    assert skillview.art_card(basic, 1).split("\n")[2] == "來源：基礎武學"
    assert skillview.art_card(basic, 1).split("\n")[0] == "【旋風腿】下品・屬快"  # 沒有傾向就不寫「無派」


def test_an_art_card_shows_an_anonymous_first_fuser_as_a_nameless_hero():
    """匿名行走（最終審查 Important 2）：首創者登記時是匿名的，功法卡寫「某位少俠」——存著的 creator 照舊是名號（身分）。"""
    fused = MartialArt(
        id="旋風腿", name="旋風腿", kind="武學", quality="下品", attribute="快", base_power=10.0, top_power=30.0,
        origin="fused", creator="沈浪", creator_shown="某位少俠", insight="feng",
    )
    card = skillview.art_card(fused, 2, "風")
    assert card.split("\n")[2] == "來源：合成（某位少俠 首創）　意境：「風」" and "沈浪" not in card


def test_forge_line_tells_a_merge_costs_stamina(state, content, world):
    """設計 12.1：合併花體力。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    merge = skillview.forge_line(state, content, world, ["feng", "huo"])
    assert "花 5 點心得、5 點體力" in merge and "⚠" not in merge


def test_forge_line_warns_when_the_stamina_is_short_for_a_merge(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    state.player.stamina = content.config.merge_stamina - 1
    merge = skillview.forge_line(state, content, world, ["feng", "huo"])
    assert "花 5 點心得、5 點體力" in merge and "⚠ 體力不足：合併一次要 5。" in merge


def test_practice_hint_does_not_send_you_to_merge_when_the_stamina_is_short(state, content):
    """沒有武學、只能合併的人：合併要體力，體力不夠就別叫他去煉製；合成不花體力，不受影響。"""
    state.player.insights = ["feng", "huo"]  # 合併要兩個意境
    state.player.stats["xinde"] = 60
    state.player.stamina = content.config.merge_stamina - 1
    assert skillview.practice_hint(state, content) is None
    state.player.stamina = content.config.merge_stamina
    assert "煉製" in skillview.practice_hint(state, content)
    state.player.member.wugong_id, state.player.member.wugong_level = "basic_fist", 10
    state.player.stamina = content.config.fuse_stamina - 1
    assert skillview.practice_hint(state, content) is None  # 合成也要體力（設計 12.1）
    state.player.stamina = content.config.fuse_stamina
    assert "煉製" in skillview.practice_hint(state, content)


# ── 計畫二 Task 3：本人卡寫出威力加成 ──────────────────────────────────────────────


def test_the_players_card_spells_out_the_boosts(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.member.neigong_id = "basic_breath"  # 實配柔：不相剋也不同屬性
    state.player.stats["str"] = 9
    card = skillview.member_card(state, content, world, "player")
    assert "武學 +12%（臂力）" in card and "內外搭配" not in card


def _inner(world, name="柔雲訣", attribute="柔"):
    """一門全服登記的內功，相容屬性只有自己那一個（基礎內功兼容並蓄、沒有屬性，比搭配要用這個）。"""
    art = generate_from_name(name, "內功", name, attribute=attribute).model_copy(update={"affinity": [attribute]})
    assert world.claim_skill_name(art)
    return art


def test_the_boost_line_reads_stats_pairing_and_resonance(state, content, world):
    # 武學重構：屬性＝相容屬性的第一個；正邪照槽裡裝的意境（浩然是正）——清風拳收柔與陽，裝進浩然就是正派
    wugong = generate_from_name("清風拳", "武學", "清風拳", attribute="柔").model_copy(update={"affinity": ["柔", "陽"]})
    assert world.claim_skill_name(wugong)
    state.player.member.wugong_id, state.player.member.neigong_id = wugong.id, _inner(world).id  # 柔配柔
    state.player.insights, state.player.art_slots[wugong.id] = ["haoran"], ["haoran", None]
    state.player.stats.update({"str": 9, "con": 7, "good": 40})
    assert skillview.boost_line(state, content, world) == (
        "威力加成：武學 +12%（臂力）・內功 +6%（根骨）・內外搭配 +20%・【清風拳】共鳴 +20%"
    )
    assert skillview.boost_line(state, content, world) in skillview.member_card(state, content, world, "player")


def test_the_boost_line_shows_a_penalty_for_a_countering_pair(state, content, world):
    wugong = generate_from_name("鐵拳", "武學", "鐵拳", attribute="剛").model_copy(update={"affinity": ["剛"]})  # 武學重構：屬性照相容屬性
    assert world.claim_skill_name(wugong)
    state.player.member.wugong_id, state.player.member.neigong_id = wugong.id, _inner(world).id  # 剛克柔
    assert skillview.boost_line(state, content, world) == "威力加成：內外搭配 -20%"


def test_the_boost_line_is_absent_when_nothing_boosts(state, content, world):
    assert skillview.boost_line(state, content, world) == ""
    assert "威力加成" not in skillview.member_card(state, content, world, "player")


def test_a_stat_is_named_by_the_art_it_boosts_and_an_empty_slot_leaves_it_out(state, content, world):
    """臂力乘的是武學那一項、根骨乘的是內功那一項（設計 6.1）：卡上寫它加成的那一門，那一欄沒有功法就不寫。"""
    state.player.stats.update({"str": 9, "con": 9})
    assert skillview.boost_line(state, content, world) == ""  # 兩欄都空：什麼都沒得加成
    state.player.member.wugong_id = "basic_fist"
    assert skillview.boost_line(state, content, world) == "威力加成：武學 +12%（臂力）"  # 沒有內功：不寫根骨
    state.player.member.wugong_id, state.player.member.neigong_id = None, "basic_breath"
    assert skillview.boost_line(state, content, world) == "威力加成：內功 +12%（根骨）"  # 沒有武學：不寫臂力
    state.player.member.wugong_id = "basic_fist"
    assert skillview.boost_line(state, content, world) == "威力加成：武學 +12%（臂力）・內功 +12%（根骨）"


def test_a_stat_below_the_base_shows_a_negative_percentage(state, content, world):
    state.player.member.wugong_id, state.player.member.neigong_id = "basic_fist", "basic_breath"
    state.player.stats.update({"str": 3, "con": 4})
    assert skillview.boost_line(state, content, world) == "威力加成：武學 -6%（臂力）・內功 -3%（根骨）"


def test_only_the_players_card_carries_the_boost_line(state, content, world):
    """同伴的卡這一版不寫加成那一行（同伴吃的是他自己的屬性，不是本人的臂力與共鳴）。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.stats.update({"str": 15, "con": 15, "good": 40})
    assert "威力加成" in skillview.member_card(state, content, world, "player")
    assert "威力加成" not in skillview.member_card(state, content, world, "mate")


def test_a_small_name_shows_its_half_points_instead_of_rounding_to_nothing(state, content, world):
    """共鳴是名聲 ÷ 2 %：善名 1 是 +0.5%、善名 15 是 +7.5%，不寫成「+0%」或湊整成 +8%。"""
    wugong = generate_from_name("清風拳", "武學", "清風拳", attribute="剛").model_copy(update={"affinity": ["剛", "陽"]})
    assert world.claim_skill_name(wugong)
    state.player.member.wugong_id = wugong.id
    state.player.insights, state.player.art_slots[wugong.id] = ["haoran"], ["haoran", None]  # 武學重構：正邪照槽裡的浩然
    state.player.stats["good"] = 1
    assert skillview.boost_line(state, content, world) == "威力加成：【清風拳】共鳴 +0.5%"
    state.player.stats["good"] = 15
    assert skillview.boost_line(state, content, world) == "威力加成：【清風拳】共鳴 +7.5%"


def _blended(world, state) -> MartialArt:
    """以前武學＋武學合出來的一門（2026-10-21 拿掉合成，登記過的照舊讀得到）：直接登記一門由粗淺拳腳與湖邊腿法衍生的。"""
    art = generate_from_name("踏浪拳", "武學", "踏浪拳").model_copy(
        update={"origin": "fused", "parents": ["basic_fist", "lake_kick"], "affinity": []},
    )
    assert world.claim_skill_name(art)
    state.player.arts.append(art.id)
    return art


def test_art_rows_name_the_parents_of_a_blended_art(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    art = _blended(world, state)
    rows = {row["id"]: row for row in skillview.art_rows(state, content, world)}
    assert "由【粗淺拳腳】與【湖邊腿法】衍生" in rows[art.id]["card"]
    assert "衍生" not in rows["basic_fist"]["card"] and "衍生" not in rows["lake_kick"]["card"]


def test_the_worn_slot_card_of_a_blended_art_names_both_parents(state, content, world):
    """身上那一欄的功法卡（detail）也寫「由…衍生」，不只清單裡的（art_rows）；穿的不是合成的就不寫。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    art = _blended(world, state)
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
    assert card.split("\n")[2] == "來源：合成（甲 首創）　由【旋風腿】與【烈火拳】衍生"


# ── 武學的功效（武學與成長設計 13.6；計畫六 Task 4）：功法卡一行功效、爐子寫已知配方的功效 ──────────────


def test_the_art_card_lists_its_traits(state, content, world):
    art = generate_from_name("裂石拳", "武學", "裂石拳", attribute="剛").model_copy(
        update={"origin": "fused", "traits": ["剛", "快"], "special": "lianhuan"},
    )
    card = skillview.art_card(art, 1, None, None, traits.card_line(content, art))
    assert "功效：〔破甲〕" in card and "〔先手〕" in card and "〔連環〕" in card


def test_the_trait_line_sits_after_the_source_and_before_the_note(content):
    art = _crafted("以柔勁纏住兵刃，借力卸力。").model_copy(update={"origin": "fused", "traits": ["柔"]})  # 武學重構：功效照槽填，純函式直接寫
    lines = skillview.art_card(art, 3, None, None, traits.card_line(content, art)).split("\n")
    assert lines[2].startswith("來源：") and lines[3].startswith("功效：〔化勁〕") and lines[-1] == "以柔勁纏住兵刃，借力卸力。"
    assert len(lines) == 5  # 名字、成數與威力、來源、功效、說明


def test_a_card_without_a_trait_line_is_exactly_as_before():
    """沒給功效那一行（舊呼叫、內容沒有功效）：功法卡一個字不變，不留空行。"""
    art = _crafted("以柔勁纏住兵刃，借力卸力。")
    assert skillview.art_card(art, 3) == skillview.art_card(art, 3, None, None, "")
    assert len(skillview.art_card(art, 3).split("\n")) == 4  # 名字、成數與威力、來源、說明


def test_the_worn_slot_cards_carry_the_traits_too(state, content, world):
    """F9：身上那一欄的功法卡（detail，網頁的 slot_cards）也有功效那一行，跟修練頁的清單（art_rows）一樣。"""
    state.player.member.wugong_id = "basic_fist"
    assert f"\n{traits.EMPTY_LINE}" in skillview.detail(state, content, world, "武學")  # 武學重構：槽空著就寫槽空著
    state.player.insights, state.player.art_slots["basic_fist"] = ["feng"], ["feng", None]
    text = skillview.detail(state, content, world, "武學")
    assert "\n功效：〔先手〕剋中對手後有 10% 的機會連環（這一回合再推一次）" in text  # 槽裡的風 ●：一層、下品 ×1


def test_the_card_in_the_practice_list_follows_the_players_own_quality(state, content, world):
    """數字跟品質一起變：同一門武學修練到上品，功效的數字乘 2。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.insights, state.player.art_slots["basic_fist"] = ["feng"], ["feng", None]  # 武學重構：功效照槽裡的意境
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == "basic_fist"]
    assert "功效：〔先手〕剋中對手後有 10% 的機會連環" in row["card"]
    state.player.art_quality["basic_fist"] = "上品"
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == "basic_fist"]
    assert "功效：〔先手〕剋中對手後有 20% 的機會連環" in row["card"]


def test_the_card_of_a_fused_art_lists_every_trait_and_the_special(state, content, world):
    # 武學重構：功效照槽填——火 ●● 是兩層破甲、風是先手、秘方合出來的意境帶特別功效（悟招）；中品三格
    art = generate_from_name("裂石拳", "武學", "裂石拳", attribute="剛").model_copy(update={"origin": "fused", "affinity": ["剛", "快", "虛"]})
    world.claim_skill_name(art)
    secret, _ = world.claim_insight_recipe("秘|x", Insight(id="秘影", name="秘影", attribute="虛", secret_special="wuzhao", parents=["a", "b"]))
    state.player.arts, state.player.art_quality[art.id] = [art.id], "中品"
    state.player.insights, state.player.insight_strength["huo"] = ["huo", "feng", secret.id], 2
    state.player.art_slots[art.id] = ["huo", "feng", secret.id]
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == art.id]
    assert "〔破甲〕強攻剋中對手時，有 30% 的機會" in row["card"] and "〔先手〕" in row["card"] and "〔悟招〕每被對手剋中一次" in row["card"]
    assert [s["skill"] for s in row["slots"]] == ["破甲二重", "先手一重", "悟招"] and row["slots"][0]["mark"] == "二重"


# ── W6：新武學跟身上同一種的那一門比 ─────────────────────────────────
# 比的是「第一成對第一成」：新合出來的從第一成起，身上那門可能已經練到第七成，拿現在的威力比，新的永遠像退步；
# 同在第一成比的才是兩門功夫本身的差別（品質、微調）與功效。數字一律是 martial_arts.power_at 照自己那一份的品質算的。


def _registered(world, name, attribute, kind="武學", **over):
    """一門下品、指定屬性的全服登記功法（武學重構：屬性＝相容屬性的第一個，所以相容屬性寫它自己那一個）。"""
    art = generate_from_name(name, kind, name, weights={"下品": 100, "中品": 0, "上品": 0, "絕學": 0}, attribute=attribute)
    art = art.model_copy(update={"affinity": [attribute], **over})
    assert world.claim_skill_name(art)
    return art


def _signed(number: float) -> str:
    return f"{number:+.1f}".replace("-", "−")


def test_the_compare_line_sets_the_new_art_against_the_worn_one_at_the_first_level(state, content, world):
    art = _registered(world, "旋風腿", "快")
    state.player.member.wugong_id, state.player.arts = "basic_fist", [art.id]
    # 武學重構：功效照槽裡的意境——旋風腿裝著風（先手）、身上的粗淺拳腳裝著山（穩）
    state.player.insights, state.player.art_slots = ["feng", "shan"], {art.id: ["feng", None], "basic_fist": ["shan", None]}
    worn = team.player_art(state, content, world, "basic_fist")
    diff = power_at(art, 1) - power_at(worn, 1)
    assert round(diff, 1) != 0  # 微調讓兩門不一樣強；下面「一樣強」另外測
    assert team.compare_with_worn(state, content, world, art) == (
        f"比身上的【粗淺拳腳】：威力 {_signed(diff)}（第一成）、多了〔先手〕、少了〔穩〕"
    )


def test_the_compare_line_only_names_what_differs(state, content, world):
    """功效只列「有沒有」：新的多出來的、少掉的；兩邊一樣的不寫。威力一樣就說一樣，不寫 +0.0。"""
    state.player.member.wugong_id = "basic_fist"
    twin = _registered(world, "拳腳二式", "實", base_power=8.0, top_power=24.0)
    worn = team.player_art(state, content, world, "basic_fist")
    assert (power_at(twin, 1), power_at(worn, 1)) == (8.0, 8.0)
    assert team.compare_with_worn(state, content, world, twin) == "比身上的【粗淺拳腳】：威力相同（第一成）"
    # 武學重構：功效照槽裡的意境（風＝先手、水＝化勁、秘方合出來的意境帶特別功效連環）；基礎武學槽空著就什麼都沒有
    secret, _ = world.claim_insight_recipe("秘|y", Insight(id="環影", name="環影", attribute="虛", secret_special="lianhuan", parents=["a", "b"]))
    state.player.insights = ["feng", "shui", secret.id]
    stacked = _registered(world, "拳腳三式", "快", base_power=8.0, top_power=24.0)
    state.player.art_slots[stacked.id] = ["feng", None]
    assert team.compare_with_worn(state, content, world, stacked) == "比身上的【粗淺拳腳】：威力相同（第一成）、多了〔先手〕"
    plain = _registered(world, "拳腳四式", "柔", base_power=8.0, top_power=24.0, affinity=["柔", "虛"])
    state.player.art_slots[plain.id] = ["shui", secret.id]
    assert team.compare_with_worn(state, content, world, plain) == (
        "比身上的【粗淺拳腳】：威力相同（第一成）、多了〔化勁〕〔連環〕"
    )


def test_the_compare_line_uses_the_players_own_quality_for_both_arts(state, content, world):
    """數字照自己那一份的品質算（跟功法卡寫的威力同一個來源）：身上那門修練到中品，它的第一成威力就是中品的那一檔。"""
    art = _registered(world, "旋風腿", "快")
    state.player.member.wugong_id, state.player.arts = "basic_fist", [art.id]
    state.player.art_quality["basic_fist"] = "中品"
    worn = team.player_art(state, content, world, "basic_fist")
    assert worn.quality == "中品" and power_at(worn, 1) > 8
    expected = _signed(power_at(art, 1) - power_at(worn, 1))
    assert f"威力 {expected}（第一成）" in team.compare_with_worn(state, content, world, art)


def test_the_compare_line_matches_the_kind_of_slot_and_is_silent_without_one(state, content, world):
    art = _registered(world, "旋風腿", "快")
    inner = _registered(world, "回風吐納", "快", kind="內功")
    state.player.arts = [art.id, inner.id]
    assert team.compare_with_worn(state, content, world, art) == ""  # 武學欄空著：新的直接上身，沒有東西可比
    state.player.member.neigong_id = "basic_breath"
    assert team.compare_with_worn(state, content, world, art) == ""  # 內功欄有東西、武學欄還是空的：武學不跟內功比
    assert team.compare_with_worn(state, content, world, inner).startswith("比身上的【粗淺吐納】：威力 ")
    state.player.member.wugong_id = "basic_fist"
    assert team.compare_with_worn(state, content, world, art).startswith("比身上的【粗淺拳腳】：威力 ")
    assert team.compare_with_worn(state, content, world, team.player_art(state, content, world, "basic_fist")) == ""  # 身上的那門自己


def test_the_practice_page_cards_compare_library_arts_with_the_worn_one_but_not_the_worn_one(state, content, world):
    art = _registered(world, "旋風腿", "快")
    state.player.member.wugong_id, state.player.arts = "basic_fist", [art.id]
    rows = {r["id"]: r for r in skillview.art_rows(state, content, world)}
    note = team.compare_with_worn(state, content, world, art)
    assert note and note in rows[art.id]["card"].split("\n")
    assert "比身上的" not in rows["basic_fist"]["card"]  # 身上那門自己的卡不比
    lines = rows[art.id]["card"].split("\n")
    assert lines.index(note) > next(i for i, line in enumerate(lines) if line.startswith("功效："))  # 功效那一行之後
    assert skillview.detail(state, content, world, "武學").count("比身上的") == 0


def test_a_card_without_a_compare_line_is_exactly_as_before():
    art = _crafted("以柔勁纏住兵刃，借力卸力。")
    assert skillview.art_card(art, 3, compare_line="") == skillview.art_card(art, 3)
    with_line = skillview.art_card(art, 3, compare_line="比身上的【甲】：威力 +1.0（第一成）").split("\n")
    assert with_line[-2] == "比身上的【甲】：威力 +1.0（第一成）" and with_line[-1] == "以柔勁纏住兵刃，借力卸力。"  # 說明句還是最後一行


def test_art_rows_carry_slots_affinity_and_rating_instead_of_forge_odds(state, content, world):
    """武學重構：卷軸卡沒有合成機率條了（forge_odds／forge_with／forge_fixed 都不給）；每列多相容屬性、意境槽與戰力。
    戰力＝威力 ×（1＋槽裡技能的加成）（arts.rating）：裝了一個 ● 的意境多 general_weight。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "haoran"]
    row = next(r for r in skillview.art_rows(state, content, world) if r["id"] == "basic_fist")
    assert "forge_odds" not in row and "forge_with" not in row and "forge_fixed" not in row
    assert row["affinity"] == "兼容並蓄" and row["slots"] == [None, None]
    bare = row["rating"]
    assert bare == round(power_at(team.player_art(state, content, world, "basic_fist"), 1))
    state.player.art_slots["basic_fist"] = ["feng", None]
    row = next(r for r in skillview.art_rows(state, content, world) if r["id"] == "basic_fist")
    assert row["rating"] == round(bare * (1 + content.config.arts.general_weight)) and row["slots"][0]["name"] == "風"
    assert row["rating"] == arts_mod.rating(content, team.player_art(state, content, world, "basic_fist"), 1, state, world)


# ── 秘方特效只算會發動的那一條（Joy 2026-10-28「可以加，但是你要讓玩家能清楚知道」）──────────────────


def _two_specials(state, world):
    """一門中品三格：火、秘方 A（悟招）、秘方 B（連環）。打的時候只有槽裡第一條（悟招）發動。"""
    art = generate_from_name("裂石拳", "武學", "裂石拳", attribute="剛").model_copy(update={"origin": "fused", "affinity": ["剛", "虛"]})
    world.claim_skill_name(art)
    a, _ = world.claim_insight_recipe("秘|a", Insight(id="秘甲", name="秘甲", attribute="虛", secret_special="wuzhao", parents=["a", "b"]))
    b, _ = world.claim_insight_recipe("秘|b", Insight(id="秘乙", name="秘乙", attribute="虛", secret_special="lianhuan", parents=["c", "d"]))
    state.player.arts, state.player.art_quality[art.id] = [art.id], "中品"
    state.player.insights = ["huo", a.id, b.id]
    state.player.art_slots[art.id] = ["huo", a.id, b.id]
    return art, a.id, b.id


def test_only_the_first_secret_special_fires_and_scores(state, content, world):
    art, first, second = _two_specials(state, world)
    mine = team.player_art(state, content, world, art.id)
    assert mine.special == "wuzhao" and mine.extra_specials == []  # 打的時候只有第一條
    assert arts_mod.idle_specials(state, content, world, mine) == {2: "同一門只發動一條秘方特效（這一門發動的是〔悟招〕）：這一條不發動，評分也不算"}
    with_both = arts_mod.score(state, content, world, mine)
    state.player.art_slots[art.id] = ["huo", first, None]
    assert arts_mod.score(state, content, world, team.player_art(state, content, world, art.id)) == with_both  # 第二條不加分


def test_the_card_says_which_secret_special_is_idle(state, content, world):
    art, _first, second = _two_specials(state, world)
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == art.id]
    assert [s["idle"] for s in row["slots"]] == ["", "", arts_mod.IDLE_SPECIAL.format(live="悟招")]
    assert [t.get("idle", False) for t in row["slots"][2]["fx"] if t.get("special")] == [True]
    assert [t.get("idle", False) for t in row["slots"][1]["fx"] if t.get("special")] == [False]
    assert row["score_note"] == skillview.SCORE_NOTE
    (ins,) = [r for r in skillview.insight_rows(state, content, world) if r["id"] == second]
    assert ins["idle"] and [e.get("idle") for e in ins["effects"] if e["special"]] == [True]
    state.player.art_slots[art.id] = ["huo", None, second]  # 只剩一條：它就是發動的那一條，什麼都不寫
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == art.id]
    assert row["score_note"] == "" and not any(s and s["idle"] for s in row["slots"])


def test_signature_arts_score_each_trait_as_a_full_cell(world):
    """本命（有本命戰法、不是小戰法）每個功效當成滿的一格（三重＋真意）：三個功效 156（Joy 2026-10-27「50 幾分很掉價」）。
    小戰法照舊。"""
    from conftest import real_content
    from tianxia.state import new_game_state

    c = real_content("season21")
    s = new_game_state(c, "甲")
    signature = [k for k, v in c.skills.items() if v.tactic is not None and not v.tactic.minor]
    minor = [k for k, v in c.skills.items() if v.tactic is not None and v.tactic.minor]
    assert len(signature) == 36 and {arts_mod.score(s, c, world, team.player_art(s, c, world, k)) for k in signature} == {156}
    assert all(arts_mod.score(s, c, world, team.player_art(s, c, world, k)) < 100 for k in minor)
