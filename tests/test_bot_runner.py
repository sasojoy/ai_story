import logging
import random
import time

import pytest

import run_bots
from tianxia import bot_policy, bot_runner, server_bots
from tianxia.battle_instance import BattleParticipant
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


def test_a_player_acting_between_bot_turns_does_not_make_the_season_run_faster(
    runner, world, content, tmp_path, clock, monkeypatch,
):
    """一輪裡每個假人之間都會放開行動鎖，真人可能就在這時候行動、把共用時鐘對到更晚的時間。
    下一個假人要用自己拿到鎖之後的時間補算，不能把時鐘撥回這一輪開頭讀的時間——不然下一個
    真人會把那一段再算一次，賽季走得比現實快。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    monkeypatch.setattr(bot_policy, "take_turn", lambda game, profile, rng: None)  # 只看時鐘
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000  # 在線就一定做一個動作
    runner.tick()  # 補人
    start_real, start_time = world.read().season_last_real, world.get_season().time

    def ticking():  # 每看一次錶就過了 10 秒
        clock[0] += 10
        return clock[0]

    runner.clock = ticking
    real_turn = runner._take_turn
    turns, players = [], []

    def turn_then_a_player_acts(path, now):
        turns.append(now)
        result = real_turn(path, now)
        players.append(ticking())
        world.catch_up_season(content, players[-1], random.Random(0))  # 這個假人做完，真人接著行動
        return result

    monkeypatch.setattr(runner, "_take_turn", turn_then_a_player_acts)
    runner.tick()
    end = ticking()
    world.catch_up_season(content, end, random.Random(0))  # 一輪結束後，真人又行動一次
    assert len(turns) == 2 and turns[1] > players[0]  # 第二個假人看的錶在真人行動之後
    assert world.get_season().time - start_time == (end - start_real) * content.config.time_scale


def _saves_snapshot(tmp_path):
    return {p.name: p.read_bytes() for p in sorted((tmp_path / "saves").glob("*.json"))}


def _round_where_something_happens_mid_round(runner, content, tmp_path, clock, monkeypatch, happen):
    """補好人之後再跑一輪：這一輪開頭還在進行中，排到第一個假人時（還沒拿行動鎖）發生 happen()。
    回傳（這一輪的報告, 真的出手的假人名號）。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000  # 在線就一定做一個動作
    runner.tick()  # 補人
    played = []
    monkeypatch.setattr(bot_policy, "take_turn", lambda game, profile, rng: played.append(game.state.player.name))
    happened = []

    def online_and_then_it_happens(profile, now):
        if not happened:
            happened.append(happen())
        return True

    monkeypatch.setattr(server_bots, "is_online", online_and_then_it_happens)
    clock[0] += 60
    return runner.tick(), played


def test_bots_stop_acting_when_the_season_ends_in_the_middle_of_a_round(
    runner, world, content, tmp_path, clock, monkeypatch,
):
    before = None

    def season_ends():
        nonlocal before
        world.mutate_season(lambda season: setattr(season, "ended", True))
        before = _saves_snapshot(tmp_path)

    report, played = _round_where_something_happens_mid_round(runner, content, tmp_path, clock, monkeypatch, season_ends)
    assert played == [] and report.acted == 0
    assert _saves_snapshot(tmp_path) == before  # 休季了：不做事，也不存檔


def test_a_bot_retired_by_a_new_season_in_the_middle_of_a_round_does_not_act(
    runner, world, content, tmp_path, clock, monkeypatch,
):
    """這一輪開頭還是第 1 季；管理者在這一輪中間開了第 2 季，第 1 季的假人都算退隱，不能跑到
    新的一季去替舊陣營做事。"""
    before = None

    def admin_opens_the_next_season():
        nonlocal before
        world.mutate_season(lambda season: setattr(season, "ended", True))
        assert world.next_season(content, now=clock[0])
        before = _saves_snapshot(tmp_path)

    report, played = _round_where_something_happens_mid_round(
        runner, content, tmp_path, clock, monkeypatch, admin_opens_the_next_season,
    )
    assert played == [] and report.acted == 0
    assert _saves_snapshot(tmp_path) == before
    assert world.faction_counts() == {}  # 沒有人替舊陣營投靠進新的一季


def test_a_bot_whose_own_catch_up_ends_the_season_saves_but_does_not_act(
    runner, world, content, tmp_path, clock, monkeypatch,
):
    """假人自己補算時間時剛好走到季末：補算的結果要存下來，但不能在休季時做事。"""
    def nearly_over():
        world.mutate_season(lambda season: setattr(season, "time", content.config.season_days * 86400 - 30))

    report, played = _round_where_something_happens_mid_round(runner, content, tmp_path, clock, monkeypatch, nearly_over)
    assert world.get_season().ended
    assert played == [] and report.acted == 0
    assert any(s.last_real == clock[0] for s in _bots(tmp_path))  # 走到季末的那一個假人存了補算的結果


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


def _identity_free(name: str, capsys, caplog) -> bool:
    """名號不能出現在任何地方：主控台輸出、log 的訊息與例外文字都算。"""
    out = capsys.readouterr()
    logged = caplog.text + "".join(
        f"{record.getMessage()}{record.exc_text or ''}{record.exc_info or ''}" for record in caplog.records
    )
    return name not in out.out and name not in out.err and name not in logged


def test_a_failing_bot_turn_is_counted_and_reported_without_any_name(
    runner, content, tmp_path, clock, monkeypatch, capsys, caplog,
):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000
    runner.tick()
    victim = _bots(tmp_path)[0].player.name

    def boom(game, profile, rng):
        if game.state.player.name == victim:
            raise OSError(f"寫不進 {path_for(tmp_path / 'saves', victim)}（{victim}）")

    monkeypatch.setattr(bot_policy, "take_turn", boom)
    clock[0] += 60
    capsys.readouterr()  # 丟掉補人那一輪的輸出
    with caplog.at_level(logging.DEBUG):
        report = runner.tick()
    assert report.failed == 1 and report.acted == 1
    assert "OSError" in caplog.text  # 看得到是什麼錯、出在哪一行，但看不到內容
    assert "boom" in caplog.text
    assert _identity_free(victim, capsys, caplog)


def test_a_failure_while_topping_up_is_counted_and_does_not_stop_the_tick(
    runner, content, tmp_path, monkeypatch, caplog,
):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1

    secret = "名號" + "字庫用完了"  # 例外訊息不能出現在 log 裡（log 會印出原始碼那一行，所以訊息不能直接寫在 raise 那行）

    def pool_empty(rng, taken):
        raise RuntimeError(secret)

    monkeypatch.setattr(server_bots, "make_name", pool_empty)
    with caplog.at_level(logging.DEBUG):
        report = runner.tick()
    assert report.failed >= 1 and report.added == 0
    assert "RuntimeError" in caplog.text and secret not in caplog.text


def test_a_new_bot_never_takes_the_name_of_an_unreadable_save(runner, content, tmp_path, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    saves = tmp_path / "saves"
    saves.mkdir()
    garbage = saves / "某人.json"
    garbage.write_bytes(b"{this is not a save")
    proposals, seen = ["某人", "某乙", "某丙"], []

    def propose(rng, taken):
        seen.append(set(taken))
        return next(name for name in proposals if name not in taken)

    monkeypatch.setattr(server_bots, "make_name", propose)
    assert runner.tick().added == 2
    assert all("某人" in taken for taken in seen)
    assert garbage.read_bytes() == b"{this is not a save"
    assert sorted(p.stem for p in saves.glob("*.json")) == ["某丙", "某乙", "某人"]


def test_a_bot_that_turned_up_for_a_battle_goes_offline_once_it_is_eliminated(
    runner, world, content, tmp_path, clock, monkeypatch,
):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)  # 都不在作息時段
    monkeypatch.setattr(server_bots, "attends_battle", lambda profile, key: True)  # 但都擲中趕來參戰
    monkeypatch.setattr(bot_policy, "take_turn", lambda game, profile, rng: None)  # 只看誰算在線
    monkeypatch.setattr(time, "time", lambda: clock[0])
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000
    assert runner.tick().online == 0  # 沒有戰鬥：不在作息時段就不上線
    for path in sorted((tmp_path / "saves").glob("*.json")):  # 兩個假人都已投靠自己的陣營
        state = load_game(path)
        state.player.faction = state.player.bot.faction
        save_game(state, path)
    battle = world.start_battle(content.battles["t1"], clock[0])
    assert battle.phase == "muster"
    assert runner.tick().online == 2  # 集結中：兩邊的假人都趕來

    bots = [(s.player.name, s.player.bot.faction) for s in _bots(tmp_path)]

    def seat(battle):
        for name, faction in bots:
            battle.participants[name] = BattleParticipant(
                name=name, faction=faction, neili=10, neili_cap=10, eliminated=name == bots[0][0],
            )

    world.mutate_battle(seat)
    assert runner.tick().online == 1  # 出局的那一位不再上線，沒出局的還在
    world.mutate_battle(lambda b: setattr(b, "phase", "ended"))
    assert runner.tick().online == 0  # 戰鬥結束，大家都回到自己的作息


def test_run_bots_keeps_going_after_a_bad_tick_and_prints_no_names(monkeypatch, capsys, caplog):
    monkeypatch.setattr(run_bots.time, "sleep", lambda seconds: None)
    calls = []
    secret = "某位" + "假人的名號"  # 例外訊息；log 會印出 raise 那一行原始碼，所以訊息不能直接寫在那行

    def flaky(self):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError(secret)
        return bot_runner.TickReport()

    monkeypatch.setattr(BotRunner, "tick", flaky)
    with caplog.at_level(logging.DEBUG):
        run_bots.main(ticks=2)
    assert len(calls) == 2  # 第一輪出錯了，第二輪照常跑
    out = capsys.readouterr()
    assert "出錯 1" in out.out
    assert "RuntimeError" in caplog.text and secret not in out.out + out.err + caplog.text


def test_run_bots_ends_cleanly_on_ctrl_c(monkeypatch, capsys):
    def interrupted(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_bots.time, "sleep", interrupted)
    run_bots.main()  # 不給輪數：本來會一直跑；Ctrl+C 要乾淨結束，不丟例外
    assert "伺服器假人程式結束" in capsys.readouterr().out
