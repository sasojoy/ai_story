"""FB-108（QA 93e7037，2026-10-08）：體力 250/250 時主線的「下一步」還寫「體力將滿」。

現在分兩段（guide.next_hint）：九成到還沒滿寫「將滿」（guide.FULL_STAMINA_NOTE，照舊）；滿了（含補滿、丹吃過頭）寫「滿了」
（guide.STAMINA_FULL_NOTE，待 joy 潤）；九成以下兩句都不寫。上限照設定（Config.stamina_max）。"""
from __future__ import annotations

import pytest

from tianxia import guide


def _hint(game, fraction):
    game.skip_tutorial()
    game.state.player.stamina = game.content.config.stamina_max * fraction
    return guide.next_hint(game.state, game.content, game.world)


@pytest.mark.parametrize("fraction, nearly, full", [
    (0.5, False, False), (0.89, False, False), (0.9, True, False), (0.99, True, False), (1.0, False, True), (1.2, False, True),
])
def test_nearly_full_and_full_are_two_bands(game, fraction, nearly, full):
    hint = _hint(game, fraction)
    assert (guide.FULL_STAMINA_NOTE in hint, guide.STAMINA_FULL_NOTE in hint) == (nearly, full)


def test_the_full_line_says_it_is_full_not_nearly(game):
    assert guide.STAMINA_FULL_NOTE.startswith("體力滿了") and "將滿" not in guide.STAMINA_FULL_NOTE
    assert guide.FULL_STAMINA_NOTE.startswith("體力將滿")


def test_the_bands_follow_the_configured_maximum(game):
    game.content.config.stamina_max = 100
    game.skip_tutorial()
    game.state.player.stamina = 100
    assert guide.STAMINA_FULL_NOTE in guide.next_hint(game.state, game.content, game.world)
    game.state.player.stamina = 95
    assert guide.FULL_STAMINA_NOTE in guide.next_hint(game.state, game.content, game.world)
