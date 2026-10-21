"""本命武學加強（企劃者 2026-10-15「現在的本命絕學很爛，甚至比玩家自己合成的還差，也沒什麼特色效果」；tianxia/signature.py）：
玩家自己那一份威力 × Config.signature_arts.power_scale、內容寫三個一般功效與一個本命戰法（tactics.py，回合裡的打法在 test_tactics）、
學到時直接第七成（舊角色讀檔補上，熔了不退那幾成）。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from test_content import copy_fixture, edit_json

from tianxia import companion_agent, library, skillview, team, traits
from tianxia.content import ContentError, load_content
from tianxia.engine import Game
from tianxia.state import PLAYER


def _game(content=None):
    content = content or real_content()
    return content, Game.new(content, "測試俠客", rng=random.Random(0))


def _wear(game, wugong, neigong, level=10):
    m = game.state.player.member
    m.wugong_id, m.wugong_level, m.neigong_id, m.neigong_level = wugong, level, neigong, level


def test_every_figure_art_has_its_own_tactic_and_three_traits():
    content = real_content()
    names = set()
    for ch in content.characters.values():
        for sid in (ch.starting_wugong, ch.starting_neigong):
            if not sid:
                continue
            skill = content.skills[sid]
            assert skill.tactic is not None, sid
            assert len(skill.traits) == 3 and skill.traits[0] == skill.attribute, sid
            names.add(skill.tactic.name)
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


def test_cards_show_the_tactic():
    """功法卡、修練頁（traits.card_line）與角色卡（本人與同伴）寫本命戰法：名字、時機、發動率、效果。"""
    content, game = _game()
    art = team.player_art(game.state, content, game.world, "liubei_neigong")
    line = traits.card_line(content, art)
    assert "本命〔仁義聚眾〕起手・每回合必定" in line and "回氣血 4%" in line
    _wear(game, "zhangfei_wugong", "zhangfei_neigong")
    card = skillview.member_card(game.state, content, game.world, PLAYER)
    assert "〔長坂一喝〕出招・每回合 40%" in card and "〔丈八狂瀾〕心法・第 1 回合一直在" in card

def test_a_tactic_on_an_ordinary_art_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)

    def put(skills):
        skills[0]["tactic"] = {"name": "亂寫", "timing": "出招", "kind": "roar", "desc": "隨便寫的。"}

    edit_json(root / "skills.json", put)
    with pytest.raises(ContentError, match="本命戰法只能寫在"):
        load_content(root)


def test_a_signature_art_melts_without_the_free_cheng():
    """學到時直接第七成（沒花心得）：熔了不退那幾成的練成心得（以前一學到就熔白拿 33 點），之後自己練上去的照八成退。"""
    content, game = _game()
    p = game.state.player
    p.arts.append("liubei_wugong")
    start = content.config.signature_arts.start_level
    p.art_levels["liubei_wugong"] = start
    assert library.melt_value(game.state, content, game.world, "liubei_wugong") == 0
    p.art_levels["liubei_wugong"] = start + 2
    spent = sum(team.practice_price(content, n) for n in range(start, start + 2))
    assert library.melt_value(game.state, content, game.world, "liubei_wugong") == int(spent * content.config.melt_refund_ratio)


def test_a_signature_art_cannot_be_melted():
    """Joy 2026-10-16「本命應該要不能熔掉」：單門、批量都擋，修練頁那一列灰掉寫原因，機器人熔最弱的那門也不挑它。"""
    from tianxia import bot

    content, game = _game()
    p = game.state.player
    p.arts.append("liubei_wugong")
    p.art_levels["liubei_wugong"] = content.config.signature_arts.start_level
    xinde = p.stats.get("xinde", 0)
    assert library.melt_art(game.state, content, game.world, "liubei_wugong") == [library.SIGNATURE_KEPT]
    assert library.melt_many(game.state, content, game.world, ["liubei_wugong"], [])[0] == library.MELT_MANY_NOTHING
    assert "liubei_wugong" in p.arts and p.stats.get("xinde", 0) == xinde
    row = next(r for r in skillview.art_rows(game.state, content, game.world) if r["id"] == "liubei_wugong")
    assert row["melt"]["ok"] is False and row["melt"]["note"] == library.SIGNATURE_KEPT
    others = [a for a in p.arts if a != "liubei_wugong"]
    for a in others:  # 庫裡只剩本命時，機器人什麼都不熔
        p.arts.remove(a)
    bot.melt_the_weakest(game)
    assert "liubei_wugong" in p.arts
