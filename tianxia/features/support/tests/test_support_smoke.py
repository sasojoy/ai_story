"""客服的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）。骨架生的這一條只驗登記與關著不出聲；
功能做出來之後換成真的那一條（真實內容 real_content("week7")）；標記 @pytest.mark.smoke 留著（每一包至少一條，test_test_for 守）。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_support_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "support")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("support:") for o in game.options())
