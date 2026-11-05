"""新手引導的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：week7 網頁上建的新角色站在城門口（開局第一分鐘），
選了一顆，那位人物的信（託付）送到；引導走完了，任務卡上亮新手目標的頭三條。"""
import random

import pytest

from conftest import real_content
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


@pytest.mark.smoke
def test_a_new_character_meets_the_gate_gets_the_letter_and_sees_the_goals():
    feature = next(f for f in FEATURES if f.name == "guide")
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "引路客", rng=random.Random(0), world=open_world(), prologue=True)
    game.sync(1000.0)
    assert feature.enabled(game) and feature.prefix is None
    assert game.state.pending_event == c.opening.event
    game.choose("growth:balanced")  # 五項屬性的季：開季準備卡先挑成長配比，才輪到城門口的三選一
    game.choose("choice:0")
    assert [x.kind for x in game.state.player.letters] == ["託付"]
    view = game.newbie_view()
    assert view is not None and len(view["rows"]) == 3
