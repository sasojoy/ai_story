import random

import pytest

from conftest import FixedRandom
from tianxia.combat import (
    ADVANTAGE, Fighter, auto_battle, battle_round, damage, player_fighter, start_battle,
    style_multiplier,
)
from tianxia.rules import learn_skill


def test_style_cycle():
    assert style_multiplier("柔", "剛") == ADVANTAGE
    assert style_multiplier("剛", "柔") == pytest.approx(1 / ADVANTAGE)
    assert style_multiplier("剛", "剛") == 1.0
    assert style_multiplier("無", "快") == 1.0


def test_player_fighter_uses_equipped_skills(state, content):
    base = player_fighter(state, content)
    assert (base.hp, base.atk, base.dfn, base.spd, base.style) == (105, 10, 10, 10, "無")
    learn_skill(state, content, "fist")  # power 10，第1成：10 * 11 // 20 = 5
    fighter = player_fighter(state, content)
    assert (fighter.atk, fighter.style) == (15, "剛")


def test_damage_minimum_one():
    weak = Fighter("弱", 10, 1, 0, 1, "無")
    tank = Fighter("硬", 10, 1, 100, 1, "無")
    assert damage(weak, tank, random.Random(0)) == 1


def test_auto_battle_strong_beats_weak():
    strong = Fighter("強", 200, 50, 20, 20, "無")
    weak = Fighter("弱", 30, 5, 2, 5, "無")
    assert auto_battle(strong, weak, random.Random(0)) == (True, 1)
    won, _ = auto_battle(weak, strong, random.Random(0))
    assert not won


def test_key_battle_flee(state, content):
    start_battle(state, content, "boss", "duel", 0)
    outcome, _ = battle_round(state, content, "撤退", FixedRandom(0.0))
    assert outcome == "flee" and state.battle is None


def test_key_battle_win_with_huge_strength(state, content):
    state.player.stats["str"] = 300
    start_battle(state, content, "boss", "duel", 0)
    outcome, _ = battle_round(state, content, "強攻", random.Random(0))
    assert outcome == "win" and state.battle is None


def test_key_battle_ultimate_only_once(state, content):
    start_battle(state, content, "boss", "duel", 0)
    outcome, _ = battle_round(state, content, "絕招", random.Random(0))
    assert outcome is None and state.battle.ultimate_used
    with pytest.raises(ValueError):
        battle_round(state, content, "絕招", random.Random(0))


def test_key_battle_lose(state, content):
    start_battle(state, content, "boss", "duel", 0)
    outcome = None
    for _ in range(5):
        outcome, _ = battle_round(state, content, "強攻", random.Random(0))
        if outcome:
            break
    assert outcome == "lose" and state.battle is None


def test_turtling_never_wins_key_battle(state, content):
    for seed in range(20):
        state.battle = None
        start_battle(state, content, "boss", "duel", 0)
        outcome = None
        rng = random.Random(seed)
        while outcome is None:
            outcome, _ = battle_round(state, content, "固守", rng)
        assert outcome != "win"


def test_key_battle_draw_at_round_limit(state, content):
    state.player.stats["con"] = 500
    start_battle(state, content, "boss", "duel", 0)
    outcome = None
    rng = random.Random(0)
    while outcome is None:
        outcome, _ = battle_round(state, content, "固守", rng)
    assert outcome == "draw" and state.battle is None
