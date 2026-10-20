"""合成（武學重構之後只剩兩種：武學＋武學 → 新武學、意境＋意境 → 揣摩或複合意境）。
武學＋意境不再是合成（裝進槽：fusion.FUSE_GONE、Game.slot_insight）；品質擲骰、合到舊的、師門配方、血統擋、深度都拿掉了，
那些測試一併刪除（見 PM 的改寫簡報）。這裡的 named／model_down／must_not_ask／Fixed／other_player 給 test_secret_recipes、
test_one_art 借用。"""
from unittest import mock

import pytest

from tianxia import arts as arts_mod
from tianxia import fusion, insights, library, naming, skillview, team
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


class AskedTheModel(BaseException):
    """naming._ask 把模型呼叫丟出的所有 Exception 當成「這次沒拿到」吞掉（連 AssertionError 也是），所以「不該叫模型」的假 client
    要丟 _ask 接不住的東西：BaseException 不是 Exception，會一路穿到測試、測試才會真的失敗。"""


def must_not_ask():
    client = mock.Mock()
    client.chat_structured.side_effect = AskedTheModel("配方已經有了，不該再叫模型")
    return client


class Fixed:
    """rng.choices 永遠挑 pick 那一個。武學重構之後合成不擲品質了（blend 的 rng 不用）；留著給 test_secret_recipes 的打造那一段用。"""

    def __init__(self, pick):
        self.pick, self.weights = pick, None

    def choices(self, population, weights):
        self.weights = dict(zip(population, weights))
        return [self.pick]


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


def _registered(world, name, affinity, kind="武學"):
    """全服登記一門帶相容屬性的合成武學（門面）：武學重構之後武學的屬性＝affinity[0]。"""
    art = generate_from_name(name, kind, name).model_copy(update={
        "origin": "fused", "creator": "丙", "creator_shown": "丙", "affinity": list(affinity),
        "attribute": affinity[0] if affinity else "",
    })
    made, first = world.claim_recipe(f"兼|測試{name}", art)
    assert made is not None and first
    return made


# ── 武學＋武學（設計 12.3；武學重構定案第三節）────────────────────────


def test_blending_two_arts_keeps_both_and_adds_a_new_one(ready, content, world):
    ready.player.arts = ["lake_kick"]
    art, msgs = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert (art.name, art.kind, art.parents, art.base) == ("踏浪拳", "武學", ["basic_fist", "lake_kick"], "basic_fist")
    assert ready.player.member.wugong_id == "basic_fist" and "lake_kick" in ready.player.arts  # 兩門都留著
    assert art.id in ready.player.arts
    assert ready.player.stats["xinde"] == 100 - content.config.fuse_xinde
    assert world.lookup_recipe(fusion.blend_key("basic_fist", "lake_kick")).name == "踏浪拳"
    assert "第一次" in msgs[0] and "（下品）" in msgs[0]  # 兩門都下品：合出來下品
    assert world.get_skill(art.id).quality == "下品"  # 全服登記的那一份一律下品


def test_a_blended_art_is_a_facade_with_no_traits_until_you_slot_insights(ready, content, world):
    """武學重構：登記的只是門面（功效、正邪、特別功效都空著），身上的樣子由槽裡的意境決定（arts.apply）。"""
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    stored = world.get_skill(art.id)
    assert (stored.traits, stored.special, stored.lean, stored.insight) == ([], None, "無", None)
    assert team.player_art(ready, content, world, art.id).traits == []
    assert arts_mod.slot(ready, content, world, art.id, "feng") == [arts_mod.SLOTTED_LINE.format(insight="風", art="踏浪拳", i=1)]
    mine = team.player_art(ready, content, world, art.id)
    assert mine.traits == ["快"] and arts_mod.slots_of(ready, content, mine) == ["feng", None]  # 下品兩格


def test_blend_affinity_is_the_union_unless_either_art_takes_anything(ready, content, world):
    """相容屬性合起來（Joy 2026-10-20「合起來」）：兩門各收快、剛的合出來收快與剛；任一門兼容並蓄（基礎武學）合出來也兼容並蓄。"""
    fast, hard = _registered(world, "風拳", ["快"]), _registered(world, "烈拳", ["剛"])
    ready.player.arts = [fast.id, hard.id]
    ready.player.insights += ["shui"]
    art, _ = fusion.blend(ready, content, world, named("風烈拳"), fast.id, hard.id)
    assert art.affinity == ["快", "剛"] and art.attribute == "快" and world.get_skill(art.id).affinity == ["快", "剛"]
    assert arts_mod.slot_problem(ready, content, world, art.id, "feng") is None
    assert arts_mod.slot_problem(ready, content, world, art.id, "shui") == arts_mod.AFFINITY_LINE.format(
        name="風烈拳", insight="水", attrs="快、剛")
    wide, _ = fusion.blend(ready, content, world, named("風樁拳"), fast.id, "basic_fist")  # 基礎拳腳兼容並蓄
    assert wide.affinity == [] and wide.attribute == "" and arts_mod.affinity_text(wide) == "兼容並蓄"
    assert fusion.blend_affinity(fast, hard) == ["快", "剛"] and fusion.blend_affinity(hard, fast) == ["剛", "快"]
    assert fusion.blend_affinity(fast, None) == []


def _ripen(state, content, world, art_id, insight_ids):
    """練到第十成、意境槽裝滿（blend_grade 升一品的條件）。"""
    member = state.player.member
    if art_id == member.wugong_id:
        member.wugong_level = 10
    elif art_id == member.neigong_id:
        member.neigong_level = 10
    else:
        state.player.art_levels[art_id] = 10
    for insight_id in insight_ids:
        assert arts_mod.slot_problem(state, content, world, art_id, insight_id) is None
        arts_mod.slot(state, content, world, art_id, insight_id)


def test_blend_grade_takes_the_higher_and_rises_one_when_both_are_ripe(ready, content, world):
    """定案第三節：兩門取高（絕學算上品）；都第十成、槽都裝滿再升一品，最高上品。"""
    ready.player.arts = ["lake_kick"]
    fist, kick = (team.player_art(ready, content, world, a) for a in ("basic_fist", "lake_kick"))
    assert fusion.blend_grade(ready, content, "basic_fist", fist, "lake_kick", kick) == ("下品", False)
    ready.player.art_quality["lake_kick"] = "上品"
    kick = team.player_art(ready, content, world, "lake_kick")
    assert fusion.blend_grade(ready, content, "basic_fist", fist, "lake_kick", kick) == ("上品", False)
    ready.player.art_quality["lake_kick"] = "絕學"
    kick = team.player_art(ready, content, world, "lake_kick")
    assert fusion.blend_grade(ready, content, "basic_fist", fist, "lake_kick", kick) == ("上品", False)  # 絕學算上品
    del ready.player.art_quality["lake_kick"]
    ready.player.insights = ["feng", "huo", "shui", "shan"]
    _ripen(ready, content, world, "basic_fist", ["feng", "huo"])
    _ripen(ready, content, world, "lake_kick", ["shui", "shan"])
    fist, kick = (team.player_art(ready, content, world, a) for a in ("basic_fist", "lake_kick"))
    assert fusion.blend_grade(ready, content, "basic_fist", fist, "lake_kick", kick) == ("中品", True)
    ready.player.art_quality["basic_fist"] = "上品"
    fist = team.player_art(ready, content, world, "basic_fist")  # 上品四格：再裝兩個才算滿
    assert fusion.blend_grade(ready, content, "basic_fist", fist, "lake_kick", kick) == ("上品", False)


def test_a_ripe_blend_writes_the_grade_and_releases_the_slotted_insights(ready, content, world):
    """合出來的品級記在自己那一份（全服那一份照舊下品）；兩門上裝著的意境拆回背包（RELEASED_LINE），意境本身不會用掉。"""
    ready.player.arts = ["lake_kick"]
    ready.player.insights = ["feng", "huo", "shui", "shan"]
    _ripen(ready, content, world, "basic_fist", ["feng", "huo"])
    _ripen(ready, content, world, "lake_kick", ["shui", "shan"])
    art, msgs = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert "（中品）" in msgs[0] and fusion.RIPE_LINE in msgs
    assert team.art_quality(ready, art) == "中品" and ready.player.art_quality[art.id] == "中品"
    assert world.get_skill(art.id).quality == "下品"
    assert fusion.RELEASED_LINE.format(names="「風」「火」「水」「山」") in msgs
    assert "basic_fist" not in ready.player.art_slots and "lake_kick" not in ready.player.art_slots
    assert ready.player.insights == ["feng", "huo", "shui", "shan"]
    assert arts_mod.slot_count(content, "中品") == 3 and len(arts_mod.slots_of(ready, content, team.player_art(ready, content, world, art.id))) == 3


def test_a_blend_with_nothing_slotted_says_nothing_about_releasing(ready, content, world):
    ready.player.arts = ["lake_kick"]
    _, msgs = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert not any("拆了下來" in m for m in msgs) and fusion.RIPE_LINE not in msgs


def test_blend_kind_follows_the_first_art_unless_you_take_the_other(ready, content, world):
    """定案第三節：種類照玩家挑的那一門（take），沒挑跟第一門；base（兵器種類照它推）也是那一門。"""
    ready.player.member.neigong_id = "basic_breath"
    fist, breath = (team.player_art(ready, content, world, a) for a in ("basic_fist", "basic_breath"))
    assert fusion.blend_kind("basic_fist", fist, "basic_breath", breath, None) == ("武學", "basic_fist")
    assert fusion.blend_kind("basic_fist", fist, "basic_breath", breath, "basic_breath") == ("內功", "basic_breath")
    art, _ = fusion.blend(ready, content, world, named("渾元功"), "basic_fist", "basic_breath", take="basic_breath")
    assert (art.kind, art.base) == ("內功", "basic_breath") and art.parents == ["basic_breath", "basic_fist"]
    assert world.get_skill(art.id).kind == "內功"


def test_a_blend_takes_the_proposed_name_and_note_without_asking_the_model(ready, content, world):
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick", proposed=("「踏浪拳」", "拳腳並用。"))
    assert art.name == "踏浪拳" and art.note == "拳腳並用。"
    assert world.lookup_recipe(fusion.blend_key("basic_fist", "lake_kick")).note == "拳腳並用。"


def test_no_proposed_name_falls_back_to_the_word_table_without_asking_the_model(ready, content, world):
    """C 段拿到 (None, "")（B 段叫不動、逾時、取壞了）：鎖裡不叫模型，直接走退路字表；取了禁用的名字也一樣。"""
    ready.player.arts = ["lake_kick"]
    key = fusion.blend_key("basic_fist", "lake_kick")
    art, _ = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick", proposed=(None, ""))
    assert art.name == naming.fallback_name(content, key, "武學", tianji=world.read().tianji) and art.note == ""
    ready.player.member.neigong_id = "basic_breath"
    bad, _ = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "basic_breath", proposed=("九陰真經", "說明"))
    assert bad.name == naming.fallback_name(content, fusion.blend_key("basic_fist", "basic_breath"), "武學", tianji=world.read().tianji)


def test_a_blend_without_a_model_falls_back_to_the_word_table(ready, content, world):
    ready.player.arts = ["lake_kick"]
    key = fusion.blend_key("basic_fist", "lake_kick")
    art, _ = fusion.blend(ready, content, world, model_down(), "basic_fist", "lake_kick")
    assert art.name == naming.fallback_name(content, key, "武學", tianji=world.read().tianji)
    assert art.kind == "武學" and art.attribute == "" and art.note == ""
    bot, _ = fusion.blend(other_player(content), content, world, None, "basic_fist", "lake_kick") if False else (None, None)


def test_a_bot_without_a_model_still_blends_with_the_word_table(ready, content, world):
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, None, "basic_fist", "lake_kick")
    assert art.name == naming.fallback_name(content, fusion.blend_key("basic_fist", "lake_kick"), "武學", tianji=world.read().tianji)


def test_a_name_taken_by_someone_else_is_replaced(ready, content, world):
    ready.player.arts = ["lake_kick"]
    world.claim_skill_name(generate_from_name("踏浪拳", "武學", "踏浪拳"))
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert art is not None and art.name != "踏浪拳"


def test_a_failed_claim_charges_nothing_and_registers_nothing(ready, content, world):
    ready.player.arts = ["lake_kick"]
    with mock.patch.object(world, "claim_recipe", return_value=(None, False)):
        art, msgs = fusion.blend(ready, content, world, model_down(), "basic_fist", "lake_kick")
    assert art is None and msgs == [fusion.NO_NAMES]
    assert ready.player.stats["xinde"] == 100 and ready.player.arts == ["lake_kick"]


def test_a_second_player_blends_into_the_same_art_without_the_model(ready, content, world):
    """配方全服共享（設計 12.3）：乙先合出來，甲照同樣兩門合（不管順序）拿到同一門，不問模型、不再登記。"""
    other = other_player(content)
    other.player.arts = ["lake_kick"]
    made, _ = fusion.blend(other, content, world, named("踏浪拳"), "lake_kick", "basic_fist")
    ready.player.arts = ["lake_kick"]
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick")
    assert art.id == made.id and "這一門由乙首創" in msgs[0] and "第一次" not in msgs[0]
    assert [a.id for a in world.fused_arts()] == [made.id]
    assert ready.player.stats["xinde"] == 100 - content.config.fuse_xinde  # 照表拿到的也收一次


def test_two_players_racing_for_a_new_recipe_end_up_with_one_registered_art(ready, content, world):
    """審查重點 3：兩個人都看見「這個配方還沒人合過」、各自請模型取了名字，登記只有第一個算數；
    第二個拿到第一個登記的那一門，全服只有一筆。"""
    ready.player.arts = ["lake_kick"]
    first, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    other = other_player(content)
    other.player.arts = ["lake_kick"]
    with mock.patch.object(world, "lookup_recipe", return_value=None):  # 乙看這一眼時，甲還沒登記
        second, msgs = fusion.blend(other, content, world, named("湖風拳"), "basic_fist", "lake_kick")
    assert (second.id, second.name) == (first.id, "踏浪拳")
    assert world.get_skill("湖風拳") is None  # 乙取的名字沒有登記
    assert "踏浪拳" in other.player.arts and "首創" in msgs[0] and "第一次" not in msgs[0]


def test_an_anonymous_first_blender_is_shown_by_name(ready, content, world):
    """匿名行走只作用在地方傳聞（傳聞分層第七節）：首創寫給別人看的地方一律寫名號。"""
    ready.player.anonymous = True
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    stored = world.get_skill(art.id)
    assert (stored.creator, stored.creator_shown) == ("沈浪", "沈浪")
    other = other_player(content)
    other.player.arts = ["lake_kick"]
    _, msgs = fusion.blend(other, content, world, must_not_ask(), "basic_fist", "lake_kick")
    assert "這一門由沈浪首創" in msgs[0] and "某位少俠" not in msgs[0]


def test_a_blend_is_refused_for_what_you_already_have_and_judged_by_id(ready, content, world):
    """「已經有了」照 id 認（絕學定名只改顯示的名字）；排在花費與持有上限之前（同一爐連按兩下不重複扣）。"""
    ready.player.arts = ["lake_kick"]
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    problem = fusion.blend_problem(ready, content, world, "lake_kick", "basic_fist")
    assert "已經有了" in problem and problem.short == "已經有了"
    assert world.rename_skill(art.id, "凌波拳") and world.get_skill(art.id).name == "凌波拳"
    ready.player.stats["xinde"], ready.player.stamina = 0, 0
    assert "已經有了" in fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick")
    again, msgs = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick")
    assert again is None and "已經有了" in msgs[0]


def test_a_recipe_registered_meanwhile_that_you_already_hold_is_refused_without_charging(ready, content, world):
    """配方被別人先登記、拿到的那一門剛好是自己已經有的：不收心得、不重複收進功法庫。"""
    ready.player.arts = ["lake_kick"]
    first, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    ready.player.stats["xinde"] = 100
    with mock.patch.object(world, "lookup_recipe", return_value=None), \
         mock.patch.object(fusion, "blend_problem", return_value=None):
        art, msgs = fusion.blend(ready, content, world, named("湖風拳"), "basic_fist", "lake_kick")
    assert art is None and "已經有了" in msgs[0]
    assert ready.player.stats["xinde"] == 100 and ready.player.arts == ["lake_kick", first.id]


@pytest.mark.parametrize(("change", "reason"), [
    (lambda s, c: s.player.arts.remove("lake_kick"), "都要是你會的"),
    (lambda s, c: s.player.stats.update(xinde=0), "心得不足"),
    (lambda s, c: setattr(c.config, "holding_cap_base", 4), "滿了"),
])
def test_blend_explains_why_it_is_refused(ready, content, world, change, reason):
    ready.player.arts = ["lake_kick"]
    change(ready, content)
    assert reason in fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick")


def test_the_full_check_for_a_blend_follows_lore(ready, content, world):
    """持有上限含博聞（設計 6.3）：正好滿的時候多放一點博聞就能合成；博聞回到 5，又滿了，訊息寫的是同一個上限。"""
    ready.player.arts = ["lake_kick"]
    content.config.holding_cap_base = 4  # 兩門武學加兩個意境，正好滿
    assert "滿了" in fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick")
    ready.player.stats["lore"] = 6  # 多 2 格
    assert fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick") is None
    ready.player.stats["lore"] = 5
    assert "4/4" in fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick")


def test_blend_needs_two_different_arts_you_know(ready, content, world):
    ready.player.arts = ["lake_kick", "ghost"]  # ghost：存檔裡記著、內容與全服登記裡都沒有
    assert fusion.blend_problem(ready, content, world, "basic_fist", "basic_fist").short == "同一門"
    assert "都要是你會的" in fusion.blend_problem(ready, content, world, "basic_fist", "basic_breath")
    assert "找不到" in fusion.blend_problem(ready, content, world, "basic_fist", "ghost")
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "basic_breath")
    assert art is None and "都要是你會的" in msgs[0] and ready.player.stats["xinde"] == 100


def test_a_blend_costs_stamina_as_well_as_xinde(ready, content, world):
    ready.player.arts = ["lake_kick"]
    before = ready.player.stamina
    art, msgs = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert art is not None and ready.player.stamina == before - content.config.fuse_stamina
    assert f"心得 -{content.config.fuse_xinde}" in msgs and f"體力 -{content.config.fuse_stamina}" in msgs


def test_a_blend_without_enough_stamina_is_refused_and_changes_nothing(ready, content, world):
    ready.player.arts = ["lake_kick"]
    ready.player.stamina = content.config.fuse_stamina - 1
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick")
    assert art is None and msgs == [f"體力不足：合成一次要 {content.config.fuse_stamina}。"]
    assert ready.player.arts == ["lake_kick"] and ready.player.stats["xinde"] == 100
    assert world.lookup_recipe(fusion.blend_key("basic_fist", "lake_kick")) is None


def test_not_enough_xinde_is_still_reported_before_the_stamina_for_a_blend(ready, content, world):
    ready.player.arts = ["lake_kick"]
    ready.player.stamina, ready.player.stats["xinde"] = 0, 0
    assert "心得不足" in fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick")


def test_a_blend_is_refused_when_the_holdings_are_full(ready, content, world):
    """持有上限含放進爐裡的兩門：兩門武學加兩個意境＝4，上限 4 就是滿的。拒絕時什麼都不收、不登記、A 段也不開單。"""
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


def test_blending_and_melting_the_result_never_makes_xinde(ready, content, world):
    """合成花 5、熔掉剛合出來的（下品第一成、全服登記的）退基本值 4：一圈淨虧 1，沒有迴圈；照表再合照樣收錢。"""
    ready.player.arts = ["lake_kick"]
    seen = [ready.player.stats["xinde"]]
    for _ in range(3):
        art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
        assert art is not None
        library.melt_art(ready, content, world, art.id)
        seen.append(ready.player.stats["xinde"])
    assert seen == [100, 99, 98, 97] and ready.player.arts == ["lake_kick"]


# ── 兩門的先後（FB-073）────────────────────────────────────────


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


# ── 合成的結果放哪、跟身上那門比（W5、W6）────────────────────────


def test_a_blended_art_that_goes_into_the_library_is_compared_with_the_worn_one_then_points_the_way(ready, content, world):
    """W5、W6：收進功法庫之後先一句跟身上同一種那門的比較（第一成對第一成），最後一句指路。"""
    ready.player.arts = ["lake_kick"]
    art, msgs = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    note = team.compare_with_worn(ready, content, world, art)
    assert note.startswith("比身上的【粗淺拳腳】：威力") and "（第一成）" in note
    assert msgs[-3:] == ["【踏浪拳】收進功法庫。", note, library.SWITCH_HINT]


def test_a_blended_art_is_compared_with_the_slot_of_its_own_kind(ready, content, world):
    ready.player.member.neigong_id = "basic_breath"
    art, msgs = fusion.blend(ready, content, world, named("渾元功"), "basic_fist", "basic_breath", take="basic_breath")
    assert art.kind == "內功"
    assert msgs[-2].startswith("比身上的【粗淺吐納】：威力") and msgs[-1] == library.SWITCH_HINT


def test_a_blended_art_that_is_worn_at_once_gets_no_switch_hint(ready, content, world):
    """武學欄空著：新武學直接上身，不在功法庫裡，也就沒有「去功法庫改練」這句。"""
    ready.player.member.wugong_id, ready.player.member.wugong_level = None, 0
    ready.player.arts = ["basic_fist", "lake_kick"]
    art, msgs = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert ready.player.member.wugong_id == art.id and ready.player.member.wugong_level == 1
    assert all(library.SWITCH_HINT not in m and "功法庫" not in m and "比身上的" not in m for m in msgs)


def test_a_merge_and_other_ways_of_storing_an_art_get_no_switch_hint(ready, content, world):
    """意境合併沒有放進功法庫；學藝、事件教的武學收進功法庫也不是「煉製」的結果，不加這句。"""
    _, msgs = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert all(library.SWITCH_HINT not in m and "比身上的" not in m for m in msgs)
    stored = library.store_art(ready, generate_from_name("甲乙丙", "武學", "甲乙丙", 0))
    assert stored == ["【甲乙丙】收進功法庫。"]


def test_the_grade_of_a_blend_goes_with_it_into_the_library(ready, content, world):
    """store_art 帶品級：跟全服登記的不一樣才記在自己那一份；合出來的從第一成起修（成數記在 art_levels、沒記是第一成）。"""
    ready.player.arts = ["lake_kick"]
    ready.player.art_quality["lake_kick"] = "中品"
    art, _ = fusion.blend(ready, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    assert ready.player.art_quality[art.id] == "中品" and library.level_of(ready, art.id) == 1
    assert power_at(team.player_art(ready, content, world, art.id), 1) > power_at(world.get_skill(art.id), 1)


# ── 意境＋意境（設計 12.6；武學重構：同＋同是揣摩，不同是複合意境）────────────


def test_merge_fire_and_wind_makes_a_shared_yang_insight(ready, content, world):
    insight, msgs = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert (insight.name, insight.attribute, insight.lean, insight.parents) == ("燎原", "陽", "無", ["feng", "huo"])
    assert ready.player.insights == ["feng", "huo", "燎原"]  # 兩個都留著
    assert ready.player.stats["xinde"] == 100 - content.config.merge_xinde
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")).name == "燎原"
    assert "第一次" in msgs[0] and "屬陽" in msgs[0]
    assert arts_mod.is_compound(content, insight)  # 複合意境：高階技能（測試內容沒有 high 表時照一般功效算）


def test_merge_shape_is_the_same_whichever_way_round(content, world):
    feng, huo = insights.resolve("feng", content, world), insights.resolve("huo", content, world)
    assert fusion.merge_shape(world, feng, huo) == fusion.merge_shape(world, huo, feng) == ("陽", "無")


def test_merge_carries_the_lean(ready, content, world):
    ready.player.insights += ["haoran", "xuesha"]
    good, _ = fusion.merge(ready, content, world, named("正氣長風"), "haoran", "feng")
    plain, _ = fusion.merge(ready, content, world, named("陰陽一氣"), "haoran", "xuesha")
    assert (good.lean, plain.lean) == ("正", "無")
    assert good.attribute in ("陽", "快")  # 陽與快不在對照表裡：配方種子挑一個


def test_a_slotted_compound_insight_gives_its_attribute_and_lean_to_the_art(ready, content, world):
    """意境就是技能：合出來的複合意境裝進武學，武學身上的功效與正邪照它（arts.apply）。"""
    ready.player.insights += ["haoran"]
    good, _ = fusion.merge(ready, content, world, named("正氣長風"), "haoran", "feng")
    assert arts_mod.slot_problem(ready, content, world, "basic_fist", good.id) is None
    arts_mod.slot(ready, content, world, "basic_fist", good.id)
    mine = team.player_art(ready, content, world, "basic_fist")
    assert mine.traits == [good.attribute] and mine.lean == "正" and mine.attribute == ""  # 基礎拳腳兼容並蓄：自己沒有屬性
    assert "正派" in skillview.art_card(mine, 1)


def test_merging_an_insight_with_itself_deepens_it(ready, content, world):
    """同＋同＝揣摩（武學重構）：強度升一級、不取名、不登記、照樣收一次錢；到 ●●● 就不能再揣摩。"""
    before = ready.player.stamina
    insight, msgs = fusion.merge(ready, content, world, must_not_ask(), "feng", "feng")
    assert insight.id == "feng" and arts_mod.strength_of(ready, "feng") == 2
    assert msgs[0] == fusion.DEEPEN_LINE.format(name="風", mark="●●")
    assert ready.player.stats["xinde"] == 100 - content.config.merge_xinde and ready.player.stamina == before - content.config.merge_stamina
    assert ready.player.insights == ["feng", "huo"] and world.lookup_insight_recipe(fusion.merge_key("feng", "feng")) is None
    _, msgs = fusion.merge(ready, content, world, must_not_ask(), "feng", "feng")
    assert msgs[0] == fusion.DEEPEN_LINE.format(name="風", mark="●●●")
    problem = fusion.merge_problem(ready, content, world, "feng", "feng")
    assert problem == fusion.DEEPEST.format(name="風", mark="●●●") and problem.short == "已到極處"
    none, msgs = fusion.merge(ready, content, world, must_not_ask(), "feng", "feng")
    assert none is None and msgs == [problem] and ready.player.stats["xinde"] == 100 - 2 * content.config.merge_xinde


def test_a_deepened_insight_stays_slotted_and_counts_more_layers(ready, content, world):
    arts_mod.slot(ready, content, world, "basic_fist", "feng")
    fusion.merge(ready, content, world, must_not_ask(), "feng", "feng")
    mine = team.player_art(ready, content, world, "basic_fist")
    assert arts_mod.slots_of(ready, content, mine) == ["feng", None] and mine.traits == ["快", "快"]


def test_merge_is_refused_for_an_insight_you_already_hold(ready, content, world):
    fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    problem = fusion.merge_problem(ready, content, world, "feng", "huo")
    assert "已經悟得" in problem and problem.short == "已經有了"
    ready.player.stats["xinde"], ready.player.stamina = 0, 0
    assert "已經悟得" in fusion.merge_problem(ready, content, world, "feng", "huo")  # 排在花費之前


@pytest.mark.parametrize(("change", "reason"), [
    (lambda s, c: s.player.insights.remove("feng"), "都要是你悟得的"),
    (lambda s, c: s.player.stats.update(xinde=0), "心得不足"),
    (lambda s, c: setattr(c.config, "holding_cap_base", 3), "滿了"),
])
def test_merge_explains_why_it_is_refused(ready, content, world, change, reason):
    change(ready, content)
    assert reason in fusion.merge_problem(ready, content, world, "feng", "huo")


def test_a_stale_reference_is_refused_instead_of_crashing(ready, content, world):
    ready.player.insights.append("ghost_insight")
    assert "找不到" in fusion.merge_problem(ready, content, world, "feng", "ghost_insight")
    ready.player.arts.append("ghost")
    assert "找不到" in fusion.blend_problem(ready, content, world, "basic_fist", "ghost")


def test_a_second_player_merges_into_the_same_insight_without_the_model(ready, content, world):
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    other = other_player(content, ("feng", "huo"))
    second, msgs = fusion.merge(other, content, world, must_not_ask(), "feng", "huo")
    assert (second.id, second.creator) == (first.id, "沈浪")
    assert other.player.insights == ["feng", "huo", "燎原"] and "首悟" in msgs[0]


def test_an_anonymous_first_merger_is_shown_by_name(ready, content, world):
    ready.player.anonymous = True
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert (first.creator, first.creator_shown) == ("沈浪", "沈浪")
    _, msgs = fusion.merge(other_player(content, ("feng", "huo")), content, world, must_not_ask(), "feng", "huo")
    assert "這個意境由沈浪首悟" in msgs[0] and "某位少俠" not in msgs[0]


def test_merge_falls_back_to_the_word_table_when_the_model_is_down(ready, content, world):
    insight, _ = fusion.merge(ready, content, world, model_down(), "huo", "feng")
    assert insight.name == naming.fallback_name(content, fusion.merge_key("huo", "feng"), "意境", tianji=world.read().tianji)


def test_two_players_racing_for_a_new_merge_end_up_with_one_registered_insight(ready, content, world):
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    other = other_player(content, ("feng", "huo"))
    with mock.patch.object(world, "lookup_insight_recipe", return_value=None):  # 乙看這一眼時，甲還沒登記
        second, msgs = fusion.merge(other, content, world, named("野火"), "feng", "huo")
    assert (second.id, second.name, second.attribute, second.creator) == (first.id, "燎原", first.attribute, "沈浪")
    assert world.get_insight("野火") is None  # 乙取的名字沒有登記
    assert other.player.insights == ["feng", "huo", "燎原"]
    assert "首悟" in msgs[0] and "第一次" not in msgs[0]
    assert other.player.stats["xinde"] == 95


# ── 合併要花體力（企劃者 2026-10-05；FB-067 降到 5）──────────


def test_merge_stamina_is_half_a_cultivation_by_default(content):
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
    assert fusion.merge_problem(ready, content, world, "feng", "feng") is not None  # 揣摩也要體力
    assert arts_mod.strength_of(ready, "feng") == 1


def test_a_merge_with_exactly_enough_stamina_goes_through_and_leaves_none(ready, content, world):
    ready.player.stamina = content.config.merge_stamina
    insight, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert insight is not None and ready.player.stamina == 0


def test_not_enough_xinde_is_still_reported_before_the_stamina(ready, content, world):
    ready.player.stamina, ready.player.stats["xinde"] = 0, 0
    assert "心得不足" in fusion.merge_problem(ready, content, world, "feng", "huo")


# ── 武學＋意境不再是合成（武學重構）────────────────────────────


def test_fuse_is_gone_and_points_to_the_slots(ready, content, world):
    problem = fusion.fuse_problem(ready, content, world, "basic_fist", "feng")
    assert problem == fusion.FUSE_GONE and problem.short == "改裝槽"
    assert fusion.forge_request(ready, content, world, "basic_fist", ["feng"]) is None  # 不開取名的單子
    assert fusion.forge_request(ready, content, world, "basic_fist", ["feng", "huo"]) is None  # 形狀不對
    assert fusion.forge_request(ready, content, world, None, ["feng"]) is None
    assert fusion.fuse_key("basic_fist", "feng") == "融|basic_fist+feng"  # 舊配方鍵還讀得到（上線前登記的）


def test_the_engine_slots_an_insight_instead_of_fusing(game):
    """Game.forge(art, [ins])：直接把意境裝進那一門的槽，不花心得體力、不叫模型；江湖紀錄一則、不是「煉製」。"""
    p = game.state.player
    p.member.wugong_id, p.insights, p.stats["xinde"] = "basic_fist", ["feng"], 100
    stamina = p.stamina
    with mock.patch.object(game.client, "chat_structured", side_effect=AskedTheModel("裝意境不叫模型")):
        msgs = game.forge("basic_fist", ["feng"])
    assert msgs[0] == arts_mod.SLOTTED_LINE.format(insight="風", art="粗淺拳腳", i=1)
    assert p.art_slots["basic_fist"] == ["feng", None] and p.arts == [] and p.insights == ["feng"]
    assert (p.stats["xinde"], p.stamina) == (100, stamina) and game.forged and game.forged_thing is None
    assert game.forge_request("basic_fist", ["feng"]) is None
    again = game.forge("basic_fist", ["feng"])
    assert again == [arts_mod.DUP_LINE.format(name="粗淺拳腳", insight="風")] and not game.forged


# ── Game.forge：江湖紀錄與價錢 ────────────────────────────────


def test_the_engine_forge_picks_blend_or_merge(game):
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id = "basic_fist", "basic_breath"
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", [], other_art="basic_breath")
        game.forge(None, ["feng", "huo"])
        msgs = game.forge(None, ["feng"])
    assert len(p.arts) == 1 and len(p.insights) == 3
    assert "放一門武學和一個意境" in msgs[0] and "兩門武學" in msgs[0]


def test_the_engine_forge_is_titled_after_the_craft_tab_and_only_written_when_something_was_made(game):
    """FB-047：開爐的江湖紀錄標題是「煉製」（合成、合併都是）；被拒絕就只回一句話、不寫紀錄。"""
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id = "basic_fist", "basic_breath"
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    before = len(game.state.journal)
    game.forge("basic_fist", ["huo", "feng"])  # 一門武學配兩個意境：不是合成也不是合併
    assert len(game.state.journal) == before
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", [], other_art="basic_breath")
        blended = game.state.journal[0]
        game.forge(None, ["feng", "huo"])
        merged = game.state.journal[0]
        game.forge(None, ["feng", "feng"])
        deepened = game.state.journal[0]
    assert (blended.title, merged.title, deepened.title) == ("煉製", "煉製", "煉製")
    assert blended.tag.startswith("合成【") and merged.tag.startswith("合併「") and deepened.tag == "合併「風」"
    assert game.forged_thing == ("ins", "feng")
    length = len(game.state.journal)
    game.forge(None, ["feng", "huo"])  # 已經悟得了：被拒絕
    assert len(game.state.journal) == length


def test_the_engine_blends_two_arts_and_logs_it_under_the_furnace(game):
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id, p.stats["xinde"] = "basic_fist", "basic_breath", 100
    before = p.stamina
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge("basic_fist", [], other_art="basic_breath")
    entry = game.state.journal[0]
    assert entry.title == "煉製" and entry.tag.startswith("合成【")
    assert "心得 -5" in entry.changes and f"體力 -{game.content.config.fuse_stamina}" in entry.changes
    assert p.stamina == before - game.content.config.fuse_stamina
    assert len(library.owned_arts(game.state)) == 3 and game.forged and game.forged_thing == ("art", p.arts[0])


def test_the_engine_merge_journal_entry_shows_both_the_xinde_and_the_stamina(game):
    p = game.state.player
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    before = p.stamina
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        msgs = game.forge(None, ["feng", "huo"])
    entry = game.state.journal[0]
    assert entry.title == "煉製" and entry.tag.startswith("合併「")
    assert "心得 -5" in entry.changes and "體力 -5" in entry.changes  # FB-067：合併 5 點體力
    assert p.stamina == before - 5 and "體力 -5" in msgs


def test_the_engine_refused_merge_writes_no_journal_entry_and_spends_nothing(game):
    p = game.state.player
    p.insights, p.stats["xinde"], p.stamina = ["feng", "huo"], 100, 3
    length = len(game.state.journal)
    msgs = game.forge(None, ["feng", "huo"])
    assert any("體力不足" in m for m in msgs) and len(game.state.journal) == length
    assert (p.stamina, p.stats["xinde"], p.insights) == (3, 100, ["feng", "huo"])


def test_the_merge_melt_merge_loop_is_still_allowed_but_every_round_costs_stamina(game):
    """要拿心得就給他拿：合併（-5 心得、-5 體力）→ 熔掉那個意境（+10 心得）→ 再合同一組，沒有被擋；每一圈都付體力。"""
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


def test_the_engine_blend_then_melt_loop_only_ever_costs_xinde(game):
    """走真的 Game.forge／Game.melt_art：每一輪「合成、熔掉結果」心得只減不增（合成花 5、退基本值 4）。"""
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id, p.stats["xinde"] = "basic_fist", "basic_breath", 100
    seen = [p.stats["xinde"]]
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        for _ in range(3):
            game.forge("basic_fist", [], other_art="basic_breath")
            (new,) = p.arts
            game.melt_art(new)
            seen.append(p.stats["xinde"])
    assert p.arts == [] and seen == [100, 99, 98, 97]


# ── 首次取名在行動鎖外（最終審查 Critical 1）：A 鎖內備料 → B 鎖外取名 → C 鎖內重驗、登記、收費 ──────────


def test_forge_request_hands_out_a_naming_slip_only_when_the_model_is_needed(ready, content, world):
    """A 段只讀：會被拒絕、配方已經登記過、放的不是兩門武學或兩個意境、同一個意境揣摩，都不必叫模型（回 None）。"""
    ready.player.arts = ["lake_kick"]
    before = ready.model_dump_json()
    blend = fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick")
    assert (blend.kind, blend.key, blend.name_kind) == ("blend", fusion.blend_key("basic_fist", "lake_kick"), "武學")
    fist, kick = (team.player_art(ready, content, world, a) for a in ("basic_fist", "lake_kick"))
    assert blend.messages == fusion._blend_messages(fist, kick, "武學") and blend.choices == ()
    assert "兩門合而為一" in blend.messages[-1]["content"]
    merge = fusion.forge_request(ready, content, world, None, ["huo", "feng"])
    assert (merge.kind, merge.key, merge.name_kind) == ("merge", fusion.merge_key("huo", "feng"), "意境")
    assert ready.model_dump_json() == before  # 什麼都沒動
    assert fusion.forge_request(ready, content, world, None, ["feng", "feng"]) is None  # 揣摩不取名
    assert fusion.forge_request(ready, content, world, "basic_fist", [], other_art="basic_breath") is None  # 會被拒絕
    assert fusion.forge_request(ready, content, world, "basic_fist", ["feng"], other_art="lake_kick") is None  # 形狀不對
    other = other_player(content, ("feng", "huo"))
    other.player.arts = ["lake_kick"]
    fusion.blend(other, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    fusion.merge(other, content, world, named("燎原"), "huo", "feng")
    assert fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick") is None  # 別人登記過了：查表就好
    assert fusion.forge_request(ready, content, world, None, ["feng", "huo"]) is None


def test_forge_request_for_a_blend_takes_the_kind_you_picked(ready, content, world):
    ready.player.member.neigong_id = "basic_breath"
    plain = fusion.forge_request(ready, content, world, "basic_fist", [], other_art="basic_breath")
    taken = fusion.forge_request(ready, content, world, "basic_fist", [], other_art="basic_breath", take="basic_breath")
    assert (plain.name_kind, taken.name_kind) == ("武學", "內功")
    assert "衍生出一門新的內功" in taken.messages[-1]["content"]


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
    """配方這一季已經有人登記：查表就好，不問模型；你還沒有它，所以 blend_problem 不攔。"""
    other = other_player(content)
    other.player.arts = ["lake_kick"]
    fusion.blend(other, content, world, named("踏浪拳"), "basic_fist", "lake_kick")
    ready.player.arts = ["lake_kick"]
    assert fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick") is None
    assert fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick") is None


def test_the_naming_slip_is_exactly_the_prompt_the_blend_and_the_merge_send(ready, content, world):
    """A 段開的單子、B 段送出去的、C 段（沒給 proposed 時）自己送的是同一份提示。"""
    ready.player.arts = ["lake_kick"]
    request = fusion.forge_request(ready, content, world, "basic_fist", [], other_art="lake_kick")
    client = named("踏浪拳")
    fusion.blend(ready, content, world, client, "basic_fist", "lake_kick")
    assert request.messages == client.chat_structured.call_args.args[0]
    request = fusion.forge_request(ready, content, world, None, ["feng", "huo"])
    client = named("燎原")
    fusion.merge(ready, content, world, client, "feng", "huo")
    assert request.messages == client.chat_structured.call_args.args[0]


def test_a_proposed_name_is_used_without_asking_the_model(ready, content, world):
    ready.player.arts = ["lake_kick"]
    art, msgs = fusion.blend(ready, content, world, must_not_ask(), "basic_fist", "lake_kick", proposed=("「踏浪拳」", "腿影如風。"))
    assert (art.name, art.note) == ("踏浪拳", "腿影如風。") and "第一次" in msgs[0]
    insight, _ = fusion.merge(ready, content, world, must_not_ask(), "huo", "feng", proposed=("燎原", "野火燒原。"))
    assert (insight.name, insight.note) == ("燎原", "野火燒原。")


def _brew_two_recipes_that_got_the_same_model_name(content, world, order):
    """同一個玩家、兩個不同的配方（拳腳＋腿法、拳腳＋吐納），模型碰巧給了同一個名字；照 order 的順序登記。"""
    state = new_game_state(content, "沈浪")
    state.player.member.wugong_id, state.player.member.neigong_id = "basic_fist", "basic_breath"
    state.player.arts, state.player.stats["xinde"] = ["lake_kick"], 100
    for other in order:
        fusion.blend(state, content, world, must_not_ask(), "basic_fist", other, proposed=("踏浪拳", "一句話。"))
    return {other: world.lookup_recipe(fusion.blend_key("basic_fist", other)).name for other in order}


def test_two_recipes_given_the_same_model_name_get_a_fallback_that_does_not_depend_on_who_came_first(content, tmp_path):
    """Infra 第 3 點：兩個不同的配方同時拿到同一個模型名字。先登記的拿到它；後到的換成退路字表的名字——
    種子是它自己的配方鍵＋這一季的天機、鹽從 0 起，所以換個順序再跑一次，後到的那一個拿到的退路名字一樣是它自己的那一個。"""
    from tianxia.sqlite_world import open_world

    names = {}
    for order in (("lake_kick", "basic_breath"), ("basic_breath", "lake_kick")):
        world = open_world(tmp_path / f"{order[0]}.db")
        world.mutate(lambda shared: setattr(shared, "tianji", 3))
        names[order] = _brew_two_recipes_that_got_the_same_model_name(content, world, order)
    fallback = {o: naming.fallback_name(content, fusion.blend_key("basic_fist", o), "武學", tianji=3) for o in ("lake_kick", "basic_breath")}
    assert names[("lake_kick", "basic_breath")] == {"lake_kick": "踏浪拳", "basic_breath": fallback["basic_breath"]}
    assert names[("basic_breath", "lake_kick")] == {"basic_breath": "踏浪拳", "lake_kick": fallback["lake_kick"]}
    assert fallback["lake_kick"] != naming.fallback_name(content, fusion.blend_key("basic_fist", "lake_kick"), "武學")  # 天機有算進去


def test_the_three_steps_run_without_a_server(game):
    """假人也叫 AI 取名：bot_runner 不經過 HTTP 也要走同樣的三段。這裡只拿 Game 與它的全服儲存：
    A 在行動鎖裡（Game.forge_request）→ B 在鎖外（naming.generate）→ C 再進行動鎖（Game.forge(..., proposed=, other_art=)）。"""
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id, p.stats["xinde"] = "basic_fist", "basic_breath", 100
    world = game.world
    with world.action_lock():
        request = game.forge_request("basic_fist", [], other_art="basic_breath")
    assert request is not None and request.kind == "blend"
    model = mock.Mock(timeout=120)

    def reply(messages, response_model, **kwargs):
        assert not world.db.writing()  # B 段沒拿著寫入交易
        return naming.NameReply(name="吐納拳", description="一吐一納，拳隨氣走。")

    model.chat_structured.side_effect = reply
    proposed = naming.generate(model, game.content, request, budget=game.content.config.naming_budget_seconds)
    assert proposed == ("吐納拳", "一吐一納，拳隨氣走。")
    with world.action_lock():
        msgs = game.forge("basic_fist", [], proposed=proposed, other_art="basic_breath")
    (made,) = p.arts
    assert world.get_skill(made).name == "吐納拳" and p.stats["xinde"] == 95 and "第一次" in msgs[0]
    assert world.lookup_recipe(fusion.blend_key("basic_fist", "basic_breath")).note == "一吐一納，拳隨氣走。"
    assert game.forge_request("basic_fist", [], other_art="basic_breath") is None  # 配方登記了：不必再問
    assert game.forge_request("basic_fist", [], other_art=made) is not None  # 另一組還沒人合過


def test_forge_request_on_the_game_needs_a_model_client(game):
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id, p.stats["xinde"] = "basic_fist", "basic_breath", 100
    assert game.forge_request("basic_fist", [], other_art="basic_breath") is not None
    assert game.forge_request(None, ["feng", "huo"]) is None  # 沒悟到：會被拒絕
    game.client = None  # 沒有 client（伺服器假人鎖內的 Game 就是這樣）：預設不開單；假人程式在鎖外自己叫模型，給 named_outside=True 才開
    assert game.forge_request("basic_fist", [], other_art="basic_breath") is None
    assert game.forge_request("basic_fist", [], other_art="basic_breath", named_outside=True) is not None


def test_the_naming_budget_fits_under_the_tunnels_cut(content):
    """trycloudflare 約 100 秒就切斷一個請求；取名的預算 60 秒，留下 A、C 兩段等行動鎖的餘裕。"""
    assert content.config.naming_budget_seconds == 60


# ── 狀態列的「可以開爐」提示（can_forge）────────────────────────


def test_can_forge_looks_only_at_the_shape_of_what_you_hold(ready, content, world):
    assert fusion.can_forge(ready, content)  # 有意境、付得起
    ready.player.insights = []
    assert not fusion.can_forge(ready, content)  # 只有一門武學、沒有意境：合不了
    ready.player.arts = ["lake_kick"]
    assert fusion.can_forge(ready, content)  # 兩門武學
    ready.player.stats["xinde"] = 0
    assert not fusion.can_forge(ready, content)


def test_a_fixed_art_cannot_be_blended(ready, content, world):
    """定案第一節：寫死的武學（本命、內容寫死的非下品）不能當合成的料；拒絕帶兩三個字的 short（清單上標）。"""
    ready.player.arts = ["fist"]  # 測試內容的長拳沒寫品級＝絕學、寫死
    problem = fusion.blend_problem(ready, content, world, "basic_fist", "fist")
    assert problem == fusion.FIXED_LINE.format(name="長拳") and problem.short == "不能當料"
    content.skills["fist"].quality = "下品"  # 下品的內容武學有空槽、不寫死，照舊合得
    assert fusion.blend_problem(ready, content, world, "basic_fist", "fist") is None


def test_slot_refusals_carry_a_short_word(ready, content, world):
    """裝槽的拒絕也帶 short（skillview.forge_picks 照它標，不再一律「合不了」）。"""
    from tianxia import arts
    ready.player.art_slots["basic_fist"] = ["feng", None]
    assert arts.slot_problem(ready, content, world, "basic_fist", "feng").short == "已裝上"
    ready.player.art_slots["basic_fist"] = ["feng", "huo"]
    ready.player.insights.append("shui")
    assert arts.slot_problem(ready, content, world, "basic_fist", "shui").short == "槽滿了"
