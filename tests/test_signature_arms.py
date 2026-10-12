"""打造第三批：名將本命兵器（docs/superpowers/specs/2026-10-09-兵器-design.md 4.10；打造隱藏配方設計第十三節第三批；
計畫 docs/superpowers/plans/2026-10-12-打造-3-名將本命兵器.md）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from test_treasures import _gear_root
from tianxia import naming
from tianxia.content import ContentError, load_content
from tianxia.engine import Game
from tianxia.models import GearBook, SignatureArmDef
from tianxia.state import GameState, SignatureClaim, Weapon

# 測試內容用的一把：韓鐵（mate）的刀。四個字、只帶「刀」：測試內容的兵器字表組出來的刀名都是三個字，撞不到
ARM = {"character": "mate", "name": "鐵脊長刀", "kind": "刀", "attribute": "剛"}


def _arms(content, **extra):
    """打開兵器（測試內容關著），裝上一把本命兵器（預設是 ARM；extra 改欄位）。直接建 GearBook，不走載入檢查。"""
    content.config.weapons.enabled = True
    content.gear = GearBook(signature_arms=[SignatureArmDef(**{**ARM, **extra})])
    return content


# ── Task 1：內容、資料形狀與載入檢查 ──

def test_the_real_table_has_seven_arms_matching_each_generals_own_art():
    c = real_content()
    arms = {a.character: a for a in c.gear.signature_arms}
    assert {cid: a.name for cid, a in arms.items()} == {
        "caocao": "梟風槍", "liubei": "雲紋雙鋒", "guanyu": "赤魄長刀", "zhangfei": "裂雷矛",
        "sunjian": "江潮槍", "yuanshao": "冠冕劍", "taoqian": "厚德杖",
    }  # 兵器設計 4.10 的暫名表（待 joy 潤；換名只改 content/gear.json）
    for cid, arm in arms.items():
        art = c.skills[c.characters[cid].starting_wugong]
        assert (arm.kind, arm.attribute) == (art.weapon, art.attribute), cid  # 種類・屬性照他的本命武學
    assert [(a.character, a.figure) for a in c.gear.signature_arms if a.figure] == [("sunjian", "sunjian")]  # 只有孫堅是大勢人物
    assert all(naming.name_problem(a.name, c) == naming.GEAR_CLASH for a in arms.values())  # 名字佔住：模型、玩家都取不到
    assert (c.config.weapons.signature_affinity, c.config.weapons.signature_wins) == (80, 3)


def test_the_signature_table_loads_from_gear_json(tmp_path):
    c = load_content(_gear_root(tmp_path, lambda d: d.update(signature_arms=[ARM])))
    arm = c.gear.signature_arms[0]
    assert (arm.character, arm.name, arm.kind, arm.attribute, arm.figure, arm.gift_line, arm.seize_line) == (
        "mate", "鐵脊長刀", "刀", "剛", None, "", "")
    assert naming.name_problem("鐵脊長刀", c) == naming.GEAR_CLASH


@pytest.mark.parametrize("bad, match", [
    ({"character": "ghost"}, "ghost"),
    ({"kind": "鞭"}, "種類"),
    ({"attribute": "冷"}, "屬性"),
    ({"name": "鐵脊長劍"}, "別種兵器"),  # 刀不能帶劍字
    ({"name": "烏木名刺"}, "重複"),  # 跟寶物同名（_gear_root 的寶物表裡有）
    ({"figure": "bocai"}, "大勢人物"),  # 測試內容沒有人物表
    ({"gift_line": "{who}把【{arm}】給你"}, "general"),
    ({"seize_line": "把【{gift}】擲給你"}, "general"),
])
def test_bad_signature_tables_are_rejected(tmp_path, bad, match):
    root = _gear_root(tmp_path, lambda d: d.update(signature_arms=[{**ARM, **bad}]))
    with pytest.raises(ContentError, match=match):
        load_content(root)


def test_one_general_has_one_arm(tmp_path):
    root = _gear_root(tmp_path, lambda d: d.update(signature_arms=[ARM, {**ARM, "name": "鐵脊重刀"}]))
    with pytest.raises(ContentError, match="兩次"):
        load_content(root)


def test_old_saves_read_with_empty_signature_fields(content, world):
    """舊存檔沒有 Equipment.signature、PlayerState.figure_wins、WorldState.signature_arms：讀得進來，都是預設值（不升資料庫版本）。"""
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    game.state.player.rack = [Weapon(id="兵:1", name="甲劍", kind="劍", attribute="剛", tier=1, quality="下品")]
    raw = game.state.model_dump(mode="json")
    raw["player"].pop("figure_wins")
    raw["player"]["rack"][0].pop("signature")
    raw["world"] = game.state.world.model_dump(mode="json")  # GameState 的 world 是 exclude 的；舊存檔裡夾帶的讀得進來、隨即被取代
    raw["world"].pop("signature_arms")
    loaded = GameState.model_validate(raw)
    assert loaded.player.figure_wins == {} and loaded.player.rack[0].signature is None and loaded.world.signature_arms == {}
    assert SignatureClaim(owner="甲", via="gift").model_dump() == {"owner": "甲", "via": "gift"}
