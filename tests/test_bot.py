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


def test_bot_accepts_whoever_wants_to_join(game):
    game.state.pending_event = "meet"
    assert pick(game, game.options(), random.Random(0)) == "choice:0"  # 「請他入門」


def never_picks_apprentice(game) -> bool:
    return all(pick(game, game.options(), random.Random(seed)) != "act:apprentice" for seed in range(50))


def test_bot_takes_in_disciples_only_with_room_and_silver_to_spare(game):
    """收徒只在名冊（含你）還塞不滿已開放的隊伍（每隊 3 人）、而且付完還付得起下一次（銀兩 ≥ 2 × 40）時才收，
    這時一定收；其他時候也不會隨機選到它（整季模擬才不會為了收徒把銀兩花光、改變主線的走向）。"""
    p = game.state.player
    assert "act:apprentice" in [o.id for o in game.options() if o.enabled]
    assert p.stats["silver"] == 50 and never_picks_apprentice(game)  # 付得起一次，付完就不夠下一次
    p.stats["silver"] = 80
    assert pick(game, game.options(), random.Random(0)) == "act:apprentice"
    for key in ("friend", "hero", "captain", "sage"):  # 名冊 6 人：開放的 2 隊剛好塞滿
        p.members[key] = Member()
        p.loadouts[key] = [None, None]
    assert "act:apprentice" in [o.id for o in game.options() if o.enabled]  # 書生、小六還收得到
    assert never_picks_apprentice(game)
    game.state.world.act_reached = 1  # 第二幕：開放 3 隊，塞得下 9 人
    assert pick(game, game.options(), random.Random(0)) == "act:apprentice"


def test_bot_has_nothing_to_pick_when_only_an_unwanted_apprenticeship_is_left(game):
    options = [o for o in game.options() if o.id == "act:apprentice"]
    assert pick(game, options, random.Random(0)) is None  # 銀兩 50：不收，也沒有別的可選（整季模擬就讓時間過去）


def test_bot_puts_the_strongest_pair_under_the_cap_in_the_main_team(game):
    for key in ("pupil", "sage", "hero"):
        game.state.player.members[key] = Member()
        game.state.player.loadouts[key] = [None, None]
    arrange_team(game)  # 你 5，另外兩人最多 10：隱士 7＋韓鐵 3 最強（26＋21）
    assert game.team_keys() == ["player", "sage", "mate"]
    entries = len(game.state.journal)
    arrange_team(game)  # 已經是最好的組合：不再動
    assert len(game.state.journal) == entries
