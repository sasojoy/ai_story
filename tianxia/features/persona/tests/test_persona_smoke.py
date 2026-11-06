"""人物性子的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：關著不出聲；開著時跟盧植說一句勸他圓融的話、
隔天結算、記在共用的季上。"""
import pytest
from stances_kit import DAY, LUZHI, at, real_game

from tianxia.core.registry import FEATURES
from tianxia.features.persona import rules as persona


@pytest.mark.smoke
def test_persona_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "persona")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("persona:") for o in game.options())


@pytest.mark.smoke
def test_a_word_to_luzhi_moves_him_the_next_day():
    g = real_game(setup=lambda c: setattr(c.config.persona_shift, "enabled", True))
    s, c = g.state, g.content
    assert next(f for f in FEATURES if f.name == "persona").enabled(g)
    axis = c.personas[LUZHI][0]
    before = persona.value(s.world, LUZHI, axis)
    for _ in range(2):
        s.player.persona_notes.pop(LUZHI, None)
        persona.record(s, c, LUZHI, axis.ends[1], 90)
    g._save_season()
    at(g, g.now + DAY)
    assert persona.value(g.world.get_season(), LUZHI, axis) == before + 8
