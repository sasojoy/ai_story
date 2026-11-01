"""換季照帶今天出陣的次數，不看地盤開不開（換季不能多出一輪陣，同回體丹、操練）。

搬成包之前 Game._reset_player_for_new_season 一律照帶 sortie_day／sorties_today；搬包之後照帶照舊寫在那裡、不掛在出陣包的
on_season_start——遊戲當下的掛鉤只叫開著的包，掛在那裡的話地盤關著的那一季就不帶了（休季換了設定、地盤從開變關、同一天又開回來時
多出一輪陣；dev/sortie-1 審查的發現）。契約測試 test_a_new_season_keeps_only_what_the_package_carries 只驗開著的那一半（week7）。
"""
from __future__ import annotations

import random

import pytest

from conftest import next_season, real_content
from tianxia import territory
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


@pytest.mark.parametrize(("profile", "off_next"), [(None, False), ("week7", True), ("week7", False)],
                         ids=["地盤兩季都關著", "地盤下一季關掉", "地盤兩季都開著"])
def test_a_new_season_carries_todays_sorties_whether_or_not_territory_is_on(profile, off_next):
    c = real_content(profile)
    c.config.auto_open_first_season = True
    world = open_world()
    game = Game.new(c, "換季客", rng=random.Random(0), world=world)
    game.skip_tutorial()
    game.sync(100.0)
    p = game.state.player
    p.sortie_day, p.sorties_today = 20751, 3
    if off_next:
        c.config.season_one = False  # 休季換設定：下一季沒有地盤（territory.on 只看內容）
    next_season(c, world, game)
    assert territory.on(c) is (profile is not None and not off_next)
    assert (game.state.player.sortie_day, game.state.player.sorties_today) == (20751, 3)
