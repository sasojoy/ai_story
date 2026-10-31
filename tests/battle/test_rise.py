"""江湖水漲（企劃者 2026-10-14「玩家變強後好像也沒有更高的挑戰，10 幾級都能把所有歷史武將跟所有事件打敗，根本不會輸」；
tianxia/rise.py，數字在 Config.rise）：大場面照全隊威力浮上來、越打越難；頭目照本人的武學威力；事件檢定隨等級加深。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import real_content
from tianxia import duel, encounter, figures, rise, rules, team
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Check


@pytest.fixture
def real():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.terrain_arts.enabled = False  # 這裡拿 power_vs 當浮難度的基準；地利浮不浮在 test_terrain_arts（武學隨地理環境）
    return c


def _player(content, store, *, mates=(), name="官甲", at="huangjin_camp") -> Game:
    game = Game.new(content, name, rng=random.Random(0), world=store)
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", at
    p.tutorial_step = len(content.tutorial.steps)
    p.visited.add(at)
    game.now = 1000.0
    for cid in mates:
        store.try_recruit(cid, p.name)
        ch = content.characters[cid]

        def seed(progress, ch=ch):
            progress.wugong_id, progress.neigong_id = ch.starting_wugong, ch.starting_neigong

        store.update_companion(cid, seed)
        p.team.append(cid)
    return game


# ── 純數字 ──

def test_the_scale_climbs_with_each_win_and_stops_at_the_cap(real):
    rule = real.config.rise
    assert rise.scale(real) == rule.big_scale
    assert rise.scale(real, 2) == pytest.approx(rule.big_scale + 2 * rule.per_win)
    assert rise.scale(real, 99) == rule.max_scale
    assert rise.big(real, 150, 100) == 150  # 沒那麼強：照內容寫的
    assert rise.big(real, 150, 400) == pytest.approx(400 * rule.big_scale)
    real.config.rise.enabled = False
    assert rise.big(real, 150, 400) == 150


def test_a_strong_team_meets_a_figure_at_its_own_height(real, world):
    game = _player(real, world, mates=("guanyu", "zhangfei"))
    s = game.state
    base = figures.squad_of(s, real, "bocai")
    power = team.power_vs(s, real, game.world, base, fresh=True)
    assert power * real.config.rise.big_scale > base.difficulty  # 兩位同伴第一級就壓過波才
    first = game._figure_squad("bocai")
    assert first.difficulty == pytest.approx(power * real.config.rise.big_scale, abs=0.1)
    assert game.challenge_odds("bocai") in ("穩勝", "有把握")
    s.player.figure_wins["bocai"] = 3
    assert game._figure_squad("bocai").difficulty > first.difficulty
    assert game.challenge_odds("bocai") in ("凶險", "必敗", "五五波", "難分勝負")


def test_a_weak_challenger_still_meets_the_written_difficulty(real, world):
    game = _player(real, world)
    assert game._figure_squad("bocai").difficulty == figures.difficulty(game.state, real, "bocai")


def test_wounds_still_hurt_against_a_risen_figure(real, world):
    game = _player(real, world, mates=("guanyu", "zhangfei"))
    fresh = game._figure_squad("bocai").difficulty
    game.state.player.member.neili = 1.0  # 帶傷：難度不跟著降
    assert game._figure_squad("bocai").difficulty == fresh


@pytest.mark.smoke
def test_the_reward_follows_the_prestige_not_the_risen_difficulty(real, world):
    game = _player(real, world, mates=("guanyu", "zhangfei"))
    game.state.player.stamina = 200.0
    base = figures.squad_of(game.state, real, "bocai")
    risen = game._figure_squad("bocai")
    assert risen.difficulty > base.difficulty
    seen = {}

    def fight(state, content, world, squad_id, rng, **kw):
        seen["difficulty"] = kw.get("difficulty")
        return EncounterResult(tier="大勝", margin=50, our_power=400, difficulty=kw.get("difficulty") or 0)

    with mock.patch.object(team, "fight", side_effect=fight):
        before = game.state.player.stats.get("xinde", 0)
        game.choose("act:challenge:bocai")
    assert seen["difficulty"] == risen.difficulty
    assert game.state.player.figure_wins["bocai"] == 1
    gained = game.state.player.stats.get("xinde", 0) - before
    assert gained <= base.reward_xinde * 1.3 + 5  # 寶物、乘勝之類的加成之外，不照浮上去的難度多給


def test_a_big_story_fight_rises_and_a_small_one_does_not(real, world):
    game = _player(real, world, mates=("guanyu", "zhangfei"))
    big, small = real.squads["shoumu"], real.squads["toumu"]
    assert game.is_big(big) and not game.is_big(small)
    assert game._story_squad(big).difficulty > big.difficulty
    assert game._story_squad(small).difficulty == small.difficulty


# ── 頭目戰 ──

def test_a_boss_snapshots_a_difficulty_at_your_height(real, world):
    game = _player(real, world)
    boss = max(real.duels.values(), key=lambda b: b.difficulty)
    with mock.patch.object(Game, "_battle_power", return_value=boss.difficulty * 3):
        game._duel_start(boss)
        first = game.state.player.duel.difficulty
        assert first == pytest.approx(boss.difficulty * 3 * real.config.rise.duel_scale)
        assert duel.foe_strength(real.config.battle, real.config.duel, boss, first) > duel.foe_strength(
            real.config.battle, real.config.duel, boss)
        game.state.player.duel = None
        game._duel_start(boss)
        assert game.state.player.duel.difficulty > first  # 這一季第二次遇上再難一截


def test_an_old_duel_without_a_snapshot_uses_the_written_difficulty(real, world):
    game = _player(real, world)
    boss = next(iter(real.duels.values()))
    game._duel_start(boss)
    game.state.player.duel.difficulty = None
    assert duel.foe_difficulty(game.state.player.duel, boss) == boss.difficulty


# ── 事件檢定 ──

def test_checks_deepen_with_level_up_to_the_cap(real, world):
    game = _player(real, world)
    rule = real.config.rise
    check = Check(stat="str", difficulty=5)
    p = game.state.player
    p.member.level = rule.event_from_level - 1
    low = rules.check_outlook(check, game.state, real, game.world)
    p.member.level = rule.event_from_level
    assert rules.check_outlook(check, game.state, real, game.world).gap == low.gap - 1
    p.member.level = rule.event_from_level + rule.event_per_levels * 50
    assert rules.check_outlook(check, game.state, real, game.world).gap == low.gap - rule.event_cap
    real.config.rise.enabled = False
    assert rules.check_outlook(check, game.state, real, game.world).gap == low.gap


def test_the_measurement_math_matches_the_engine(real):
    rng = random.Random(1)
    wins = sum(encounter.resolve_encounter(133, 100, rng).tier in ("大勝", "險勝") for _ in range(4000)) / 4000
    assert 0.7 < wins < 0.9  # 倍數 0.75 → 威力是難度的 1.33 倍，贏面約八成（Config.rise 的註解）
