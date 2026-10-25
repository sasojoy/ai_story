"""後期體力玩法第一批（Joy 2026-10-16）：設伏劫道、修築工事、屯糧練兵。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import real_content
from tianxia import ambush, encounter, territory, works
from tianxia.characters import CharacterStore
from tianxia.encounter import EncounterResult
from tianxia.engine import Game

HOUR = 3600.0


def _plays_on(c):
    """正式內容把三個開關寫成關（企劃者 10/16：數字與設計等第 5 塊）；這一份測的是規則本身，自己打開。"""
    c.config.ambush.enabled = c.config.fortify.enabled = c.config.stockpile.enabled = True
    return c


@pytest.fixture
def real():
    c = _plays_on(real_content())
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.road_sight_chance = 0.0
    return c


def _player(content, store, name, faction, at) -> Game:
    game = Game.new(content, name, rng=random.Random(0), world=store)
    p = game.state.player
    p.faction, p.location = faction, at
    p.tutorial_step = len(content.tutorial.steps)
    p.visited.add(at)
    p.joined_at = -1e9  # 過了新手期
    p.stamina = 250
    p.stats["silver"] = 100
    game.now = 1000.0
    game._save_season()
    CharacterStore(store.db).save(game.state)
    return game


def _reload(store, content, name) -> Game:
    state = CharacterStore(store.db).load(name)
    game = Game(content, state, random.Random(0), store)
    game.state.world = store.get_season()
    return game


def _fight(tier):
    """伏兵那一邊看的結果（resolve_encounter 從伏兵算）。"""
    return mock.patch.object(encounter, "resolve_encounter",
                             return_value=EncounterResult(tier=tier, margin=50 if tier == "大勝" else -80, our_power=200, difficulty=120))


def _set(owner: Game, to="changshe"):
    msgs = owner.choose(f"ambush:set:{to}")
    assert owner.state.player.ambush is not None, msgs
    CharacterStore(owner.world.db).save(owner.state)
    return msgs


def test_only_roads_without_a_town_at_either_end(real):
    segs = {ambush.key(a, b) for a, loc in real.locations.items() for b in loc.connections if ambush.road_ok(real, a, b)}
    assert "changshe|huangjin_camp" in segs
    for seg in segs:
        for loc_id in seg.split("|"):
            assert real.config.explore_mix_of(real.locations[loc_id].tags).kind != "town"


def test_setting_an_ambush_costs_stamina_and_pins_you_in_place(real, world):
    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    ids = {o.id for o in owner.options() if o.enabled}
    assert "ambush:set:changshe" in ids
    _set(owner)
    p = owner.state.player
    assert p.stamina == 250 - real.config.ambush.stamina
    ids = {o.id: o for o in owner.options()}
    assert "ambush:lift" in ids and not any(i.startswith("ambush:set:") for i in ids)
    assert not ids["move:changshe"].enabled
    assert owner.travel_refusal("changshe") is not None
    owner.choose("ambush:lift")
    assert owner.state.player.ambush is None and ids  # 收了就能走
    assert {o.id: o for o in owner.options()}["move:changshe"].enabled


def test_a_ranger_without_a_wanted_poster_gets_no_ambush_button(real, world):
    ranger = _player(real, world, "散甲", None, "huangjin_camp")
    assert not any(o.id.startswith("ambush:") for o in ranger.options())


def test_walking_into_an_enemy_ambush_and_losing(real, world):
    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    passer = _player(real, world, "官乙", "guan", "changshe")
    passer.state.player.materials = {next(m.id for m in real.materials.values() if m.tier == 1): 3}
    CharacterStore(world.db).save(passer.state)
    _set(owner)
    passer = _reload(world, real, "官乙")
    with _fight("大勝"):
        passer.travel("huangjin_camp", "dash")  # 疾行也會中伏
    lp = passer.state.player
    assert lp.location == "huangjin_camp"
    assert lp.stats["silver"] == 90  # 一成
    assert sum(lp.materials.values()) == 1  # 被搶走兩個
    rec = passer.state.battles[-1]
    assert rec.kind == "ambush" and rec.tier == "落敗"
    back = _reload(world, real, "黃甲")
    assert back.state.player.stats["silver"] == 110
    assert sum(back.state.player.materials.values()) == 2
    assert back.state.battles[-1].kind == "ambush"
    assert back.state.player.ambush is not None  # 伏兵贏了照守
    assert world.get_season().ambushes[ambush.key("huangjin_camp", "changshe")][0].caught == 1


def test_the_ambusher_losing_pays_with_his_own_goods_and_the_ambush_breaks(real, world):
    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    _player(real, world, "官乙", "guan", "changshe")
    _set(owner)
    passer = _reload(world, real, "官乙")
    with _fight("落敗"):
        passer.travel("huangjin_camp", "dash")
    assert passer.state.player.stats["silver"] == 110
    back = _reload(world, real, "黃甲")
    assert back.state.player.stats["silver"] == 90
    assert back.state.player.ambush is None
    assert any(ambush.BROKEN.format(rival="官乙", to="長社") in line for e in back.state.journal for line in e.lines) or \
        back.state.journal[-1].title.startswith("設伏")
    assert ambush.active(world.get_season(), ambush.key("huangjin_camp", "changshe"), world.get_season().time) is None


def test_friends_newbies_and_the_cooldown_walk_through(real, world):
    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    _player(real, world, "黃丙", "huang", "changshe")
    newbie = _player(real, world, "官丁", "guan", "changshe")
    newbie.state.player.joined_at = None
    CharacterStore(world.db).save(newbie.state)
    _set(owner)
    for name in ("黃丙", "官丁"):
        g = _reload(world, real, name)
        if name == "官丁":
            g.state.player.joined_at = g.state.world.time
        g.travel("huangjin_camp", "dash")
        assert not any(r.kind == "ambush" for r in g.state.battles), name


def test_a_walker_caught_offline_is_judged_at_the_time_he_passed(real, world):
    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    _player(real, world, "官乙", "guan", "changshe")
    _set(owner)
    passer = _reload(world, real, "官乙")
    passer.travel("huangjin_camp")  # 步行，在路上
    arrive = passer.state.player.journey.arrive_at[-1]
    CharacterStore(world.db).save(passer.state)
    # 伏兵收了埋伏（在路過的人抵達之後才收），路過的人很久以後才回來補算
    owner = _reload(world, real, "黃甲")
    owner.state.world.time = arrive + 60
    owner.choose("ambush:lift")
    passer = _reload(world, real, "官乙")
    passer.state.world.time = arrive + 2 * HOUR
    with _fight("大勝"):
        passer._arrivals()
    assert passer.state.battles and passer.state.battles[-1].kind == "ambush"


def test_ambush_expires_on_sync(real, world):
    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    _set(owner)
    owner.state.world.time += real.config.ambush.hours * HOUR + 1
    owner._ambush_expire()
    assert owner.state.player.ambush is None


def test_prune_keeps_records_for_late_walkers_then_drops_them(real, world):
    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    _set(owner)
    w = owner.state.world
    seg = ambush.key("huangjin_camp", "changshe")
    w.time += (real.config.ambush.hours + real.config.ambush.keep_hours - 1) * HOUR
    ambush.prune(w, real)
    assert seg in w.ambushes
    w.time += 2 * HOUR
    ambush.prune(w, real)
    assert seg not in w.ambushes


# ── 修築工事 ──


def _fort_world(real, world, line_value):
    game = _player(real, world, "官甲", "guan", "changshe")
    w = game.state.world
    territory.update(w, real)
    return game, w


def test_tug_holds_longer_with_a_fort():
    assert territory._tug("guan", 56, 50, "guan", "huang", 5) == "huang"
    assert territory._tug("guan", 56, 50, "guan", "huang", 5, extra=10) == "guan"
    assert territory._tug("guan", 66, 50, "guan", "huang", 5, extra=10) == "huang"
    assert territory._tug("huang", 44, 50, "guan", "huang", 5, extra=10) == "huang"  # 黃巾守著：官軍那頭的門檻也照推
    assert territory._tug(None, 56, 50, "guan", "huang", 5, extra=10) == "huang"


def test_fortify_on_your_own_spot_and_decay(real, world):
    game = _player(real, world, "官甲", "guan", "changshe")
    w = game.state.world
    territory.update(w, real)
    spots = [loc for spots in real.scenario.territory.lines.values() for loc in spots]
    mine = next(loc for loc in spots if w.territory.control.get(loc) == "guan" and w.territory.tug.get(loc) == "guan")
    game.state.player.location = mine
    assert "works:fortify" in {o.id for o in game.options() if o.enabled}
    game.choose("works:fortify")
    assert works.fort_now(game.state, real) == real.config.fortify.per_press
    assert game.state.player.stamina == 250 - real.config.fortify.stamina
    w = game.state.world
    w.time += 1.25 * HOUR
    assert territory.fort_level(w, real, mine) == pytest.approx(real.config.fortify.per_press - 1.25 * real.config.fortify.decay_per_hour)


def test_no_fortify_on_the_enemys_spot(real, world):
    game = _player(real, world, "黃甲", "huang", "changshe")
    territory.update(game.state.world, real)
    assert not works.fort_spot(game.state, real, "huang")


# ── 屯糧練兵 ──


def test_lean_formula():
    c = real_content("week7")
    d = next(b for b in c.battles.values() if b.timetable_event)
    f0, f1 = d.factions[0].id, d.factions[1].id
    assert works.lean({}, d, c) == 0
    assert works.lean({f0: 20, f1: 0}, d, c) == 3
    assert works.lean({f0: 0, f1: 1000}, d, c) == -6
    assert works.lean({f0: 30, f1: 30}, d, c) == 0


def test_stockpile_shifts_the_next_timetable_battle(world):
    from tianxia import world as world_mod

    c = _plays_on(real_content("week7"))
    c.config.auto_open_first_season = True
    world.open_season(c, 0.0)
    d = next(b for b in c.battles.values() if b.timetable_event)
    f0 = d.factions[0].id
    world.mutate_season(lambda s: s.supply.update({f0: 20}))
    msgs = world_mod._open_claimed(world, c, 0.0, lambda vehicle: (d, 50))
    b = world.get_battle()
    assert b.trend_start == 53 and b.supply_lean == {f0: 20, d.factions[1].id: 0}
    assert any("屯了" in m for m in msgs)
    assert world.get_season().supply == {}


def test_stockpile_button_only_for_the_two_armies_in_season_one(world):
    c = _plays_on(real_content("week7"))
    c.config.auto_open_first_season = True
    g = _player(c, world, "官甲", "guan", "changshe")
    assert "works:stockpile" in {o.id for o in g.options() if o.enabled}
    g.choose("works:stockpile")
    assert g.state.world.supply == {"guan": 1}
    ranger = _player(c, world, "散甲", None, "changshe")
    assert "works:stockpile" not in {o.id for o in ranger.options()}
