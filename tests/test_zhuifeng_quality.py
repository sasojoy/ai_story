"""追風步的品質（PM 2026-10-14，企劃者「城內可以直接免費學到絕學追風步？」）：content/skills.json 的 zhuifeng 沒寫 quality，
照 SkillDef 的預設成了絕學——潁川「汝南商行」付四十兩、山林「瀑布怪客」過一個悟性檢定就拿得到。改成下品；
混元一氣（玉璽碎片的獎勵）照舊是絕學。玩家拿得到的內容武學品質都要明寫（content.validate 擋）。
已經學到的不退回（企劃者 2026-10-14「追風步這算是我們的bug，已經學到的不可以退回，新學的的才是下品」）：
讀檔核對一次（Game._keep_old_zhuifeng），把絕學記進自己那一份（art_quality、art_rolled）；新角色、換季之後學的照內容是下品。"""
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


def _old_save_with_zhuifeng():
    """改之前的存檔：追風步在功法庫、自己那一份沒有品質的紀錄、還沒核對過。"""
    content = real_content()
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    apply_effect(Effect(learn_skills=["zhuifeng"]), game.state, content, game.world)
    game.state.player.art_quality.pop("zhuifeng", None)
    game.state.player.zhuifeng_kept = False
    return content, game


def test_an_old_character_keeps_the_peerless_zhuifeng_on_load():
    content, game = _old_save_with_zhuifeng()
    loaded = Game(content, game.state, random.Random(0), game.world)
    p = loaded.state.player
    assert team.player_art(loaded.state, content, loaded.world, "zhuifeng").quality == "絕學"
    assert p.art_rolled["zhuifeng"] == "絕學" and p.zhuifeng_kept  # 熔的時候跟以前一樣：絕學是登記時就有的，不算修練加給
    again = Game(content, loaded.state, random.Random(0), loaded.world)  # 核對過就不再動
    assert team.player_art(again.state, content, again.world, "zhuifeng").quality == "絕學"


def test_a_new_character_learns_the_low_grade_zhuifeng():
    content = real_content()
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    assert game.state.player.zhuifeng_kept  # 新角色建立時就核對過了：之後學到的不會被當成舊的
    apply_effect(Effect(learn_skills=["zhuifeng"]), game.state, content, game.world)
    reloaded = Game(content, game.state, random.Random(0), game.world)
    assert team.player_art(reloaded.state, content, reloaded.world, "zhuifeng").quality == "下品"
    assert "zhuifeng" not in reloaded.state.player.art_quality


def test_melting_the_kept_one_and_learning_again_gives_the_low_grade():
    content, game = _old_save_with_zhuifeng()
    loaded = Game(content, game.state, random.Random(0), game.world)
    library.remove_art(loaded.state, "zhuifeng")  # 熔煉與交出懸賞共用的拿掉
    apply_effect(Effect(learn_skills=["zhuifeng"]), loaded.state, content, loaded.world)
    assert team.player_art(loaded.state, content, loaded.world, "zhuifeng").quality == "下品"


def test_a_new_season_counts_as_checked(content):
    """換季武學歸零：核對的記號一起記成核對過，新的一季學到的追風步不會被當成改之前學的。"""
    from conftest import next_season
    from tianxia.sqlite_world import open_world

    content.config.auto_open_first_season = True
    world = open_world()
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.sync(100.0)
    game.state.player.zhuifeng_kept = False
    next_season(content, world, game)
    assert game.state.player.zhuifeng_kept
