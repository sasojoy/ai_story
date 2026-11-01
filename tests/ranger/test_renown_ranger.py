"""遊俠名號併進善惡稱號（名聲設計 2.3）：人人都有、投靠了也照算；散人原本的好處照舊只給散人、階讀善惡稱號；
懸賞的功績照交差那一刻走的路記成善名或惡名；狀態列不再接遊俠名號。關著一個字都不變。"""

import pytest

from conftest import real_content

from tianxia import bounties, ranger, renown, rules, social
from tianxia.models import Condition
from tianxia.state import Bounty, new_game_state


def _sanren(c, good=0, evil=0):
    s = new_game_state(c, "甲")
    s.player.stats.update({"good": good, "evil": evil})
    return s


def test_sanren_perks_read_the_virtue_tier():
    c = real_content("week7")
    s = _sanren(c, good=18)
    assert ranger.tier(s, c) == renown.virtue_tier(s, c) == 2
    assert ranger.audience_discount(s, c) == 6 and ranger.exp_factor(s, c) == 1.10
    s.player.faction = "guan"
    assert ranger.tier(s, c) == 0  # 好處照舊只給散人
    assert renown.virtue_tier(s, c) == 2  # 稱號照算、不凍結


def test_old_ranger_books_are_ignored_when_merged():
    c = real_content("week7")
    s = _sanren(c)
    s.player.ranger_good, s.player.ranger_deeds = 40, 30  # 上線前記的帳：不讀、不補
    assert ranger.tier(s, c) == 0 and ranger.status(s, c) is None


@pytest.mark.smoke
def test_affiliation_no_longer_carries_the_ranger_title():
    c = real_content("week7")
    s = _sanren(c, good=18)
    assert social.affiliation(s, c) == "散人"
    c.config.renown.titles = False
    s.player.ranger_good = 18
    assert social.affiliation(s, c) == "散人・一方豪俠"  # 關著照舊


def test_ranger_conditions_read_the_new_tiers():
    c = real_content("week7")
    cond = Condition(ranger_min=3, ranger_path="寇")
    assert not rules.check_condition(cond, _sanren(c, evil=29), c)
    assert rules.check_condition(cond, _sanren(c, evil=30), c)
    assert not rules.check_condition(cond, _sanren(c, good=40, evil=30), c)


def test_good_and_evil_gains_no_longer_feed_the_old_books():
    c = real_content("week7")
    s = _sanren(c)
    ranger.note_gain(s, c, "good", 5)
    assert s.player.ranger_good == 0


def test_bounty_deeds_become_good_or_ill_name_by_the_path():
    c = real_content("week7")
    b = Bounty(id="b1", kind="scout", faction="guan", week=1, expires=1e9, silver=10, deeds=3)
    s = _sanren(c, evil=8)
    assert "惡名 +3" in bounties.reward_text(s, c, b)
    assert ranger.add_deeds(s, c, 3) == ["惡名 +3"] and s.player.stats["evil"] == 11
    s = _sanren(c)
    assert ranger.add_deeds(s, c, 3) == ["善名 +3"] and s.player.stats["good"] == 3
    s.player.faction = "guan"
    assert ranger.add_deeds(s, c, 3) == []  # 陣營的人照舊不記


def test_switch_off_keeps_the_old_ranger_book():
    c = real_content("week7")
    c.config.renown.titles = False
    s = _sanren(c)
    assert ranger.add_deeds(s, c, 3) == ["俠名 +3"] and s.player.ranger_deeds == 3 and s.player.stats.get("good", 0) == 0
    assert ranger.status(s, c)["points"] == 3
    b = Bounty(id="b1", kind="scout", faction="guan", week=1, expires=1e9, silver=10, deeds=3)
    assert "俠名 +3" in bounties.reward_text(s, c, b)
