"""門派論劍的煙霧測試（開發規範手冊 4.1 第三級）：登記了、關著不出聲；打開之後拜了門的人報得了名、到點開打。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_lunjian_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "lunjian")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("lunjian:") for o in game.options())
    assert "lunjian" not in game.state.world.model_dump(exclude_defaults=True)


def test_sign_through_choose_then_the_week_is_fought():
    from lunjian_kit import season21_game, to

    from tianxia.features.lunjian import actions

    game = season21_game()
    game.choose("lunjian:sign")
    w = actions.week_of(game, actions._week(game))
    assert game._mall_owner() in w.entries
    to(game, actions.fight_at(game, w.week) + 1)
    actions.on_sync(game)
    assert w.fought and len(w.matches) == 1 and w.matches[0].b == ""
