"""假人看到求見選單的選項怎麼按（features/socialize/bots.py；全部拆包第 21 批從 bot_policy.score 的 call 那一段搬來）：
萬一停在求見選單上，假人只按「返回」；`call:<人物>`（名望不夠的求見也按得下去，只是被打發）一律不給分。"""
import pytest

from stances_kit import real_game
from tianxia import bot_policy
from tianxia.core import features as features_core
from tianxia.core.option import Option
from tianxia.features.socialize import bots
from tianxia.state import BotProfile

PRESSED = {"call:back": 0.0}
NOT_PRESSED = ["call:huangfusong", "call:zhujun", "call:nobody"]


def test_the_package_owns_the_call_prefix():
    for oid in ("call:back", "call:huangfusong"):
        assert features_core.owner_of(oid).name == "socialize"
    assert features_core.owner_of("act:call") is None  # act:call 是核心 act 的子動詞，不是這一包的前綴


@pytest.mark.parametrize("oid", [*PRESSED, *NOT_PRESSED])
def test_the_bots_only_press_back(oid):
    assert bots.score(Option(id=oid, label=oid)) == PRESSED.get(oid)


def test_the_policy_asks_the_package_for_a_call_option():
    g = real_game("week7", location="changshe")
    profile = BotProfile(personality="普通", seed=3, faction="guan", season_number=1)
    assert bot_policy.score(g, Option(id="call:back", label="返回"), profile) == 0.0
    assert all(bot_policy.score(g, Option(id=oid, label=oid), profile) is None for oid in NOT_PRESSED)


def test_a_bot_stuck_on_the_audience_list_would_only_press_back():
    g = real_game("week7", location="changshe")
    g.state.player.stats["fame"] = 999
    g.state.player.picking_audience = True
    profile = BotProfile(personality="普通", seed=3, faction="guan", season_number=1)
    scored = {o.id: bot_policy.score(g, o, profile) for o in g.options(odds=False)}
    assert "call:huangfusong" in scored and {oid for oid, value in scored.items() if value is not None} == {"call:back"}
