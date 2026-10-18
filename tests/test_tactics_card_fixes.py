"""本命戰法跟卡上寫的對齊（PM 2026-10-16 整理「裝備特技與武學特效」時核對出來的六處；企劃者定：我們修、修完通知 joy）。
每一條鎖住卡上寫的行為：
1. 曹操的人器合一：帶著梟風槍，亂世心術反彈 60%；反彈有好幾個來源時取最高的，不互相蓋掉、不清成 0。
2. 人器合一只加強卡上寫的那一門（袁紹的冠冕劍只拉長世家威儀，名門心法的猶疑兩端照舊一直在）。
3. 盧植〈經師正氣訣〉海內儒宗：守一只撐前 3 回合。
4. 特別功效〔悟招〕決戰不發（決戰只記剋中、不記被剋，層數疊不起來）。
5. 寶物〔觀山石〕的卡片照探索三選一的開關寫。
6. 本命底蘊照實際寫（19.5%，不四捨五入）。"""
from __future__ import annotations

import itertools
import random

import pytest
from conftest import real_content

from tianxia import tactics, team, treasures
from tianxia.engine import Game
from tianxia.state import PLAYER, Equipment

FIGURES_WITH_ARMS = ("caocao", "liubei", "guanyu", "zhangfei", "sunjian", "yuanshao", "taoqian")


def _ctx(**kw):
    return tactics.Ctx(**({"foe": "對手", "our_agility": 5.0, "foe_agility": 5.0, "team": [PLAYER]} | kw))


def _only(content, skill_id, **update):
    tactic = content.skills[skill_id].tactic.model_copy(update=update)
    return tactics.Holder(who="你", key=PLAYER, skill=skill_id, figure=tactics.figure_of(content, skill_id), tactic=tactic)


def _armed(content, figure, *, wugong=True, neigong=True):
    """新角色練著那位名將的本命（武學、內功照參數），身上帶著他的本命兵器。回（Game, 戰法名 → Holder）。"""
    content.config.weapons.enabled = True
    game = Game.new(content, "試器俠客", rng=random.Random(0))
    ch, p = content.characters[figure], game.state.player
    if wugong:
        p.member.wugong_id, p.member.wugong_level = ch.starting_wugong, 10
    if neigong:
        p.member.neigong_id, p.member.neigong_level = ch.starting_neigong, 10
    arm = next(a for a in content.gear.signature_arms if a.character == figure)
    p.weapon = Equipment(id="兵:7", name=arm.name, kind=arm.kind, attribute=arm.attribute, tier=3, quality="上品",
                         original=True, signature=figure)
    holders = team.tactic_holders(game.state, content, game.world)
    return game, holders


def _reflect_after_round_one(holders, content):
    bout = tactics.open_bout(tactics.side_for(holders, _ctx()), None, "你", "對手")
    tactics.step(bout, "強攻", "固守", 50.0, content.config.tactics, random.Random(0))
    return bout.a.status.reflect, bout.a.status.reflect_by


# ── 1. 曹操的人器合一：反彈 60%，取最高的 ──


def test_caocao_with_his_spear_reflects_sixty_percent():
    content = real_content()
    _game, holders = _armed(content, "caocao", wugong=False)
    by_name = {h.tactic.name: h for h in holders}
    assert by_name["亂世心術"].tactic.params["reflect_pct"] == pytest.approx(0.6) and "挾勢" in by_name
    # 梟風槍〔挾勢〕也是起手的守一、排在亂世心術後面：以前它把反彈寫回 0
    assert _reflect_after_round_one(holders, content) == (pytest.approx(0.6), "亂世心術")


def test_reflect_takes_the_highest_source_in_any_order():
    """亂世心術 40%、絕招〔穩〕30%、梟風槍〔挾勢〕0%：誰先發動都一樣，取 40%（不被後面的蓋掉、不清成 0）。"""
    content = real_content()
    ward = _only(content, "caocao_neigong", rate=1.0)
    steady = next(t for t in content.traits.general if t.name == "穩").ultimate
    arm = next(a for a in content.gear.signature_arms if a.character == "caocao")
    others = [tactics.Holder(who="你", key=PLAYER, skill="絕學", tactic=steady),
              tactics.Holder(who="你", key=PLAYER, skill="兵:7", tactic=arm.tactic)]
    for order in itertools.permutations([ward, *others]):
        assert _reflect_after_round_one(list(order), content) == (pytest.approx(0.4), "亂世心術"), [h.tactic.name for h in order]
    assert _reflect_after_round_one(others, content) == (pytest.approx(0.3), steady.name)  # 沒練亂世心術：穩的 30% 照舊


# ── 2. 人器合一只加強卡上寫的那一門 ──


@pytest.mark.parametrize("figure", FIGURES_WITH_ARMS)
def test_a_bond_strengthens_only_the_tactic_its_card_names(figure):
    content = real_content()
    _game, holders = _armed(content, figure)
    ch = content.characters[figure]
    plain = {content.skills[s].tactic.name: content.skills[s].tactic for s in (ch.starting_wugong, ch.starting_neigong)}
    got = {h.tactic.name: h.tactic for h in holders}
    arm = next(a for a in content.gear.signature_arms if a.character == figure)
    changed = [name for name, tactic in plain.items() if got[name] != tactic]
    assert changed == [arm.bond.tactic] and arm.bond.tactic in arm.bond.desc


def test_yuanshao_crown_sword_lengthens_the_awe_and_leaves_the_neigong_always_on():
    content = real_content()
    _game, holders = _armed(content, "yuanshao")
    got = {h.tactic.name: h.tactic for h in holders}
    assert got["世家威儀"].rounds == 3
    assert got["猶疑兩端"].rounds == 0 and tactics.when_text(got["猶疑兩端"]) == "心法・一直在"


# ── 3. 盧植的海內儒宗：守一只撐前 3 回合 ──


def test_luzhi_ward_lasts_the_first_three_rounds_only():
    content = real_content()
    t = content.config.tactics
    bout = tactics.open_bout(tactics.side_for([_only(content, "luzhi_neigong")], _ctx()), None, "你", "對手")
    held = []
    for r in range(5):
        step = tactics.step(bout, "固守", "固守", 50.0, t, random.Random(r))
        held.append(bout.a.status.has("守一"))
        tactics.close_round(bout, step.push, t, random.Random(r))
    assert held == [True, True, True, False, False]
    assert "前 3 回合" in tactics.card_text(content.skills["luzhi_neigong"].tactic)


# ── 4. 悟招決戰不發 ──


def test_wuzhao_is_not_a_showdown_tactic():
    """決戰只記你剋中（battle_instance 傳的 beat 是 1 或 0）、不記被剋，悟招的層數疊不起來：不列在決戰發得了的裡面。"""
    content = real_content()
    special = next(s for s in content.traits.special if s.name == "悟招")
    assert special.tactic.kind == "insight" and "insight" not in tactics.WAR_KINDS


# ── 5. 觀山石的卡片照探索三選一的開關 ──


def test_the_insight_stone_card_follows_the_explore_switch():
    content = real_content()
    cfg = content.config
    assert cfg.explore_modes.enabled and cfg.treasures.effects["insight"] != 1.0
    assert treasures.effect_text(content, "insight") == f"靜心感悟擲中的機會 +{cfg.explore_modes.sense_treasure_points:g} 個百分點"
    cfg.explore_modes.enabled = False
    assert treasures.effect_text(content, "insight") == f"探索悟得意境的機會 ×{cfg.treasures.effects['insight']:g}"


# ── 6. 本命底蘊照實際寫 ──


@pytest.mark.parametrize("skill_id, shown", [
    ("caocao_wugong", "11"), ("guanyu_wugong", "15"), ("yuanshao_wugong", "18"), ("taoqian_wugong", "28"),
    ("zhujun_wugong", "9"), ("sunjian_wugong", "2"), ("sunjian_neigong", "2"),
])
def test_the_might_note_writes_the_real_number(skill_id, shown):
    content = real_content()
    tactic = content.skills[skill_id].tactic
    assert f"{tactic.might * 100:.1f}".rstrip("0").rstrip(".") == shown  # 內容寫的數字本身不動
    assert f"每一回合推力 +{shown}%" in tactics.card_text(tactic)
