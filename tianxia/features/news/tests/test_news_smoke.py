"""見聞的煙霧測試（開發規範手冊 4.1 第三級：一包一條）：登記了、只有畫面、沒有選項。畫法的測試在 tests/web/test_news_web.py。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_news_is_registered_and_only_draws(game):
    feature = next(f for f in FEATURES if f.name == "news")
    assert feature.enabled(game) is True and feature.web == ("news.js", "news.css")
    assert not any(o.id.startswith("news:") for o in game.options())
