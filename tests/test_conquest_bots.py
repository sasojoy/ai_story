"""領地爭奪第二批 Task 12：假人參加攻城戰（照趕去決戰那一套；設計 4.9；裁決 8、9）。"""
from __future__ import annotations

import json
import random

import pytest

from conquest_kit import announce, conquest_game, go, join
from tianxia import battle_instance, bot_policy, conquest, siege
from tianxia.bot_runner import BotRunner
from tianxia.characters import open_characters
from tianxia.state import BotProfile

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0


def _bot(game, side):
    game.state.player.bot = BotProfile(personality="普通", seed=7, faction=side, season_number=game.world.get_season_number())
    return game


def _open(game, slot):
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()


def test_attacker_bot_heads_to_the_siege_region():
    game = _bot(go(join(conquest_game("season21", name="假黃"), "huang"), "julu_altar"), "huang")  # 人在冀州
    game.now = NOW
    _open(game, announce(game, "nanyang_road", "huang"))  # 南陽的攻城
    assert game.rally_region() == "nanyang"
    before = game.state.player.location
    bot_policy._toward_battle(game)
    assert game.state.player.journey is not None or game.state.player.location != before  # 往南陽走
    guan = _bot(go(join(conquest_game("season21", name="假官", world=game.world), "guan"), "luzhi_camp"), "guan")
    guan.now = NOW
    assert guan.rally_region() is None  # 黃巾攻中立地：官軍站不進守將那一格，不趕去（裁決 8）


def test_bot_runner_sees_the_siege_and_bots_come():
    game = _bot(go(join(conquest_game("season21", name="假黃"), "huang"), "julu_altar"), "huang")
    game.now = NOW
    _open(game, announce(game, "nanyang_road", "huang"))
    runner = BotRunner(game.content, game.world, open_characters(game.world.db.path), random.Random(1), clock=lambda: NOW)
    rows = runner._battle_sides()
    assert len(rows) == 1 and "huang" in rows[0][1] and "guan" not in rows[0][1]


def test_bot_submits_every_siege_round():
    a = _bot(go(join(conquest_game("season21", name="假黃"), "huang"), "nanyang_road"), "huang")
    b = _bot(go(join(conquest_game("season21", name="假官", world=a.world), "guan"), "nanyang_road"), "guan")
    a.now = b.now = NOW
    conquest.set_control(a.state.world, a.content, "nanyang_road", "guan")  # 官軍佔著：兩邊都站得進去
    _open(a, announce(a, "nanyang_road", "huang"))
    b.state.world = b.world.get_season()
    for g in (a, b):
        join_id = next(o.id for o in g.options() if o.id.startswith("battle:join"))
        g.choose(join_id)
    rid = a.world.get_sieges()[0].record_id
    a.world.mutate_siege(rid, lambda x: battle_instance.close_muster(x, siege.template(a.content, "nanyang_road"), random.Random(0), NOW))
    chars = open_characters(a.world.db.path)
    for g in (a, b):
        chars.save(g.state)
    clock = [NOW + 60]
    runner = BotRunner(a.content, a.world, chars, random.Random(1), clock=lambda: clock[0])
    assert runner.battle_on() and runner._battle_owes() == frozenset({"假黃", "假官"})
    report = runner.battle_tick()
    assert report.failed == 0 and report.acted == 2
    battle = a.world.get_sieges()[0]
    assert battle.round_number == 1 or {"假黃", "假官"} <= set(battle.round.pending_actions)  # 兩個都出手了（湊齊就結算）


def test_switch_off_showdown_rally_unchanged():
    """關著：只有時刻表決戰那一格，趕去與「會趕來的陣營」照舊（兩軍加上劇本每一個陣營）。"""
    from conquest_kit import plain_game

    game = _bot(go(join(plain_game("season21", name="假黃"), "huang"), "julu_altar"), "huang")
    game.now = NOW
    definition = game.content.battles["changshe_fire"]
    game.world.start_battle(definition, NOW, 50)
    assert game.rally_region() == definition.region
    runner = BotRunner(game.content, game.world, open_characters(game.world.db.path), random.Random(1), clock=lambda: NOW)
    rows = runner._battle_sides()
    assert rows == [(NOW + definition.muster_seconds, {f.id for f in game.content.scenario.factions}, set())]


def test_no_bot_hint_in_siege_views():
    human = go(join(conquest_game("season21", name="真某"), "huang"), "nanyang_road")
    bot = _bot(go(join(conquest_game("season21", name="假某", world=human.world), "huang"), "nanyang_road"), "huang")
    human.now = bot.now = NOW
    _open(human, announce(human, "nanyang_road", "huang"))
    bot.state.world = bot.world.get_season()
    bot_policy._conquest_vote(bot)  # 假人投票：只公開比例
    human.state.world = human.world.get_season()
    hv, bv = human.conquest_view(), bot.conquest_view()
    assert hv["today"] == bv["today"] and hv["tomorrow"]["rows"] == bv["tomorrow"]["rows"]
    blob = json.dumps(hv, ensure_ascii=False) + human.scene_text()
    assert "假某" not in blob and "假人" not in blob
