"""後期體力玩法第一批（Joy 2026-10-16）：設伏劫道、修築工事、屯糧練兵。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import real_content
from tianxia import allied, ambush, encounter, territory, works
from tianxia.characters import CharacterStore
from tianxia.encounter import EncounterResult
from tianxia.engine import Game

HOUR = 3600.0


def _plays_on(c):
    """正式內容把兩個開關寫成關（企劃者 10/16：數字與設計等第 5 塊）；這一份測的是規則本身，自己打開。"""
    c.config.ambush.enabled = c.config.stockpile.enabled = True
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


@pytest.mark.smoke
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


# ── 設伏打開之後（Joy 2026-10-30「直接打開」）：現行規則下照樣走得通 ──


def test_real_content_has_ambush_on_without_switching_it():
    """正式內容自己就開著（7 天、21 天兩種季）；上面那幾條的 _plays_on 只是另外打開屯糧。"""
    for profile in (None, "week7", "season21"):
        assert ambush.on(real_content(profile))


def test_haoqiang_counts_as_the_army_it_helps(real, world):
    """三陣營：敵我照 allied.side_of（同截殺）——豪強分屬兩軍的季，幫哪一軍就算哪一軍；不分屬的季豪強自己一方，兩軍都劫得到。"""
    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    _set(owner)
    for name, ally in (("豪乙", "guan"), ("豪丙", "huang")):
        g = _player(real, world, name, "haoqiang", "changshe")
        g.state.player.ally = ally
        CharacterStore(world.db).save(g.state)
    ambusher = _reload(world, real, "黃甲").state
    split = allied.on(real, ambusher.world)
    helps_guan, helps_huang = _reload(world, real, "豪乙"), _reload(world, real, "豪丙")
    assert ambush.hostile(ambusher, helps_guan.state, real)
    assert ambush.hostile(ambusher, helps_huang.state, real) is (not split)
    with _fight("大勝"):
        helps_guan.travel("huangjin_camp", "dash")
    assert helps_guan.state.battles[-1].kind == "ambush"


def test_the_newbie_window_is_48_real_hours(real, world):
    """新手期照現實時間（Config.newbie_real_hours 48）：加入不到 48 小時沒有設伏鈕、硬按也被擋；過了才有。"""
    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    p = owner.state.player
    hours = real.config.newbie_real_hours
    assert hours == 48
    p.joined_at = owner.state.world.time - (hours - 1) * HOUR * real.config.time_scale
    assert not any(o.id.startswith("ambush:") for o in owner.options())
    assert ambush.set_problem(owner.state, real, "changshe") == ambush.NEWBIE
    p.joined_at = owner.state.world.time - (hours + 1) * HOUR * real.config.time_scale
    assert "ambush:set:changshe" in {o.id for o in owner.options() if o.enabled}


def test_both_sides_get_a_report_and_an_annals_line(real, world):
    """戰報（kind ambush）與行狀（交手那一類，留對手的名號）兩邊都記。"""
    from tianxia import annals

    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    _player(real, world, "官乙", "guan", "changshe")
    _set(owner)
    passer = _reload(world, real, "官乙")
    with _fight("落敗"):
        passer.travel("huangjin_camp", "dash")
    back = _reload(world, real, "黃甲")
    for g, rival in ((passer, "黃甲"), (back, "官乙")):
        assert g.state.battles[-1].kind == "ambush"
        assert any(e.kind == annals.FIGHT and rival in e.text for e in g.state.player.annals), g.state.player.name


def test_a_server_bot_sets_ambushes_and_walks_into_them_like_anyone(real, world):
    """假人：體力多時有機會從選單按設伏（bot_policy._stamina_play，跟真人同一顆鈕）；假人路過敵方埋伏一樣中伏、戰報一樣。"""
    from tianxia import bot_policy
    from tianxia.state import BotProfile

    owner = _player(real, world, "黃甲", "huang", "huangjin_camp")
    owner.state.player.bot = BotProfile(personality="普通", seed=1)
    owner.state.player.stamina = real.config.stamina_max

    class Low(random.Random):
        def random(self):
            return 0.0

        def choice(self, seq):
            assert "ambush:set:changshe" in seq, seq
            return "ambush:set:changshe"
    bot_policy._stamina_play(owner, Low())
    assert owner.state.player.ambush is not None
    CharacterStore(world.db).save(owner.state)
    passer = _player(real, world, "官乙", "guan", "changshe")
    passer.state.player.bot = BotProfile(personality="普通", seed=2)
    CharacterStore(world.db).save(passer.state)
    passer = _reload(world, real, "官乙")
    with _fight("大勝"):
        passer.travel("huangjin_camp", "dash")
    assert passer.state.battles[-1].kind == "ambush"


def test_the_howto_page_explains_ambush_with_the_config_numbers(real):
    """玩法說明的「行動」那一段多一行設伏（開著才寫），數字讀設定。"""
    from tianxia import howto

    cfg = real.config.ambush
    line = howto.ambush_lines(real)[0]
    assert "**設伏**" in line and f"體力 {cfg.stamina}" in line and f"{cfg.hours:g} 小時" in line and f"最多 {cfg.silver_cap} 兩" in line
    cfg.enabled = False
    assert howto.ambush_lines(real) == []
