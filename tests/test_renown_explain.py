"""求見與拜師的門檻（名聲設計 2.4、6.3）、熟練那一句、散人加成的原因。"""
import random

from conftest import real_content

from tianxia import library, rules
from tianxia.engine import Game
from tianxia.state import new_game_state
from tianxia.world_state import fresh_season

WHO = "huangfusong"  # 皇甫嵩：求見門檻 25


def test_audience_bar_scales_with_the_season():
    c = real_content()
    s = new_game_state(c, "甲")
    s.world = fresh_season(c)  # 14 天：5.6 倍
    assert rules.audience_parts(s, c, WHO).bar == 140 and rules.audience_bar(s, c, WHO) == 140
    s.world.renown_scale = None  # 上線那一刻正在跑的季
    assert rules.audience_bar(s, c, WHO) == 25


def test_brush_off_names_each_discount():
    c = real_content("weekend")
    s = new_game_state(c, "甲")
    s.player.stats.update({"fame": 12, "good": 6})
    parts = rules.audience_parts(s, c, WHO)
    assert parts.bar == 25 and parts.discounts == [("江湖遊俠", 3)]
    assert rules.audience_bar(s, c, WHO) == 22
    assert rules.audience_hint(s, c, WHO) == "名望還差 10；門檻 25，江湖遊俠抵 3"


def test_brush_off_without_explain_keeps_the_short_hint():
    c = real_content("weekend")
    c.config.renown.explain = False
    s = new_game_state(c, "甲")
    s.player.stats.update({"fame": 12, "good": 6})
    assert rules.audience_hint(s, c, WHO) == "名望還差 10"


def test_brush_off_line_from_the_game():
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    g.state.player.stats.update({"fame": 12, "good": 6})
    line = g._brush_off(WHO)[0]
    assert line.endswith("（名望還差 10；門檻 25，江湖遊俠抵 3）")


def test_lesson_fame_scales_too():
    c = real_content()
    s = new_game_state(c, "甲")
    s.world = fresh_season(c)
    s.player.stats.update({"fame": 27, "silver": 999})
    assert library.learn_problem(s, c, c.skills["youxia_jian"]) == "名望 28 以上才肯教"
    s.player.stats["fame"] = 28
    assert library.learn_problem(s, c, c.skills["youxia_jian"]) is None


def test_practice_line_explains_when_on():
    c = real_content("weekend")
    cfg = c.config.practice_bonus["evil"]
    assert cfg.line_explained and cfg.line_explained != cfg.line


def test_ranger_bonuses_say_why():
    from tianxia import renown

    c = real_content("weekend")
    s = new_game_state(c, "甲")
    s.player.stats["good"] = 15
    assert renown.ranger_exp_note(s, c, 1.10) == ["（一方豪俠：打贏的經驗多 10%）"]
    s.player.stats["good"] = 50
    assert renown.ranger_bounty_note(s, c, 1.25) == ["（天下名俠：賞銀 ×1.25）"]
    assert renown.ranger_exp_note(s, c, 1.0) == []
    c.config.renown.explain = False
    assert renown.ranger_exp_note(s, c, 1.20) == []


def test_switches_off_keep_the_old_bar():
    c = real_content()
    c.config.renown.titles = False
    s = new_game_state(c, "甲")
    s.world = fresh_season(c)
    assert rules.audience_bar(s, c, WHO) == 25
    s.player.stats["fame"] = 5
    assert library.learn_problem(s, c, c.skills["youxia_jian"]) != "名望 28 以上才肯教"
