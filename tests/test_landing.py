"""合到舊的（武學與成長設計 12.2）：規則管多常、管退路；模型挑哪一個在 fusion／naming。"""
import types

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


def test_the_roll_never_reaches_one_even_on_the_largest_hash(content, monkeypatch):
    """雜湊全是 1 的極端情形：擲出來的數必須還是小於 1——機會 100% 的一定合到舊的、規則挑的位置也不會超出清單。"""
    class Digest:
        def digest(self):
            return b"\xff" * 32

    monkeypatch.setattr(landing, "hashlib", types.SimpleNamespace(sha256=lambda data: Digest()))
    content.config.land_chance_per_candidate, content.config.land_chance_cap = 1.0, 1.0
    assert landing.lands(content, "融|a", 0, 1)
    candidates = [_fused("甲拳"), _fused("乙拳"), _fused("丙拳")]
    assert landing.rule_pick(candidates, "融|a", 0) in candidates  # 不丟 IndexError


def test_the_tianji_changes_both_the_land_roll_and_the_rule_pick(content):
    """同一個配方換一季（天機不同）要重擲：兩個種子都帶天機。"""
    content.config.land_chance_per_candidate, content.config.land_chance_cap = 0.5, 0.9
    keys = [f"融|{i}" for i in range(200)]
    assert any(landing.lands(content, key, 1, 1) != landing.lands(content, key, 2, 1) for key in keys)
    arts = [_fused("甲拳"), _fused("乙拳"), _fused("丙拳")]
    assert any(landing.rule_pick(arts, key, 1) is not landing.rule_pick(arts, key, 2) for key in keys)


def test_the_land_roll_and_the_pick_are_rolled_independently(content):
    """兩個擲骰用不同的鹽：只有兩個候選、機會一半時，若共用同一個數，「合到舊的」就永遠等於「挑到第一個」。"""
    content.config.land_chance_per_candidate, content.config.land_chance_cap = 0.5, 0.9
    first, second = _fused("甲拳"), _fused("乙拳")
    pairs = {
        (landing.lands(content, f"融|{i}", 1, 1), landing.rule_pick([first, second], f"融|{i}", 1) is first)
        for i in range(200)
    }
    assert pairs == {(True, True), (True, False), (False, True), (False, False)}


def test_the_rule_pick_follows_the_ids_not_the_names():
    """改名（練成絕學）只動名字；規則挑的結果只看 id，所以同樣的 id 不管名字怎麼排都挑到同一個。"""
    def arts(*pairs):
        return [_fused("甲拳").model_copy(update={"id": art_id, "name": name}) for art_id, name in pairs]

    aligned = arts(("a1", "甲拳"), ("a2", "乙拳"), ("a3", "丙拳"))  # id 的順序跟名字的順序一樣
    reversed_names = arts(("a1", "丙拳"), ("a2", "乙拳"), ("a3", "甲拳"))  # 名字的順序跟 id 的順序相反
    for i in range(60):
        key = f"融|{i}"
        assert landing.rule_pick(aligned, key, 1).id == landing.rule_pick(reversed_names, key, 1).id


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
