"""頭目找上門的機會與打贏的賞（名聲設計 4.4）：只放大門檻、擲的還是同一顆骰；名動一方以上打贏，經驗、銀兩、心得多兩成。"""
from conftest import real_content

from tianxia import renown
from tianxia.state import new_game_state


def test_chance_and_reward_follow_the_fame_tier():
    c = real_content("week7")
    s = new_game_state(c, "甲")
    assert renown.duel_chance(s, c) == 1.0 and renown.duel_reward(s, c) == 1.0
    s.player.stats["fame"] = 10
    assert renown.duel_chance(s, c) == 1.1 and renown.duel_reward(s, c) == 1.0
    s.player.stats["fame"] = 25
    assert renown.duel_chance(s, c) == 1.2 and renown.duel_reward(s, c) == 1.2
    c.config.renown.duel = False
    assert renown.duel_chance(s, c) == 1.0 and renown.duel_reward(s, c) == 1.0


def test_meet_and_paid_lines():
    c = real_content("week7")
    s = new_game_state(c, "甲")
    assert renown.duel_meet_line(s, c) == ""
    s.player.stats["fame"] = 25
    assert renown.duel_meet_line(s, c) == "你名動一方，攔路的也多了。"
    assert renown.duel_paid_line(s, c) == "（名動一方：賞多兩成）"
