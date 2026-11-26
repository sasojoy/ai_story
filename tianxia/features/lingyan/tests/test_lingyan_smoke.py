"""凌煙閣的煙霧測試（開發規範手冊 4.1 第三級：一包一條）：開著時江湖畫面多一格 lingyan、沒有選項；關著一個鍵都不多。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_lingyan_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "lingyan")
    assert feature.enabled(game) is False
    assert feature.status(game) == {}
    assert not any(o.id.startswith("lingyan:") for o in game.options())
    game.content.config.lingyan.enabled = True
    assert feature.status(game) == {"lingyan": True}
    assert not any(o.id.startswith("lingyan:") for o in game.options())
