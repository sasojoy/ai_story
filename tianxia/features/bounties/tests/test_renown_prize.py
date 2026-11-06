"""掛著重賞的討伐要名動一方以上才揭得了（名聲設計 4.2）；重賞給出去之後誰都揭得了；手上揭著的不收回。"""
from conftest import real_content

from tianxia import bounties
from tianxia.state import Bounty, new_game_state


def _prize(c):
    loc = next(iter(c.locations))
    return Bounty(id="b1", kind="strike", faction="guan", week=1, expires=1e9, silver=10, deeds=3, quota=3,
                  prize="treasure", location=loc)


def test_prize_strikes_need_the_tier():
    c = real_content("week7")
    s = new_game_state(c, "甲")
    b = _prize(c)
    assert bounties.take_problem(s, c, b) == bounties.PRIZE_GATE
    s.player.stats["fame"] = 25
    assert bounties.take_problem(s, c, b) != bounties.PRIZE_GATE
    s.player.stats["fame"] = 0
    b.done_by = ["乙"]  # 重賞給出去了：一般的單
    assert bounties.take_problem(s, c, b) != bounties.PRIZE_GATE


def test_switch_off_lets_anyone_take_it():
    c = real_content("week7")
    c.config.renown.prize_gate = False
    s = new_game_state(c, "甲")
    assert bounties.take_problem(s, c, _prize(c)) != bounties.PRIZE_GATE
