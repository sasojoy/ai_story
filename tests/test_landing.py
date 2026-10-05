"""合到舊的（武學與成長設計 12.2）：規則管多常、管退路；模型挑哪一個在 fusion／naming。"""
import pytest

from tianxia import landing
from tianxia.martial_arts import Insight, generate_from_name
from tianxia.models import Config


def _fused(name, kind="武學", attribute="快", lean="無"):
    return generate_from_name(name, kind, name).model_copy(
        update={"origin": "fused", "attribute": attribute, "lean": lean},
    )


def test_the_defaults_are_the_planners():
    cfg = Config()
    assert (cfg.fuse_xinde, cfg.fuse_stamina) == (cfg.merge_xinde, cfg.merge_stamina) == (5, 5)
    assert (cfg.land_chance_per_candidate, cfg.land_chance_cap) == (0.05, 0.9)


@pytest.mark.parametrize("field", ["land_chance_per_candidate", "land_chance_cap"])
def test_the_chances_stay_between_zero_and_one(field):
    with pytest.raises(ValueError):
        Config(**{field: 1.5})
    with pytest.raises(ValueError):
        Config(**{field: -0.1})


def test_the_chance_grows_per_candidate_up_to_the_cap(content):
    content.config.land_chance_per_candidate, content.config.land_chance_cap = 0.05, 0.9
    assert landing.chance(content, 0) == 0
    assert landing.chance(content, 3) == pytest.approx(0.15)
    assert landing.chance(content, 40) == pytest.approx(0.9)


def test_no_candidates_never_lands(content):
    content.config.land_chance_per_candidate, content.config.land_chance_cap = 1.0, 1.0
    assert not landing.lands(content, "融|a", 0, 0)
    assert landing.lands(content, "融|a", 0, 1)


def test_the_roll_is_the_same_for_the_same_recipe_and_season(content):
    content.config.land_chance_per_candidate, content.config.land_chance_cap = 0.5, 0.9
    assert len({landing.lands(content, "融|a", 3, 1) for _ in range(5)}) == 1


def test_about_the_chance_share_of_recipes_land(content):
    content.config.land_chance_per_candidate, content.config.land_chance_cap = 0.05, 0.9
    hits = sum(landing.lands(content, f"融|{i}", 1, 6) for i in range(4000))  # 六個候選：三成
    assert 0.27 < hits / 4000 < 0.33


def test_the_rule_pick_ignores_the_order_and_is_stable():
    a, b, c = _fused("甲拳"), _fused("乙拳"), _fused("丙拳")
    picked = landing.rule_pick([a, b, c], "融|x", 2)
    assert picked is landing.rule_pick([c, a, b], "融|x", 2)
    assert {landing.rule_pick([a, b, c], f"融|{i}", 2).id for i in range(60)} == {"甲拳", "乙拳", "丙拳"}


def test_choose_takes_the_models_pick_only_when_it_is_a_candidate():
    a, b = _fused("甲拳"), _fused("乙拳")
    assert landing.choose([a, b], "融|x", 1, "乙拳") is b
    assert landing.choose([a, b], "融|x", 1, "不在清單") is landing.rule_pick([a, b], "融|x", 1)
    assert landing.choose([a, b], "融|x", 1, None) is landing.rule_pick([a, b], "融|x", 1)


def test_art_candidates_match_kind_attribute_and_lean(world):
    for art in (_fused("甲拳"), _fused("乙拳", attribute="剛"), _fused("丙功", kind="內功"), _fused("丁拳", lean="正")):
        world.claim_recipe(f"融|{art.id}", art)
    assert [a.id for a in landing.art_candidates(world, "武學", "快", "無")] == ["甲拳"]
    assert [a.id for a in landing.art_candidates(world, "武學", "快", "正")] == ["丁拳"]


def test_insight_candidates_match_attribute_and_lean(world):
    world.claim_insight_recipe("合|a", Insight(id="狂風", name="狂風", attribute="快"))
    world.claim_insight_recipe("合|b", Insight(id="燎原", name="燎原", attribute="陽"))
    world.claim_insight_recipe("合|c", Insight(id="正風", name="正風", attribute="快", lean="正"))
    assert [i.id for i in landing.insight_candidates(world, "快", "無")] == ["狂風"]
