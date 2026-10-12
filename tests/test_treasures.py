"""寶物與好馬（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第六節、5.7；計畫 docs/superpowers/plans/2026-10-11-裝備-3-寶物與好馬.md）。"""
from __future__ import annotations

import json
import random
from unittest import mock

import pytest

from conftest import install_season_one, next_season, real_content
from test_content import copy_fixture, edit_json
from tianxia import equipment, rules, treasures
from tianxia.characters import CharacterStore
from tianxia.content import ContentError, load_content
from tianxia.engine import Game
from tianxia.models import GOOD_HORSE, TREASURE_EFFECTS, Effect, GearBook, GiftDef, SteedDef, TreasureDef
from tianxia.state import BattleRecord, Bounty, Equipment, GameState

NAMES = {"cultivate": "凝神香囊", "insight": "觀山石", "win_xinde_pct": "戰記殘簡", "win_exp_pct": "百戰護符",
         "seclusion": "入定蒲團", "audience": "烏木名刺", "win_material": "拾遺囊", "legend": "叩關玉"}


def _book(content):
    """打開寶物（測試內容四欄都關著），裝上一份寶物表：掉落池八件（id 就是效果鍵），名將贈禮韓鐵（mate）一件寶物、小六（pupil）一匹名駒。"""
    content.config.treasures.enabled = True
    content.gear = GearBook(
        treasures={**{key: TreasureDef(id=key, name=name, effect=key) for key, name in NAMES.items()},
                   "caoxie": TreasureDef(id="caoxie", name="舊草鞋", effect="win_material", pool=False)},
        steeds={"tashuang": SteedDef(id="tashuang", name="踏霜駒")},
        gifts=[GiftDef(character="mate", gear="caoxie"), GiftDef(character="pupil", gear="tashuang")],
    )
    return content


def _item(key, iid="寶:1"):
    """一件寶物（template 就是 _book 寶物表的 id）。"""
    return Equipment(id=iid, slot="treasure", name=NAMES.get(key, key), template=key)


def _game(content, world, name="寶客", at="town"):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    game.state.player.location = at
    return game


GEAR = {  # 測試內容用的 content/gear.json（_gear_root 寫進一份複本）
    "treasures": [{"id": "mingci", "name": "烏木名刺", "effect": "audience"},
                  {"id": "caoxie", "name": "舊草鞋", "effect": "win_material", "pool": False}],
    "steeds": [{"id": "tashuang", "name": "踏霜駒"}],
    "gifts": [{"character": "mate", "gear": "caoxie"}, {"character": "pupil", "gear": "tashuang"}],
}


def _gear_root(tmp_path, edit=None):
    root = copy_fixture(tmp_path)
    data = json.loads(json.dumps(GEAR))
    if edit is not None:
        edit(data)
    (root / "gear.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return root


# ── Task 1：資料形狀、寶物表與寶物那一欄 ──

def test_the_treasure_slot_is_on_by_its_own_switch(content):
    assert not equipment.on(content, "treasure")  # 測試內容關著（設計 2.6）
    content.config.treasures.enabled = True
    slot = equipment.SLOTS["treasure"]
    assert equipment.on(content, "treasure")
    # 寶物不設限制（2.3【定】，企劃者 2026-10-11）：不擋路上（只有坐騎擋）；沒有磨損，所以沒有提醒旗標
    assert (slot.prefix, slot.label, slot.warned, slot.road_locked) == ("寶", "寶物", "", False)
    assert "treasure" not in equipment.DISMANTLABLE  # 寶物不能拆（4.8）


def test_a_treasure_needs_no_tier_or_quality_and_keeps_its_template():
    item = Equipment(id="寶:1", slot="treasure", name="烏木名刺", template="wumu_mingci")
    assert (item.tier, item.quality, item.template) == (0, "", "wumu_mingci")
    assert equipment.grade(item) == ""


def test_store_puts_a_treasure_on_without_a_warning_flag_or_into_the_rack(content, state):
    _book(content)
    item = treasures.new_treasure(state, content, "audience")
    assert (item.id, item.slot, item.name, item.template) == ("寶:1", "treasure", "烏木名刺", "audience")
    assert equipment.store(state, item) == equipment.SLOTS["treasure"].put_on.format(name="烏木名刺")
    assert state.player.treasure is item
    second = treasures.new_treasure(state, content, "win_material")
    assert equipment.store(state, second) == equipment.STORED.format(name="拾遺囊")  # 寶物欄有東西了：進裝備庫
    assert state.player.rack == [second] and second.id == "寶:2"


def test_old_save_from_equipment_batch_two_reads_with_empty_treasure_fields(content, world):
    """裝備四欄 3.2：裝備二的舊存檔（沒有 treasure、treasure_drops、held_gear，裝備沒有 template；季沒有 general_gifts、tianji）
    讀得進來，欄位都是預設值。"""
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    game.state.player.rack = [Equipment(id="騎:1", slot="mount", name="棗騮馬", tier=1, quality="下品")]
    raw = game.state.model_dump(mode="json")
    for key in ("treasure", "treasure_drops", "held_gear"):
        raw["player"].pop(key)
    raw["player"]["rack"][0].pop("template")
    raw["world"] = game.state.world.model_dump(mode="json")  # GameState 的 world 是 exclude 的；舊存檔裡夾帶的 world 讀得進來、隨即被取代
    for key in ("general_gifts", "tianji"):
        raw["world"].pop(key)
    loaded = GameState.model_validate(raw)
    p = loaded.player
    assert p.treasure is None and p.treasure_drops == set() and p.held_gear == []
    assert p.rack[0].template is None and loaded.world.general_gifts == {} and loaded.world.tianji == 0
    old = Bounty.model_validate({"id": "b1", "kind": "strike", "faction": "guan", "week": 1, "expires": 1.0, "silver": 20, "deeds": 3})
    assert old.prize is None


def test_a_new_season_clears_the_treasure_fields(content, world):
    _book(content)
    game = _game(content, world)
    p = game.state.player
    p.treasure, p.rack, p.held_gear = _item("audience"), [_item("win_material", "寶:2")], [_item("legend", "寶:3")]
    p.treasure_drops = {"bocai"}
    game.state.world.general_gifts = {"mate": "寶客"}
    next_season(content, world, game)
    p = game.state.player
    assert p.treasure is None and p.rack == [] and p.held_gear == [] and p.treasure_drops == set()
    assert game.state.world.general_gifts == {}  # 全服的贈禮名單跟著新的一季重來（2.4、第八節）


def test_the_gear_table_loads_from_gear_json(tmp_path):
    c = load_content(_gear_root(tmp_path))
    assert c.gear.treasures["mingci"].effect == "audience" and c.gear.treasures["caoxie"].pool is False
    assert c.gear.steeds["tashuang"].quality == "上品" and [g.character for g in c.gear.gifts] == ["mate", "pupil"]


def test_no_gear_json_means_an_empty_table(content):
    assert content.gear == GearBook()


@pytest.mark.parametrize(("edit", "match"), [
    (lambda d: d["treasures"][0].update(name="韓鐵"), "命名過濾"),  # 跟人物同名
    (lambda d: d["treasures"][0].update(effect="power"), "effect"),  # 不是八種之一
    (lambda d: d["gifts"][0].update(character="ghost"), "ghost"),
    (lambda d: d["gifts"][1].update(gear="mingci"), "贈禮"),  # 掉落池的寶物不能當贈禮
    (lambda d: d["gifts"].append({"character": "mate", "gear": "tashuang"}), "兩次"),
    (lambda d: d["treasures"][0].update(pool=False), "掉落池"),  # 掉落池一件都沒有
    (lambda d: d["steeds"].append({"id": "good_horse", "name": "雪蹄駒"}), "good_horse"),
    (lambda d: d["gifts"][0].update(line="{who}送你【{gift}】"), "general"),
    (lambda d: d.update(armor=[]), "gear.json"),
])
def test_bad_gear_tables_are_rejected(tmp_path, edit, match):
    with pytest.raises(ContentError, match=match):
        load_content(_gear_root(tmp_path, edit))


def test_the_real_gear_table_has_eight_pool_treasures_and_seven_gifts():
    c = real_content()
    pool = [t for t in c.gear.treasures.values() if t.pool]
    assert len(pool) == 8 and {t.effect for t in pool} == set(TREASURE_EFFECTS)
    assert {g.character for g in c.gear.gifts} == {"caocao", "sunjian", "liubei", "guanyu", "zhangfei", "yuanshao", "taoqian"}
    assert sorted(c.gear.steeds[g.gear].name for g in c.gear.gifts if g.gear in c.gear.steeds) == ["破浪駒", "踏霜駒"]


def test_effect_of_reads_the_template_and_names_follow_the_content(content, state):
    _book(content)
    p = state.player
    p.treasure = _item("audience")
    p.treasure.name = "舊名"
    assert treasures.effect_of(content, p.treasure) == "audience"
    assert treasures.effect_of(content, Equipment(id="兵:1", name="試刃", template="audience")) is None  # 不是寶物那一欄
    treasures.refresh_names(p, content)
    assert p.treasure.name == "烏木名刺"
    p.treasure.template = "gone"  # 內容拿掉了這一件：名字留著當備份、沒有效果
    treasures.refresh_names(p, content)
    assert p.treasure.name == "烏木名刺" and treasures.effect_of(content, p.treasure) is None
    assert "3" in treasures.effect_text(content, "audience") and "20%" in treasures.effect_text(content, "win_xinde_pct")
    assert "25%" in treasures.effect_text(content, "win_material")
    assert "×2" in treasures.effect_text(content, "legend") and content.config.legend_item_name in treasures.effect_text(content, "legend")


def test_loading_a_save_refreshes_treasure_and_steed_names(content, world):
    """設計 3.1：寶物與名駒的名字照 template 從內容讀（joy 改名不動存檔）——每次建 Game 都照內容重寫一次 name。"""
    _book(content)
    content.config.mounts.enabled = True
    game = _game(content, world)
    p = game.state.player
    p.treasure = _item("audience")
    p.treasure.name = "舊名"
    p.held_gear = [Equipment(id="騎:2", slot="mount", name="舊駒", tier=3, quality="上品", template="tashuang")]
    CharacterStore(world.db).save(game.state)
    loaded = Game(content, CharacterStore(world.db).load("寶客"), random.Random(0), world)
    assert loaded.state.player.treasure.name == "烏木名刺" and loaded.state.player.held_gear[0].name == "踏霜駒"
    assert treasures.owned_templates(loaded.state.player) == {"audience", "tashuang"}
