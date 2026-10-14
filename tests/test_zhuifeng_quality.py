"""追風步的品質（PM 2026-10-14，企劃者「城內可以直接免費學到絕學追風步？」）：content/skills.json 的 zhuifeng 沒寫 quality，
照 SkillDef 的預設成了絕學——潁川「汝南商行」付四十兩、山林「瀑布怪客」過一個悟性檢定就拿得到。改成下品；
混元一氣（玉璽碎片的獎勵）照舊是絕學。玩家拿得到的內容武學品質都要明寫（content.validate 擋）。
已經學到的也退回下品（企劃者跟玩家談過、玩家同意）：內容武學的品質照內容讀，舊角色讀檔就是下品；
中間一版（7f993d2）把絕學寫進了自己那一份，讀檔時拿掉（Game._drop_old_zhuifeng）。追風步修練不了，碰不到絕學定名與江湖史。"""
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


def _learned(content):
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    apply_effect(Effect(learn_skills=["zhuifeng"]), game.state, content, game.world)
    return game


def test_an_old_character_holding_zhuifeng_reads_it_as_low_grade():
    content = real_content()
    game = _learned(content)
    assert "zhuifeng" not in game.state.player.art_quality  # 改之前的存檔就是這個樣子：沒有自己那一份的紀錄
    loaded = Game(content, game.state, random.Random(0), game.world)
    assert team.player_art(loaded.state, content, loaded.world, "zhuifeng").quality == "下品"


def test_the_peerless_record_written_by_the_keep_version_is_dropped_on_load():
    content = real_content()
    game = _learned(content)
    p = game.state.player
    p.art_quality["zhuifeng"] = p.art_rolled["zhuifeng"] = "絕學"  # 7f993d2 那一版讀檔時寫的
    loaded = Game(content, game.state, random.Random(0), game.world)
    assert "zhuifeng" not in loaded.state.player.art_quality and "zhuifeng" not in loaded.state.player.art_rolled
    assert team.player_art(loaded.state, content, loaded.world, "zhuifeng").quality == "下品"


def test_other_peerless_records_are_left_alone():
    content = real_content()
    game = _learned(content)
    apply_effect(Effect(learn_skills=["hunyuan"]), game.state, content, game.world)
    game.state.player.art_quality["hunyuan"] = "絕學"
    loaded = Game(content, game.state, random.Random(0), game.world)
    assert loaded.state.player.art_quality["hunyuan"] == "絕學"
