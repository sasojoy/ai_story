"""一條線的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）。標記 @pytest.mark.smoke 留著（每一包至少一條，test_test_for 守）。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_story_is_registered_and_quiet_while_no_line_is_open(game):
    feature = next(f for f in FEATURES if f.name == "story")
    assert feature.enabled(game) is True  # 一直開著：線自己看 Config.jianfa.storylines
    assert not any(o.id.startswith("story:") for o in game.options())
    assert game.story_card_view() == []
