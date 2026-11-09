"""門派第一批（tianxia/features/zongmen/；設計稿 v6，Joy 2026-11-08「不錯，按照設計稿動工」）：新五門關著時不存在、開著在山門拜入、
學得到本門第一式、不綁勢力（拜書院不再算投靠官軍、叛投不帶走門派）、叛出之後這一季回不來、換季照帶、假人會拜。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import library
from tianxia.engine import Game
from tianxia.features.zongmen import bots, rules
from tianxia.rules import apply_effect
from tianxia.models import Effect


def _content(on=True):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    c.config.zongmen.enabled = on
    return c


def _game(c, at="baima_temple", name="沈青衫"):
    g = Game.new(c, name, rng=random.Random(0))
    g.sync(1_000_000.0)
    g.state.player.location = at
    g.state.player.journey = None
    return g


def _ids(g):
    return [o.id for o in g.options()]


@pytest.mark.smoke
def test_join_baima_at_the_temple_and_learn_the_first_art():
    c = _content()
    g = _game(c)
    opt = next(o for o in g.options() if o.id == "zongmen:join:baima")
    assert opt.label == "拜入白馬寺" and "不算投靠" in opt.confirm
    msgs = g.choose("zongmen:join:baima")
    p = g.state.player
    assert p.sect == "baima" and p.faction is None
    assert any("伏魔棍" in m for m in msgs)
    fumo = c.skills["fumo_gun"]
    assert fumo in library._taught_here(g.state, c) and library.learn_problem(g.state, c, fumo) is None
    assert "zongmen:join:baima" not in _ids(g) and "zongmen:leave:baima" in _ids(g)


def test_closed_the_new_sects_are_nowhere():
    c = _content(on=False)
    g = _game(c)
    assert not any(i.startswith("zongmen:") for i in _ids(g))
    assert c.skills["fumo_gun"] not in library._taught_here(g.state, c)
    assert not c.sect_open("baima") and c.sect_open("yingchuan_academy")
    assert g.choose("zongmen:join:baima") != ["你拜入了白馬寺。"] and g.state.player.sect is None


def test_every_new_sect_has_a_place_and_a_first_art():
    c = _content()
    mine = [s for s in c.sects.values() if rules.own(s)]
    assert {s.id for s in mine} == {"baima", "nanhua", "songyang", "lulin", "xiangshe"}
    for s in mine:
        assert s.location in c.locations and rules.first_art(c, s.id), s.id
        assert rules.sect_here(c, s.location) is s


def test_academy_no_longer_makes_you_imperial_army_and_defection_keeps_the_sect():
    c = _content()
    g = _game(c, at="yingchuan_academy")
    apply_effect(Effect(join_sect="yingchuan_academy"), g.state, c, g.world)
    assert g.state.player.sect == "yingchuan_academy" and g.state.player.faction is None
    c2 = _content(on=False)
    g2 = _game(c2, at="yingchuan_academy", name="柳青")
    apply_effect(Effect(join_sect="yingchuan_academy"), g2.state, c2, g2.world)
    assert g2.state.player.faction == "guan"  # 關著照舊：拜書院算投靠官軍
    from tianxia.features.faction import defection

    old = c.scenario.faction("guan")
    assert defection._sect_left(g.state.player, old, c) is None
    assert defection._sect_left(g2.state.player, old, c2) is not None


def test_leaving_locks_that_sect_for_the_season_but_not_the_others():
    c = _content()
    g = _game(c)
    g.choose("zongmen:join:baima")
    msgs = g.choose("zongmen:leave:baima")
    assert g.state.player.sect is None and msgs == ["你叛出了白馬寺。"]
    assert "zongmen:join:baima" not in _ids(g)
    g.state.player.location = "jade_cave"
    assert "zongmen:join:nanhua" in _ids(g)


def test_the_sect_carries_into_the_next_season():
    c = _content()
    g = _game(c)
    g.choose("zongmen:join:baima")
    g._reset_player_for_new_season(g.state.player.season_number + 1)
    assert g.state.player.sect == "baima"


def test_bots_join_some_sects_by_a_fixed_roll():
    c = _content()
    g = _game(c)
    opt = next(o for o in g.options() if o.id == "zongmen:join:baima")
    first = bots.score(g, opt)
    assert first in (None, bots.JOIN_SCORE) and bots.score(g, opt) == first
    names = [f"甲{i}" for i in range(40)]
    joined = sum(bots._roll(n, "baima") < bots.JOIN_SHARE for n in names)
    assert 5 < joined < 30
