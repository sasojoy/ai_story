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


def _saved_news(g):
    """存進資料庫的那一份季（下一個請求讀的就是它），不是記憶體裡的 state.world。"""
    return [r.text for r in g.world.get_season().rumors if "甲" in r.text]


def test_a_crossing_found_on_a_sync_is_saved():
    """FB-291：散人在輪詢時才跨過威震州郡（決戰收場後回來補的軍餉、名望）：同步只存角色，天下大事那一句要自己存進共用賽季，
    不然旗標跟著角色存了、那一句永遠不會再傳。"""
    g = _game()
    g.state.player.stats["fame"] = 46
    g._log(["（看一眼）"])  # 第一次看：記下名動一方
    g.state.player.stats["fame"] = 52  # 同步時補到的名望
    g.sync(1_000_000.0)
    assert _saved_news(g) == ["江湖上傳開了甲的名號。"]


def test_a_crossing_at_the_end_of_an_action_is_saved():
    """動作照例先存季、再 _log：跨段在 _log 裡才發現，那一句也要存進去（同 FB-291）。"""
    g = _game()
    g.state.player.stats["fame"] = 49
    g._log(["（看一眼）"])
    g.state.player.stats["fame"] = 50
    g._save_season()
    g._log(["名望 +1"])
    assert _saved_news(g) == ["江湖上傳開了甲的名號。"]


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
