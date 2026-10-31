"""減法季批 3b QA 之後的修正 FB-857：約戰開著的季，玩法說明「投靠」那一條不再寫「自家的地方守一回、推一半」。

約戰沒有零風險的守（守就是應戰）：同一份說明的出陣段（howto.duel_lines）、地盤段早就換成約戰版，只有投靠那一條照 conquest.on 挑了舊句。
約戰開著換成 howto.CONQUEST_JOIN_DUEL（待 joy 潤）；子開關關著（舊出陣）一個字都不變。"""
from __future__ import annotations

import pytest

from duel_kit import duel_content, duel_world, game_of, seat
from tianxia import howto

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_join_line_says_post_a_duel_not_hold_one_while_duels_are_on(profile):
    c = duel_content(profile)
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    game = game_of(c, world, "甲")
    join = "".join(howto.join_lines(c, game.state.world))
    assert howto.CONQUEST_JOIN_DUEL in join and howto.CONQUEST_JOIN not in join
    assert "守一回" not in join and "推一半" not in join
    assert "守一回" not in game.howto_text() and "推一半" not in game.howto_text()


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_join_line_is_unchanged_when_duels_are_off(profile):
    c = duel_content(profile, off=True)
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    game = game_of(c, world, "甲")
    join = "".join(howto.join_lines(c, game.state.world))
    assert howto.CONQUEST_JOIN in join and howto.CONQUEST_JOIN_DUEL not in join
