"""被看見（名聲設計 4.5）：跨過威震州郡天下大事傳一句（一季一人一次）；天下聞名打完大場面點名（一個遊戲日最多 2 則）。"""
import random

from conftest import real_content

from tianxia import renown
from tianxia.engine import Game


def _game(c=None):
    c = c or real_content("weekend")
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    return g


def _news(g):
    return [r.text for r in g.state.world.rumors if "甲" in r.text]


def test_crossing_into_the_third_tier_is_news_once():
    g = _game()
    g.state.player.stats["fame"] = 49
    g._log(["（看一眼）"])
    g.state.player.stats["fame"] = 50
    g._log(["名望 +1"])
    assert _news(g) == ["江湖上傳開了甲的名號。"]
    g.state.player.stats["fame"] = 49
    g._log(["（掉下來）"])
    g.state.player.stats["fame"] = 50
    g._log(["（又上去）"])
    assert len(_news(g)) == 1


def test_world_famous_big_fights_are_named_twice_a_day_at_most():
    g = _game()
    g.state.player.stats["fame"] = 90
    for _ in range(3):
        g._famed_news("宛城", "張曼成", "大勝")
    assert _news(g) == ["天下聞名的甲在宛城與張曼成一戰，大勝。"] * 2


def test_not_famous_enough_or_switch_off_means_no_news():
    g = _game()
    g.state.player.stats["fame"] = 89
    g._famed_news("宛城", "張曼成", "大勝")
    c = real_content("weekend")
    c.config.renown.news = False
    h = _game(c)
    h.state.player.stats["fame"] = 90
    h._famed_news("宛城", "張曼成", "大勝")
    assert _news(g) == [] and _news(h) == [] and renown.on(c)
