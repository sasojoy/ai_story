"""部下真的有用（PM 2026-10-12 派工）：戰報寫部下助陣多了幾成、部下的武學跟著本人的等級長、
角色卡寫部下的威力、全服決戰裡每名部下讓強攻與奇襲多份量（加入時快照）；頭目戰只算本人。"""

import random
from pathlib import Path

import pytest

from conftest import at
from tianxia import battle_instance, battlelog, encounter, skillview, team
from tianxia.content import load_content
from tianxia.engine import TROOPS_LINE, TROOPS_REPORT, Game
from tianxia.models import BattleTuning, FollowerDef

CONTENT_DIR = Path(__file__).parents[2] / "content"


def _real_game(level=1, followers=("follower_guan_spear", "follower_guan_crossbow")):
    real = load_content(CONTENT_DIR)
    real.config.auto_open_first_season = True
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    game = Game.new(real, "甲", rng=random.Random(0))
    game.state.player.followers = list(followers)
    game.state.player.member.level = level
    return real, game


# ── 成長 ──

def test_follower_art_grows_with_the_players_level_but_never_below_the_template():
    real, game = _real_game()
    spear = real.followers["follower_guan_spear"]
    per = real.config.follower.levels_per_cheng
    for level, want in ((1, spear.wugong_level), (per * 3, 3), (per * 4, 4), (per * 7 + 2, 7), (30, 10)):
        game.state.player.member.level = level
        assert team.follower_level(game.state, real, spear) == want
    assert [u.wugong_level for u in team.follower_units(game.state, real)] == [10, 10]


def test_a_grown_follower_hits_harder():
    real, game = _real_game(level=1)
    spear = real.followers["follower_guan_spear"]
    early = team.follower_power(game.state, real, game.world, spear)
    game.state.player.member.level = 21
    assert team.follower_power(game.state, real, game.world, spear) > early > 0


def test_the_follower_card_shows_his_power_and_grown_art():
    real, game = _real_game(level=15)
    spear = real.followers["follower_guan_spear"]
    card = skillview.member_card(game.state, real, game.world, team.FOLLOWER_KEY + "0")
    assert f"威力　{round(team.follower_power(game.state, real, game.world, spear))}" in card.splitlines()
    assert "5成" in card or "五成" in card


# ── 戰報那一句 ──

def test_names_of_the_same_template_are_counted():
    real = load_content(CONTENT_DIR)
    spear, bow = real.followers["follower_guan_spear"], real.followers["follower_guan_crossbow"]
    assert team.troop_names([spear]) == "持矛鄉勇"
    assert team.troop_names([spear, bow, spear]) == "兩名持矛鄉勇、弩手鄉勇"


@pytest.mark.parametrize("ratio, words", [
    (None, "全靠他們撐著"), (0.02, "多了一點"), (0.2, "多了兩成"), (0.94, "多了九成"), (1.0, "翻了一倍"), (2.4, "翻了兩倍"),
])
def test_how_much_more_is_said_in_words(ratio, words):
    assert team._more(ratio) == words


def test_aid_line_matches_the_followers_share_of_the_fight():
    real, game = _real_game(level=12)
    s = game.state
    squad = real.squads[next(iter(real.squads))]
    arts = team.team_arts(s, real, game.world)
    members, conditions, boosts = team._styled_fighters(s, real, game.world, arts, squad)
    powers = [encounter.member_power(m, arts, squad.attribute, c, b) for m, c, b in zip(members, conditions, boosts, strict=True)]
    ratio = sum(powers[-2:]) / sum(powers[:-2])
    line = team.aid_line(s, real, game.world, squad)
    assert line == f"持矛鄉勇、弩手鄉勇助陣，威力{team._more(ratio)}。"
    s.player.followers = []
    assert team.aid_line(s, real, game.world, squad) == ""


def test_train_records_carry_the_aid_line_but_spars_do_not():
    real, game = _real_game(level=12)
    squad = real.squads[next(iter(real.squads))]
    result = encounter.EncounterResult(tier="大勝", margin=50.0, our_power=100.0, difficulty=50.0)
    line = team.aid_line(game.state, real, game.world, squad)
    for kind in battlelog.AID_KINDS:
        assert line in battlelog.new_record(game.state, real, game.world, squad, result, kind).notes
    for kind in ("spar", "raid", "duel"):
        assert line not in battlelog.new_record(game.state, real, game.world, squad, result, kind).notes


def test_no_followers_when_season_one_is_off():
    real, game = _real_game()
    real.config.season_one = False
    squad = real.squads[next(iter(real.squads))]
    assert team.aid_line(game.state, real, game.world, squad) == ""
    assert game._battle_troops() == ("", 0.0)


# ── 全服決戰 ──

def test_troops_multiply_charge_and_raid_and_stack_with_cavalry_and_role():
    t = BattleTuning()
    plain = battle_instance.move_scores(t, 100.0, None, None)
    assert battle_instance.move_scores(t, 100.0, None, None, troops=0.0) == plain
    base = battle_instance.strength(t, 100.0) * t.affinity_base / 100
    both = battle_instance.move_scores(t, 100.0, None, None, role="str", cavalry=0.1, troops=0.1)
    assert both["強攻"] == round(base * (1 + t.role_move_bonus) * 1.1 * 1.1, 1)
    assert both["奇襲"] == round(base * 1.1 * 1.1, 1) and both["固守"] == plain["固守"]


def test_battle_troops_count_each_follower():
    real, game = _real_game()
    per = real.config.follower.battle_per
    assert game._battle_troops() == ("持矛鄉勇、弩手鄉勇", pytest.approx(2 * per))
    mounted, duel = game._battle_scores(), game._battle_scores(mounted=False)  # 頭目戰只算本人
    assert mounted["強攻"] > duel["強攻"] and mounted["奇襲"] > duel["奇襲"] and mounted["固守"] == duel["固守"]


def test_joining_a_showdown_snapshots_the_troops_and_shows_them(content, game, monkeypatch):
    from test_engine import _fighter, _three_round_showdown
    definition = _three_round_showdown(content)
    p = game.state.player
    p.faction = "guan"
    spear = FollowerDef(id="f1", faction="guan", name="持矛鄉勇", wugong="x", wugong_level=3)
    mine = {p.name}
    monkeypatch.setattr(team, "follower_rows", lambda state, c: [("follower:0", spear), ("follower:1", spear)]
                        if state.player.name in mine else [])
    foe = _fighter(content, game, "乙", "huang")
    game.world.start_battle(definition, now=0.0)
    line = TROOPS_LINE.format(names="兩名持矛鄉勇", pct="10%")
    with at(game, 0.0), at(foe, 0.0):
        game.choose("battle:join:guan")
        foe.choose("battle:join:huang")
        assert line + "。" in game.scene_text()
    me = game.world.get_battle().participants[p.name]
    assert (me.troops, me.troop_bonus) == ("兩名持矛鄉勇", pytest.approx(0.10)) and me.scores == game._battle_scores()
    assert game.world.get_battle().participants["乙"].troops == ""
    mine.clear()  # 加入之後部下沒了：這一場照快照
    start = definition.muster_seconds + 1
    with at(game, start):
        assert line in game.scene_text()
    for i in range(3):
        with at(game, start + i), at(foe, start + i):
            game.choose("battle:act:guan_hold")
            foe.choose("battle:act:huang_hold")
    game.sync(start + 10)
    assert TROOPS_REPORT.format(names="兩名持矛鄉勇") in game.state.battles[0].notes
