"""回饋單丙批（PM 2026-10-14 派工：回饋單甲批、乙批 QA 新開的四張小單）：一張單一段，各自的重現與修正。新寫的字都待 joy 潤。"""
from __future__ import annotations

import pytest
from test_forge_divine import _forger, divine_content  # noqa: F401（fixture）

import server
import webharness
from tianxia import equipment, forge_secrets, shopview, skillview, smithing, weapons
from tianxia.state import Weapon

needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


# ── FB-197：防具神器的定名表單寫「這把神器」→ 量詞照 equipment.unit_for，伺服器帶出去、網頁照它寫 ──


def _slot_rows(game, content, world, slot):
    block = next(b for b in skillview.gear_rows(game.state, content, world)["slots"] if b["slot"] == slot)
    return [block["worn"], *block["rack"]]


def test_fb197_the_practice_rows_carry_the_unit_of_the_unnamed_original(divine_content, world):
    """修練頁（與店面裝備庫，shopview._rack 讀同一份）那一列的 divine 多帶量詞：兵器照種類（劍一把），防具一件。"""
    game = _forger(divine_content, world, name="甲")
    blade, _ = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")
    coat, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3",
                             rng=smithing.own_rng(game.state, "鎧|gang_3+gang_3"))
    assert blade.original and coat.original
    [row] = [r for r in _slot_rows(game, divine_content, world, "weapon") if r and r["id"] == blade.id]
    assert row["divine"] == {"pattern": "墜星劍", "unit": "把"}
    [row] = [r for r in _slot_rows(game, divine_content, world, "armor") if r and r["id"] == coat.id]
    assert row["divine"] == {"pattern": "鎮星甲", "unit": "件"}
    assert row["divine"]["unit"] == equipment.unit_for("armor")


def test_fb197_a_fist_original_is_a_fu(divine_content, world, monkeypatch):
    """拳套論副（FB-133）：等著定名的拳套那一列寫「副」，跟 equipment.unit_for 同一個字。"""
    game = _forger(divine_content, world, name="甲")
    fist = weapons.new_weapon(game.state, name="無名神器", kind="拳腳", attribute="剛", tier=3, quality="上品")
    game.state.player.rack.append(fist)
    monkeypatch.setattr(forge_secrets, "unnamed_originals", lambda state, world: {fist.id: "撼岳拳套"})
    [row] = [r for r in _slot_rows(game, divine_content, world, "weapon") if r and r["id"] == fist.id]
    assert row["divine"] == {"pattern": "撼岳拳套", "unit": "副"} == {"pattern": "撼岳拳套", "unit": equipment.unit_for("weapon", "拳腳")}


def test_fb197_the_forged_card_carries_the_unit(divine_content, world):
    """店面的出爐卡（shopview.forged_card）多一個 unit：防具一件、拳套一副、其他兵器一把。"""
    game = _forger(divine_content, world, name="甲")
    coat, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3",
                             rng=smithing.own_rng(game.state, "鎧|gang_3+gang_3"))
    card = shopview.forged_card(game.state, divine_content, world, coat, {"first": True})
    assert card["divine"] == "鎮星甲" and card["unit"] == "件"
    fist = weapons.new_weapon(game.state, name="鐵拳", kind="拳腳", attribute="剛", tier=1, quality="下品")
    assert shopview.forged_card(game.state, divine_content, world, fist, {})["unit"] == "副"
    blade = weapons.new_weapon(game.state, name="鐵劍", kind="劍", attribute="剛", tier=1, quality="下品")
    assert shopview.forged_card(game.state, divine_content, world, blade, {})["unit"] == "把"


@needs_node
def test_fb197_the_practice_page_form_says_jian_for_armor_and_fu_for_a_fist(hints_content, world):
    """修練頁那一列底下的表單：照 divine.unit 寫「這件神器」「這副神器」「這把神器」，不再一律寫「把」。"""
    import random

    from test_prologue_web import run
    from test_weapons_web import _armor_row, _gear, _row, _slot_block

    from tianxia.engine import Game

    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    m, x = server.main_view(game), server.menxia_view(game)
    x["gear"] = _gear(
        weapon={"worn": None, "rack": [_row(id="兵:2", kind="拳腳", name="無名神器", keep="原品不能拆", divine={"pattern": "撼岳拳套", "unit": "副"}),
                                       _row(id="兵:3", name="無名神器", keep="原品不能拆", divine={"pattern": "墜星劍", "unit": "把"})]},
        armor={"worn": _armor_row(id="甲:1", name="無名神器", keep="原品不能拆", divine={"pattern": "鎮星甲", "unit": "件"}), "rack": []},
    )
    page = run(m, "return H.pagePractice();", menxia=x)
    armor_block, weapon_block = _slot_block(page, "armor"), _slot_block(page, "weapon")
    assert "打出這件神器的人" in armor_block and "這把神器" not in armor_block
    assert "打出這副神器的人" in weapon_block and "打出這把神器的人" in weapon_block


@needs_node
def test_fb197_the_shop_forged_card_and_rack_follow_the_server_unit(content, world, monkeypatch):
    """店面：出爐卡照卡上的 unit（防具一件），裝備庫那一頁照那一列的 divine.unit（拳套一副）。伺服器真的帶出去的資料（main_view）。"""
    import json

    from test_shop import _smith
    from test_shop_web import FORGED
    from test_shop_web import run as shop_run

    game = _smith(content, world)
    fist = Weapon(id="兵:7", name="無名神器", kind="拳腳", attribute="剛", tier=3, quality="上品", original=True)
    game.state.player.rack = [fist]
    monkeypatch.setattr(forge_secrets, "unnamed_originals", lambda state, world: {fist.id: "撼岳拳套"})
    m = server.main_view(game)
    [row] = m["shop"]["rack"]["rows"]
    assert row["divine"] == {"pattern": "撼岳拳套", "unit": "副"}
    rack = shop_run(m, 'H.S.shopTab = "rack"; H.render(); return T.els.app.innerHTML;')
    assert "打出這副神器的人" in rack and "這把神器" not in rack
    shop = json.loads(json.dumps(m["shop"]))
    shop["pending"] = {"甲:1": "鎮星甲"}
    card = {**FORGED, "id": "甲:1", "slot": "armor", "kind": "防具", "first": True, "glow": "redgold", "divine": "鎮星甲", "unit": "件"}
    html = shop_run({**m, "shop": shop}, "H.S.shopReveal = H.S.next; H.S.shopOpened = true; H.render(); return T.els.app.innerHTML;",
                    S={"next": card})
    assert 'id="shop-name-divine-甲:1"' in html and "打出這件神器的人" in html and "這把神器" not in html
