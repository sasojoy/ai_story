"""移動的煙霧測試（開發規範手冊 4.1 第三級：一包一條）：包登記了、move／road 兩個前綴由這一包接走、喊停是它的 act 子動詞、
選單上「前往」照舊在。整段的規則在 tests/core/test_engine.py 等混合檔（見 README）。"""
import pytest

from tianxia.core import features as features_core
from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_travel_is_registered_and_takes_move_road_and_halt(game):
    feature = next(f for f in FEATURES if f.name == "travel")
    assert set(feature.prefix) == {"move", "road"} and feature.bot_always == ("road:",)
    assert set(feature.player_fields) == {"leg_actions", "recent_sights", "road_rewards_today"}
    assert [v.verb for v in feature.verbs()] == ["halt"]
    game.skip_tutorial()
    ids = [o.id for o in game.options() if o.id.startswith("move:") and o.enabled]
    assert ids and features_core.choose(game, "move", ids[0][5:]).title.startswith("前往 ")
    assert features_core.choose(game, "act", "rest") is None and features_core.choose(game, "road", "think") is not None
