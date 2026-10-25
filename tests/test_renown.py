"""名聲（核心玩法重整第 3 塊）的共用地基：段、稱號、季長倍數、開關。"""
from conftest import real_content, renown_on

from tianxia import renown
from tianxia.state import new_game_state
from tianxia.world_state import fresh_season, length_factor, stamp_season


def _state(content, fame=0, good=0, evil=0):
    s = new_game_state(content, "甲")
    s.player.stats.update({"fame": fame, "good": good, "evil": evil})
    return s


def test_fame_has_five_tiers_and_titles_show_from_the_first():
    c = real_content("week7")
    assert [renown.fame_tier(_state(c, fame=f), c) for f in (0, 9, 10, 24, 25, 49, 50, 89, 90)] == [0, 0, 1, 1, 2, 2, 3, 3, 4]
    assert renown.fame_title(_state(c, fame=27), c) == "名動一方"
    assert renown.fame_title(_state(c, fame=3), c) is None


def test_virtue_follows_the_higher_book_and_ties_go_to_xia():
    c = real_content("week7")
    assert renown.path(_state(c, good=18, evil=3)) == "俠"
    assert renown.path(_state(c, good=4, evil=22)) == "寇"
    assert renown.path(_state(c, good=6, evil=6)) == "俠"
    assert renown.virtue_title(_state(c, good=18, evil=3), c) == "一方豪俠"
    assert renown.virtue_title(_state(c, good=4, evil=22), c) == "江湖巨寇"
    assert renown.virtue_title(_state(c, good=2, evil=1), c) is None


def test_women_get_the_female_title():
    c = real_content("week7")
    s = _state(c, good=0, evil=6)
    s.player.gender = "女"
    assert renown.virtue_title(s, c) == "綠林女傑"


def test_titles_lists_fame_then_virtue_from_a_given_fame_tier():
    c = real_content("week7")
    s = _state(c, fame=12, good=4, evil=22)
    assert renown.titles(s, c) == ["小有名氣", "江湖巨寇"]
    assert renown.titles(s, c, fame_from=2) == ["江湖巨寇"]


def test_meets_checks_path_and_tier():
    c = real_content("week7")
    s = _state(c, good=15, evil=3)
    assert renown.meets(s, c, "俠", 2) and not renown.meets(s, c, "俠", 3) and not renown.meets(s, c, "寇", 1)


def test_the_scale_multiplies_thresholds_from_the_stamp():
    c = real_content()  # 14 天
    season = fresh_season(c)
    assert season.renown_scale == length_factor(season, c) == 5.6
    s = _state(c, fame=27)
    s.world = season
    assert renown.fame_bars(c, season) == [56, 140, 280, 504]
    assert renown.fame_tier(s, c) == 0
    assert renown.virtue_bars(c, season) == [28, 84, 168, 280]


def test_a_season_without_the_stamp_counts_as_one():
    c = real_content()
    season = fresh_season(c)
    season.renown_scale = None  # 上線那一刻正在跑的季
    assert renown.scale(season) == 1.0 and renown.fame_bars(c, season) == [10, 25, 50, 90]


def test_switches_off_mean_no_titles_and_no_stamp():
    c = real_content("week7")
    c.config.renown.titles = False
    s = _state(c, fame=99, good=60)
    assert renown.fame_tier(s, c) == renown.virtue_tier(s, c) == 0 and renown.titles(s, c) == []
    c.config.renown.titles = True
    c.config.renown.scale = False
    season = fresh_season(c)
    stamp_season(season, c)
    assert season.renown_scale is None


def test_fixture_content_has_every_switch_off_and_renown_on_turns_them_on(content):
    cfg = content.config.renown
    assert not cfg.titles and not cfg.official_wanted
    assert not renown.on(content) and not renown.on(content, "duel")
    renown_on(content)
    assert cfg.titles and cfg.official_wanted and renown.on(content, "duel")


def test_discount_words():
    assert [renown.discount_word(f) for f in (0.97, 0.94, 0.9, 0.85, 1.2)] == ["九七折", "九四折", "九折", "八五折", "貴兩成"]


def test_price_factor_follows_the_fame_tier():
    c = real_content("week7")
    assert [renown.price_factor(_state(c, fame=f), c) for f in (0, 10, 25, 50, 90)] == [1.0, 0.97, 0.94, 0.9, 0.85]
    c.config.renown.discount = False
    assert renown.price_factor(_state(c, fame=90), c) == 1.0
