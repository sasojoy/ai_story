"""煉製（tianxia/craft.py）：配方快取、品質位移、屬性規則、命名過濾、全服共享。

LLM 一律 mock 掉——真正要驗的是「引擎決定所有數值、LLM 只給名字」這件事本身。
"""
import random
from unittest import mock

import pytest

from tianxia import craft, materials
from tianxia.martial_arts import CREATED_QUALITY_WEIGHTS, QUALITIES, generate_from_name
from tianxia.ollama_client import OllamaClient


def naming(name: str, description: str = "一句話說明。"):
    """讓 LLM 永遠回同一個名字。"""
    return mock.patch.object(
        OllamaClient, "chat_structured",
        lambda self, messages, response_model, **kw: craft.CraftedName(name=name, description=description),
    )


def llm_down():
    """LLM 連不上（chat_structured 丟例外）。"""
    def boom(self, messages, response_model, **kw):
        raise RuntimeError("Ollama 連不上")

    return mock.patch.object(OllamaClient, "chat_structured", boom)


@pytest.fixture
def stocked(state, content):
    """背包裡每種素材各 4 個、心得 500，夠煉好幾次。"""
    for mid in content.materials:
        materials.grant(state, content, mid, 4)
    state.player.stats["xinde"] = 500
    return state


# ── 配方鍵與成本 ──────────────────────────────────────────


def test_recipe_key_does_not_care_about_order(content):
    assert craft.recipe_key(["gang_2", "gang_1"], "武學") == craft.recipe_key(["gang_1", "gang_2"], "武學")


def test_recipe_key_separates_the_two_kinds(content):
    assert craft.recipe_key(["gang_1", "gang_1"], "武學") != craft.recipe_key(["gang_1", "gang_1"], "內功")


def test_cost_counts_the_tiers(content):
    cfg = content.config
    cfg.craft_xinde_base, cfg.craft_xinde_per_tier = 5, 3
    assert craft.cost(content, ["gang_1", "gang_3"]) == 5 * 2 + 3 * 4
    assert craft.cost(content, ["gang_3", "gang_3"]) == 5 * 2 + 3 * 6


def test_an_all_common_recipe_costs_no_xinde(content):
    """企劃者 2026-10-03 決定「凡品免心得」：素材先到、心得後到，撿到凡品就該煉得動。"""
    assert craft.cost(content, ["gang_1", "gang_1"]) == 0
    assert craft.cost(content, ["gang_1", "kuai_1"]) == 0
    assert craft.cost(content, ["gang_1", "gang_2"]) > 0  # 有一樣靈品就照公式收


def test_a_common_recipe_can_be_crafted_with_no_xinde(state, content, world):
    materials.grant(state, content, "gang_1", 2)
    state.player.stats["xinde"] = 0
    assert craft.can_craft(state, content, ["gang_1", "gang_1"], "武學") is None
    with naming("裂江訣"):
        art, msgs = craft.craft(state, content, world, OllamaClient(), ["gang_1", "gang_1"], "武學")
    assert art is not None and state.player.stats["xinde"] == 0
    assert not any(m.startswith("心得 -") for m in msgs)


# ── 品質：素材的階位移機率分佈（整個系統的平衡核心）────────


def test_the_first_tier_weights_are_exactly_todays_self_created_weights():
    """隨手撿的凡品煉出來的東西，不該比自己取個名字強——所以 1.0 那一列刻意相等。"""
    assert craft.quality_weights(1.0) == CREATED_QUALITY_WEIGHTS


def test_weights_are_in_quality_order_because_the_roll_is_cumulative():
    assert list(craft.quality_weights(2.4)) == list(QUALITIES)


def test_higher_tiers_shift_weight_towards_the_good_qualities():
    low, high = craft.quality_weights(1.0), craft.quality_weights(3.0)
    assert high["絕學"] > low["絕學"] and high["上品"] > low["上品"]
    assert high["下品"] < low["下品"]


def test_weights_interpolate_between_the_anchors():
    mid = craft.quality_weights(2.5)
    two, three = craft.quality_weights(2.0), craft.quality_weights(3.0)
    assert two["絕學"] < mid["絕學"] < three["絕學"]
    assert sum(mid.values()) == pytest.approx(100, abs=1)


def test_weights_clamp_outside_the_anchor_range():
    assert craft.quality_weights(0.5) == craft.quality_weights(1.0)
    assert craft.quality_weights(9.0) == craft.quality_weights(3.0)


def test_two_top_tier_materials_really_do_beat_two_bottom_ones(content):
    """抽一萬個名字比期望品質，確認「蒐集材料變強」沒有斷掉。"""
    def expected(weights):
        rank = {q: i for i, q in enumerate(QUALITIES)}
        rng = random.Random(0)
        names = [f"測試{rng.random()}" for _ in range(10000)]
        got = [generate_from_name(n, "武學", n, weights=weights).quality for n in names]
        return sum(rank[q] for q in got) / len(got)

    low = content.materials["gang_1"]
    high = content.materials["gang_3"]
    assert expected(craft.quality_weights(craft.mean_tier(high, high))) > expected(
        craft.quality_weights(craft.mean_tier(low, low))
    )


def test_counter_materials_get_a_tier_bonus(content):
    """fixture 沒有柔，所以直接造一個相剋的素材來驗規則本身。"""
    gang = content.materials["gang_2"]
    rou = gang.model_copy(update={"id": "rou_2", "attribute": "柔"})
    assert craft.mean_tier(gang, gang) == 2.0
    assert craft.mean_tier(gang, rou) == 2.5


def test_the_tier_bonus_cannot_push_past_the_top_anchor(content):
    gang = content.materials["gang_3"]
    rou = gang.model_copy(update={"id": "rou_3", "attribute": "柔"})
    assert craft.mean_tier(gang, rou) == 3.0


# ── 屬性由素材決定 ────────────────────────────────────────


def test_same_attribute_materials_decide_the_attribute(content):
    assert craft.result_attribute(content.materials["gang_1"], content.materials["gang_3"]) == "剛"


def test_an_opposed_pair_is_decided_by_the_higher_tier(content):
    """相剋是相互的（剛克柔、柔也克剛），所以沒有單方面的「克方」——改成階高者勝。"""
    gang2 = content.materials["gang_2"]
    rou1 = content.materials["gang_1"].model_copy(update={"id": "rou_1", "attribute": "柔"})
    assert craft.result_attribute(gang2, rou1) == "剛"
    assert craft.result_attribute(rou1, gang2) == "剛"


def test_an_opposed_pair_of_the_same_tier_leaves_it_to_the_name(content):
    gang = content.materials["gang_2"]
    rou = gang.model_copy(update={"id": "rou_2", "attribute": "柔"})
    assert craft.result_attribute(gang, rou) is None


def test_unrelated_attributes_leave_it_to_the_name(content):
    assert craft.result_attribute(content.materials["gang_1"], content.materials["kuai_1"]) is None


# ── 命名過濾（一定要在永久登記之前）────────────────────────


@pytest.mark.parametrize("raw", ["【龍吟九霄】", " 龍吟九霄 ", "「龍吟九霄」"])
def test_clean_name_strips_the_wrapping(raw):
    assert craft.clean_name(raw) == "龍吟九霄"


def test_clean_name_converts_simplified_characters():
    assert craft.clean_name("龙吟九霄") == "龍吟九霄"


@pytest.mark.parametrize(
    ("name", "why"),
    [("一", "長度"), ("七個字的功法名稱", "長度"), ("Fist", "中文"), ("劍法X", "中文"), ("九陰真經", "專有名詞"),
     ("小龍女心法", "專有名詞")],
)
def test_bad_names_are_rejected(content, name, why):
    assert craft.name_problem(name, content) is not None, why


def test_a_name_that_collides_with_content_is_rejected(content):
    assert craft.name_problem("精鐵砂", content) is not None  # 素材
    assert craft.name_problem("長拳", content) is not None  # 本命武學


def test_a_good_name_passes(content):
    assert craft.name_problem("裂江訣", content) is None


def test_the_fallback_name_is_deterministic_and_passes_the_filter(content):
    key = craft.recipe_key(["gang_1", "gang_1"], "武學")
    first = craft.fallback_name(content, key, "武學")
    assert first == craft.fallback_name(content, key, "武學")
    assert craft.name_problem(first, content) is None


def test_the_fallback_name_differs_by_kind_and_salt(content):
    key = craft.recipe_key(["gang_1", "gang_1"], "武學")
    assert craft.fallback_name(content, key, "武學") != craft.fallback_name(content, key, "內功")
    assert craft.fallback_name(content, key, "武學") != craft.fallback_name(content, key, "武學", salt=1)


def test_a_banned_name_from_the_llm_falls_back_to_the_deterministic_one(stocked, content, world):
    client = OllamaClient()
    with naming("九陰真經"):
        art, msgs = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert art is not None and art.name != "九陰真經"
    assert art.name == craft.fallback_name(content, craft.recipe_key(["gang_1", "gang_1"], "武學"), "武學")


def test_a_simplified_name_is_registered_in_traditional_characters(stocked, content, world):
    client = OllamaClient()
    with naming("裂江诀"):  # 「诀」是簡體
        art, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert art is not None and art.name == "裂江訣"
    assert "裂江訣" in world.read().created_skills


# ── 煉製的檢查 ────────────────────────────────────────────


def test_crafting_needs_two_materials(state, content):
    assert craft.can_craft(state, content, ["gang_1"], "武學") is not None
    assert craft.can_craft(state, content, ["gang_1", "gang_1", "gang_1"], "武學") is not None


def test_crafting_needs_a_real_kind(stocked, content):
    assert craft.can_craft(stocked, content, ["gang_1", "gang_1"], "輕功") is not None


def test_crafting_needs_the_materials_in_hand(state, content):
    state.player.stats["xinde"] = 500
    materials.grant(state, content, "gang_1", 1)
    assert craft.can_craft(state, content, ["gang_1", "gang_1"], "武學") is not None  # 只有一個
    materials.grant(state, content, "gang_1", 1)
    assert craft.can_craft(state, content, ["gang_1", "gang_1"], "武學") is None


def test_crafting_needs_enough_xinde(stocked, content):
    stocked.player.stats["xinde"] = craft.cost(content, ["gang_3", "gang_3"]) - 1
    problem = craft.can_craft(stocked, content, ["gang_3", "gang_3"], "武學")
    assert problem is not None and "心得不足" in problem


def test_a_failed_check_changes_nothing(state, content, world):
    client = OllamaClient()
    art, msgs = craft.craft(state, content, world, client, ["gang_1", "gang_1"], "武學")
    assert art is None and len(msgs) == 1
    assert state.player.materials == {} and world.read().recipes == {}


# ── 煉製成功 ──────────────────────────────────────────────


def test_crafting_spends_the_materials_and_the_xinde(stocked, content, world):
    client = OllamaClient()
    before = stocked.player.stats["xinde"]
    with naming("裂江訣"):
        art, msgs = craft.craft(stocked, content, world, client, ["gang_3", "gang_3"], "武學")
    assert art is not None
    assert materials.held(stocked, "gang_3") == 2  # 原本 4 個，吃掉 2 個
    assert stocked.player.stats["xinde"] == before - craft.cost(content, ["gang_3", "gang_3"])
    assert f"心得 -{craft.cost(content, ['gang_3', 'gang_3'])}" in msgs


def test_the_materials_decide_the_attribute_not_the_name(stocked, content, world):
    client = OllamaClient()
    with naming("裂江訣"):
        art, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_3"], "武學")
    by_name_alone = generate_from_name("裂江訣", "武學", "裂江訣")
    assert art is not None and art.attribute == "剛"
    # 名字單獨生成時剛好不是剛，才證明屬性真的來自素材（fixture 的名字是挑過的）
    assert by_name_alone.attribute != "剛"


def test_the_crafted_art_records_who_first_made_it(stocked, content, world):
    client = OllamaClient()
    with naming("裂江訣"):
        art, msgs = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert art is not None and art.creator == stocked.player.name
    assert art.note == "一句話說明。"
    assert "江湖上第一次煉成" in "\n".join(msgs)


def test_an_empty_slot_gets_the_art_equipped_right_away(stocked, content, world):
    client = OllamaClient()
    with naming("裂江訣"):
        art, msgs = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert stocked.player.member.wugong_id == art.id
    assert stocked.player.member.wugong_level == 1
    assert stocked.player.arts == []


def test_a_second_art_of_the_same_kind_goes_to_the_library(stocked, content, world):
    client = OllamaClient()
    with naming("裂江訣"):
        craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    with naming("沉山勢"):
        art2, msgs = craft.craft(stocked, content, world, client, ["gang_2", "gang_2"], "武學")
    assert art2 is not None and stocked.player.arts == [art2.id]
    assert "功法庫" in "\n".join(msgs)


def test_a_neigong_and_a_wugong_both_get_equipped(stocked, content, world):
    client = OllamaClient()
    with naming("裂江訣"):
        craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    with naming("玄淵經"):
        craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "內功")
    member = stocked.player.member
    assert member.wugong_id == "裂江訣" and member.neigong_id == "玄淵經"


# ── 配方快取：全服共享（設計 §十二 第 1 點）──────────────────


def test_the_recipe_is_registered_server_wide(stocked, content, world):
    client = OllamaClient()
    with naming("裂江訣"):
        craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    key = craft.recipe_key(["gang_1", "gang_1"], "武學")
    assert world.read().recipes[key] == "裂江訣"
    assert world.lookup_recipe(key) is not None


def test_a_cached_recipe_never_calls_the_llm_again(stocked, content, world):
    client = OllamaClient()
    with naming("裂江訣"):
        first, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    stocked.player.member.wugong_id = None  # 散功：這樣這個配方才又煉得起來（否則會被擋，見下面那個測試）
    with mock.patch.object(OllamaClient, "chat_structured", side_effect=AssertionError("不該再呼叫 LLM")):
        second, msgs = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert second is not None and second.name == first.name
    assert second.quality == first.quality and second.attribute == first.attribute
    assert "首創" in "\n".join(msgs)


def test_another_player_crafting_the_same_recipe_gets_the_same_art(stocked, content, world):
    """配方的結果全服共享：第二個人拿到同一門功法，首創者記在 creator 上。"""
    from tianxia.state import new_game_state

    client = OllamaClient()
    with naming("裂江訣"):
        mine, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")

    other = new_game_state(content, "另一個玩家")
    materials.grant(other, content, "gang_1", 2)
    other.player.stats["xinde"] = 500
    with mock.patch.object(OllamaClient, "chat_structured", side_effect=AssertionError("不該再呼叫 LLM")):
        theirs, msgs = craft.craft(other, content, world, client, ["gang_1", "gang_1"], "武學")
    assert theirs is not None and theirs.name == mine.name
    assert theirs.creator == stocked.player.name  # 仍然記著首創者
    assert "首創" in "\n".join(msgs)


def test_a_name_already_taken_by_someone_elses_self_created_art_is_worked_around(stocked, content, world):
    """取名自創仍然是獨佔的，所以煉製撞到那個名字時要自己換一個。"""
    from tianxia import team

    team.create_skill(stocked, content, world, "裂江訣", "內功")  # 別人（這裡是自己）先占走名字
    client = OllamaClient()
    with naming("裂江訣"):
        art, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert art is not None and art.name != "裂江訣"
    # LLM 的名字用掉了第一次嘗試，所以退路組名從 salt=1 開始（仍然是決定性的）
    assert art.name == craft.fallback_name(content, craft.recipe_key(["gang_1", "gang_1"], "武學"), "武學", salt=1)


# ── LLM 不可用 ────────────────────────────────────────────


def test_crafting_works_with_the_llm_down(stocked, content, world):
    client = OllamaClient()
    with llm_down():
        art, msgs = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert art is not None
    assert art.name == craft.fallback_name(content, craft.recipe_key(["gang_1", "gang_1"], "武學"), "武學")
    assert art.note == ""


def test_the_llm_returning_nothing_also_falls_back(stocked, content, world):
    client = OllamaClient()
    with mock.patch.object(OllamaClient, "chat_structured", return_value=None):
        art, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert art is not None


def test_the_same_recipe_crafted_offline_twice_is_identical(stocked, content, world):
    client = OllamaClient()
    with llm_down():
        first, _ = craft.craft(stocked, content, world, client, ["gang_2", "gang_2"], "內功")
        stocked.player.member.neigong_id = None  # 散功，不然同一門功法不准重煉
        second, _ = craft.craft(stocked, content, world, client, ["gang_2", "gang_2"], "內功")
    assert first is not None and second is not None
    assert (first.name, first.quality, first.attribute) == (second.name, second.quality, second.attribute)


# ── 改練（功法庫 → 身上）──────────────────────────────────


def craft_two_wugong(state, content, world):
    """煉兩門武學：第一門自動配上身，第二門進功法庫。"""
    client = OllamaClient()
    with naming("裂江訣"):
        first, _ = craft.craft(state, content, world, client, ["gang_1", "gang_1"], "武學")
    with naming("沉山勢"):
        second, _ = craft.craft(state, content, world, client, ["gang_2", "gang_2"], "武學")
    return first, second


def test_switching_swaps_the_equipped_art_with_the_library_one(stocked, content, world):
    from tianxia import team

    first, second = craft_two_wugong(stocked, content, world)
    msgs = team.switch_art(stocked, content, world, second.id)
    member = stocked.player.member
    assert member.wugong_id == second.id
    assert stocked.player.arts == [first.id]
    assert f"改練【{second.name}】" in "\n".join(msgs)


def test_switching_keeps_each_arts_level(stocked, content, world):
    """熟練度各自保留：換回來不用重練（設計 §六）。"""
    from tianxia import team

    first, second = craft_two_wugong(stocked, content, world)
    stocked.player.member.wugong_level = 7  # 把第一門練到第七成
    team.switch_art(stocked, content, world, second.id)
    assert stocked.player.member.wugong_level == 1  # 新的那門從第一成開始
    team.switch_art(stocked, content, world, first.id)
    assert stocked.player.member.wugong_level == 7  # 換回來還是第七成
    assert stocked.player.art_levels[second.id] == 1


def test_switching_into_an_empty_slot_needs_no_swap(stocked, content, world):
    from tianxia import team

    client = OllamaClient()
    with naming("玄淵經"):
        art, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "內功")
    stocked.player.member.neigong_id = None  # 假裝這門內功只在庫裡
    stocked.player.arts.append(art.id)
    msgs = team.switch_art(stocked, content, world, art.id)
    assert stocked.player.member.neigong_id == art.id and stocked.player.arts == []
    assert len(msgs) == 1  # 沒有「你收起了…」那一句


def test_switching_something_not_in_the_library_is_refused(stocked, content, world):
    from tianxia import team

    assert team.switch_art(stocked, content, world, "ghost") == ["你的功法庫裡沒有這一門。"]


def test_a_neigong_in_the_library_does_not_displace_a_wugong(stocked, content, world):
    from tianxia import team

    client = OllamaClient()
    with naming("裂江訣"):
        wugong, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    with naming("玄淵經"):
        neigong, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "內功")
    stocked.player.member.neigong_id = None
    stocked.player.arts.append(neigong.id)
    team.switch_art(stocked, content, world, neigong.id)
    assert stocked.player.member.wugong_id == wugong.id  # 武學沒被動到
    assert stocked.player.member.neigong_id == neigong.id


# ── 不准重煉自己已經有的功法（第四層）────────────────────────


def test_recrafting_an_art_you_already_practise_is_refused(stocked, content, world):
    """煉製的意義是取得你還沒有的功法。重煉只會白燒素材與心得——而舊版還會讓同一門功法
    同時在身上也在功法庫裡（實測機器人一季 17 爐有 8 爐是這種）。"""
    client = OllamaClient()
    with naming("裂江訣"):
        art, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    before_materials = dict(stocked.player.materials)
    before_xinde = stocked.player.stats["xinde"]
    again, msgs = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert again is None
    assert art.name in msgs[0] and "你已經有了" in msgs[0]
    assert stocked.player.materials == before_materials  # 什麼都沒扣
    assert stocked.player.stats["xinde"] == before_xinde
    assert stocked.player.arts == []  # 也沒有塞重複的進功法庫


def test_recrafting_something_only_in_your_library_is_also_refused(stocked, content, world):
    client = OllamaClient()
    with naming("裂江訣"):
        craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    with naming("沉山勢"):
        second, _ = craft.craft(stocked, content, world, client, ["gang_2", "gang_2"], "武學")
    assert stocked.player.arts == [second.id]  # 在庫裡
    again, msgs = craft.craft(stocked, content, world, client, ["gang_2", "gang_2"], "武學")
    assert again is None and "你已經有了" in msgs[0]


def test_a_recipe_someone_else_discovered_can_still_be_crafted(stocked, content, world):
    """全服共享配方的價值就在這裡：別人首創、自己還沒有，照樣煉得出來（而且零 LLM）。"""
    from tianxia.state import new_game_state

    client = OllamaClient()
    with naming("裂江訣"):
        mine, _ = craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    other = new_game_state(content, "另一個玩家")
    materials.grant(other, content, "gang_1", 2)
    other.player.stats["xinde"] = 500
    assert craft.can_craft(other, content, ["gang_1", "gang_1"], "武學", world) is None
    with mock.patch.object(OllamaClient, "chat_structured", side_effect=AssertionError("不該呼叫 LLM")):
        theirs, _ = craft.craft(other, content, world, client, ["gang_1", "gang_1"], "武學")
    assert theirs is not None and theirs.name == mine.name


def test_can_craft_without_a_world_skips_the_duplicate_check(stocked, content, world):
    """沒傳 world 時只做素材與心得的檢查（舊呼叫端不會壞）。"""
    client = OllamaClient()
    with naming("裂江訣"):
        craft.craft(stocked, content, world, client, ["gang_1", "gang_1"], "武學")
    assert craft.can_craft(stocked, content, ["gang_1", "gang_1"], "武學") is None


# ── 換季：配方每季清空、煉製吃天機（第一季設計第十四節）──────────


def supplied(content, name: str):
    """一個剛好湊得出一爐「剛＋剛」的新玩家。"""
    from tianxia.state import new_game_state

    other = new_game_state(content, name)
    materials.grant(other, content, "gang_1", 2)
    other.player.stats["xinde"] = 500
    return other


def test_the_tianji_decides_what_a_recipe_grows_into(content, world, tmp_path):
    """同一個配方、同一個名字，天機不同就長出不同的功法（每季換一次天機，同名長出不同武學）。
    fixture 的剛＋剛武學在天機 0 與天機 1 的品質剛好不同，所以差異是確定的、不靠運氣。"""
    from tianxia.world_state import WorldStateStore

    later = WorldStateStore(path=tmp_path / "later" / "state.json")
    later.mutate(lambda state: setattr(state, "tianji", 1))
    client = OllamaClient()
    with llm_down():
        before, _ = craft.craft(supplied(content, "甲"), content, world, client, ["gang_1", "gang_1"], "武學")
        after, _ = craft.craft(supplied(content, "乙"), content, later, client, ["gang_1", "gang_1"], "武學")
    assert before is not None and after is not None
    assert before.name == after.name  # 退路組名只看配方，所以名字一樣
    assert before.quality != after.quality
    gang = content.materials["gang_1"]
    expected = generate_from_name(
        after.name, "武學", after.name, tianji=1,
        weights=craft.quality_weights(craft.mean_tier(gang, gang)), attribute="剛",
    )
    assert (after.quality, after.base_power, after.top_power) == (expected.quality, expected.base_power, expected.top_power)


def test_recipes_are_cleared_every_season_and_rediscovered(content, world):
    """配方每季清空，大家重新發現、首創者重新認定。以前換季只清了功法本體、沒清配方表，
    舊配方全部指向已經不存在的功法，第二季起同一爐永遠「爐火熄了」。"""
    world.seed_first_season(content)  # 測試內容會直接開季
    client = OllamaClient()
    key = craft.recipe_key(["gang_1", "gang_1"], "武學")
    with llm_down():
        first, _ = craft.craft(supplied(content, "甲"), content, world, client, ["gang_1", "gang_1"], "武學")
    assert first is not None and first.creator == "甲"
    world.mutate_season(lambda season: setattr(season, "ended", True))
    assert world.next_season(content, now=1.0)

    with llm_down():
        again, msgs = craft.craft(supplied(content, "乙"), content, world, client, ["gang_1", "gang_1"], "武學")
    assert again is not None, msgs
    assert again.creator == "乙"  # 這一季的首創者
    assert "江湖上第一次煉成" in "\n".join(msgs)
    assert world.read().recipes == {key: again.name}
