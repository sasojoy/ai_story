"""傳功門下（企劃者 2026-10-14「心得大量溢出」，決策卡選「傳功門下」）：用心得替同伴、部下練武學、加屬性；
隊伍變強，本人的威力不動；價錢越後越貴；整季機器人與假人也會傳。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import bot, chuangong, encounter, skillview, team
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.state import PLAYER

CONTENT_DIR = Path(__file__).parents[2] / "content"


def _with_mate(game, xinde=10_000):
    def own(progress):
        progress.owner = game.state.player.name
        progress.wugong_id = "palm"

    game.world.update_companion("mate", own)
    game.state.player.team = ["mate"]
    game.state.player.stats["xinde"] = xinde
    return game


def _real_game(xinde=10_000, followers=("follower_guan_spear", "follower_guan_crossbow")):
    real = load_content(CONTENT_DIR)
    real.config.auto_open_first_season = True
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    game = Game.new(real, "甲", rng=random.Random(0))
    game.state.player.followers = list(followers)
    game.state.player.stats["xinde"] = xinde
    return real, game


def _lesson(game, key, what):
    return next(row for row in game.chuangong_lessons(key) if row["what"] == what)


# ── 同伴 ──

@pytest.mark.smoke
def test_teaching_a_companion_his_art_costs_more_each_cheng(game):
    _with_mate(game)
    per = game.content.config.chuangong.mate_art_xinde
    assert _lesson(game, "mate", "wugong")["label"].endswith(f"{per} 心得")
    game.chuangong("mate", "wugong")
    assert game.world.get_companion("mate").wugong_level == 2
    assert game.state.player.stats["xinde"] == 10_000 - per
    assert _lesson(game, "mate", "wugong")["label"].endswith(f"{per * 2} 心得")


def test_teaching_stats_gets_dearer_and_stops_at_the_cap(game):
    _with_mate(game, xinde=10 ** 7)
    rule = game.content.config.chuangong
    before = team.member_stats(game.state, game.content, game.world, "mate")["str"]
    game.chuangong("mate", "str")
    game.chuangong("mate", "con")
    assert game.state.player.stats["xinde"] == 10 ** 7 - rule.mate_stat_xinde * (1 + 2)  # k 算三項合計
    assert team.member_stats(game.state, game.content, game.world, "mate")["str"] == before + 1
    for _ in range(rule.mate_stat_max + 3):
        game.chuangong("mate", "str")
    assert game.world.get_companion("mate").taught["str"] == rule.mate_stat_max
    assert _lesson(game, "mate", "str")["problem"]


def test_no_wisdom_and_nothing_for_yourself_or_other_peoples_companions(game):
    _with_mate(game)
    assert {row["what"] for row in game.chuangong_lessons("mate")} == {"neigong", "wugong", "str", "agi", "con"}
    assert game.chuangong_lessons(PLAYER) == []
    game.world.update_companion("mate", lambda progress: setattr(progress, "owner", "別人"))
    assert game.chuangong_lessons("mate") == []
    xinde = game.state.player.stats["xinde"]
    assert game.chuangong("mate", "str") == [chuangong.NOT_YOURS]
    assert game.state.player.stats["xinde"] == xinde


def test_a_companion_without_an_inner_art_cannot_practise_it(game):
    _with_mate(game)
    row = _lesson(game, "mate", "neigong")
    assert row["problem"] == chuangong.NO_ART.format(kind="內功")


def test_short_of_xinde_is_refused_without_writing_anything(game):
    _with_mate(game, xinde=1)
    entries = len(game.state.journal)
    assert game.chuangong("mate", "wugong")[0].startswith("心得不足")
    assert game.world.get_companion("mate").wugong_level == 1
    assert len(game.state.journal) == entries


def test_the_team_gets_stronger_but_your_own_power_does_not_move(game):
    _with_mate(game, xinde=10 ** 6)
    s, c, w = game.state, game.content, game.world

    def powers():
        arts = team.team_arts(s, c, w)
        return (encounter.member_power(s.player.member, arts, None, 1.0, team.player_boost(s, c, w)),
                encounter.member_power(w.get_companion("mate"), arts, None, 1.0, team.mate_boost(s, c, w, "mate")))

    mine, mate = powers()
    for _ in range(5):
        game.chuangong("mate", "wugong")
        game.chuangong("mate", "str")
    mine_after, mate_after = powers()
    assert mine_after == mine
    assert mate_after > mate > 0


def test_what_was_taught_stays_with_the_companion_when_he_changes_hands(game):
    _with_mate(game)
    game.chuangong("mate", "con")
    game.world.release_companion("mate")
    game.world.update_companion("mate", lambda progress: setattr(progress, "owner", "乙"))
    assert game.world.get_companion("mate").taught == {"con": 1}


def test_the_companion_card_lists_what_was_taught(game):
    _with_mate(game)
    game.chuangong("mate", "str")
    card = skillview.member_card(game.state, game.content, game.world, "mate")
    assert "傳功　臂力 +1" in card.splitlines()


def test_switched_off_means_no_buttons_and_no_teaching(game):
    _with_mate(game)
    game.content.config.chuangong.enabled = False
    assert game.chuangong_lessons("mate") == []
    assert game.chuangong("mate", "str") == [chuangong.OFF]


# ── 部下 ──

def test_a_follower_can_be_drilled_past_the_level_line_up_to_ten():
    real, game = _real_game()
    spear, key = real.followers["follower_guan_spear"], team.FOLLOWER_KEY + "0"
    line = team.follower_line(game.state, real, spear)
    game.chuangong(key, "wugong")
    game.chuangong(key, "wugong")
    assert team.follower_level(game.state, real, spear, key) == line + 2
    assert team.follower_level(game.state, real, spear) == line  # 不給 key 當沒傳過
    assert game.state.player.stats["xinde"] == 10_000 - real.config.chuangong.follower_cheng_xinde * 3
    game.state.player.member.level = 30  # 線到十成：多練的再也長不上去
    assert team.follower_level(game.state, real, spear, key) == 10
    assert _lesson(game, key, "wugong")["problem"] == chuangong.LINE_FULL


def test_a_follower_gets_stronger_arms_until_the_cap():
    real, game = _real_game(xinde=10 ** 6)
    spear, key = real.followers["follower_guan_spear"], team.FOLLOWER_KEY + "0"
    early = team.follower_power(game.state, real, game.world, spear, key)
    for _ in range(20):
        game.chuangong(key, "str")
    assert team.follower_strength(real, spear, team.drill_of(game.state, key)) == real.config.stat_cap
    assert team.follower_power(game.state, real, game.world, spear, key) > early
    other = team.follower_power(game.state, real, game.world, real.followers["follower_guan_crossbow"], team.FOLLOWER_KEY + "1")
    assert other == team.follower_power(game.state, real, game.world, real.followers["follower_guan_crossbow"])  # 另一名沒傳
    assert "傳功　" in skillview.member_card(game.state, real, game.world, key)


def test_the_battle_weight_counts_followers_not_their_power():
    real, game = _real_game(xinde=10 ** 6)
    before = game._battle_troops()
    for _ in range(5):
        game.chuangong(team.FOLLOWER_KEY + "0", "str")
    assert game._battle_troops() == before


def test_defecting_drops_the_drill_with_the_followers():
    from tianxia import defection

    real, game = _real_game()
    game.chuangong(team.FOLLOWER_KEY + "0", "str")
    defection.clear_progress(game.state.player)
    assert game.state.player.follower_drill == []


# ── 機器人 ──

def test_bots_spend_spare_xinde_on_the_cheapest_lesson(game):
    _with_mate(game, xinde=200)
    done = bot.teach(game)
    assert done > 0
    assert game.state.player.stats["xinde"] >= bot.TEACH_RESERVE
    nxt = chuangong.cheapest(game.state, game.content, game.world)
    assert nxt is None or game.state.player.stats["xinde"] - nxt.price < bot.TEACH_RESERVE


def test_bots_without_anyone_to_teach_keep_their_xinde(game):
    game.state.player.stats["xinde"] = 500
    assert bot.teach(game) == 0
    assert game.state.player.stats["xinde"] == 500
