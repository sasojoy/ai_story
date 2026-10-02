import random
import time

import pytest

import run_bots
from tianxia import bot_runner, server_bots
from tianxia.bot_runner import BotRunner
from tianxia.engine import Game
from tianxia.models import (
    BattleAct, BattleActionEffect, BattleAdvanceWhen, BattleDef, BattleFaction, BattleOption, BattleOutcome,
    FactionDef,
)
from tianxia.save import load_game, path_for, save_game
from tianxia.state import BotProfile
from tianxia.world_state import WorldStateStore

START = 1_791_198_000.0  # 2026-10-05 19:00 台灣時間


def _install(content):
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"], goals={"kou": -1}),
        FactionDef(id="huang", name="黃巾", join_at=["lake"], goals={"kou": 1}),
    ]
    definition = BattleDef(
        id="t1", name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[
            BattleAct(
                id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                options=[BattleOption(text="穩紮穩打", tag="safe"), BattleOption(text="全力進攻", tag="aggressive")],
                advance_when=BattleAdvanceWhen(trend_min=90),
            ),
        ],
        action_tags={
            "safe": BattleActionEffect(trend_delta=1, neili_damage=5),
            "aggressive": BattleActionEffect(trend_delta=5, neili_damage=20),
        },
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。")],
        muster_seconds=600, round_seconds=120,
    )
    content.battles[definition.id] = definition
    content.scenario.thresholds[0].starts_battle = definition.id  # kou50


@pytest.fixture
def clock():
    return [START]


@pytest.fixture
def world(content):
    store = WorldStateStore()
    store.seed_first_season(content)  # 測試內容會直接開季
    return store


@pytest.fixture
def runner(content, world, tmp_path, clock):
    _install(content)
    return BotRunner(content, world, tmp_path / "saves", random.Random(1), clock=lambda: clock[0])


def _bots(tmp_path):
    states = [load_game(p) for p in sorted((tmp_path / "saves").glob("*.json"))]
    return [s for s in states if s.player.bot is not None]


def test_fill_adds_one_bot_per_faction_per_interval_up_to_the_minimum(runner, content, tmp_path, clock, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 2
    assert runner.tick().added == 2
    assert runner.tick().added == 0  # 同一個小時內不再補
    clock[0] += content.config.bot_fill_seconds
    assert runner.tick().added == 2
    clock[0] += content.config.bot_fill_seconds
    assert runner.tick().added == 0  # 每陣營 2 人了（還在路上、沒投靠的也算）
    assert sorted(s.player.bot.faction for s in _bots(tmp_path)) == ["guan", "guan", "huang", "huang"]


def test_players_who_already_joined_count_toward_the_minimum(runner, world, content, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    world.record_faction("真人甲", "guan")
    assert runner.tick().added == 1  # 只補黃巾


def test_a_retired_bot_is_woken_before_a_new_one_is_made(runner, world, content, tmp_path, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    old = Game.new(content, "老假人", world=world)
    old.state.player.bot = BotProfile(personality="懶散", seed=9)  # 退隱中：faction 是 None
    save_game(old.state, path_for(tmp_path / "saves", "老假人"))
    assert runner.tick().added == 2
    bots = {s.player.name: s.player.bot for s in _bots(tmp_path)}
    assert len(bots) == 2 and "老假人" in bots
    assert bots["老假人"].faction in ("guan", "huang") and bots["老假人"].season_number == 1


def test_a_new_season_retires_every_bot_and_wakes_them_again_by_name(runner, world, content, tmp_path, clock, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    runner.tick()
    names = sorted(s.player.name for s in _bots(tmp_path))
    world.mutate_season(lambda season: setattr(season, "ended", True))
    assert world.next_season(content, now=clock[0])
    assert all(not server_bots.active(s.player.bot, 2) for s in _bots(tmp_path))
    clock[0] += content.config.bot_fill_seconds
    assert runner.tick().added == 2
    assert sorted(s.player.name for s in _bots(tmp_path)) == names  # 沒有新名號，都是叫醒的
    assert all(server_bots.active(s.player.bot, 2) for s in _bots(tmp_path))


def test_an_online_bot_acts_and_saves(runner, content, tmp_path, clock, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000  # 在線就一定做一個動作
    runner.tick()  # 補人，這一輪也會讓剛補的假人做事
    clock[0] += 60
    report = runner.tick()
    assert report.online == 2 and report.acted == 2
    assert all(s.last_real == clock[0] for s in _bots(tmp_path))


def test_a_bot_skips_its_turn_while_a_player_holds_the_action_lock(runner, world, content, tmp_path, clock, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    monkeypatch.setattr(bot_runner, "LOCK_WAIT", 0.05)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000
    runner.tick()
    before = [s.model_dump() for s in _bots(tmp_path)]
    clock[0] += 60
    with world.action_lock():
        report = runner.tick()
    assert report.acted == 0 and report.skipped >= 2
    assert [s.model_dump() for s in _bots(tmp_path)] == before


def test_bots_do_nothing_until_the_admin_opens_the_season(content, tmp_path, clock):
    _install(content)
    content.config.auto_open_first_season = False
    store = WorldStateStore()
    store.seed_first_season(content)
    runner = BotRunner(content, store, tmp_path / "saves", random.Random(1), clock=lambda: clock[0])
    assert runner.tick().added == 0
    assert not (tmp_path / "saves").exists()


def test_a_season_of_server_bots_runs_to_the_end_and_both_sides_fight(runner, world, content, clock, monkeypatch):
    """整季：只有假人程式，用假時鐘跑完一季；背景跨過門檻開戰，兩邊的假人都以一般參戰者上場。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    monkeypatch.setattr(time, "time", lambda: clock[0])  # 戰鬥的集結與回合計時用現實時間
    cfg = content.config
    cfg.time_scale, cfg.bot_tick_seconds = 12.0, 60
    cfg.bots_min_per_faction, cfg.bot_fill_seconds = 3, 600
    sides, flagged = set(), False
    for i in range(400):
        if i == 30:  # 半小時後六個假人都補齊了：讓大勢人物在背景把水寇推過開戰門檻（官軍假人會一直壓寇亂，不能等它自己漲）
            world.mutate_season(lambda season: season.trends.__setitem__("kou", 60))
        runner.tick()
        battle = world.get_battle()
        if battle is not None:
            sides |= {p.faction for p in battle.participants.values()}
            flagged = flagged or any(p.is_bot for p in battle.participants.values())
        if world.get_season().ended:
            break
        clock[0] += cfg.bot_tick_seconds
    assert world.get_season().ended
    assert sides == {"guan", "huang"} and not flagged
    assert world.faction_counts() == {"guan": 3, "huang": 3}


def test_run_bots_starts_and_runs_a_round(monkeypatch, capsys):
    monkeypatch.setattr(run_bots.time, "sleep", lambda seconds: None)
    run_bots.main(ticks=1)
    out = capsys.readouterr().out
    assert "伺服器假人程式啟動" in out
