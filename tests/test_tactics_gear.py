"""本命戰法第三批：武學功效換成的戰法、神器特技、名將本命兵器與人器合一（tianxia/tactics.py、traits.tactic_defs、team.own_extras）。"""
from __future__ import annotations

import random
from types import SimpleNamespace

import pytest
from conftest import real_content

from tianxia import armor, battle_instance, tactics, team, traits, weapons
from tianxia.engine import Game
from tianxia.state import PLAYER, Equipment


def _game(content):
    return Game.new(content, "試器俠客", rng=random.Random(0))


def _divine(recipe, *, original=True, slot="weapon", kind="劍"):
    return Equipment(id="兵:9" if slot == "weapon" else "甲:9", slot=slot, name="試", kind=kind if slot == "weapon" else "",
                     attribute="剛", tier=3, quality="上品", original=original,
                     secret=recipe if original else None, copy_of=None if original else f"鑄|{recipe}")


def test_trait_tactics_take_their_numbers_from_the_layers():
    content = real_content()
    lo = traits.Loadout(layers={"big_win": 3.0, "toll_cut": 2.0})
    defs = {t.name: t for t in traits.tactic_defs(content, lo)}
    assert defs["先手"].rate == pytest.approx(0.3) and "30%" in defs["先手"].desc
    assert defs["化勁"].params["toll_pct"] == pytest.approx(0.2) and defs["化勁"].params["chance_pct"] == pytest.approx(0.1)
    assert "{" not in defs["化勁"].desc
    capped = {t.name: t for t in traits.tactic_defs(content, traits.Loadout(layers={"big_win": 99.0}))}
    assert capped["先手"].rate == pytest.approx(0.5)  # 上限
    assert "厚" not in {t.name for t in traits.tactic_defs(content, traits.Loadout(layers={"condition_floor": 3.0}))}


def test_a_divine_original_has_its_tactic_and_a_copy_fires_less_often():
    content = real_content()
    orig = tactics.item_tactic(content, _divine("wd_dark_crystal"))
    copy = tactics.item_tactic(content, _divine("wd_dark_crystal", original=False))
    assert orig[0].name == copy[0].name == "虛影"
    assert copy[0].rate == pytest.approx(orig[0].rate * content.config.tactics.copy_rate)
    plain = Equipment(id="兵:1", name="鐵劍", kind="劍", attribute="剛", tier=1, quality="下品")
    assert tactics.item_tactic(content, plain) is None and tactics.item_lines(content, plain) == []
    lines = tactics.item_lines(content, _divine("wd_dark_crystal"))
    assert lines == [tactics.card_text(orig[0], tactics.GEAR_TITLE)] and lines[0].startswith("特技〔虛影〕")


def test_signature_arms_carry_a_bond_line():
    content = real_content()
    arm = next(a for a in content.gear.signature_arms if a.character == "guanyu")
    item = Equipment(id="兵:7", name=arm.name if hasattr(arm, "name") else "刀", kind="刀", attribute="剛", tier=3, quality="上品",
                     original=True, signature="guanyu")
    lines = tactics.item_lines(content, item)
    assert lines[0].startswith("特技〔斬將〕") and lines[1] == f"{tactics.BOND_TITLE}：{arm.bond.desc}"


def test_own_extras_adds_gear_and_traits_and_bonds_the_figure_art():
    content = real_content()
    game = _game(content)
    p = game.state.player
    p.member.wugong_id, p.member.wugong_level = "guanyu_wugong", 10
    base = team.tactic_holders(game.state, content, game.world)
    plain = {h.tactic.name: h.tactic for h in base}
    p.weapon = Equipment(id="兵:7", name="刀", kind="刀", attribute="剛", tier=3, quality="上品", original=True, signature="guanyu")
    content.config.weapons.enabled = True
    got = {h.tactic.name: h for h in team.tactic_holders(game.state, content, game.world)}
    assert "斬將" in got and got["斬將"].skill == "兵:7"
    sig = content.skills["guanyu_wugong"].tactic.name
    assert got[sig].tactic.prep == max(0, plain[sig].prep - 1)  # 人器合一：青龍拖刀不用蓄力
    p.member.wugong_id = None  # 沒練著關羽的本命：特技照有、沒有人器合一
    names = {h.tactic.name for h in team.tactic_holders(game.state, content, game.world)}
    assert "斬將" in names and sig not in names


def test_toll_cut_and_luck_scale_and_guard_pool():
    content = real_content()
    lo = traits.Loadout(layers={"toll_cut": 3.0, "luck_narrow": 2.0}, specials={"no_loss": next(
        t for t in content.traits.special if t.hook == "no_loss")})
    hs = [tactics.Holder(who="你", key=PLAYER, skill="trait", tactic=t) for t in traits.tactic_defs(content, lo)]
    assert tactics.toll_cut(hs) == pytest.approx(0.3)
    bout = tactics.open_bout(tactics.side_for(hs, tactics.Ctx(foe="")), None, "你", "他", b_agility=5.0)
    assert tactics.luck_scale(bout) == pytest.approx(0.7)
    assert tactics.luck_scale(None) == 1.0
    harm, said = tactics.guard_pool(bout, "a", 50.0, 80.0, 1000.0)
    assert harm == pytest.approx(0.0) and said and said[0].startswith("〔護命〕")  # 池子 50 不到一成：這一下不扣
    harm, said = tactics.guard_pool(bout, "a", 300.0, 400.0, 1000.0)
    assert harm == 400.0 and said == []  # 一場只用一次
    bout2 = tactics.open_bout(tactics.side_for(hs, tactics.Ctx(foe="")), None, "你", "他", b_agility=5.0)
    harm, _ = tactics.guard_pool(bout2, "a", 300.0, 400.0, 1000.0)
    assert harm == pytest.approx(200.0)  # 留一成
    assert tactics.guard_pool(bout2, "a", 300.0, 100.0, 1000.0)[0] == 100.0  # 打不空的不管


def test_a_bout_step_reports_the_soft_cut():
    content = real_content()
    lo = traits.Loadout(layers={"toll_cut": 3.0})
    hs = [tactics.Holder(who="你", key=PLAYER, skill="trait", tactic=t) for t in traits.tactic_defs(content, lo)]
    bout = tactics.open_bout(tactics.side_for(hs, tactics.Ctx(foe="")), None, "你", "他", b_agility=5.0)
    step = tactics.step(bout, "固守", "奇襲", 50.0, content.config.tactics, random.Random(0), b_auto=True)
    assert step.a_cut == pytest.approx(0.3) and step.b_cut == 0.0


def test_the_rally_signature_raises_allies_on_the_same_move_but_not_the_holder():
    content = real_content()
    arm = next(a for a in content.gear.signature_arms if a.character == "yuanshao")
    kit = tactics.side_for([tactics.Holder(who="袁", key=PLAYER, skill="gear", tactic=arm.tactic)], tactics.Ctx(foe=""))
    people = {
        "袁": SimpleNamespace(eliminated=False, kit=kit, faction="guan"),
        "甲": SimpleNamespace(eliminated=False, kit=None, faction="guan"),
    }
    instance = SimpleNamespace(participants=people)
    rally = battle_instance._war_rally(instance, {"袁": "強攻", "甲": "強攻"}, True)
    assert rally == {("guan", "強攻"): [("袁", arm.tactic.params["war_ally_pct"])]}
    assert battle_instance._war_rally(instance, {"袁": "強攻"}, False) == {}


def test_weapon_and_armor_rows_and_cards_write_the_tactic():
    content = real_content()
    game = _game(content)
    content.config.weapons.enabled = content.config.armor.enabled = True
    p = game.state.player
    p.weapon = _divine("wd_fallen_star", kind="刀")
    p.armor = _divine("ad_skim_shadow", slot="armor")
    w = weapons.rows(game.state, content, game.world, None)["worn"]
    a = armor.rows(game.state, content, None)["worn"]
    assert w["tactic"][0].startswith("特技〔墜星〕") and a["tactic"][0].startswith("特技〔殘影〕")
    assert "特技〔墜星〕" in weapons.card_line(game.state, content, game.world, None)
    assert "特技〔殘影〕" in armor.card_line(game.state, content, None)
