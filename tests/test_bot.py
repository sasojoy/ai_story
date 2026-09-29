import random

from tianxia.bot import arrange_team, pick, spend_xinde
from tianxia.state import Member


def test_bot_spends_xinde_on_the_cheapest_upgrade_first(game):
    p = game.state.player
    p.stats["xinde"] = 100
    spend_xinde(game)
    # 三門都在第一成（各 20）→ 依序各升一成；剩 40 剛好把排在最前面的長拳再升到第三成
    assert p.skills == {"fist": 3, "family": 2}
    assert p.members["mate"].innate_level == 2
    assert p.stats["xinde"] == 0


def test_bot_keeps_xinde_it_cannot_spend(game):
    p = game.state.player
    p.stats["xinde"] = 19
    spend_xinde(game)
    assert p.skills == {"fist": 1, "family": 1}
    assert p.stats["xinde"] == 19


def test_bot_skips_arts_at_tenth_level(game):
    p = game.state.player
    p.skills.update({"fist": 10, "family": 10})
    p.stats["xinde"] = 1200
    spend_xinde(game)  # 只剩同伴本命能升：第 1→10 成共 900；之後全滿，剩下的心得留著
    assert p.members["mate"].innate_level == 10
    assert p.skills == {"fist": 10, "family": 10}
    assert p.stats["xinde"] == 300


def test_bot_takes_in_disciples_and_accepts_whoever_wants_to_join(game):
    rng = random.Random(0)
    assert pick(game, game.options(), rng) == "act:apprentice"
    game.state.pending_event = "meet"
    assert pick(game, game.options(), rng) == "choice:0"  # 「請他入門」


def test_bot_puts_the_strongest_pair_under_the_cap_in_the_main_team(game):
    for key in ("pupil", "sage", "hero"):
        game.state.player.members[key] = Member()
        game.state.player.loadouts[key] = [None, None]
    arrange_team(game)  # 你 5，另外兩人最多 10：隱士 7＋韓鐵 3 最強（26＋21）
    assert game.team_keys() == ["player", "sage", "mate"]
    entries = len(game.state.journal)
    arrange_team(game)  # 已經是最好的組合：不再動
    assert len(game.state.journal) == entries
