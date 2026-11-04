"""有所感與頓悟的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：week7 的散人在潁水河畔靜下心來有所感，
選對做法、擲中（成功率擺到頂、特殊頓悟擺到不中）、順其自然——悟到這一處的基本意境，江湖紀錄記一則「有所感・場景」。"""
import random

import pytest

from conftest import real_content
from tianxia import insights
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


@pytest.mark.smoke
def test_a_wanderer_senses_the_river_picks_right_and_lets_it_settle():
    feature = next(f for f in FEATURES if f.name == "sense")
    c = real_content("week7")
    c.config.auto_open_first_season = True
    c.config.sense_rate_range = (100, 100)
    c.config.epiphany.chances = [0.0, 0.0, 0.0]
    game = Game.new(c, "觀水客", rng=random.Random(0), world=open_world())
    game.skip_tutorial()
    game.sync(1000.0)
    for _ in range(6):  # 開局三選一之類待選的事件：選掉
        first = next((o.id for o in game.options() if o.id.startswith("choice:") and o.enabled), None)
        if first is None:
            break
        game.choose(first)
    assert feature.enabled(game) and feature.prefix == ("sense", "dunwu")
    p = game.state.player
    p.location = "yingshui"
    loc = c.locations["yingshui"]
    game._sense_here(loc, random.Random(1))
    s = p.sensing
    assert s is not None and s.stage == "choose"
    scene = c.insight_scenes[s.scene]
    right = next(i for i, j in enumerate(s.order) if scene.methods[j].attribute in insights.pool_attributes(loc, c))
    game.choose(f"sense:{right}")
    assert [o.id for o in game.options()] == ["sense:draw", "sense:let"]
    game.choose("sense:let")
    assert p.sensing is None and len(p.insights) == 1
    assert game.state.journal[0].title == f"有所感・{scene.title}"
