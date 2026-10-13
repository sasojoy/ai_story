"""店面第一批：共用店面與鐵匠鋪（docs/superpowers/specs/2026-10-13-店面獨立介面-design.md；
計畫 docs/superpowers/plans/2026-10-13-店面-1-共用店面與鐵匠鋪.md）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import equipment, shopview, smithing
from tianxia.content import validate

LINES = {"smith": {key: [f"鐵匠說{key}之一。", f"鐵匠說{key}之二。"] for key in shopview.SITUATIONS["smith"]}}


def _smith(content, world, silver=300, name="試鋪"):
    """測試內容的城鎮（town）、兵器防具都開著、店面的字照 LINES；身上那門是流雲劍（柔・劍）；背包：精鐵砂 ×4、玄鋼骨 ×1、驚羽 ×2。
    走進鐵匠鋪（act:smith）。"""
    from tianxia import rules
    from tianxia.engine import Game

    content.config.weapons.enabled = content.config.armor.enabled = True
    content.shop_lines = LINES
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, "sword")
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.stats["wis"] = "town", 100.0, silver, 5
    p.member.wugong_id = "sword"
    p.materials = {"gang_1": 4, "gang_2": 1, "kuai_1": 2}
    game.sync(0.0)
    game.choose("act:smith")
    return game


# ── Task 1：開關、掌櫃的話與存檔欄位 ──


def test_the_switch_is_on_by_default_and_the_lines_load_from_content():
    c = real_content()
    assert c.config.shop_screens is True
    for key in shopview.SITUATIONS["smith"]:
        assert c.shop_lines["smith"][key], key
    validate(c)


def test_a_missing_situation_is_refused_when_the_smithy_is_open():
    from tianxia.content import ContentError

    c = real_content()
    del c.shop_lines["smith"]["temper"]
    with pytest.raises(ContentError, match="temper"):
        validate(c)
    c = real_content()
    c.shop_lines["smith"]["buy"] = [" "]
    with pytest.raises(ContentError, match="空白"):
        validate(c)
    c = real_content()
    c.shop_lines["inn"] = {"enter": ["掌櫃說話。"]}
    with pytest.raises(ContentError, match="不認得的店"):
        validate(c)


def test_entering_and_each_smith_action_record_a_keeper_situation(content, world):
    game = _smith(content, world)
    p = game.state.player
    assert p.shop_line == "enter" and shopview.line_text(game.state, content, "smith") in LINES["smith"]["enter"]
    game.choose("smith:buy:劍")
    assert p.shop_line == "buy"
    p.stats["silver"] = 3
    game.choose("smith:buy:刀")  # 灰掉的鈕：choose 在選單那一關就擋下，掌櫃那一句不動（錢不夠那一句留給開爐被拒絕，Task 4）
    assert p.shop_line == "buy"
    p.stats["silver"] = 300
    p.weapon.edge = 40
    game.choose("smith:repair")
    assert p.shop_line == "repair"
    game.choose("smith:temper")
    assert p.shop_line == "temper"
    game.choose("smith:back")
    assert (p.shop_line, p.shop_clue) == ("", "")


def test_the_keeper_line_stays_put_across_polls(content, world):
    game = _smith(content, world)
    first = shopview.line_text(game.state, content, "smith")
    game.sync(50.0)
    assert shopview.line_text(game.state, content, "smith") == first
    lines = {shopview.line_text(game.state, content, "smith") for _ in range(5)}
    assert lines == {first}


def test_problem_and_forged_keys():
    from tianxia.state import Weapon

    assert shopview.problem_key(None, "buy") == "buy"
    assert shopview.problem_key("還差 12 兩", "buy") == "short_silver"
    assert shopview.problem_key(equipment.RACK_FULL, "buy") == "rack_full"
    assert shopview.problem_key("刀口還利", "repair") == "refused"
    w = Weapon(id="兵:1", name="試刃", kind="劍", attribute="剛", tier=1, quality="中品")
    assert shopview.forged_key(w) == "forge_mid"
    assert shopview.forged_key(w.model_copy(update={"secret": "t_blade"})) == "forge_named"
    assert shopview.forged_key(w.model_copy(update={"original": True})) == "forge_divine"
    assert shopview.forged_key(w.model_copy(update={"copy_of": "鑄|t_star"})) == "forge_divine"


def test_the_smith_clue_takes_over_the_keeper_line_for_one_action(content, world, monkeypatch):
    game = _smith(content, world)
    monkeypatch.setattr(game, "_smith_clue", lambda: ["鐵匠順口說了一句口訣。"])
    game.choose("smith:buy:劍")
    assert shopview.line_text(game.state, content, "smith") == "鐵匠順口說了一句口訣。"
    game.choose("smith:page:armor")
    assert shopview.line_text(game.state, content, "smith") in LINES["smith"]["buy"]
