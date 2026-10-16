"""後期體力玩法（joy 10/16：設伏劫道、修築工事、屯糧練兵）合進 main 時，三個開關在正式內容都關著（企劃者 10/16：數字與設計等第 5 塊、
21 天的季再一起定）。開關關著：選單上沒有這三樣（假人與整季機器人照選單做，所以也不做）。"""
import random

import pytest
from conftest import real_content

from tianxia import ambush, works
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

PLAYS = ("ambush:", "works:")


@pytest.mark.parametrize("profile", [None, "weekend"])
def test_real_content_ships_the_three_stamina_plays_off(profile):
    cfg = real_content(profile).config
    assert not cfg.ambush.enabled and not cfg.fortify.enabled and not cfg.stockpile.enabled


def _guan_at_changshe(c):
    c.config.auto_open_first_season = True
    g = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    g.client = None
    p = g.state.player
    p.faction, p.location = "guan", "changshe"  # 官軍的大本營：屯糧屯得了，路上設得了伏
    p.joined_at = g.state.world.time - 10**9  # 過了截殺的新手期：開關開著時設伏鈕才畫得出來
    return g


def _plays(g):
    return [o.id for o in g.options() if o.id.startswith(PLAYS)]


def test_no_stamina_play_on_the_menu_with_the_real_switches():
    c = real_content("weekend")
    assert _plays(_guan_at_changshe(c)) == []
    assert not ambush.on(c) and not works.fortify_on(c)


def test_the_same_spot_offers_them_once_switched_on():  # 反證：上面那一條是空的，不是因為站錯了地方
    c = real_content("weekend")
    c.config.ambush.enabled = True
    c.config.stockpile.enabled = True
    plays = _plays(_guan_at_changshe(c))
    assert "works:stockpile" in plays and any(i.startswith("ambush:set:") for i in plays)
