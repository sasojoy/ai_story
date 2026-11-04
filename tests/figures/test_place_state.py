"""地點會變樣（世界活起來第二批，tianxia/place_state.py）：五種樣子怎麼變、照時間怎麼走、讀它的地方（事件條件、店價、馬市、
人物走動、場景那一句）。用真實內容（Config.plans 開著）；每個測試拿自己的一份複本。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import deeds, figure_life, figures, mounts, place_state, plans, rules, territory
from tianxia.engine import Game
from tianxia.models import Condition, Itinerary, ItineraryStop, PlanContest
from tianxia.state import GameState, PlayerState
from tianxia.world_state import fresh_season, season_length_days



@pytest.fixture
def c():
    return real_content()


def _season(content, location: str = "changshe") -> GameState:
    player = PlayerState(name="甲", location=location, stats={"silver": 100}, stamina=100)
    return GameState(player=player, world=fresh_season(content))


def _day7(s: GameState, content) -> float:
    return season_length_days(s.world, content) * 86400 / 7


def test_a_fight_burns_then_rebuilds_then_settles_back_to_peace(c):
    s = _season(c)
    w = s.world
    assert place_state.kind_at(w, c, "changshe") == place_state.PEACE
    place_state.strike(w, c, "changshe")
    assert place_state.kind_at(w, c, "changshe") == place_state.WAR
    d = _day7(s, c)
    w.time += d * c.config.plans.war_days7 + 1
    assert place_state.kind_at(w, c, "changshe") == place_state.REBUILD
    w.time += d * c.config.plans.rebuild_days7
    assert place_state.kind_at(w, c, "changshe") == place_state.PEACE
    assert [x.kind for x in w.deeds] == [deeds.PLACE_KIND] and "長社燃起戰火" in w.deeds[0].text


def test_a_second_fight_before_the_fire_dies_brings_famine(c):
    s = _season(c)
    place_state.strike(s.world, c, "changshe")
    place_state.strike(s.world, c, "changshe")
    assert place_state.kind_at(s.world, c, "changshe") == place_state.FAMINE


def test_a_fallen_place_stays_fallen_until_someone_takes_it_back(c):
    s = _season(c)
    w = s.world
    place_state.fall(w, c, "wan_city", "huang")
    w.time += _day7(s, c) * 7  # 一整季過去了也還淪陷
    assert place_state.kind_at(w, c, "wan_city") == place_state.FALLEN
    place_state.strike(w, c, "wan_city", "huang")  # 佔著的人又打贏一仗：照舊
    assert place_state.kind_at(w, c, "wan_city") == place_state.FALLEN
    place_state.strike(w, c, "wan_city", "guan")  # 另一方打贏：收復
    assert place_state.kind_at(w, c, "wan_city") == place_state.REBUILD
    assert "宛城收復了" in w.deeds[-1].text


def test_a_flip_to_the_rebels_is_a_fall_and_a_flip_back_is_a_retake(c):
    s = _season(c)
    place_state.flipped(s.world, c, "changshe", "huang")
    assert place_state.view(s.world, c, "changshe")["name"] == "淪陷・黃巾軍"
    place_state.flipped(s.world, c, "changshe", "guan")
    assert place_state.kind_at(s.world, c, "changshe") == place_state.REBUILD


def test_the_switch_off_keeps_every_place_at_peace(c):
    c.config.plans.places = False
    s = _season(c)
    place_state.strike(s.world, c, "changshe")
    assert place_state.kind_at(s.world, c, "changshe") == place_state.PEACE and not s.world.places
    assert place_state.factor(s.world, c, "changshe") == 1.0


def test_a_settled_plan_marks_its_place_by_what_the_contest_says(c):
    contest = PlanContest(side="huang", announce="{name}打算在{place}反撲。", win="成了。", lose="沒成。", base=1.0, place_win="fallen")
    c.itineraries = [Itinerary(who="liubei", stops=[ItineraryStop(id="t_hit", day=2.0, place="changshe", contest=contest)])]
    s = _season(c)
    end = season_length_days(s.world, c) * 86400
    s.world.time = _day7(s, c) * 1.5
    plans.tick(s, c, end)
    if plans.find(s, "t_hit").won:  # 成了：落入黃巾之手；不成（成算夾在 cap）是打過一仗
        assert place_state.kind_at(s.world, c, "changshe") == place_state.FALLEN and s.world.places["changshe"].side == "huang"
    else:
        assert place_state.kind_at(s.world, c, "changshe") == place_state.WAR


def test_a_quiet_contest_leaves_the_place_alone(c):
    contest = PlanContest(side="guan", announce="搜書信。", win="搜到了。", lose="沒搜到。", base=1.0, place_win="none", place_lose="none")
    c.itineraries = [Itinerary(who="liubei", stops=[ItineraryStop(id="t_quiet", day=2.0, place="changshe", contest=contest)])]
    s = _season(c)
    s.world.time = _day7(s, c) * 1.5
    plans.tick(s, c, season_length_days(s.world, c) * 86400)
    assert s.world.stops_done["t_quiet"] is True and not s.world.places


def test_the_real_timetable_and_itineraries_name_places_and_kinds_the_loader_knows(c):
    marked = [e.id for e in c.timetable for o in e.outcomes.values() if o.places]
    assert {"changshe_fire", "zhangmancheng_wan", "wancheng"} <= set(marked)
    assert any(st.contest and st.contest.place_win == "fallen" for it in c.itineraries for st in it.stops)


def test_events_can_ask_for_the_look_of_the_place(c):
    s = _season(c)
    cond = Condition(place_state=["war"])
    assert not rules.check_condition(cond, s, c)
    place_state.strike(s.world, c, "changshe")
    assert rules.check_condition(cond, s, c)
    assert not rules.check_condition(Condition(place_state_none=["war"]), s, c)
    assert sum(1 for e in c.events.values() if e.condition.place_state) >= 8  # 每一種樣子都有自己的事件（content/events/places.json）


def test_prices_go_up_and_say_why(c):
    s = _season(c)
    before = territory.price_here(s, c)
    place_state.strike(s.world, c, "changshe")
    assert territory.price_here(s, c) == pytest.approx(before * c.config.plans.price["war"])
    assert "戰火・貴兩成" in territory.price_note(s, c)


def test_the_horse_market_shuts_while_the_place_burns(c):
    town = next(loc.id for loc in c.locations.values() if mounts.MARKET_TAG in (loc.tags or []))
    s = _season(c, location=town)
    assert mounts.market_here(s, c)
    place_state.strike(s.world, c, town)
    assert not mounts.market_here(s, c)


def test_wanderers_keep_away_from_burning_places(c):
    s = _season(c)
    cid = next(cid for cid, ch in c.characters.items() if len(ch.haunts) >= 3 and figure_life.on(c) and not plans.holds(c, cid))
    haunts = c.characters[cid].haunts
    fid = figures.of_character(c, cid)
    here = figure_life.where(s, c, cid)
    others = [loc for loc in haunts if loc != here]
    for loc in others[1:]:
        place_state.strike(s.world, c, loc)
    for seed in range(8):
        figure_life._move(s, c, cid, fid, random.Random(seed))
        assert figure_life.where(s, c, cid) == others[0]
        figure_life._place_at(s, c, cid, fid, here)


def test_the_scene_says_how_the_place_looks(c):
    c.config.auto_open_first_season = True
    game = Game.new(c, "甲", rng=random.Random(0))
    game.state.player.location = "changshe"
    assert game.place_state_view() is None
    place_state.strike(game.state.world, c, "changshe")
    assert game.place_state_view()["kind"] == "war"
    text = game.location_text()
    assert text.startswith("【長社】") and "〔戰火〕" in text.split("\n\n")[1]
    art = game.scene_art()
    assert art is None or (art["mood"] == "war" and art["sub"].endswith("・戰火") and art["head"] == "【長社】危險 " + "★" * c.locations["changshe"].danger)
    assert all(d.kind != deeds.PLACE_KIND for d in deeds.at_place(game.state, c, "changshe"))  # 此地舊事不列變樣那幾筆
