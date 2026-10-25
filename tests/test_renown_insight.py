"""浩然、血煞（名聲設計 5.1）：門檻固定 15、不乘季長，要走對那條路；悟到時寫原因。"""
import random

from conftest import real_content

from tianxia import insights
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import new_game_state
from tianxia.world_state import fresh_season


def test_needs_the_right_path_and_does_not_scale():
    c = real_content()  # 14 天：稱號門檻乘 5.6，浩然照內容寫的 15
    w = open_world()
    s = new_game_state(c, "甲")
    s.world = fresh_season(c)
    s.world.renown_scale = 5.6
    s.player.stats.update({"good": 15, "evil": 20})
    assert not any("浩然" in line for line in insights.grant_by_name(s, c, w))  # 走的是寇
    s.player.stats.update({"good": 15, "evil": 3})
    lines = insights.grant_by_name(s, c, w)
    assert lines[0] == "你行俠日久，胸中多了一股浩然之氣。" and "haoran" in s.player.insights


def test_the_wicked_get_xuesha_only_when_evil_leads():
    c = real_content()
    w = open_world()
    s = new_game_state(c, "甲")
    s.player.stats.update({"good": 15, "evil": 15})  # 一樣多算俠
    assert not any("血煞" in line for line in insights.grant_by_name(s, c, w))
    s.player.stats["evil"] = 16
    assert insights.grant_by_name(s, c, w)[0] == "你橫行日久，胸中多了一股血煞之氣。"


def test_switch_off_keeps_the_old_rule():
    c = real_content()
    c.config.renown.virtue_insight = False
    s = new_game_state(c, "甲")
    s.player.stats.update({"good": 15, "evil": 20})
    lines = insights.grant_by_name(s, c, open_world())
    assert lines[0] == "你心有所感，胸中多了一股浩然之氣。"


def test_gains_outside_events_are_caught_at_the_end_of_the_action():
    """善名從懸賞、截殺來的（不走 rules.apply_effect）：那一下的紀錄結束時也悟得到。"""
    c = real_content("week7")
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    g.state.player.stats["good"] = 15
    g._log(["（交了一張懸賞）"])
    assert "haoran" in g.state.player.insights
    assert any("浩然之氣" in line for e in g.state.journal for line in e.lines)
