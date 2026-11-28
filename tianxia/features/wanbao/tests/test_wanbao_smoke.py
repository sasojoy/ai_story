"""萬寶閣重排的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：開關打開，/api/main 帶 main.wanbao，
關著不出聲；這一包沒有選項。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_wanbao_reports_on_only_when_switched_on(game):
    feature = next(f for f in FEATURES if f.name == "wanbao")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("wanbao:") for o in game.options())
    game.content.config.wanbao.enabled = True
    assert feature.enabled(game) is True
    assert not any(o.id.startswith("wanbao:") for o in game.options())
