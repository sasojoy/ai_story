"""假人看到人物對話的選項怎麼按（features/companions/bots.py；全部拆包第 20 批從 bot_policy.score 的 talk 那一段搬來）：
萬一停在對話裡，假人只按「告辭」，其餘一律不按；talk:、parley: 兩個前綴都是這一包的。"""
import pytest

from stances_kit import real_game
from tianxia import bot_policy
from tianxia.core import features as features_core
from tianxia.core.option import Option
from tianxia.features.companions import bots
from tianxia.state import BotProfile

PRESSED = {"talk:leave": 0.0}
NOT_PRESSED = ["talk:0", "talk:1", "talk:say", "talk:plan", "talk:terms:yes", "talk:terms:no", "talk:repay", "talk:owed", "talk:clue:chain:0",
               "talk:opp:x", "parley:road"]


def test_the_package_owns_both_prefixes():
    for oid in ("talk:0", "talk:leave", "parley:road"):
        assert features_core.owner_of(oid).name == "companions"


@pytest.mark.parametrize("oid", [*PRESSED, *NOT_PRESSED])
def test_the_bots_only_press_leave(oid):
    assert bots.score(Option(id=oid, label=oid)) == PRESSED.get(oid)


def test_the_policy_asks_the_package_for_a_talk_option():
    g = real_game("week7")
    profile = BotProfile(personality="普通", seed=3, faction="guan", season_number=1)
    assert bot_policy.score(g, Option(id="talk:leave", label="告辭"), profile) == 0.0
    assert all(bot_policy.score(g, Option(id=oid, label=oid), profile) is None for oid in NOT_PRESSED)


def test_a_bot_stuck_in_a_talk_would_only_press_leave():
    g = real_game("week7")
    g.state.player.pending_companion = "luzhi"
    g.state.player.last_offered_dialogue["luzhi"] = [["勸他速攻", "告辭"], ["真誠請教", "尋常寒暄"]]
    profile = BotProfile(personality="普通", seed=3, faction="guan", season_number=1)
    scored = {o.id: bot_policy.score(g, o, profile) for o in g.options(odds=False)}
    assert "talk:0" in scored and {oid for oid, value in scored.items() if value is not None} == {"talk:leave"}
