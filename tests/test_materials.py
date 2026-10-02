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


# ── 探索撿到的 ────────────────────────────────────────────


def test_explore_picks_from_the_locations_own_list(content):
    loc = content.locations["lake"].model_copy(update={"materials": ["gang_3"]})
    always = random.Random()
    always.random = lambda: 0.0  # type: ignore[method-assign]
    assert materials.roll_explore_drop(loc, content, always) == "gang_3"


def test_explore_falls_back_to_a_first_tier_material(content):
    loc = content.locations["lake"].model_copy(update={"materials": []})
    always = random.Random(3)
    always.random = lambda: 0.0  # type: ignore[method-assign]
    picked = materials.roll_explore_drop(loc, content, always)
    assert picked is not None and content.materials[picked].tier == 1


def test_explore_usually_finds_nothing(content):
    loc = content.locations["lake"]
    never = random.Random()
    never.random = lambda: 0.99  # type: ignore[method-assign]
    assert materials.roll_explore_drop(loc, content, never) is None


def test_explore_respects_the_configured_chance(content):
    content.config.explore_material_chance = 0.0
    loc = content.locations["lake"].model_copy(update={"materials": ["gang_1"]})
    assert materials.roll_explore_drop(loc, content, random.Random(0)) is None


def test_tier_label_reads_in_words(content):
    assert materials.tier_label(content.materials["gang_1"]) == "凡品"
    assert materials.tier_label(content.materials["gang_2"]) == "靈品"
    assert materials.tier_label(content.materials["gang_3"]) == "天品"
