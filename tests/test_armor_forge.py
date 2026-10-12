"""防具打造（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 4.7、4.1；打造隱藏配方設計第九節：照兵器那一套，沒有種類，
名字照對照表、不叫模型；計畫 docs/superpowers/plans/2026-10-12-打造-1-隱藏配方與防具.md Task 2～5）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import armor, equipment, naming, rules, smithing, team, weapons
from tianxia.state import Equipment, SmithDraft, Weapon

KEY_YANG = "鎧|gang_1+kuai_1"  # 精鐵砂（剛）＋驚羽（快）＝陽 → 接「鎧」
GO_YANG = "smith:forge-go:防具:gang_1:kuai_1"


def _on(content, weapons_on=False):
    """打開防具（測試內容兩欄都關著）；weapons_on 連武器也開。"""
    content.config.armor.enabled = True
    content.config.weapons.enabled = weapons_on
    return content


def _jacket(attribute="虛", tier=1, quality="下品", edge=100, aid="甲:1", name="試甲", tempers=0, recipe=None):
    return Equipment(id=aid, slot="armor", name=name, attribute=attribute, tier=tier, quality=quality, edge=edge,
                     tempers=tempers, recipe=recipe)


def _game(content, world, name="試甲", inner="calm"):
    """身上一門內功（預設靜心訣，屬虛）。"""
    from tianxia.engine import Game
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, inner)
    game.state.player.member.neigong_id = inner
    return game


def _smithy(content, world, silver=200, weapons_on=False, name="試甲", inner="calm"):
    """站在測試內容的城鎮（town），悟性 5；背包：精鐵砂（剛一階）×3、玄鋼骨（剛二階）×2、驚羽（快一階）×2。"""
    _on(content, weapons_on)
    game = _game(content, world, name=name, inner=inner)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.stats["wis"] = "town", 100.0, silver, 5
    p.materials = {"gang_1": 3, "gang_2": 2, "kuai_1": 2}
    game.sync(0.0)
    return game


def _ids(game):
    return {o.id: o for o in game.options(odds=False)}


def _inner(game, content, world):
    return team.player_art(game.state, content, world, game.state.player.member.neigong_id)


# ── Task 2：防具的配方鍵、名字對照表與打造規則 ──

def test_armor_recipe_keys_have_their_own_prefix():
    assert armor.recipe_key("gang_1", "kuai_1") == KEY_YANG
    assert armor.recipe_key("kuai_1", "gang_1") != KEY_YANG  # 主輔不交換
    assert armor.recipe_parts(KEY_YANG) == ("gang_1", "kuai_1")
    assert armor.recipe_parts("兵|劍|gang_1+kuai_1") is None and armor.recipe_parts(None) is None
    assert weapons.recipe_parts(KEY_YANG) is None  # 前綴就是欄位：兵器那一側讀不到防具的鍵


def test_recipe_text_writes_main_then_aux(content):
    assert armor.recipe_text(content, KEY_YANG) == "精鐵砂＋驚羽"
    assert armor.recipe_text(content, "兵|劍|gang_1+kuai_1") is None and armor.recipe_text(content, None) is None


def test_the_armor_word_follows_the_attribute_and_matches_the_shop():
    assert armor.noun_for("剛") == armor.noun_for("柔") == "甲" and armor.noun_for("快") == armor.noun_for("虛") == "衫"
    assert armor.noun_for("慢") == armor.noun_for("陰") == "袍" and armor.noun_for("陽") == armor.noun_for("實") == "鎧"
    for attribute, shop in armor.SHOP_NAMES.items():
        assert shop.endswith(armor.noun_for(attribute))  # 架上四件就是這個對法（鐵葉甲、軟皮甲、輕綃衫、厚氈袍）
    assert set(armor.FORGE_NOUNS.values()) == set(armor.FORGE_WORDS)  # 四個字都用得到


def test_word_problem_wants_an_armor_word_and_no_weapon_word():
    assert armor.word_problem("玄鱗鎧") is None and armor.word_problem("石鱗甲") is None
    assert armor.word_problem("玄甲雲紋") is None  # 帶防具字就行：隱藏配方的名字由內容寫，不必以它結尾
    assert armor.word_problem("玄鱗") == armor.WORD_MISSING
    assert armor.word_problem("刀鱗甲") == armor.WORD_CLASH and armor.word_problem("護手衫") == armor.WORD_CLASH  # 像兵器
    assert armor.word_problem("軟皮甲") == armor.SHOP_CLASH  # 鐵匠鋪架上的防具名


def test_armor_table_names_follow_main_and_aux_and_never_repeat(content):
    """PM 2026-10-12 決定第 1 條（「要 PM 定的」第 1 條）：字首照主料、中間字（craft_names.armor）照輔料的位置，最後接照屬性的防具字。"""
    names, order = content.craft_names, list(content.materials)
    assert armor.table_name(content, "gang_1", "kuai_1", "陽") == (
        names.prefixes[order.index("gang_1")] + names.armor[order.index("kuai_1")] + "鎧")
    heads = {armor.table_name(content, m, a, "剛")[:2] for m in order for a in order}
    assert len(heads) == len(order) ** 2  # 前兩個字只看組合，全部不同：不管接哪個防具字都不重名
    for m in order:
        for a in order:
            name = armor.table_name(content, m, a, "實")
            assert naming.name_problem(name, content) is None and armor.word_problem(name) is None


def test_validate_checks_the_armor_table(content):
    from tianxia.content import ContentError, validate
    content.craft_names.armor = ["刀", "霜", "雲", "紋"]  # 「某刀甲」看起來像兵器：載入當下就要報錯
    with pytest.raises(ContentError, match="craft_names.armor 組出的防具名"):
        validate(content)
    content.craft_names.armor = list("鱗鱗雲紋")
    with pytest.raises(ContentError, match="craft_names.armor 至少要 4 個不重複的字"):
        validate(content)
    content.craft_names.armor = []
    with pytest.raises(ContentError, match="craft_names.armor 不能是空的"):
        validate(content)
    assert real_content().craft_names.armor  # 正式內容載入時已經驗過每一個組合


def test_armor_forging_numbers_follow_the_weapons_and_live_in_the_armor_config(content):
    rule = content.config.armor
    assert rule.forge_silver == {"1": 20, "2": 60, "3": 150} and rule.temper_max == 5
    assert rule.temper_silver == {"1": 0, "2": 30, "3": 80} and rule.temper_step == 0.01
    assert rule.quality.odds == {"下品": 50, "中品": 30, "上品": 20} and (rule.quality.terrain, rule.quality.calm) == (0, 0)
    q = real_content().config.armor.quality
    assert (q.terrain, q.battlefield, q.calm) == (10, 10, 8) and q.setting_good


def test_new_armor_can_carry_its_recipe(content, world):
    game = _game(_on(content), world)
    a = armor.new_armor(game.state, name="玄鱗鎧", attribute="陽", tier=1, quality="中品", recipe=KEY_YANG)
    assert a.recipe == KEY_YANG and a.id.startswith("甲:") and a.slot == "armor"
    assert armor.new_armor(game.state, name="鐵葉甲", attribute="剛", tier=1, quality="下品").recipe is None


def test_the_armor_kind_maps_to_the_armor_slot_key_and_rules(content):
    assert smithing.is_armor(smithing.ARMOR_KIND) and not smithing.is_armor("劍") and not smithing.is_armor(None)
    assert smithing.slot_of(smithing.ARMOR_KIND) == "armor" and smithing.slot_of("劍") == smithing.slot_of(None) == "weapon"
    assert smithing.rules_of(content, "armor") is content.config.armor and smithing.rules_of(content, "weapon") is content.config.weapons
    assert smithing.recipe_key(smithing.ARMOR_KIND, "gang_1", "kuai_1") == KEY_YANG
    assert smithing.recipe_key("劍", "gang_1", "kuai_1") == "兵|劍|gang_1+kuai_1"


def test_armor_forge_problem_reasons(content, world):
    game = _smithy(content, world)  # 只開防具
    s, p = game.state, game.state.player
    A = smithing.ARMOR_KIND
    assert smithing.forge_problem(s, content, A, "gang_1", "kuai_1") is None
    p.materials = {"gang_1": 1}
    assert smithing.forge_problem(s, content, A, "gang_1", "gang_1") == "精鐵砂不夠（要 2 個）"
    p.materials, p.stats["silver"] = {"gang_1": 2}, 5
    assert smithing.forge_problem(s, content, A, "gang_1", "gang_1") == "還差 15 兩"
    p.stats["silver"] = 200
    p.armor = _jacket()
    p.rack = [_jacket(aid=f"甲:{i + 2}") for i in range(content.config.weapons.rack_cap)]
    assert smithing.forge_problem(s, content, A, "gang_1", "gang_1") == equipment.RACK_FULL
    p.rack = []
    assert smithing.forge_problem(s, content, "劍", "gang_1", "gang_1") == weapons.NOT_HERE  # 兵器關著：只能打防具
    content.config.armor.enabled = False
    assert smithing.forge_problem(s, content, A, "gang_1", "gang_1") == weapons.NOT_HERE


def test_armor_attribute_tier_and_price(content, world):
    A = smithing.ARMOR_KIND
    assert smithing.attribute_of(world, content, A, "gang_1", "kuai_1") == "陽"
    assert smithing.attribute_of(world, content, A, "kuai_1", "kuai_1") == "快"
    content.config.armor.forge_silver = {"1": 7, "2": 8, "3": 9}
    assert [smithing.price(content, t, "armor") for t in (1, 2, 3)] == [7, 8, 9]
    assert [smithing.price(content, t) for t in (1, 2, 3)] == [20, 60, 150]  # 兵器照舊


def test_the_armor_attribute_seed_is_the_armor_key():
    """剛＋柔不在四對裡：照「天機|配方鍵」挑，防具的鍵是「鎧|主料+輔料」（正式內容的柳絲綿 rou_1）。"""
    from tianxia.insights import merged_attribute
    rc = real_content()
    for tianji in range(4):
        assert smithing.attribute_with(rc, tianji, smithing.ARMOR_KIND, "gang_1", "rou_1") == merged_attribute(
            rc.materials["gang_1"], rc.materials["rou_1"], f"{tianji}|鎧|gang_1+rou_1")


def test_armor_odds_use_the_armor_rule_and_the_armor_key(content, world):
    game = _smithy(content, world)
    A = smithing.ARMOR_KIND
    odds = smithing.forge_odds(game.state, content, world, A, "gang_1", "kuai_1")
    assert odds.odds == {"下品": 46.0, "中品": 32.0, "上品": 22.0} and odds.reasons == ("輔料壓得住主料",)
    game.state.player.forge_counts = {KEY_YANG: 3, "兵|劍|gang_1+kuai_1": 5}
    assert smithing.forge_odds(game.state, content, world, A, "gang_1", "kuai_1").odds == {"下品": 40.0, "中品": 35.0, "上品": 25.0}  # 熟手照防具自己的配方鍵（+6）
    content.config.armor.quality.aux_tier = {"0": 0}
    assert smithing.forge_odds(game.state, content, world, A, "gang_1", "kuai_1").odds == {"下品": 44.0, "中品": 33.0, "上品": 23.0}


def test_armor_setting_uses_the_armor_rule(content, world, monkeypatch):
    from tianxia import fusion
    game = _smithy(content, world)
    content.config.armor.quality.terrain = 10
    monkeypatch.setattr(fusion, "terrain_here", lambda state, content, attribute: attribute == "剛")
    assert smithing.setting_points(game.state, content, "剛", "armor") == [("terrain", 10)]
    assert smithing.setting_points(game.state, content, "剛") == []  # 兵器的天時地利照舊（測試內容是 0）
    content.config.armor.quality.setting_good = "爐火正旺。"
    assert smithing.setting_line(content, [("terrain", 10)], "armor") == ["爐火正旺。"]
    assert smithing.setting_line(content, [("terrain", 10)]) == []  # 兵器那一句是空的
