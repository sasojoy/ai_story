"""正式季整合第 8 批：各陣營最好的練功點一樣好（設計 3.6、12.1 第 16 條）。黃巾練得到的官軍營寨（盧植營）最弱的那一路是北軍五校，
跟官軍在廣宗打的黃巾死士同一檔：對手經驗差不到一成（勝率照難度，難度也只差一截）。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia.engine import Game
from tianxia.sqlite_world import open_world


def _practice_foe(faction, at):
    c = real_content("season21")
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    game.state.player.faction, game.state.player.location = faction, at
    return game._gather_foe(c.locations[at])


@pytest.mark.slow
def test_the_yellow_turbans_best_practice_spot_is_as_good_as_the_imperials():
    huang = _practice_foe("huang", "luzhi_camp")
    guan = _practice_foe("guan", "guangzong")
    assert huang.id == "beijun_wuzu" and guan.id == "huangjin_sishi"
    assert huang.exp >= 0.9 * guan.exp and abs(huang.difficulty - guan.difficulty) <= 10
