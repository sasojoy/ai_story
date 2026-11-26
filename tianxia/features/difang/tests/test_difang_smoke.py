"""地方大事的煙霧測試（開發規範手冊 4.1 第三級）：登記了、關著不出聲；打開之後探索一趟就算第一幕的一份力。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_difang_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "difang")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("difang:") for o in game.options())
    assert "difang" not in game.state.world.model_dump(exclude_defaults=True)


def test_an_outing_in_the_region_counts_for_act_one():
    from difang_kit import affair_here, open_here, season21_game

    game = season21_game()
    open_here(game)
    game.state.pending_event = None
    game.outing_go(1)
    a = affair_here(game)
    assert a is not None and a.affair == "yingshui_dike" and a.act == 1
    assert a.shares.get(game._mall_owner(), 0) >= 1
