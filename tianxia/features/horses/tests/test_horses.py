"""馬的來路（Joy 2026-11-10 選擇卡選「奪馬＋馴野馬＋論功賜馬」）：打贏騎馬的那幾路奪良駒、北方野馬群連三步馴馬、決戰論功前三賜馬。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia.core.battle_base import BattleInstance, BattleParticipant
from tianxia.engine import Game
from tianxia.features.horses import actions, bots, rules

NOW = 1_000_000.0


def _content(**kw):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    c.config.horses.enabled = True
    for k, v in kw.items():
        setattr(c.config.horses, k, v)
    return c


def _game(c, name="馬客", loc="juma_river"):
    g = Game.new(c, name, rng=random.Random(0))
    g.sync(NOW)
    p = g.state.player
    p.location, p.journey, p.busy_until = loc, None, None
    p.stamina = 200
    p.materials["gang_1"] = 10
    return g


def _horses(g):
    p = g.state.player
    return [i for i in [p.mount, *p.rack] if i is not None and i.slot == "mount"]


@pytest.mark.smoke
def test_three_steps_at_a_pasture_tame_a_horse():
    c = _content(tame_chance=1.0, wild_steed_chance=0.0)
    g = _game(c)
    opt = next(o for o in g.options() if o.id == "horses:tame")
    assert opt.enabled and "第 1／3 步" in opt.label and "體力 20" in opt.label
    for step in (1, 2, 3):
        g.choose("horses:tame")
        if step < 3:
            assert g.state.player.horses_tame == step
    p = g.state.player
    assert p.horses_tame == 0 and p.horses_tamed == 1 and p.stamina == 140 and p.materials.get("gang_1") == 7
    got = _horses(g)
    assert len(got) == 1 and got[0].tier == 2 and got[0].name.endswith("駒")
    again = next(o for o in g.options() if o.id == "horses:tame")
    assert not again.enabled and rules.TAME_CAPPED in again.label


def test_a_failed_last_step_lets_the_horse_run_and_leaving_starts_over():
    c = _content(tame_chance=0.0)
    g = _game(c)
    for _ in range(3):
        g.choose("horses:tame")
    assert g.state.player.horses_tamed == 0 and not _horses(g) and g.state.player.horses_tame == 0
    g.choose("horses:tame")
    assert actions.step_now(g) == 2
    g.state.player.location = "yanshan_foot"
    assert actions.step_now(g) == 1  # 走開了就從頭來


def test_the_herd_is_shared_and_runs_out_for_the_week():
    c = _content(tame_chance=1.0, herd_per_week=1, wild_steed_chance=0.0)
    a = _game(c, "甲")
    for _ in range(3):
        a.choose("horses:tame")
    b = Game(c, a.state.model_copy(deep=True), random.Random(0), a.world)
    b.state.player.name = "乙"
    b.state.player.horses_tamed = 0
    b.state.world = a.world.get_season()
    opt = actions.options(b)[0]
    assert not opt.enabled and rules.TAME_GONE in opt.label


def test_a_wild_steed_is_capped_server_wide_and_makes_news():
    c = _content(tame_chance=1.0, wild_steed_chance=1.0, wild_steed_cap=1)
    g = _game(c)
    for _ in range(3):
        g.choose("horses:tame")
    assert _horses(g)[0].tier == 3 and g.state.world.horses_steeds == 1
    assert any("名駒" in r.text for r in g.state.world.rumors)


def test_no_pasture_no_option_and_off_is_silent():
    c = _content()
    g = _game(c, loc="wan_city")
    assert not any(o.id.startswith("horses:") for o in g.options())
    c.config.horses.enabled = False
    g = _game(c)
    assert not any(o.id.startswith("horses:") for o in g.options())
    assert actions.win(g, "juma_river", "nz_huqi") == []


def test_beating_a_mounted_squad_can_seize_a_horse_up_to_the_cap():
    c = _content(seize_squads={"nz_huqi": 1.0}, seize_cap=2)
    g = _game(c)
    assert actions.win(g, "juma_river", "dipi") == []  # 不在名單上的那一路沒有馬
    for _ in range(3):
        actions.win(g, "juma_river", "nz_huqi")
    assert g.state.player.horses_seized == 2
    assert [h.tier for h in _horses(g)] == [2, 2]


def _battle(me_merit_acts: list[tuple[str, int]], won="guan"):
    b = BattleInstance(battle_id="x", outcome_side=won, record_id=7)
    for name, acted in me_merit_acts:
        b.participants[name] = BattleParticipant(name=name, faction="guan", acted_rounds=acted, neili=0, neili_cap=0)
    return b


def test_merit_ranking_gives_a_steed_to_first_and_a_horse_to_the_next_two():
    c = _content()
    g = _game(c, "丙")
    battle = _battle([("甲", 9), ("乙", 8), ("丙", 7), ("丁", 6)])
    lines: list[str] = []
    assert actions.merit_rank(battle, c.config.battle, battle.participants["丙"]) == 3
    gain = actions.showdown_pay(g, battle, battle.participants["丙"], lines)
    assert gain and gain[0].startswith("賜馬【") and any("戰功排第 3" in x for x in lines)
    assert _horses(g)[0].tier == 2 and _horses(g)[0].quality == "上品"
    first = _game(c, "甲")
    actions.showdown_pay(first, battle, battle.participants["甲"], [])
    assert _horses(first)[0].tier == 3
    fourth = _game(c, "丁")
    assert actions.showdown_pay(fourth, battle, battle.participants["丁"], []) == []
    lost = _battle([("丙", 9)], won="huang")
    assert actions.showdown_pay(_game(c, "戊"), lost, lost.participants["丙"], []) == []


def test_bots_tame_only_without_a_good_horse():
    c = _content()
    g = _game(c)
    opt = actions.options(g)[0]
    s = bots.score(g, opt)
    assert s in (None, bots.TAME_SCORE)
