"""擂台賽（隨時挑擂；docs/superpowers/specs/2026-10-14-擂台賽-design.md）。Joy 2026-10-14 選「隨時挑擂」：報名的人留下守擂的分身，
別人隨時來挑，對的是分身，照積分排名、只算本季。規則在 tianxia/arena.py，接到 Game 的在 engine.py 的「擂台」那一段。

兩個角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己（server._locked），做完存回去（同 test_raid）。"""
from __future__ import annotations

import random

import pytest

from tianxia import arena, atlas, bot, bot_policy, rules
from tianxia.characters import CharacterStore
from tianxia.engine import ARENA_YIELD, Game
from tianxia.models import MOVES
from tianxia.state import ArenaEntry

NOW = 1000.0


@pytest.fixture
def ring(content, world):
    """甲、乙兩個人都在小鎮（城鎮類），都學了拳腳。"""
    content.config.auto_open_first_season = True
    content.config.arena.enabled = True
    for name in ("甲", "乙"):
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, content, "fist")
        game.state.player.location = "town"
        game.state.player.stamina = 100.0
        game.sync(NOW)
        CharacterStore(world.db).save(game.state)
    return content, world


def _do(content, world, name, act, now=NOW):
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, random.Random(0), world)
    game.client = None
    game.sync(now)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _ids(game):
    return [o.id for o in game.options()]


def _join(content, world, name):
    return _do(content, world, name, lambda g: g.choose("act:arena") + g.choose("arena:join") + g.choose("arena:back"))


def _fight(content, world, name="甲", foe="乙", moves=None, now=NOW):
    """甲挑乙，一路出招打完；回傳最後一下的訊息與甲的 Game。"""
    def go(g):
        msgs = g.choose("act:arena") + g.choose(f"arena:fight:{foe}")
        i = 0
        while g.state.player.arena is not None:
            msgs = g.choose(f"arena:{(moves or MOVES)[i % len(moves or MOVES)]}")
            i += 1
        return msgs
    return _do(content, world, name, go, now)


def test_the_ring_is_in_towns_only_and_opening_it_costs_nothing(ring):
    content, world = ring
    _, game = _do(content, world, "甲", lambda g: [])
    assert "act:arena" in _ids(game)
    msgs = game.choose("act:arena")
    assert msgs[0] == arena.UNRANKED
    assert game.state.player.stamina == 100.0
    assert _ids(game) == ["arena:join", "arena:none", "arena:back"]
    assert atlas.travel_block(game.state, content) is not None  # 擂台邊：先返回
    game.choose("arena:back")
    game.state.player.location = "lake"
    assert "act:arena" not in _ids(game)


def test_joining_leaves_a_snapshot_and_joining_again_only_refreshes_it(ring):
    content, world = ring
    msgs, game = _join(content, world, "甲")
    assert any("留下一份分身" in m for m in msgs)
    entry = arena.entry_of(game.state.world, "甲")
    assert entry.power > 0 and entry.hp_cap > 0 and entry.arts and entry.rating == content.config.arena.start_rating
    entry.rating, entry.wins = 1100.0, 3
    game._save_season()
    msgs, game = _join(content, world, "甲")
    assert any("換了一份守擂的分身" in m for m in msgs)
    entry = arena.entry_of(game.state.world, "甲")
    assert (entry.rating, entry.wins) == (1100.0, 3)  # 積分與戰績照舊


def test_a_fighter_without_arts_cannot_join(ring):
    content, world = ring
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    game.state.player.member.wugong_id = None
    game.state.player.member.neigong_id = None
    assert not next(o for o in game.options() if o.id == "arena:join").enabled
    assert game._arena_join() == [arena.NO_ARTS]


def test_you_must_join_before_you_can_challenge(ring):
    content, world = ring
    _join(content, world, "乙")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    option = next(o for o in game.options() if o.id == "arena:fight:乙")
    assert not option.enabled and arena.JOIN_FIRST in option.label
    _join(content, world, "甲")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    option = next(o for o in game.options() if o.id == "arena:fight:乙")
    assert option.enabled and "積分 1000" in option.label and "體力 -10" in option.label


def test_a_whole_bout_moves_both_ratings_and_spares_the_body(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    before = CharacterStore(world.db).load("甲")
    hp_before, wear_before = before.player.member.neili, before.player.member.injury
    rng_state = random.Random(0).getstate()
    msgs, game = _fight(content, world)
    p = game.state.player
    assert p.arena is None and p.stamina == 90.0
    assert (p.member.neili, p.member.injury) == (hp_before, wear_before)  # 打完不扣回角色
    record = game.state.battles[0]
    assert record.kind == "arena" and record.opponent == "乙的分身" and record.rounds
    w = game.state.world
    mine, theirs = arena.entry_of(w, "甲"), arena.entry_of(w, "乙")
    assert mine.bouts == theirs.bouts == 1
    assert round(mine.rating + theirs.rating) == 2000  # Elo 兩邊加減同一個數
    assert len(theirs.inbox) == 1
    assert game.rng.getstate() == rng_state  # 不碰 Game.rng
    assert any(e.title == "擂台・乙" for e in game.state.journal)
    # 守的人下次同步補一份戰報與一則「守擂・甲」
    _, defender = _do(content, world, "乙", lambda g: [])
    assert defender.state.battles[0].kind == "arena" and defender.state.battles[0].event == "守擂・甲"
    assert any(e.title == "守擂・甲" for e in defender.state.journal)
    assert arena.entry_of(defender.state.world, "乙").inbox == []


def test_yielding_is_a_loss(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")

    def go(g):
        g.choose("act:arena")
        g.choose("arena:fight:乙")
        assert _ids(g) == [f"arena:{m}" for m in MOVES] + [ARENA_YIELD]
        assert atlas.travel_block(g.state, content) is not None
        return g.choose(ARENA_YIELD)
    msgs, game = _do(content, world, "甲", go)
    assert msgs[0] == arena.YIELDED
    assert game.state.battles[0].tier == "落敗"
    w = game.state.world
    assert arena.entry_of(w, "甲").losses == 1 and arena.entry_of(w, "乙").wins == 1
    assert arena.entry_of(w, "甲").rating < 1000 < arena.entry_of(w, "乙").rating


def test_the_pair_cooldown_and_the_daily_protection(ring):
    content, world = ring
    cfg = content.config.arena
    _join(content, world, "乙")
    _join(content, world, "甲")
    _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙") + g.choose(ARENA_YIELD))
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    option = next(o for o in game.options() if o.id == "arena:fight:乙")
    assert not option.enabled and arena.COOLING in option.label
    w = game.state.world
    foe = arena.entry_of(w, "乙")
    assert arena.defended_today(foe, arena.day_of(w)) == 1
    w.arena_pairs.clear()
    foe.defended = [arena.day_of(w), cfg.defend_per_day]
    assert arena.challenge_problem(w, "甲", foe, cfg) == arena.PROTECTED.format(n=cfg.defend_per_day)


def test_elo_math():
    assert arena.expected(1000, 1000) == pytest.approx(0.5)
    me, foe = arena.rated(1000, 1000, 1.0, 32)
    assert (me, foe) == (pytest.approx(1016), pytest.approx(984))
    me, foe = arena.rated(1000, 1400, 1.0, 32)  # 爆冷門：贏得多
    assert me - 1000 > 28


def test_a_gamble_rides_the_boss_duel_box_and_tells_the_model_who_it_faces(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙"))
    assert game.duel_free_text_prompt() == arena.PROMPT
    request = game.duel_text_request("踢沙迷他的眼")
    assert request.boss.startswith("arena:") and request.target.startswith("乙") and request.setting == arena.SETTING
    msgs = game.duel_gamble("踢沙迷他的眼", 5, ("甲一把沙揚過去，竟然奏效。", "沙被風吹回來。"), request=request)
    assert "第 1 回合" in msgs[0]
    fight = game.state.player.arena
    assert fight is None or fight.best_set


def test_a_long_shot_that_lands_makes_the_news(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙"))
    fight = game.state.player.arena
    fight.best_text, fight.best_rate, fight.best_won, fight.best_set = "倒立出拳", 10, True, True
    fame = game.state.player.stats.get("fame", 0)
    game.choose(ARENA_YIELD)
    assert game.state.player.stats.get("fame", 0) == fame + content.config.arena.highlight_fame
    assert any("倒立出拳" in r.text for r in game.state.world.rumors)


def test_an_upset_and_a_streak_make_the_news(ring):
    content, world = ring
    cfg = content.config.arena
    w = world.get_season()
    w.arena["甲"] = ArenaEntry(name="甲", power=10, hp_cap=100, rating=1000, streak=cfg.streak_news - 1)
    w.arena["乙"] = ArenaEntry(name="乙", power=10, hp_cap=100, rating=1400)
    _, game = _do(content, world, "甲", lambda g: [])
    game.state.world.arena.update(w.arena)
    game._save_season()

    def win(g):
        g.choose("act:arena")
        g.choose("arena:fight:乙")
        g.state.player.arena.edge = 95  # 氣勢到頂：提前大勝
        return g.choose(f"arena:{MOVES[0]}")
    _, game = _do(content, world, "甲", win)
    texts = [r.text for r in game.state.world.rumors]
    assert any("擂台爆冷" in t for t in texts)
    assert any(f"連勝 {cfg.streak_news} 場" in t for t in texts)


def test_season_end_ranks_the_top_three_and_pays_them_during_the_break(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙") + g.choose(ARENA_YIELD))
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.admin_end_season(now=NOW + 10)
    assert any("本季擂台前三名" in r.text for r in admin.state.world.chronicle)
    pills = CharacterStore(world.db).load("乙").player.stamina_pills
    _, winner = _do(content, world, "乙", lambda g: [], now=NOW + 20)
    fame, gift = content.config.arena.prizes[0]
    assert winner.state.player.stamina_pills == pills + gift
    assert any("本季擂台第 1 名" in line for e in winner.state.journal for line in e.lines)
    _, again = _do(content, world, "乙", lambda g: [], now=NOW + 30)
    assert again.state.player.stamina_pills == pills + gift  # 只補一次
    assert "act:arena" not in _ids(again)  # 休季沒有擂台


def test_a_bout_left_open_when_the_season_closes_is_void(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙"))
    content.config.admins = ["管理者"]
    Game.new(content, "管理者", rng=random.Random(1), world=world).admin_end_season(now=NOW + 10)
    _, game = _do(content, world, "甲", lambda g: [], now=NOW + 20)
    assert game.state.player.arena is None
    assert any(arena.UNSETTLED in e.lines for e in game.state.journal)


def test_bots_join_then_challenge_and_read_the_tell(ring):
    content, world = ring
    _join(content, world, "乙")
    _, game = _do(content, world, "甲", lambda g: [])
    rng = random.Random(0)
    bot_policy._arena(game, rng)
    assert arena.entry_of(game.state.world, "甲") is not None and not game.state.player.picking_arena
    bot_policy.ARENA_CHANCE, old = 1.0, bot_policy.ARENA_CHANCE
    try:
        bot_policy._arena(game, rng)
    finally:
        bot_policy.ARENA_CHANCE = old
    fight = game.state.player.arena
    assert fight is not None and fight.foe.name == "乙"
    move = bot_policy.duel_move(game, random.Random(0), fight)
    assert move in MOVES


def test_season_bots_never_open_the_ring_or_yield(ring):
    content, world = ring
    _, game = _do(content, world, "甲", lambda g: [])
    assert "act:arena" in _ids(game)
    picks = {bot.pick(game, game.options(), random.Random(i)) for i in range(40)}
    assert "act:arena" not in picks
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙"))
    picks = {bot.pick(game, game.options(), random.Random(i)) for i in range(40)}
    assert ARENA_YIELD not in picks and picks <= {f"arena:{m}" for m in MOVES}
