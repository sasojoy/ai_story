"""門下與隊伍：武學與成長 Task 3 加進來的部分——基礎武學照品質解析、每個人自己那一份的品質。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import team
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.martial_arts import generate_from_name

LOW_ONLY = {"下品": 100, "中品": 0, "上品": 0, "絕學": 0}
CONTENT_DIR = Path(__file__).parent.parent / "content"


def _claim_whirlwind(world):
    art = generate_from_name("旋風腿", "武學", "旋風腿", weights=LOW_ONLY)
    world.claim_skill_name(art)
    return art


def test_content_basic_art_resolves_as_low_grade(content, world):
    assert team.resolve_art("basic_fist", content, world).quality == "下品"


def test_a_peerless_content_art_still_resolves_as_peerless(content, world):
    art = team.resolve_art("fist", content, world)
    assert (art.quality, art.origin) == ("絕學", "historical")


def test_resolve_art_gives_the_shared_registered_copy(state, content, world):
    """resolve_art 回的是全服共享那一份，不看玩家自己的品質；玩家自己的品質另走 player_art。"""
    _claim_whirlwind(world)
    state.player.art_quality["旋風腿"] = "上品"
    assert team.resolve_art("旋風腿", content, world).quality == "下品"
    assert team.resolve_art(None, content, world) is None


def test_art_quality_defaults_to_the_registered_quality(state, content, world):
    art = _claim_whirlwind(world)
    assert team.art_quality(state, art) == "下品"
    state.player.art_quality["旋風腿"] = "中品"
    assert team.art_quality(state, art) == "中品"


def test_player_art_uses_the_players_own_quality(state, content, world):
    _claim_whirlwind(world)
    assert team.player_art(state, content, world, "旋風腿").quality == "下品"
    state.player.art_quality["旋風腿"] = "上品"
    assert team.player_art(state, content, world, "旋風腿").quality == "上品"
    assert world.get_skill("旋風腿").quality == "下品"  # 全服那一筆不動


def test_player_art_of_nothing_is_nothing(state, content, world):
    assert team.player_art(state, content, world, None) is None
    assert team.player_art(state, content, world, "ghost") is None


def test_player_art_works_for_a_content_art_too(state, content, world):
    state.player.art_quality["basic_fist"] = "中品"
    art = team.player_art(state, content, world, "basic_fist")
    assert (art.quality, art.base_power, art.top_power) == ("中品", 16, 44)
    assert team.resolve_art("basic_fist", content, world).quality == "下品"


def test_team_arts_hand_the_encounter_the_players_quality(state, content, world):
    _claim_whirlwind(world)
    state.player.member.wugong_id = "旋風腿"
    state.player.art_quality["旋風腿"] = "中品"
    assert team.team_arts(state, content, world)["旋風腿"].quality == "中品"


def test_team_arts_keep_the_companions_content_arts(state, content, world):
    """同伴的武學照舊從內容解析（沒有「自己的品質」這回事）。"""
    world.update_companion("mate", lambda p: setattr(p, "wugong_id", "fist"))
    state.player.team = ["mate"]
    state.player.member.wugong_id = "basic_fist"
    arts = team.team_arts(state, content, world)
    assert arts["fist"].quality == "絕學"
    assert arts["basic_fist"].quality == "下品"


def test_team_arts_keep_the_followers_arts():
    """審查裁示 F6：部下的武學要留在 team_arts 裡，不然部下的威力悄悄變成 0（encounter 查不到那門武學）。"""
    real = load_content(CONTENT_DIR)
    real.config.auto_open_first_season = True
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    game = Game.new(real, "甲", rng=random.Random(0))
    game.state.player.followers = ["follower_guan_spear", "follower_guan_crossbow"]
    wanted = {real.followers[f].wugong for f in game.state.player.followers}
    assert len(wanted) == 2
    arts = team.team_arts(game.state, real, game.world)
    assert wanted <= set(arts)
    assert all(arts[skill_id].quality == "上品" for skill_id in wanted)


def test_switch_art_message_shows_the_players_own_quality(state, content, world):
    """審查裁示 F11：改練的訊息寫玩家自己那一份的品質，不是全服登記的。"""
    _claim_whirlwind(world)
    state.player.arts = ["旋風腿"]
    state.player.art_quality["旋風腿"] = "上品"
    msgs = team.switch_art(state, content, world, "旋風腿")
    assert any("旋風腿" in m and "上品" in m for m in msgs)
    assert not any("下品" in m for m in msgs)


def test_old_saves_without_the_new_player_fields_still_load(state):
    from tianxia.state import PlayerState

    old = state.player.model_dump()
    for key in ("insights", "art_quality", "art_mastery", "naming"):
        old.pop(key)
    loaded = PlayerState.model_validate(old)
    assert (loaded.insights, loaded.art_quality, loaded.art_mastery, loaded.naming) == ([], {}, {}, None)
