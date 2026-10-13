"""決戰的節奏（Joy 2026-10-13 試玩：「大決戰的倒數秒數包含送出行動，十秒才跳一次，全部人都送出也還在跳最遲1分x秒後結算」
「機器人是不是都不會第一時間選擇行動，這樣很拖時間」）：「已送出／在場」跟結算等的是同一批人、在場的假人第一時間出招。
（豪強那一欄戰功跟著第三方一起拿掉：豪強臨時投效兩軍之一，戰功記在投效的那一軍。）"""
import random

import pytest
from test_battle_instance import three  # noqa: F401（fixture）
from test_bot_runner import _install, _tick_cleanly, clock, runner, world  # noqa: F401（fixture）

import server
import webharness
from tianxia import battle_instance as bi
from tianxia import bot_policy, server_bots
from tianxia.characters import open_characters
from tianxia.models import BattleTuning

node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _fight(definition, people):
    battle = bi.start_muster(definition, now=0)
    for name, side in people:
        bi.join_faction(battle, name, side, neili_cap=1000)
    bi.close_muster(battle, definition, random.Random(0), now=0)
    return battle


def test_the_count_waits_for_the_same_people_the_round_does(three):
    """「已送出／在場」跟回合結算等的是同一批人：還有人沒出手，數字看得出來在等誰。"""
    battle = _fight(three, [("甲", "guan"), ("乙", "huang"), ("丙", "huang")])
    bi.submit_action(battle, "甲", "guan_hold")
    bi.submit_action(battle, "乙", "huang_hold")
    assert not bi.round_is_complete(battle)
    assert bi.round_progress(battle, three) == (2, 3)
    bi.submit_action(battle, "丙", "huang_hold")
    assert bi.round_is_complete(battle) and bi.round_progress(battle, three) == (3, 3)


def test_the_merit_board_has_only_the_two_armies(three):
    """豪強不再是第三方（Joy 2026-10-13）：戰局條的戰功只有兩軍兩欄。"""
    battle = _fight(three, [("甲", "guan"), ("乙", "huang")])
    battle.participants["乙"].acted_rounds = 2
    g = bi.gauge(battle, three, "guan", timetable=False, tuning=BattleTuning(), viewer="甲")
    assert "third" not in g and set(g["merit"]) == {"me", "left", "right"}
    assert g["merit"]["right"] == [{"name": "乙", "merit": 4, "mine": False}]


# ── 假人第一時間出招 ─────────────────────────────


def _seated(runner, world, content, clock, monkeypatch):
    """兩個假人（一邊一個）加一個真人「真人甲」站官軍，開打第一回合。"""
    monkeypatch.setattr(bot_policy, "take_turn", lambda game, profile, rng, slot=None: None)
    content.config.bots_min_per_faction = 1
    _tick_cleanly(runner)  # 補兩個假人
    characters = open_characters()
    bots = []
    for state in characters.all(bots_only=True):
        state.player.faction = state.player.bot.faction
        characters.save(state)
        bots.append((state.player.name, state.player.faction))
    definition = content.battles["t1"]
    world.start_battle(definition, clock[0])

    def seat(battle):
        for name, side in bots + [("真人甲", "guan")]:
            bi.join_faction(battle, name, side, neili_cap=1000)
        bi.close_muster(battle, definition, random.Random(0), now=clock[0])

    world.mutate_battle(seat)
    return [name for name, _ in bots]


def test_bots_wait_a_few_seconds_then_act_without_the_slow_tick(runner, world, content, clock, monkeypatch):
    bots = _seated(runner, world, content, clock, monkeypatch)
    assert runner.battle_on()
    clock[0] += 1
    assert runner.battle_tick().acted == 0  # 回合才開一秒：假人跟真人一樣先看一下
    clock[0] += 12
    report = runner.battle_tick()
    assert report.failed == 0 and report.acted == 2
    assert set(bots) <= set(world.get_battle().round.pending_actions)


def test_bots_act_at_once_when_every_human_has_sent(runner, world, content, clock, monkeypatch):
    bots = _seated(runner, world, content, clock, monkeypatch)
    world.mutate_battle(lambda b: bi.submit_action(b, "真人甲", "guan_hold"))
    clock[0] += 1
    report = runner.battle_tick()
    assert report.failed == 0 and report.acted == 2
    battle = world.get_battle()
    assert battle.round_number == 1  # 最後一個假人出手就結算了，不等逾時
    assert all(n not in battle.round.pending_actions for n in bots)


def test_no_battle_no_fast_tick(runner, world, content, clock, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    assert not runner.battle_on() and runner.battle_tick().acted == 0
