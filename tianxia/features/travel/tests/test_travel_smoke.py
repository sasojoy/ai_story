"""移動的煙霧測試（開發規範手冊 4.1 第三級：一包一條）：包登記了、move／road 兩個前綴由這一包接走、喊停是它的 act 子動詞、
選單上「前往」照舊在。整段的規則在 tests/core/test_engine.py 等混合檔（見 README）。"""
import pytest

from tianxia.core import features as features_core
from tianxia.core.registry import FEATURES


def test_the_content_fixture_loads_the_core_and_this_pack_only(content):
    """全部拆包第 63 批（手冊 4.1 第二級）：路上見聞是這一包的，門派是別包的；釘住 tianxia/features/conftest.py 的覆寫真的接上。"""
    assert content.road_sights and not content.sects


@pytest.mark.whole_content
def test_whole_content_gets_every_pack_test_content(content):
    assert content.road_sights and content.sects


@pytest.mark.smoke
def test_travel_is_registered_and_takes_move_road_and_halt(game):
    feature = next(f for f in FEATURES if f.name == "travel")
    assert set(feature.prefix) == {"move", "road"} and feature.bot_always == ("road:",)
    assert set(feature.player_fields) == {"leg_actions", "recent_sights", "road_rewards_today", "tagalong"}
    assert [v.verb for v in feature.verbs()] == ["halt", "part"]
    game.skip_tutorial()
    ids = [o.id for o in game.options() if o.id.startswith("move:") and o.enabled]
    assert ids and features_core.choose(game, "move", ids[0][5:]).title.startswith("前往 ")
    assert features_core.choose(game, "act", "rest") is None and features_core.choose(game, "road", "think") is not None
