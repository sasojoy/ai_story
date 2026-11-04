"""簽到的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路，真實內容 season21）：開季那一天同步時自動領了第 1 天，
同一天再領被擋、第 6 天（要挑四階的日子）不自動領、挑了才領。標記 @pytest.mark.smoke 留著（每一包至少一條，test_test_for 守）。"""
import random

import pytest
from conftest import real_content

from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）：開季那一天


def _game():
    c = real_content("season21")
    c.config.admins = ["沈浪"]
    c.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, MON + 10 * HOUR)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.state.player.tutorial_step = len(c.tutorial.steps)
    return game


def _at(game, now):
    game.world.catch_up_season(game.content, now, random.Random(0))
    game.sync(now)


@pytest.mark.smoke
def test_checkin_claims_the_first_day_on_its_own_and_waits_for_the_pick_on_day_six():
    game = _game()
    feature = next(f for f in FEATURES if f.name == "checkin")
    _at(game, MON + 10 * HOUR)
    assert feature.enabled(game) is True
    p = game.state.player
    assert p.checkin_days == [1]
    assert game.checkin_view()["done"] is True
    assert "今天已經簽過了" in game.check_in()[0]  # 同一天再領：被擋
    _at(game, MON + 5 * DAY + 10 * HOUR)  # 第 6 天：要自己挑一種四階，不自動領
    pick = game.checkin_view()["pick"]
    assert p.checkin_days == [1] and pick  # 小卡上列著四種四階料等著挑
    game.check_in(pick[0]["attribute"])
    assert p.checkin_days == [1, 6]
