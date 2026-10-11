"""防具與裝備四欄（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第二～四節、第九節；
計畫 docs/superpowers/plans/2026-10-10-裝備-1-四欄化與防具.md）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import next_season, real_content, walk_to
from tianxia import armor, equipment, rules, team, weapons
from tianxia.state import BattleRecord, Equipment, Weapon


def _on(content, weapons_on=False):
    """打開防具（測試內容三欄都關著）；weapons_on 連武器也開。"""
    content.config.armor.enabled = True
    content.config.weapons.enabled = weapons_on
    return content


def _jacket(attribute="虛", tier=1, quality="下品", edge=100, aid="甲:1", name="試甲"):
    return Equipment(id=aid, slot="armor", name=name, attribute=attribute, tier=tier, quality=quality, edge=edge)


def _blade(aid="兵:3", name="厚背刀", kind="刀", attribute="剛"):
    return Weapon(id=aid, name=name, kind=kind, attribute=attribute, tier=1, quality="下品")


def _game(content, world, name="試甲", inner="calm"):
    """身上一門內功（預設靜心訣，屬虛：它的一般功效是「險」，不碰扣血；粗淺吐納屬柔，會帶化勁）。"""
    from tianxia.engine import Game
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, inner)
    game.state.player.member.neigong_id = inner
    return game


def _neigong(game, content, world):
    return team.player_art(game.state, content, world, game.state.player.member.neigong_id)


def _town(content, world, silver=200, weapons_on=False, name="試甲", inner="calm"):
    """站在測試內容的城鎮（town：標籤城鎮）。"""
    _on(content, weapons_on)
    game = _game(content, world, name=name, inner=inner)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"] = "town", 100.0, silver
    p.materials = {}
    game.sync(0.0)
    return game


def _ids(game):
    return {o.id: o for o in game.options(odds=False)}


# ── Task 1：資料形狀與 equipment ──

def test_weapon_is_the_same_model_as_equipment_and_defaults_to_the_weapon_slot():
    assert Weapon is Equipment
    assert _blade().slot == "weapon"
    a = _jacket()
    assert a.kind == "" and a.slot == "armor" and Equipment.model_validate_json(a.model_dump_json()) == a


def test_fixture_turns_armor_off_and_real_content_on(content):
    assert content.config.armor.enabled is False
    real = real_content().config.armor
    assert real.enabled is True and real.total_cap == 0.6 and real.shop_price == 40 and real.repair_silver == 5
    assert real.tier_cut == {"1": 0.06, "2": 0.12, "3": 0.18}
    assert real.wear == {"大勝": 1, "險勝": 2, "僵持": 3, "落敗": 5}


def test_slots_are_on_by_their_own_switch_and_unknown_slots_are_off(content):
    assert not equipment.on(content, "weapon") and not equipment.on(content, "armor")
    content.config.armor.enabled = True
    assert equipment.on(content, "armor") and not equipment.on(content, "weapon")
    assert not equipment.on(content, "mount") and not equipment.on(content, "treasure")  # 這一批表外的欄位一律關著


def test_store_puts_each_slot_on_when_empty_and_counts_the_rack_across_slots(content, world):
    game = _town(content, world, weapons_on=True)
    s, p = game.state, game.state.player
    assert equipment.store(s, _jacket()) == "你穿上了【試甲】。" and p.armor.id == "甲:1"
    assert equipment.store(s, _jacket(aid="甲:2", name="鐵葉甲")) == "【鐵葉甲】放上了裝備庫。"
    content.config.weapons.rack_cap = 2
    assert not equipment.rack_full(s, content, "weapon")  # 武器欄空著：新的一把直接拿上手，用不到裝備庫
    p.rack.append(_blade())
    assert equipment.rack_full(s, content, "armor")  # 裝備庫兩格（一件防具、一把兵器）合算滿了
    assert equipment.next_id(s, "armor") == "甲:1" and equipment.next_id(s, "weapon") == "兵:2"  # 共用 weapon_serial


def test_wield_takes_each_item_into_its_own_slot_and_resets_its_reminder(content, world):
    game = _town(content, world, weapons_on=True)
    p = game.state.player
    p.armor, p.armor_warned = _jacket(edge=20), True
    p.rack = [_jacket(aid="甲:2", name="鐵葉甲", attribute="剛"), _blade()]
    assert game.wield_weapon("甲:2") == ["你換上了【鐵葉甲】。"]
    assert p.armor.id == "甲:2" and p.armor_warned is False and p.weapon is None
    assert [i.id for i in p.rack] == ["兵:3", "甲:1"]  # 換下來的那件回裝備庫
    assert game.wield_weapon("兵:3") == ["你換上了【厚背刀】。"] and p.weapon.id == "兵:3"
    assert game.state.journal[0].tag == "你換上了【厚背刀】。"  # 修練紀錄照舊


def test_wield_and_dismantle_obey_the_slot_switch_after_finding_the_item(content, world):
    game = _town(content, world)  # 只開防具
    p = game.state.player
    p.rack = [_blade(), _jacket(aid="甲:2")]
    assert game.wield_weapon("兵:3") == ["（此刻無法這麼做。）"]  # 武器關著：裝備庫裡的兵器不能動
    assert game.dismantle_weapon("兵:3") == ["（此刻無法這麼做。）"] and len(p.rack) == 2
    assert game.wield_weapon("甲:9") == [equipment.WIELD_MISSING]  # 防具開著：找不到就是找不到
    assert game.dismantle_weapon("甲:2")[0].startswith(equipment.DISMANTLE_PREFIX)
    assert [i.id for i in p.rack] == ["兵:3"] and sum(p.materials.values()) == 1
    content.config.armor.enabled = False
    assert game.wield_weapon("甲:9") == ["（此刻無法這麼做。）"]


def test_armor_can_be_changed_in_seclusion_and_on_the_road(content, world):
    """設計 2.3：武器、防具隨時能換（含閉關中、路上）、不花體力。之後坐騎、寶物加換裝限制（2.3 的三條）時不能誤擋到防具。"""
    game = _town(content, world)
    p = game.state.player
    p.rack = [_jacket(aid="甲:2", name="鐵葉甲", attribute="剛"), _jacket(aid="甲:3", name="軟皮甲", attribute="柔")]
    p.busy_until = game.state.world.time + 3600.0  # 閉關中（同 tests/test_engine.py 的寫法）
    assert game.wield_weapon("甲:2") == ["你換上了【鐵葉甲】。"] and p.armor.id == "甲:2"
    p.busy_until = None
    game.choose("move:lake")
    assert p.journey is not None  # 在路上
    stamina = p.stamina
    assert game.wield_weapon("甲:3") == ["你換上了【軟皮甲】。"] and p.armor.id == "甲:3" and p.stamina == stamina
    assert [i.id for i in p.rack] == ["甲:2"]


def test_a_new_season_starts_with_no_armor_and_an_empty_rack(content, world):
    game = _town(content, world)
    p = game.state.player
    p.armor, p.rack, p.smith_page = _jacket(), [_jacket(aid="甲:2")], "armor"
    next_season(content, world, game)
    p = game.state.player
    assert p.armor is None and p.rack == [] and p.smith_page == "weapon" and p.weapon_serial == 0  # 新欄位跟著新角色重來（設計 2.4）


# ── Task 2：防具的規則 ──

def test_cut_adds_tier_quality_and_the_inner_art_then_scales_by_durability(content, world):
    _on(content)
    game = _game(content, world)
    ng = _neigong(game, content, world)  # 靜心訣：虛
    assert armor.cut(_jacket(), ng, content) == pytest.approx(0.06 + 0.03)  # 同屬性 +3%
    assert armor.cut(_jacket(attribute="實"), ng, content) == pytest.approx(0.06 - 0.03)  # 實剋虛（兩個方向都查）
    assert armor.cut(_jacket(attribute="柔"), ng, content) == pytest.approx(0.06)
    assert armor.cut(_jacket(edge=80), ng, content) == pytest.approx(0.09 * 0.9)  # 設計 2.5 的例子：8.1%
    assert armor.cut(_jacket(edge=0), ng, content) == pytest.approx(0.09 * 0.5)  # 全壞剩一半
    best = _jacket(tier=3, quality="上品").model_copy(update={"tempers": 5})
    assert armor.cut(best, ng, content) == pytest.approx(0.30)  # 最好的：18＋4＋5＋3
    assert armor.cut(_jacket(), None, content) == pytest.approx(0.06)  # 沒有內功：沒有那 ±3%
    assert armor.cut(_blade(), ng, content) == 0.0  # 不是防具那一欄的
    content.config.armor.enabled = False
    assert armor.cut(_jacket(), ng, content) == 0.0 and armor.cut(None, ng, content) == 0.0


def test_wear_by_tier_and_warn_once(content, world):
    _on(content)
    game = _game(content, world)
    s, p = game.state, game.state.player
    p.armor = _jacket(edge=34)
    assert armor.wear(s, content, "大勝") == [] and p.armor.edge == 33  # 大勝扣 1（武器是 2）
    assert armor.wear(s, content, "險勝") == [] and p.armor.edge == 31
    assert armor.wear(s, content, "僵持") == [armor.WORN_WARNING.format(name="試甲")] and p.armor.edge == 28
    assert armor.wear(s, content, "落敗") == [] and p.armor.edge == 23  # 只提醒一次
    p.armor.edge = 2
    armor.wear(s, content, "落敗")
    assert p.armor.edge == 0
    content.config.armor.enabled = False
    assert armor.wear(s, content, "落敗") == [] and p.armor.edge == 0


def test_only_training_wild_fights_and_a_lost_raid_wear_the_armor():
    assert armor.wears("train", "大勝") and armor.wears("wild", "落敗")
    assert armor.wears("raid", "落敗") and not armor.wears("raid", "大勝") and not armor.wears("raid", "僵持")
    for kind in ("spar", "duel", "event"):
        assert not armor.wears(kind, "落敗")


def test_buy_one_of_four_shop_pieces_puts_it_on(content, world):
    game = _town(content, world)
    s, p = game.state, game.state.player
    assert armor.SHOP_ATTRIBUTES == ("剛", "柔", "快", "慢")
    assert armor.buy(s, content, "柔") == ["你花 40 兩買下一件【軟皮甲】。", "你穿上了【軟皮甲】。"]
    assert p.armor.slot == "armor" and p.armor.id == "甲:1" and p.armor.tier == 1 and p.armor.quality == "下品"
    assert p.stats["silver"] == 160
    assert armor.buy(s, content, "剛")[-1] == "【鐵葉甲】放上了裝備庫。"
    assert armor.buy(s, content, "陰") == ["（沒有這一件。）"]
    p.stats["silver"] = 10
    assert armor.buy(s, content, "快") == ["（還差 30 兩。）"] and p.stats["silver"] == 10
    content.config.weapons.rack_cap = 1
    p.stats["silver"] = 200
    assert armor.buy_problem(s, content, "快") == equipment.RACK_FULL
    p.location = "lake"
    assert armor.buy_problem(s, content, "快") == equipment.NOT_HERE


def test_repair_needs_a_tier_one_material_and_silver_at_the_smith(content, world):
    game = _town(content, world)
    s, p = game.state, game.state.player
    assert armor.repair(s, content) == [f"（{armor.NO_ARMOR}。）"]
    p.armor, p.armor_warned = _jacket(edge=20), True
    assert armor.repair_problem(s, content) == equipment.NO_REPAIR_MATERIAL
    p.materials = {"kuai_1": 2, "gang_1": 1}
    msgs = armor.repair(s, content)
    assert p.armor.edge == 100 and not p.armor_warned and p.stats["silver"] == 195
    assert p.materials == {"kuai_1": 1, "gang_1": 1} and "驚羽" in msgs[0]  # 用數量最多的一階素材
    assert armor.repair_problem(s, content) == armor.INTACT
    p.armor.edge, p.stats["silver"] = 10, 2
    assert armor.repair_problem(s, content) == "還差 3 兩"
    p.location = "lake"
    assert armor.repair_problem(s, content) == equipment.NOT_HERE


def test_wanted_wields_a_better_piece_then_buys_then_repairs(content, world):
    game = _town(content, world, inner="basic_breath")  # 粗淺吐納：屬柔，架上有軟皮甲
    s, p = game.state, game.state.player
    ng = _neigong(game, content, world)
    assert armor.wanted(s, content, ng) == f"{armor.BUY}柔"  # 跟內功同屬性的那一件
    p.armor = _jacket(attribute="剛")  # 剛剋柔：3%
    p.rack = [_jacket(aid="甲:2", attribute="快", edge=10)]  # 不剋：修好之後 6%
    assert armor.wanted(s, content, ng) == "smith:wield:甲:2"  # 比的是修好之後的減損
    p.armor, p.rack = _jacket(attribute="快", edge=40), []
    assert armor.wanted(s, content, ng) == f"{armor.BUY}柔"  # 架上有同屬性的（9%）
    p.armor = _jacket(attribute="柔", edge=40)
    p.materials = {"gang_1": 1}
    assert armor.wanted(s, content, ng) == armor.REPAIR
    p.armor.edge = 60
    assert armor.wanted(s, content, ng) is None  # 耐久 50 以上不修
    p.location = "lake"
    assert armor.wanted(s, content, ng) is None


def test_wanted_buys_a_piece_that_does_not_clash_when_the_shop_has_no_match(content, world):
    game = _town(content, world)  # 靜心訣：虛，架上沒有虛
    s, p = game.state, game.state.player
    ng = _neigong(game, content, world)
    assert armor.wanted(s, content, ng) == f"{armor.BUY}剛"  # 剛不剋虛：照剛柔快慢的順序第一件
    p.armor = _jacket(attribute="剛", name="鐵葉甲")
    assert armor.wanted(s, content, ng) is None  # 身上那件跟架上一樣好：不會路過就再買一件
    assert armor.wanted(s, content, None) is None  # 沒有內功也一樣挑剛


def test_rows_and_card_line(content, world):
    _on(content)
    game = _game(content, world)
    s, p = game.state, game.state.player
    ng = _neigong(game, content, world)
    assert armor.card_line(s, content, ng) == ""
    p.armor = _jacket(edge=80)
    p.rack = [_jacket(aid="甲:2", name="鐵葉甲", attribute="實", tier=2, quality="中品"), _blade()]
    assert armor.card_line(s, content, ng) == "防具　【試甲】屬虛・一階下品・耐久度 80，一場少扣 8% 氣血（跟你的內功同屬性）"
    data = armor.rows(s, content, ng)
    assert data["worn"]["cut"] == "8%" and data["worn"]["confirm"] == "" and data["worn"]["grade"] == "一階下品"
    assert data["worn"]["wear_word"] == equipment.WEAR_WORDS["armor"] == "耐久度" and "recipe" not in data["worn"]  # 配方等防具打造那一批
    assert [r["id"] for r in data["rack"]] == ["甲:2"]  # 裝備庫裡的兵器不列在防具那一段
    assert data["rack"][0]["fit"] == armor.CLASH_NOTE and data["rack"][0]["cut"] == "11%"  # 12＋2－3
    assert data["rack"][0]["confirm"] == "把【鐵葉甲】（二階中品）拆成玄鋼骨×1？拆掉就沒了。"
    content.config.armor.enabled = False
    assert armor.rows(s, content, ng) == {"worn": None, "rack": []} and armor.card_line(s, content, ng) == ""


def test_shop_names_are_original_and_do_not_clash_with_weapons():
    from tianxia import naming
    from tianxia.models import WEAPON_KINDS
    c = real_content()
    names = set(armor.SHOP_NAMES.values())
    assert set(armor.SHOP_NAMES) == set(armor.SHOP_ATTRIBUTES) and len(names) == 4
    assert not names & {weapons.shop_name(k, a) for k in WEAPON_KINDS for a in weapons.ATTR_WORDS}
    taken = {s.name for s in c.skills.values()} | {m.name for m in c.materials.values()} | {ch.name for ch in c.characters.values()}
    assert not names & taken
    assert not [n for n in names if naming.name_problem(n, c, None)]
