"""追風步的品質（PM 2026-10-14，企劃者「城內可以直接免費學到絕學追風步？」）：content/skills.json 的 zhuifeng 沒寫 quality，
照 SkillDef 的預設成了絕學——潁川「汝南商行」付四十兩、山林「瀑布怪客」過一個悟性檢定就拿得到。改成下品；
混元一氣（玉璽碎片的獎勵）照舊是絕學。玩家拿得到的內容武學品質都要明寫（content.validate 擋）。
舊角色手上的追風步不另外搬：內容武學的品質每次照內容讀（team.resolve_art），沒修練過（追風步沒融意境、修不了）
就沒有 art_quality 那一筆，讀檔就是下品；絕學定名、江湖史只記修練上去的絕學，碰不到它。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from test_content import copy_fixture, edit_json

from tianxia import library, team
from tianxia.content import ContentError, load_content
from tianxia.engine import Game
from tianxia.models import Effect
from tianxia.rules import apply_effect


def test_zhuifeng_is_low_grade_and_hunyuan_stays_peerless():
    content = real_content()
    assert content.skills["zhuifeng"].quality == "下品"
    assert content.skills["hunyuan"].quality == "絕學"


def test_every_content_art_a_player_can_get_names_its_quality():
    content = real_content()
    given = {sid for e in content.events.values() for c in e.choices for eff in (c.effect, c.fail_effect) if eff for sid in eff.learn_skills}
    taught = {s.id for s in content.skills.values() if s.learn is not None} | set(content.config.starter_skills)
    assert "zhuifeng" in given and "hunyuan" in given
    for sid in given | taught:
        assert "quality" in content.skills[sid].model_fields_set, sid


def test_an_event_teaching_an_art_without_a_quality_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)  # 測試內容的 step（追風步）沒寫 quality
    edit_json(root / "events" / "test.json", lambda d: d[0]["choices"][0].setdefault("effect", {}).update(learn_skills=["step"]))
    with pytest.raises(ContentError, match="沒寫 quality"):
        load_content(root)


def test_an_old_character_holding_zhuifeng_reads_it_as_low_grade():
    content = real_content()
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    apply_effect(Effect(learn_skills=["zhuifeng"]), game.state, content, game.world)
    p = game.state.player
    assert "zhuifeng" in library.owned_arts(game.state) and "zhuifeng" not in p.art_quality  # 舊存檔就是這個樣子
    assert team.player_art(game.state, content, game.world, "zhuifeng").quality == "下品"
    p.art_quality["zhuifeng"] = "中品"  # 萬一有自己修練上去的紀錄：照紀錄算，不往下拉
    assert team.player_art(game.state, content, game.world, "zhuifeng").quality == "中品"
