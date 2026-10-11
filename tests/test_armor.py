"""防具與裝備四欄（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第二～四節、第九節；
計畫 docs/superpowers/plans/2026-10-10-裝備-1-四欄化與防具.md）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import next_season, real_content, walk_to
from tianxia import equipment, rules, team, weapons
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
