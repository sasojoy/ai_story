"""稱號與官職的煙霧測試（開發規範手冊 4.1 第三級：一包一條）：真實內容 week7，開關打開，換週之後結算、自動戴上、收進名號簿。"""
import random

import pytest
from conftest import real_content

from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.features.titles import actions
from tianxia.sqlite_world import open_world

MON = 1792339200  # 2026-10-19 週一 00:00（台灣）


@pytest.mark.smoke
def test_titles_week7_settles_and_wears(monkeypatch):
    feature = next(f for f in FEATURES if f.name == "titles")
    c = real_content("week7")
    c.config.titles.enabled = True
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, MON + 36000)
    g = Game.new(c, "沈浪", rng=random.Random(0), world=store, prologue=False)
    g.client = None
    g.state.player.tutorial_step = len(c.tutorial.steps)
    monkeypatch.setattr(actions, "_board", lambda ctx: {"武學": [("沈浪", "某劍", "上品", 10.0, 50)]})
    for day in range(0, 4):
        now = MON + 36000 + day * 86400
        store.catch_up_season(c, now, random.Random(0))
        g.sync(now)
        if g.state.world.titles_week:
            break
    assert g.state.world.titles_week >= 2
    assert g.state.player.titles_worn["name"] == "武冠群倫"
    assert feature.enabled(g) and feature.status(g)["titles"]["worn"]["id"] == "wuxue"
