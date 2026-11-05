"""假人看移動的選項（移動包的 bots.py，全部拆包第 47 批）：move: 的分數跟 bot_policy.score 給的一樣（照傳進來的 profile，不是照存檔裡那一份）、
road: 一律不按。"""
from __future__ import annotations

from tianxia import bot_policy
from tianxia.core import features as features_core
from tianxia.core.option import Option
from tianxia.features.travel import bots
from tianxia.state import BotProfile


_PROFILE = BotProfile(personality="普通", seed=1)


def _moves(game) -> list[Option]:
    return [o for o in game.options() if o.id.startswith("move:") and o.enabled]


def test_move_scores_through_the_package_and_follows_the_given_profile(game):
    game.skip_tutorial()
    profile = _PROFILE
    options = _moves(game)
    assert options
    for option in options:
        assert bot_policy.score(game, option, profile) == bots.score(game, option, profile) is not None


def test_road_options_are_never_pressed_by_bots(game):
    for option_id in ("road:back", "road:think", "road:ask", "road:gather"):
        option = Option(id=option_id, label="")
        assert bots.score(game, option, _PROFILE) is None
        assert bot_policy.score(game, option, _PROFILE) is None
        assert features_core.bot_pick(game, option) == (True, None)
