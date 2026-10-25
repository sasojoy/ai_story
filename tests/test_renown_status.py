"""狀態列與玩家卡的名聲資料、個人目標（名聲設計 2.5、6.1、第九節 guide）。"""
import random

from conftest import real_content, renown_unscaled

from tianxia import howto, renown, rules, social
from tianxia.engine import Game
from tianxia.models import Condition
from tianxia.state import new_game_state


def test_status_has_both_ladders_and_the_gap():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.stats.update({"fame": 27, "good": 18, "evil": 3})
    st = renown.status(s, c)
    assert st["short"] == ["名動一方", "一方豪俠"]
    assert (st["fame"]["next"], st["fame"]["gap"]) == ("威震州郡", 23)
    assert (st["virtue"]["by"], st["virtue"]["next"], st["virtue"]["gap"]) == ("善名", "州郡大俠", 12)
    assert [row["title"] for row in st["fame"]["ladder"]] == ["小有名氣", "名動一方", "威震州郡", "天下聞名"]
    assert [row["at"] for row in st["virtue"]["ladder"]["寇"]] == [5, 15, 30, 50]
    assert st["scale_note"] is None  # 週末季沒有倍數
    assert st["sanren"] is not None  # 散人另列
    s.player.faction = "guan"
    assert renown.status(s, c)["sanren"] is None


def test_top_tier_has_no_next_and_long_seasons_say_the_scale():
    c = real_content()  # 14 天：倍數 5.6
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    s = g.state
    s.player.stats["fame"] = 10_000
    st = renown.status(s, c)
    assert (st["fame"]["tier"], st["fame"]["next"], st["fame"]["gap"]) == (4, None, None)
    assert st["scale_note"] == "這一季 14 天，門檻是週末季的 5.6 倍。"
    assert st["fame"]["ladder"][0]["at"] == 56


def test_status_and_card_are_none_when_off():
    c = renown_unscaled(real_content("week7"))
    c.config.renown.titles = False
    s = new_game_state(c, "甲")
    assert renown.status(s, c) is None and renown.card(s, c) is None


def test_card_shows_titles_only():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.stats.update({"fame": 12, "good": 4, "evil": 22})
    assert renown.card(s, c) == {"titles": ["小有名氣", "江湖巨寇"], "path": "寇"}
    s.player.stats.update({"good": 0, "evil": 0})
    assert renown.card(s, c) == {"titles": ["小有名氣"], "path": None}


def test_status_data_and_the_player_card_carry_it():
    c = renown_unscaled(real_content("week7"))
    c.config.auto_open_first_season = True
    a = Game.new(c, "甲", rng=random.Random(0))
    b = Game.new(c, "乙", rng=random.Random(0))
    for g in (a, b):
        g.client = None
    b.state.player.stats.update({"fame": 30, "good": 16})
    assert a.status_data()["renown"]["short"] == []
    assert social.card(a, b)["renown"] == {"titles": ["名動一方", "一方豪俠"], "path": "俠"}


def test_fame_tier_condition_reads_this_seasons_bar():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.stats["fame"] = 10
    assert rules.check_condition(Condition(fame_tier=1), s, c)
    assert not rules.check_condition(Condition(fame_tier=2), s, c)
    assert not rules.check_condition(Condition(fame_tier=1), s, None)  # 要 content 才判得出
    c.config.renown.titles = False  # 名聲關著：照沒乘倍數的門檻比名望，同改之前的「名望達到 10」
    assert rules.check_condition(Condition(fame_tier=1), s, c)
    s.player.stats["fame"] = 9
    assert not rules.check_condition(Condition(fame_tier=1), s, c)


def test_the_fame_goal_reads_the_tier():
    c = renown_unscaled(real_content("week7"))
    goal = next(m for m in c.scenario.milestones if m.id == "fame_10")
    assert goal.condition.fame_tier == 1 and "小有名氣" in goal.text


def test_howto_has_a_renown_section_with_this_seasons_bars():
    c = real_content()
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    text = howto.page(c, g.state.world, recruitable=False)
    assert "#### 名聲" in text and "#### 名望" not in text
    assert "小有名氣 56" in text  # 14 天的季：門檻 10 × 5.6
    assert "這一季 14 天，門檻是週末季的 5.6 倍。" in text
    c.config.renown.titles = False
    text = howto.page(c, g.state.world, recruitable=False)
    assert "#### 名望" in text and "#### 名聲" not in text
