from tianxia import library
from tianxia.martial_arts import generate_from_name

LOW = {"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}


def _fused(world, name):
    art = generate_from_name(name, "武學", name, weights=LOW, attribute="快").model_copy(
        update={"origin": "fused", "insight": "feng"},
    )
    world.claim_skill_name(art)
    return art


def test_holding_cap_grows_every_five_levels(content):
    assert [library.holding_cap(content, lv) for lv in (1, 4, 5, 9, 10)] == [50, 50, 55, 55, 60]


def test_held_count_counts_what_is_worn_the_library_and_insights(state):
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    state.player.insights = ["feng", "huo"]
    assert library.held_count(state) == 4


def test_owned_arts_lists_the_worn_ones_first(state):
    state.player.member.neigong_id = "basic_breath"
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    assert library.owned_arts(state) == ["basic_breath", "basic_fist", "lake_kick"]


def test_full_is_true_at_the_cap_and_beyond(state, content):
    content.config.holding_cap_base = 2
    state.player.insights = ["feng"]
    assert not library.full(state, content)
    state.player.insights = ["feng", "huo"]
    assert library.full(state, content)
    state.player.insights = ["feng", "huo", "shui"]  # 奇遇給的意境不受上限擋，所以會超過
    assert library.full(state, content)


def test_store_art_fills_an_empty_slot_then_uses_the_library(state, content, world):
    library.store_art(state, _fused(world, "旋風腿"), "中品")
    assert state.player.member.wugong_id == "旋風腿" and state.player.art_quality["旋風腿"] == "中品"
    library.store_art(state, _fused(world, "疾風腳"))
    assert state.player.arts == ["疾風腳"] and "疾風腳" not in state.player.art_quality


def test_store_art_sends_a_neigong_to_the_neigong_slot(state, content, world):
    art = _fused(world, "寒玉訣").model_copy(update={"kind": "內功"})
    library.store_art(state, art)
    member = state.player.member
    assert member.neigong_id == "寒玉訣" and member.neigong_level == 1 and member.wugong_id is None


def test_store_art_does_not_keep_a_quality_that_matches_the_registered_one(state, world):
    art = _fused(world, "旋風腿")
    library.store_art(state, art, art.quality)
    assert state.player.art_quality == {}


def test_store_art_does_not_stack_the_same_art_twice(state, world):
    state.player.member.wugong_id = "basic_fist"
    art = _fused(world, "旋風腿")
    library.store_art(state, art)
    library.store_art(state, art)
    assert state.player.arts == ["旋風腿"]


def test_store_art_does_not_add_an_art_that_is_already_worn(state, world):
    """Task 6 審查的小毛病：已經配在身上的武學再收一次，會在功法庫裡多出一份，改練時被換下來又疊一份。"""
    art = _fused(world, "旋風腿")
    state.player.member.wugong_id = "旋風腿"
    state.player.member.wugong_level = 4
    assert library.store_art(state, art, "中品") == []
    assert state.player.arts == [] and state.player.member.wugong_level == 4
    assert state.player.art_quality == {}  # 已經有的那一份，品質也不被覆寫


def test_learning_a_basic_art_costs_silver(state, content):
    state.player.location = "lake"
    state.player.stats["silver"] = 30
    (skill, problem), = library.lessons_here(state, content)
    assert skill.id == "lake_kick" and problem is None
    library.learn(state, content, "lake_kick")
    assert state.player.member.wugong_id == "lake_kick" and state.player.stats["silver"] == 20
    assert library.lessons_here(state, content) == []  # 會了就不再列


def test_a_learned_art_goes_to_the_library_when_the_slot_is_taken(state, content):
    state.player.location = "lake"
    state.player.stats["silver"] = 30
    state.player.member.wugong_id = "basic_fist"
    library.learn(state, content, "lake_kick")
    assert state.player.member.wugong_id == "basic_fist" and state.player.arts == ["lake_kick"]
    assert library.owned_arts(state) == ["basic_fist", "lake_kick"]


def test_lessons_explain_why_they_are_refused(state, content):
    state.player.location = "lake"
    content.skills["lake_kick"].learn.fame = 5
    assert "名望 5" in library.lessons_here(state, content)[0][1]
    content.skills["lake_kick"].learn.fame = 0
    content.skills["lake_kick"].learn.faction = "guan"
    assert "只教投靠" in library.lessons_here(state, content)[0][1]
    state.player.faction = "guan"
    state.player.stats["silver"] = 30
    assert library.lessons_here(state, content)[0][1] is None


def test_a_lesson_you_cannot_afford_says_the_fee(state, content):
    state.player.location = "lake"
    state.player.stats["silver"] = 3
    problem = library.lessons_here(state, content)[0][1]
    assert "10 兩" in problem and "3 兩" in problem


def test_learn_refuses_what_it_cannot_teach_and_changes_nothing(state, content):
    state.player.location = "lake"
    state.player.stats["silver"] = 3
    assert "學不了" in library.learn(state, content, "lake_kick")[0]
    assert state.player.stats["silver"] == 3 and library.owned_arts(state) == []
    assert "沒有人教" in library.learn(state, content, "basic_fist")[0]  # 這裡不教
    state.player.location = "town"
    assert "沒有人教" in library.learn(state, content, "lake_kick")[0]  # 不在教的地點


def test_nothing_new_can_be_learned_when_full(state, content):
    state.player.location = "lake"
    state.player.stats["silver"] = 30
    content.config.holding_cap_base = 1
    state.player.insights = ["feng"]
    assert "滿了" in library.lessons_here(state, content)[0][1]


def test_starter_arts_are_taught_free_in_any_town(state, content):
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    state.player.location = "town"
    state.player.member.neigong_id = "basic_breath"
    taught = {skill.id: problem for skill, problem in library.lessons_here(state, content)}
    assert taught == {"basic_fist": None}
    silver = state.player.stats["silver"]
    library.learn(state, content, "basic_fist")
    assert state.player.stats["silver"] == silver


def test_a_worn_art_cannot_be_melted(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    msgs = library.melt_art(state, content, world, "basic_fist")
    assert state.player.member.wugong_id == "basic_fist" and "先改練" in msgs[0]


def test_an_art_waiting_to_be_named_cannot_be_melted(state, content, world):
    """審查：練成絕學、等著取名的那門（PlayerState.naming）不能熔，要先定名。其他庫裡的照樣能熔。"""
    _fused(world, "旋風腿")
    _fused(world, "裂地腿")
    state.player.arts = ["旋風腿", "裂地腿"]
    state.player.naming = "旋風腿"
    state.player.stats["xinde"] = 0
    msgs = library.melt_art(state, content, world, "旋風腿")
    assert len(msgs) == 1 and "先替它定名" in msgs[0] and "【旋風腿】" in msgs[0]
    assert state.player.arts == ["旋風腿", "裂地腿"] and state.player.naming == "旋風腿" and state.player.stats["xinde"] == 0
    assert "熔成了心得" in library.melt_art(state, content, world, "裂地腿")[0] and state.player.arts == ["旋風腿"]
    state.player.naming = None
    assert "熔成了心得" in library.melt_art(state, content, world, "旋風腿")[0]


def test_melting_something_you_do_not_have_changes_nothing(state, content, world):
    state.player.stats["xinde"] = 0
    assert "沒有" in library.melt_art(state, content, world, "旋風腿")[0]
    assert "沒有" in library.melt_insight(state, content, world, "feng")[0]
    assert state.player.stats["xinde"] == 0


def test_melting_refunds_eighty_percent_of_practice_plus_a_quality_bonus(state, content, world):
    _fused(world, "旋風腿")
    state.player.arts = ["旋風腿"]
    state.player.art_levels["旋風腿"] = 5  # 練到第 5 成花了 1+2+3+4 = 10
    state.player.art_quality["旋風腿"] = "中品"
    state.player.art_mastery["旋風腿"] = 2
    state.player.stats["xinde"] = 0
    library.melt_art(state, content, world, "旋風腿")
    assert state.player.stats["xinde"] == 8 + 5
    assert "旋風腿" not in state.player.arts
    assert {"旋風腿"} & (set(state.player.art_levels) | set(state.player.art_quality) | set(state.player.art_mastery)) == set()


def test_melting_pays_the_bonus_of_the_grade_you_raised_the_art_to_and_nothing_for_the_rest(state, content, world):
    """企劃者 2026-10-05（改了設計 4.3）：品質加給只算你自己修練出來的那幾階——現在的品質減去登記的品質。
    合成的武學登記在下品，所以修練到中品、第一成熟練度（沒花練成的心得）熔掉，退中品那 5 點，
    加上 FB-068 墊在練成那一份底下的基本值 4。"""
    bonus, floor = content.config.melt_quality_bonus, content.config.melt_min_refund
    _fused(world, "旋風腿")
    state.player.arts = ["旋風腿"]
    state.player.art_quality["旋風腿"] = "中品"
    state.player.stats["xinde"] = 0
    msgs = library.melt_art(state, content, world, "旋風腿")
    assert state.player.stats["xinde"] == floor + bonus["中品"] - bonus["下品"] == 9
    assert f"心得 +{floor + bonus['中品']}" in msgs


def test_a_content_art_handed_out_at_its_top_grade_pays_no_bonus_when_melted(state, content, world):
    """本命武學（情誼送的絕學）、劇情教的絕學：登記就是絕學，沒修練過，熔了只退練成花的八成，沒有品質加給。"""
    state.player.arts = ["fist"]
    state.player.stats["xinde"] = 0
    library.melt_art(state, content, world, "fist")
    assert state.player.stats["xinde"] == 0  # 第一成：什麼都沒花
    state.player.arts, state.player.art_levels["fist"] = ["fist"], 5  # 練到第 5 成花了 10
    library.melt_art(state, content, world, "fist")
    assert state.player.stats["xinde"] == 8


def test_melt_refund_counts_only_the_grades_above_the_registered_one(content):
    bonus = content.config.melt_quality_bonus
    assert library.melt_refund(content, 1, "下品") == 0
    assert library.melt_refund(content, 1, "絕學") == bonus["絕學"]  # registered 預設是下品（合成的武學）
    assert library.melt_refund(content, 1, "上品", registered="中品") == bonus["上品"] - bonus["中品"]
    assert library.melt_refund(content, 1, "絕學", registered="絕學") == 0
    assert library.melt_refund(content, 1, "下品", registered="絕學") == 0  # 不會是負的
    assert library.melt_refund(content, 5, "中品", registered="中品") == 8  # 練成的八成照退


def test_melting_an_insight_pays_and_warns_about_the_arts_that_need_it(state, content, world):
    _fused(world, "旋風腿")
    state.player.arts = ["旋風腿"]
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 0
    msgs = library.melt_insight(state, content, world, "feng")
    assert state.player.insights == [] and state.player.stats["xinde"] == 10
    assert any("旋風腿" in m and "不能再修練" in m for m in msgs)


def test_melting_an_insight_nobody_needs_has_no_warning(state, content, world):
    state.player.insights = ["huo"]
    msgs = library.melt_insight(state, content, world, "huo")
    assert not any("不能再修練" in m for m in msgs)


# ── 熟練度與熔煉的共用判斷（武學與成長計畫 T11）──────────────────


def test_level_of_reads_the_worn_slot_the_stored_level_or_nothing(state):
    """一份查表給修練頁與功法卡共用：身上的看欄位、庫裡的看換下來時存的（沒存過從第一成算）、不是自己的是 None。"""
    member = state.player.member
    member.neigong_id, member.neigong_level = "basic_breath", 4
    member.wugong_id, member.wugong_level = "basic_fist", 7
    state.player.arts = ["lake_kick", "旋風腿"]
    state.player.art_levels["旋風腿"] = 3
    assert library.level_of(state, "basic_breath") == 4
    assert library.level_of(state, "basic_fist") == 7
    assert library.level_of(state, "lake_kick") == 1
    assert library.level_of(state, "旋風腿") == 3
    assert library.level_of(state, "ghost") is None


def test_melt_problem_is_the_one_place_that_decides_what_cannot_be_melted(state):
    """熔煉頁的按鈕與 melt_art 的拒絕共用同一個判斷：身上的、不是自己的、等著定名的都不行；其餘 None。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["旋風腿", "裂地腿"]
    state.player.naming = "旋風腿"
    assert "先改練" in library.melt_problem(state, "basic_fist")
    assert "沒有這一門" in library.melt_problem(state, "ghost")
    assert "先替它定名" in library.melt_problem(state, "旋風腿")
    assert library.melt_problem(state, "裂地腿") is None


def test_melt_problem_names_the_art_when_it_is_given_one(state):
    state.player.arts = ["旋風腿"]
    state.player.naming = "旋風腿"
    assert "【旋風腿】" in library.melt_problem(state, "旋風腿", name="旋風腿")


# ── FB-068：熔掉沒練成過的合成武學有基本值（企劃者 2026-10-05）──────────────────


def test_the_melt_minimum_is_four_by_default(content):
    assert content.config.melt_min_refund == 4 < content.config.fuse_xinde  # 合成花 5、熔回最多 4：一圈淨虧 1


def test_melting_a_fused_art_that_was_never_practised_refunds_the_minimum(state, content, world):
    _fused(world, "旋風腿")
    state.player.arts, state.player.stats["xinde"] = ["旋風腿"], 0
    assert library.melt_value(state, content, world, "旋風腿") == 4
    msgs = library.melt_art(state, content, world, "旋風腿")
    assert state.player.stats["xinde"] == 4 and msgs[-1] == "心得 +4"


def test_the_minimum_is_a_floor_under_the_practice_part_and_the_own_grade_bonus_still_adds(state, content, world):
    """max(4, 練成花的八成) ＋ 自己修上去的品質加給：第五成（練成花 10、八成是 8）照退 8，不是 12；
    第二成（花 1、八成是 0）退 4；修到中品的第一成退 4 ＋ 5。"""
    _fused(world, "旋風腿")
    state.player.arts = ["旋風腿"]
    for level, quality, refund in ((5, "下品", 8), (2, "下品", 4), (1, "中品", 4 + 5), (5, "上品", 8 + 15)):
        state.player.art_levels["旋風腿"], state.player.art_quality["旋風腿"] = level, quality
        assert library.melt_value(state, content, world, "旋風腿") == refund, (level, quality)


def test_a_content_art_gets_no_minimum_so_learning_and_melting_is_no_loop(state, content, world):
    """基礎武學有的免費教、拜師學藝也不花體力：要是它們也有基本值，「學、熔、再學」就是無本的心得迴圈。
    基本值只給全服登記的武學（合成出來的、舊的自創與煉製），內容裡的武學照舊。"""
    state.player.arts, state.player.stats["xinde"] = ["lake_kick"], 0
    assert library.melt_value(state, content, world, "lake_kick") == 0
    library.melt_art(state, content, world, "lake_kick")
    assert state.player.stats["xinde"] == 0
