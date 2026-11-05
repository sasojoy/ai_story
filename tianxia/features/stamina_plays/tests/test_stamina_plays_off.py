"""後期體力玩法（joy 10/16：設伏劫道、修築工事、屯糧練兵）的正式開關：設伏 2026-10-30 打開（Joy「直接打開」，7 天、21 天兩種季都有），
屯糧練兵照舊關著（修築工事 10/27 跟著舊拔河拿掉）。開關關著：選單上沒有那一樣（假人與整季機器人照選單做，所以也不做）。"""
import random

import pytest
from conftest import real_content

from tianxia import ambush
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

PLAYS = ("ambush:", "works:")


@pytest.mark.parametrize("profile", [None, "week7", "season21"])
def test_real_content_ships_ambush_on_and_stockpile_off(profile):
    cfg = real_content(profile).config
    assert cfg.ambush.enabled and not cfg.stockpile.enabled


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


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_the_real_menu_offers_ambush_but_not_stockpile(profile):
    c = real_content(profile)
    plays = _plays(_guan_at_changshe(c))
    assert ambush.on(c) and any(i.startswith("ambush:set:") for i in plays) and not any(i.startswith("works:") for i in plays)
    c.config.ambush.enabled = False  # 主機的緊急開關：關了就沒有鈕
    assert _plays(_guan_at_changshe(c)) == []


def test_the_same_spot_offers_them_once_switched_on():  # 反證：上面那一條是空的，不是因為站錯了地方
    c = real_content("week7")
    c.config.ambush.enabled = True
    c.config.stockpile.enabled = True
    plays = _plays(_guan_at_changshe(c))
    assert "works:stockpile" in plays and any(i.startswith("ambush:set:") for i in plays)
