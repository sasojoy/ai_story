"""煉製素材的掉落與背包（tianxia/materials.py）。

fixture 內容只有四種素材（剛的三階 + 快的一階，見 tests/fixtures/content/materials.json），
剛好夠驗預設掉落表的每一階與「屬性挑不到就退回同階」這條退路。
"""
import random

import pytest

from tianxia import materials
from tianxia.models import Drop


@pytest.fixture
def rng():
    return random.Random(0)


# ── 背包 ──────────────────────────────────────────────────


def test_grant_adds_to_the_bag_and_says_so(state, content):
    assert materials.grant(state, content, "gang_1") == "獲得 精鐵砂 ×1"
    assert materials.grant(state, content, "gang_1", 2) == "獲得 精鐵砂 ×2"
    assert state.player.materials == {"gang_1": 3}


def test_grant_ignores_unknown_materials_and_nonpositive_counts(state, content):
    assert materials.grant(state, content, "ghost") is None
    assert materials.grant(state, content, "gang_1", 0) is None
    assert state.player.materials == {}


def test_take_removes_the_entry_once_it_hits_zero(state, content):
    materials.grant(state, content, "gang_1", 2)
    assert materials.take(state, "gang_1") is True
    assert materials.take(state, "gang_1") is True
    assert state.player.materials == {}


def test_take_without_enough_changes_nothing(state, content):
    materials.grant(state, content, "gang_1")
    assert materials.take(state, "gang_1", 2) is False
    assert materials.held(state, "gang_1") == 1
    assert materials.take(state, "ghost") is False


def test_bag_contents_puts_the_high_tiers_first(state, content):
    for mid in ("gang_1", "gang_3", "kuai_1", "gang_2"):
        materials.grant(state, content, mid)
    assert [m.id for m, _ in materials.bag_contents(state, content)] == ["gang_3", "gang_2", "gang_1", "kuai_1"]


def test_bag_contents_skips_unknown_and_empty_entries(state, content):
    state.player.materials = {"gang_1": 1, "ghost": 5, "gang_2": 0}
    assert [m.id for m, _ in materials.bag_contents(state, content)] == ["gang_1"]


# ── 打贏的掉落 ────────────────────────────────────────────


def test_squad_drops_follow_the_content_when_it_lists_them(content, rng):
    squad = content.squads["thug"].model_copy(update={"drops": [Drop(material="gang_3")]})
    assert materials.roll_squad_drops(squad, content, rng) == [("gang_3", 1)]


def test_a_listed_drop_can_miss(content):
    squad = content.squads["thug"].model_copy(update={"drops": [Drop(material="gang_3", chance=0.0)]})
    assert materials.roll_squad_drops(squad, content, random.Random(1)) == []


def test_a_listed_drop_of_an_unknown_material_is_skipped(content, rng):
    squad = content.squads["thug"].model_copy(update={"drops": [Drop(material="ghost")]})
    assert materials.roll_squad_drops(squad, content, rng) == []


@pytest.mark.parametrize(
    ("difficulty", "tiers"),
    [(5, [1]), (50, [1, 2]), (80, [2]), (150, [2, 3])],
)
def test_the_default_table_gives_higher_tiers_for_harder_opponents(content, difficulty, tiers):
    """沒寫 drops 的對手走依難度的預設表；用機率永遠命中的 rng 看它「最多」會掉什麼。"""
    squad = content.squads["thug"].model_copy(update={"difficulty": difficulty, "drops": []})
    always = random.Random()
    always.random = lambda: 0.0  # type: ignore[method-assign]
    rolled = materials.roll_squad_drops(squad, content, always)
    assert [content.materials[mid].tier for mid, _ in rolled] == tiers


def test_the_default_table_can_come_up_empty_for_the_weakest_opponents(content):
    squad = content.squads["thug"].model_copy(update={"difficulty": 5, "drops": []})
    never = random.Random()
    never.random = lambda: 0.99  # type: ignore[method-assign]
    assert materials.roll_squad_drops(squad, content, never) == []


def test_the_default_table_matches_the_opponents_attribute(content):
    """fixture 裡「快」只有一階，所以難度 80（必掉二階）會退回同階的剛，不會掉不出東西。"""
    always = random.Random()
    always.random = lambda: 0.0  # type: ignore[method-assign]
    gang = content.squads["thug"].model_copy(update={"difficulty": 50, "attribute": "剛", "drops": []})
    assert [content.materials[mid].attribute for mid, _ in materials.roll_squad_drops(gang, content, always)] == ["剛", "剛"]
    kuai = content.squads["thug"].model_copy(update={"difficulty": 80, "attribute": "快", "drops": []})
    rolled = materials.roll_squad_drops(kuai, content, always)
    assert [content.materials[mid].id for mid, _ in rolled] == ["gang_2"]


def test_tier_label_reads_in_words(content):
    assert materials.tier_label(content.materials["gang_1"]) == "凡品"
    assert materials.tier_label(content.materials["gang_2"]) == "靈品"
    assert materials.tier_label(content.materials["gang_3"]) == "天品"


# ── 糧草（計畫 T6 的最小版：背包裡的慢屬性素材當糧草，伏筆 T7 讀它）────


def _with_slow_materials(content):
    """fixture 只有剛與快：補上慢屬性的三階（凡 1、靈 3、天 9，Config.grain_values）。"""
    from tianxia.models import Material

    for tier, name in ((1, "粗糧"), (2, "細糧"), (3, "軍糧")):
        content.materials[f"man_{tier}"] = Material(id=f"man_{tier}", name=name, attribute="慢", tier=tier)
    return content


def test_grain_of_and_take_grain_use_low_tier_first(state, content):
    _with_slow_materials(content)
    assert content.config.grain_values == [1, 3, 9]
    assert materials.grain_of(state, content) == 0
    materials.grant(state, content, "man_1", 2)
    materials.grant(state, content, "man_2", 1)
    materials.grant(state, content, "gang_1", 5)  # 不是慢屬性：不算糧草，也不會被拿去用
    assert materials.grain_of(state, content) == 2 * 1 + 3
    assert materials.take_grain(state, content, 2) is True  # 先用兩份凡品
    assert state.player.materials == {"man_2": 1, "gang_1": 5}
    assert materials.take_grain(state, content, 4) is False  # 只剩 3 份：不夠就不動
    assert state.player.materials == {"man_2": 1, "gang_1": 5}
    materials.grant(state, content, "man_1", 1)
    materials.grant(state, content, "man_3", 1)
    assert materials.take_grain(state, content, 4) is True  # 凡 1 → 靈 3，天品留著
    assert state.player.materials == {"man_3": 1, "gang_1": 5}
    assert materials.take_grain(state, content, 0) is True and state.player.materials == {"man_3": 1, "gang_1": 5}


def test_donations_start_empty(state):
    assert state.player.donations == {}
