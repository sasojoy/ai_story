"""體力玩法的煙霧測試（開發規範手冊 4.1 第三級：一包一條）：包登記了、前綴 ambush／works 由這一包接走、關著（測試內容沒有陣營）設伏屯糧都硬按
也只回「此刻無法這麼做」、選單上一顆都沒有；假人的分數一律 None。整段的規則在 test_stamina_plays.py（正式內容、打開開關）。"""
import pytest

from tianxia.core import features as features_core
from tianxia.core.option import Option
from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_stamina_plays_is_registered_and_quiet_without_a_faction(game):
    feature = next(f for f in FEATURES if f.name == "stamina_plays")
    assert set(feature.prefix) == {"ambush", "works"} and set(feature.bot_always) == {"ambush:", "works:"}
    assert not any(o.id.startswith(("ambush:", "works:")) for o in game.options())
    assert features_core.choose(game, "ambush", "lift") is not None and features_core.choose(game, "works", "stockpile") is not None
    assert features_core.choose(game, "act", "rest") is None
    assert features_core.bot_pick(game, Option(id="ambush:lift", label="收伏")) == (True, None)
    assert features_core.bot_pick(game, Option(id="works:stockpile", label="屯糧")) == (True, None)
    assert game.choose("works:stockpile")[0].startswith("（此刻無法這麼做")
