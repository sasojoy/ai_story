"""本命武學加強（企劃者 2026-10-15「現在的本命絕學很爛，甚至比玩家自己合成的還差，也沒什麼特色效果」；tianxia/signature.py）：
玩家自己那一份威力 × Config.signature_arts.power_scale、內容寫三個一般功效與一個本命特效、學到時直接第七成（舊角色讀檔補上）。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from test_content import copy_fixture, edit_json

from tianxia import companion_agent, encounter, ranger, signature, skillview, team, traits
from tianxia.content import ContentError, load_content
from tianxia.engine import Game
from tianxia.state import PLAYER


def _game(content=None):
    content = content or real_content()
    return content, Game.new(content, "測試俠客", rng=random.Random(0))


def _wear(game, wugong, neigong, level=10):
    m = game.state.player.member
    m.wugong_id, m.wugong_level, m.neigong_id, m.neigong_level = wugong, level, neigong, level


def test_every_figure_art_has_its_own_signature_and_three_traits():
    content = real_content()
    names = set()
    for ch in content.characters.values():
        for sid in (ch.starting_wugong, ch.starting_neigong):
            if not sid:
                continue
            skill = content.skills[sid]
            assert skill.signature is not None, sid
            assert len(skill.traits) == 3 and skill.traits[0] == skill.attribute, sid
            names.add(skill.signature.name)
    assert len(names) == 36


def test_only_the_player_copy_is_scaled():
    content, game = _game()
    w = game.world
    own = team.player_art(game.state, content, w, "liubei_wugong")
    plain = team.resolve_art("liubei_wugong", content, w)
    k = content.config.signature_arts.power_scale
    assert own.top_power == pytest.approx(plain.top_power * k)
    assert plain.top_power == 120  # 同伴練的照內容（不乘）
    assert team.player_art(game.state, content, w, "zhuifeng").top_power == team.resolve_art("zhuifeng", content, w).top_power


def test_self_and_mate_power_lift_the_team():
    content, game = _game()
    _wear(game, "liubei_wugong", "liubei_neigong")  # 仁德：門下威力 +10%
    assert signature.amount(game.state, content, "mate_power") == pytest.approx(0.10)
    _wear(game, "zhangfei_wugong", "zhangfei_neigong")  # 燕人豪氣：本人 +6%
    before = team.player_boost(game.state, content, game.world).factor
    assert team.team_boosts(game.state, content, game.world)[0].factor == pytest.approx(before * 1.06)


def test_combat_hooks_reach_mods_dodge_and_toll():
    content, game = _game()
    _wear(game, "guanyu_wugong", "guanyu_neigong")  # 溫酒斬將：破甲、先手
    lo = traits.loadout(game.state, content, game.world)
    plain, sig = team.trait_mods(content, lo), team.trait_mods(content, lo, game.state)
    assert sig.difficulty_cut == pytest.approx(plain.difficulty_cut + 0.06)
    assert sig.big_win_cut == pytest.approx(plain.big_win_cut + 0.06)
    _wear(game, "zhangbao_wugong", "zhangbao_neigong")  # 呼風喚霧：閃避 +10%
    assert team.dodge_chance(game.state, content) == pytest.approx(0.10)
    assert team.armor_cut(game.state, content, game.world) == pytest.approx(0.08)  # 地公：少扣 8%（沒穿防具）


def test_injury_cut_halves_the_injury():
    content, game = _game()
    _wear(game, "guanyu_wugong", "guanyu_neigong")  # 刮骨療毒：內傷少 50%
    m = game.state.player.member
    team.take_encounter_toll(game.state, content, game.world, "落敗")
    with_cut = m.injury
    _wear(game, "caocao_wugong", "caocao_neigong")
    m.injury, m.neili = 0.0, None
    team.take_encounter_toll(game.state, content, game.world, "落敗")
    assert with_cut == pytest.approx(m.injury * 0.5, rel=0.05)


def test_rewards_and_train_stamina():
    content, game = _game()
    base = game._action_costs()["train"]
    _wear(game, "caocao_wugong", "caocao_neigong")  # 兵貴神速：遊歷少花 2 點體力；唯才是舉：打贏經驗 +15%
    assert game._action_costs()["train"] == base - 2
    squad = next(s for s in content.squads.values() if s.exp >= 20)
    record = type("R", (), {"silver": 0, "xinde": 0, "exp": 0, "materials": [], "notes": [], "levelups": [], "kind": "event", "id": 1})()
    game.state.player.member.level = 50  # 滿級不升級，經驗照樣記
    streak = traits.amount(content, traits.loadout(game.state, content, game.world), "win_reward")  # 陽的乘勝照算
    game._battle_rewards(squad, record)
    assert record.exp == round(squad.exp * (1 + streak + 0.15) * ranger.exp_factor(game.state, content))


def test_heal_after_comes_back_after_a_fight():
    content, game = _game()
    _wear(game, "zhangjiao_wugong", "zhangjiao_neigong")  # 符水救人：打完回 4%、打贏再回 3%
    msgs, _, _ = game._take_toll("險勝")
    assert any(line.startswith("氣血 +") for line in msgs)


def test_learning_lands_on_the_seventh_cheng_and_old_saves_are_lifted():
    content, game = _game()
    p = game.state.player
    p.affinities["liubei"] = content.config.signature_affinity
    companion_agent._maybe_grant_signature_skill(game.state, content, content.characters["liubei"], "liubei")
    start = content.config.signature_arts.start_level
    assert {p.art_levels.get("liubei_wugong"), p.art_levels.get("liubei_neigong")} == {start}
    p.art_levels["liubei_wugong"] = 1  # 這一版之前學到的舊角色
    loaded = Game(content, game.state, random.Random(0), game.world)
    assert loaded.state.player.art_levels["liubei_wugong"] == start
    loaded.state.player.art_levels["liubei_wugong"] = 9  # 練得更高的不動
    again = Game(content, loaded.state, random.Random(0), loaded.world)
    assert again.state.player.art_levels["liubei_wugong"] == 9


def test_cards_show_the_signature():
    content, game = _game()
    art = team.player_art(game.state, content, game.world, "liubei_neigong")
    line = traits.card_line(content, art)
    assert "本命特效〔仁德〕" in line and "門下威力 +10%" in line
    _wear(game, "liubei_wugong", "liubei_neigong")
    card = skillview.member_card(game.state, content, game.world, PLAYER)
    assert "〔仁德〕" in card and "〔百折不撓〕" in card


def test_a_signature_on_an_ordinary_art_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)

    def put(skills):
        skills[0]["signature"] = {"name": "亂寫", "desc": "隨便寫的。", "effects": {"self_power": 0.1}}

    edit_json(root / "skills.json", put)
    with pytest.raises(ContentError, match="本命特效只能寫在"):
        load_content(root)


def test_encounter_mods_stay_plain_without_signature():
    content, game = _game()
    lo = traits.loadout(game.state, content, game.world)
    assert team.trait_mods(content, lo, game.state) == team.trait_mods(content, lo)
    assert isinstance(team.trait_mods(content, lo), encounter.Mods)
