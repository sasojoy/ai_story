"""天下聞名的人守擂，排在他後面 famous_reach 名內的人都挑得到他（名聲設計 4.7）。"""
import random

from conftest import real_content, renown_unscaled

from tianxia import arena
from tianxia.engine import Game
from tianxia.state import ArenaEntry, WorldState


def _ladder(n):
    w = WorldState(storyline="x")
    for i in range(1, n + 1):
        w.arena[f"p{i}"] = ArenaEntry(name=f"p{i}", power=1, hp_cap=1, rank=i)
    return w


def test_famous_reach_lets_five_below_challenge():
    c = renown_unscaled(real_content("week7"))
    w = _ladder(8)
    me = "p6"
    assert arena.challenge_problem(w, me, w.arena["p1"], c.config.arena, 10) is not None
    w.arena["p1"].famed = True
    assert arena.challenge_problem(w, me, w.arena["p1"], c.config.arena, 10) is None
    assert [e.name for e, _ in arena.challengers(w, c, me, 10)][0] == "p1"
    assert arena.challenge_problem(_ladder(8), "p7", w.arena["p1"], c.config.arena, 10) is not None  # 六名外照樣挑不到


def test_the_flag_follows_the_fame_tier_and_the_switch():
    c = renown_unscaled(real_content("week7"))
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    g.state.player.stats["fame"] = 90
    g._arena_join()
    entry = arena.entry_of(g.state.world, "甲")
    assert entry is not None and entry.famed
    g.state.player.stats["fame"] = 89
    g._deliver_arena()
    assert not entry.famed
    c.config.renown.arena_reach = False
    g.state.player.stats["fame"] = 90
    g._deliver_arena()
    assert not entry.famed


def test_the_arena_page_says_why_a_far_name_is_in_reach():
    c = renown_unscaled(real_content("week7"))
    c.config.auto_open_first_season = True
    g = Game.new(c, "p6", rng=random.Random(0))
    g.client = None
    w = g.state.world
    for i in (1, 2, 3, 4, 5):
        w.arena[f"p{i}"] = ArenaEntry(name=f"p{i}", power=1, hp_cap=1, rank=i, famed=i == 1)
    g.state.player.picking_arena = True
    g._arena_join()
    view = g.shop_view()
    rows = {f["name"]: f["famed"] for f in view["foes"]}
    assert rows == {"p1": "天下聞名：排在他後面 5 名內的人都挑得到他", "p3": "", "p4": "", "p5": ""}
