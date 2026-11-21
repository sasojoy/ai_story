"""異聞的煙霧測試（開發規範手冊 4.1 第三級）：登記了、關著不出聲；新欄位 None 起家不寫鍵、舊存檔照讀。"""
import json

import pytest

from tianxia.core import features as features_core
from tianxia.core.registry import FEATURES
from tianxia.state import PlayerState, WorldState


def _feature():
    return next(f for f in FEATURES if f.name == "yiwen")


@pytest.mark.smoke
def test_registered_and_off_gives_nothing(game):
    feature = _feature()
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("yiwen:") for o in game.options())
    assert feature.menu(game) is None
    assert feature.status(game) == {}
    assert "yiwen" not in features_core.status(game)
    run = features_core.bus_hooks("outing")["yiwen"]
    loc = game.state.player.location
    for _ in range(50):
        assert run(game, loc) == []
    assert game.state.player.yiwen is None


def test_step_op_off_does_nothing(game):
    from tianxia.features.yiwen import actions

    before = game.state.model_dump_json()
    assert actions.step(game, {"tale": 1, "opening": "fog_figure", "node": 0, "pick": 0}) == []
    assert game.state.model_dump_json() == before


def test_off_season_writes_no_yiwen_keys_and_old_saves_load(game):
    """關著：全服存檔、角色存檔都沒有 yiwen、yiwen_on 鍵；沒有這幾個鍵的舊存檔照讀（None 起家）。開著、沒人撞見的那一半在 test_yiwen_walk。"""
    player = json.loads(game.state.player.model_dump_json())
    world = json.loads(game.state.world.model_dump_json())
    assert "yiwen" not in player
    assert "yiwen" not in world and "yiwen_on" not in world
    old = PlayerState.model_validate(player)
    assert old.yiwen is None
    assert WorldState.model_validate(world).yiwen is None
