"""江湖錄的煙霧測試：驗登記與關著不出聲；@pytest.mark.smoke 留著（每一包至少一條，test_test_for 守）。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_codex_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "codex")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("codex:") for o in game.options())
