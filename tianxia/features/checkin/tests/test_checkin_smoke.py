"""簽到的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）。標記 @pytest.mark.smoke 留著（每一包至少一條，test_test_for 守）。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_checkin_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "checkin")
    assert feature.enabled(game) is False  # 測試內容的簽到關著
    assert game.checkin_view() is None
