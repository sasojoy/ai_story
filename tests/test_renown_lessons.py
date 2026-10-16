"""正邪武學與綠林山寨（名聲設計 5.1）。"""
import random

import pytest
from conftest import real_content

from tianxia import atlas, library, renown, skillview, team
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import new_game_state


def test_lean_reaches_the_art_and_resonance():
    c = real_content("weekend")
    art = team.resolve_art("shouyi_jian", c, open_world())
    assert art.lean == "正" and team.resolve_art("xiaolin_gong", c, open_world()).lean == "邪"
    assert team.resolve_art("jichu_tuna", c, open_world()).lean == "無"  # 現有的不加正邪
    s = new_game_state(c, "甲")
    s.player.stats["good"] = 22
    assert team.resonance(s, c, art) == pytest.approx(1.11)


def test_title_gate():
    c = real_content("weekend")
    s = new_game_state(c, "甲")
    skill = c.skills["yanghao_jue"]
    s.player.stats.update({"good": 10, "silver": 100})
    assert library.learn_problem(s, c, skill) == "要一方豪俠才肯教"
    s.player.stats["good"] = 15
    assert library.learn_problem(s, c, skill) is None
    s.player.stats["evil"] = 16  # 惡名高過善名：走的是寇，書院不教
    assert library.learn_problem(s, c, skill) == "要一方豪俠才肯教"


def test_the_wicked_gate_says_the_female_title():
    c = real_content("weekend")
    s = new_game_state(c, "甲")
    s.player.gender = "女"
    s.player.stats.update({"evil": 2, "silver": 100})
    assert library.learn_problem(s, c, c.skills["jianjing_dao"]) == "要綠林女傑才肯教"


def test_lessons_off_hides_the_four():
    c = real_content("weekend")
    c.config.renown.lessons = False
    s = new_game_state(c, "甲")
    s.player.location = c.skills["shouyi_jian"].learn.at
    assert all(sk.id != "shouyi_jian" for sk, _ in library.lessons_here(s, c))
    assert library.learn(s, c, "shouyi_jian") == ["這裡沒有人教這一門。"]


def test_learning_one_at_the_academy():
    c = real_content("weekend")
    s = new_game_state(c, "甲")
    s.player.location = "yingchuan_academy"
    s.player.stats.update({"good": 6, "silver": 50})
    assert ("shouyi_jian", None) in [(sk.id, why) for sk, why in library.lessons_here(s, c)]
    lines = library.learn(s, c, "shouyi_jian")
    assert lines[0].startswith("你學會了【守義劍】") and "銀兩 -20" in lines and s.player.stats["silver"] == 30
    assert library.lesson_note(c.skills["shouyi_jian"]) == "武學・下品・屬剛・正派・銀兩 20"


def test_the_greenwood_fort_opens_with_the_season_only_when_lessons_are_on():
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    assert renown.GREENWOOD_FLAG in g.state.world.flags
    assert atlas.is_unlocked(c.locations["lulin_zhai"], g.state, c)
    off = real_content("weekend")
    off.config.renown.lessons = False
    off.config.auto_open_first_season = True
    h = Game.new(off, "乙", rng=random.Random(0), world=g.world)
    h.state.world.flags.discard(renown.GREENWOOD_FLAG)
    h.advance(3600)
    assert renown.GREENWOOD_FLAG not in h.state.world.flags
    assert not atlas.is_unlocked(off.locations["lulin_zhai"], h.state, off)


def test_the_greenwood_fort_is_strongest_in_mountain():
    """FB-295：意境提示（main 的第四塊）規定悟得到意境的地點都要寫最濃的那一種。綠林山寨是山林（意境提示設計：山上是山），
    悟得到風與山，最濃是山；這裡用得到的有所感場景線索指得到慢（山）。"""
    from tianxia.insights import scenes_for

    c = real_content("weekend")
    fort = c.locations["lulin_zhai"]
    assert fort.insight_strong == "shan" and c.insights["shan"].strong_line
    assert any("慢" in scene.hints for scene in scenes_for(fort, c))


def test_the_virtue_perks_name_the_lessons():
    c = real_content("weekend")
    assert "潁川書院教守義劍" in renown.virtue_perks(c, "俠", 1) and "潁川書院教養浩訣" in renown.virtue_perks(c, "俠", 2)
    assert "綠林山寨教剪徑刀" in renown.virtue_perks(c, "寇", 1) and "綠林山寨教嘯林功" in renown.virtue_perks(c, "寇", 2)
    c.config.renown.lessons = False
    assert not any(perk.endswith("守義劍") for perk in renown.virtue_perks(c, "俠", 1))


def test_the_boost_line_names_the_title_when_the_path_matches():
    c = real_content("weekend")
    w = open_world()
    s = new_game_state(c, "甲")
    s.player.member.wugong_id = "shouyi_jian"
    s.player.stats.update({"good": 22, "evil": 4})
    assert "你是一方豪俠：【守義劍】正派，吃善名 22，+11%" in skillview.boost_line(s, c, w)
    s.player.stats.update({"good": 2, "evil": 9})  # 走寇：正派的共鳴照算，不寫稱號
    assert "【守義劍】正派，吃善名 2，+1%" in skillview.boost_line(s, c, w)
    assert "你是" not in skillview.boost_line(s, c, w)
    c.config.renown.explain = False
    assert "【守義劍】共鳴 +1%" in skillview.boost_line(s, c, w)
