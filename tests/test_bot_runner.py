import contextlib
import logging
import random

import pytest

import run_bots
from test_bot import armed
from tianxia import bot_policy, bot_runner, database, fusion, library, naming, server_bots, team
from tianxia.battle_instance import BattleParticipant
from tianxia.bot_runner import BotRunner
from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.models import (
    BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome,
    FactionDef, ThirdParty,
)
from tianxia.database import Database
from tianxia.sqlite_world import SqliteWorldStore, open_world
from tianxia.state import BotProfile

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
                options=[BattleOption(text=f"{s}{m}", tag=f"{s}_{c}", faction=s, move=m)
                         for s in ("guan", "huang") for m, c in (("強攻", "strong"), ("固守", "hold"), ("奇襲", "raid"))],
            ),
        ],
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
    store = open_world()
    store.seed_first_season(content)  # 測試內容會直接開季
    return store


@pytest.fixture
def runner(content, world, clock):
    _install(content)
    return BotRunner(content, world, open_characters(), random.Random(1), clock=lambda: clock[0])


def _bots():
    return open_characters().all(bots_only=True)


def _tick_cleanly(runner):
    """跑一輪並要求沒有出錯：tick 會吞掉假人回合裡的例外（記一筆 log、算一次 failed）。拿假的 take_turn／_take_turn 換掉真的時，
    參數數量一旦跟真的對不上（例如多了取名名額 slot）就是 TypeError——被吞掉的話，只看別的結果（沒人出手、誰算在線）的測試
    會空過、再也抓不到假人真的出手了。所以這些測試的每一輪都要沒有出錯。"""
    report = runner.tick()
    assert report.failed == 0
    return report


def test_fill_adds_one_bot_per_faction_per_interval_up_to_the_minimum(runner, content, clock, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 2
    assert runner.tick().added == 2
    assert runner.tick().added == 0  # 同一個小時內不再補
    clock[0] += content.config.bot_fill_seconds
    assert runner.tick().added == 2
    clock[0] += content.config.bot_fill_seconds
    assert runner.tick().added == 0  # 每陣營 2 人了（還在路上、沒投靠的也算）
    assert sorted(s.player.bot.faction for s in _bots()) == ["guan", "guan", "huang", "huang"]


def test_a_new_bot_leaves_the_start_like_a_human_who_walked_the_hut(prologue_content, clock, monkeypatch):
    """內容有序章時，bot_runner 新建的假人離開起點的樣子跟走完草廬的真人一樣（Game.new(graduated=True)）：
    等級 2、一門中品第三成的師門功夫、一點內傷、多了盤纏；站在起點、不在草廬、序章算走過。"""
    from tianxia import library, prologue, team

    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    _install(prologue_content)
    prologue_content.config.bots_min_per_faction = 1
    world = open_world()
    world.seed_first_season(prologue_content)
    runner = BotRunner(prologue_content, world, open_characters(), random.Random(1), clock=lambda: clock[0])
    assert runner.tick().added == 2
    for state in _bots():
        p = state.player
        assert p.bot is not None and p.location == "town" and state.pending_event is None
        assert p.tutorial_step == prologue_content.tutorial.prologue_steps and not prologue.active(state, prologue_content)
        assert p.member.level == 2 and p.member.injury > 0
        fused = prologue.fused_arts(state, prologue_content, world)
        assert len(fused) == 1 and fused[0].preset and fused[0].quality == "中品" and library.level_of(state, fused[0].id) == 3
        assert team.player_art(state, prologue_content, world, p.member.wugong_id).id == fused[0].id  # 換上身了
        assert p.stats["silver"] > prologue_content.config.start_stats["silver"]  # 盤纏


def test_players_who_already_joined_count_toward_the_minimum(runner, world, content, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    world.record_faction("真人甲", "guan")
    assert runner.tick().added == 1  # 只補黃巾


def test_a_retired_bot_is_woken_before_a_new_one_is_made(runner, world, content, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    old = Game.new(content, "老假人", world=world)
    old.state.player.bot = BotProfile(personality="懶散", seed=9)  # 退隱中：faction 是 None
    open_characters().save(old.state)
    assert runner.tick().added == 2
    bots = {s.player.name: s.player.bot for s in _bots()}
    assert len(bots) == 2 and "老假人" in bots
    assert bots["老假人"].faction in ("guan", "huang") and bots["老假人"].season_number == 1


def test_a_new_season_retires_every_bot_and_wakes_them_again_by_name(runner, world, content, clock, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    runner.tick()
    names = sorted(s.player.name for s in _bots())
    world.mutate_season(lambda season: setattr(season, "ended", True))
    assert world.next_season(content, now=clock[0])
    assert all(not server_bots.active(s.player.bot, 2) for s in _bots())
    clock[0] += content.config.bot_fill_seconds
    assert runner.tick().added == 2
    assert sorted(s.player.name for s in _bots()) == names  # 沒有新名號，都是叫醒的
    assert all(server_bots.active(s.player.bot, 2) for s in _bots())


def test_an_online_bot_acts_and_saves(runner, content, clock, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000  # 在線就一定做一個動作
    runner.tick()  # 補人，這一輪也會讓剛補的假人做事
    clock[0] += 60
    report = runner.tick()
    assert report.online == 2 and report.acted == 2
    assert all(s.last_real == clock[0] for s in _bots())


def test_a_bot_skips_its_turn_while_a_player_holds_the_action_lock(runner, world, content, clock, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    monkeypatch.setattr(bot_runner, "LOCK_WAIT", 0.05)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000
    runner.tick()
    before = [s.model_dump() for s in _bots()]
    clock[0] += 60
    holder = Database(world.db.path)  # 另一組連線，像真人那邊的程式拿著寫入權
    try:
        with holder.transaction():
            report = runner.tick()
    finally:
        holder.close()
    assert report.acted == 0 and report.skipped >= 2
    assert [s.model_dump() for s in _bots()] == before


def test_a_player_acting_between_bot_turns_does_not_make_the_season_run_faster(
    runner, world, content, clock, monkeypatch,
):
    """一輪裡每個假人之間都會放開行動鎖，真人可能就在這時候行動、把共用時鐘對到更晚的時間。
    下一個假人要用自己拿到鎖之後的時間補算，不能把時鐘撥回這一輪開頭讀的時間——不然下一個
    真人會把那一段再算一次，賽季走得比現實快。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    monkeypatch.setattr(bot_policy, "take_turn", lambda game, profile, rng, slot=None: None)  # 只看時鐘
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000  # 在線就一定做一個動作
    _tick_cleanly(runner)  # 補人
    start_real, start_time = world.read().season_last_real, world.get_season().time

    def ticking():  # 每看一次錶就過了 10 秒
        clock[0] += 10
        return clock[0]

    runner.clock = ticking
    real_turn = runner._take_turn
    turns, players = [], []

    def turn_then_a_player_acts(name, now, slot=None):
        turns.append(now)
        result = real_turn(name, now, slot)
        players.append(ticking())
        world.catch_up_season(content, players[-1], random.Random(0))  # 這個假人做完，真人接著行動
        return result

    monkeypatch.setattr(runner, "_take_turn", turn_then_a_player_acts)
    _tick_cleanly(runner)
    end = ticking()
    world.catch_up_season(content, end, random.Random(0))  # 一輪結束後，真人又行動一次
    assert len(turns) == 2 and turns[1] > players[0]  # 第二個假人看的錶在真人行動之後
    assert world.get_season().time - start_time == (end - start_real) * content.config.time_scale


def _saves_snapshot():
    with open_characters().db.snapshot() as conn:
        return {row["key"]: row["data"] for row in conn.execute("SELECT key, data FROM characters ORDER BY key")}


def _round_where_something_happens_mid_round(runner, content, clock, monkeypatch, happen):
    """補好人之後再跑一輪：這一輪開頭還在進行中，排到第一個假人時（還沒拿行動鎖）發生 happen()。
    回傳（這一輪的報告, 真的出手的假人名號）。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000  # 在線就一定做一個動作
    runner.tick()  # 補人
    played = []
    monkeypatch.setattr(
        bot_policy, "take_turn", lambda game, profile, rng, slot=None: played.append(game.state.player.name),
    )
    happened = []

    def online_and_then_it_happens(profile, now):
        if not happened:
            happened.append(happen())
        return True

    monkeypatch.setattr(server_bots, "is_online", online_and_then_it_happens)
    clock[0] += 60
    return _tick_cleanly(runner), played


def test_bots_stop_acting_when_the_season_ends_in_the_middle_of_a_round(
    runner, world, content, clock, monkeypatch,
):
    before = None

    def season_ends():
        nonlocal before
        world.mutate_season(lambda season: setattr(season, "ended", True))
        before = _saves_snapshot()

    report, played = _round_where_something_happens_mid_round(runner, content, clock, monkeypatch, season_ends)
    assert played == [] and report.acted == 0
    assert _saves_snapshot() == before  # 休季了：不做事，也不存檔


def test_a_bot_retired_by_a_new_season_in_the_middle_of_a_round_does_not_act(
    runner, world, content, clock, monkeypatch,
):
    """這一輪開頭還是第 1 季；管理者在這一輪中間開了第 2 季，第 1 季的假人都算退隱，不能跑到
    新的一季去替舊陣營做事。"""
    before = None

    def admin_opens_the_next_season():
        nonlocal before
        world.mutate_season(lambda season: setattr(season, "ended", True))
        assert world.next_season(content, now=clock[0])
        before = _saves_snapshot()

    report, played = _round_where_something_happens_mid_round(
        runner, content, clock, monkeypatch, admin_opens_the_next_season,
    )
    assert played == [] and report.acted == 0
    assert _saves_snapshot() == before
    assert world.faction_counts() == {}  # 沒有人替舊陣營投靠進新的一季


def test_a_bot_whose_own_catch_up_ends_the_season_saves_but_does_not_act(
    runner, world, content, clock, monkeypatch,
):
    """假人自己補算時間時剛好走到季末：補算的結果要存下來，但不能在休季時做事。"""
    def nearly_over():
        world.mutate_season(lambda season: setattr(season, "time", content.config.season_days * 86400 - 30))

    report, played = _round_where_something_happens_mid_round(runner, content, clock, monkeypatch, nearly_over)
    assert world.get_season().ended
    assert played == [] and report.acted == 0
    assert any(s.last_real == clock[0] for s in _bots())  # 走到季末的那一個假人存了補算的結果


def test_bots_do_nothing_until_the_admin_opens_the_season(content, clock):
    _install(content)
    content.config.auto_open_first_season = False
    store = open_world()
    store.seed_first_season(content)
    runner = BotRunner(content, store, open_characters(), random.Random(1), clock=lambda: clock[0])
    assert runner.tick().added == 0
    assert open_characters().names() == set()


@pytest.mark.slow
def test_a_season_of_server_bots_runs_to_the_end_and_both_sides_fight(runner, world, content, clock, monkeypatch):
    """整季：只有假人程式，用假時鐘跑完一季；背景跨過門檻開戰，兩邊的假人都以一般參戰者上場。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
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


def test_run_bots_says_which_database_file_it_uses(monkeypatch, capsys):
    """兩支程式要用同一個資料庫檔；TIANXIA_DB 設錯時，開機畫面一眼就看得出來（只印路徑，不印任何名號）。"""
    monkeypatch.setattr(run_bots.time, "sleep", lambda seconds: None)
    run_bots.main(ticks=1)
    assert str(database.default_path().resolve()) in capsys.readouterr().out


def test_run_bots_reads_the_profile_from_the_environment(monkeypatch, capsys):
    """跟 server.py 用同一份設定（TIANXIA_PROFILE），啟動時印出來；沒設就是預設。"""
    monkeypatch.setattr(run_bots.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(BotRunner, "tick", lambda self: bot_runner.TickReport())
    monkeypatch.delenv("TIANXIA_PROFILE", raising=False)
    run_bots.main(ticks=1)
    assert "設定：預設" in capsys.readouterr().out
    monkeypatch.setenv("TIANXIA_PROFILE", "weekend")
    run_bots.main(ticks=1)
    assert "設定：weekend（第一季濃縮版規則開啟、季長 2.5 天、人數上限 2）" in capsys.readouterr().out


def _identity_free(name: str, capsys, caplog) -> bool:
    """名號不能出現在任何地方：主控台輸出、log 的訊息與例外文字都算。"""
    out = capsys.readouterr()
    logged = caplog.text + "".join(
        f"{record.getMessage()}{record.exc_text or ''}{record.exc_info or ''}" for record in caplog.records
    )
    return name not in out.out and name not in out.err and name not in logged


def test_a_failing_bot_turn_is_counted_and_reported_without_any_name(
    runner, content, clock, monkeypatch, capsys, caplog,
):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000
    runner.tick()
    victim = _bots()[0].player.name

    def boom(game, profile, rng, slot=None):
        if game.state.player.name == victim:
            raise OSError(f"寫不進存檔（{victim}）")

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
    runner, content, monkeypatch, caplog,
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


def test_a_new_bot_never_takes_the_name_of_an_unreadable_save(runner, content, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    characters = open_characters()
    with characters.db.transaction() as conn:
        conn.execute(
            "INSERT INTO characters (key, name, is_bot, faction, data) "
            "VALUES ('某人', '某人', 0, NULL, '{this is not a save')"
        )
    proposals, seen = ["某人", "某乙", "某丙"], []

    def propose(rng, taken):
        seen.append(set(taken))
        return next(name for name in proposals if name not in taken)

    monkeypatch.setattr(server_bots, "make_name", propose)
    assert runner.tick().added == 2
    assert all("某人" in taken for taken in seen)
    with characters.db.snapshot() as conn:
        assert conn.execute("SELECT data FROM characters WHERE key = '某人'").fetchone()["data"] == "{this is not a save"
    assert sorted(characters.names()) == ["某丙", "某乙", "某人"]


def test_a_new_bot_never_takes_the_name_of_a_historical_figure_in_the_content(runner, content, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    seen = []
    real_make_name = server_bots.make_name

    def spy(rng, taken):
        seen.append(set(taken))
        return real_make_name(rng, taken)

    monkeypatch.setattr(server_bots, "make_name", spy)
    assert runner.tick().added == 2
    figures = {ch.name for ch in content.characters.values()}
    assert figures and all(figures <= taken for taken in seen)


def test_a_bot_that_turned_up_for_a_battle_goes_offline_once_it_is_eliminated(
    runner, world, content, clock, monkeypatch,
):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)  # 都不在作息時段
    monkeypatch.setattr(server_bots, "attends_battle", lambda profile, key: True)  # 但都擲中趕來參戰
    monkeypatch.setattr(bot_policy, "take_turn", lambda game, profile, rng, slot=None: None)  # 只看誰算在線
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000
    assert _tick_cleanly(runner).online == 0  # 沒有戰鬥：不在作息時段就不上線
    characters = open_characters()
    for state in characters.all(bots_only=True):  # 兩個假人都已投靠自己的陣營
        state.player.faction = state.player.bot.faction
        characters.save(state)
    battle = world.start_battle(content.battles["t1"], clock[0])
    assert battle.phase == "muster"
    assert _tick_cleanly(runner).online == 2  # 集結中：兩邊的假人都趕來

    bots = [(s.player.name, s.player.bot.faction) for s in _bots()]

    def seat(battle):
        for name, faction in bots:
            battle.participants[name] = BattleParticipant(
                name=name, faction=faction, neili=10, neili_cap=10, eliminated=name == bots[0][0],
            )

    world.mutate_battle(seat)
    assert _tick_cleanly(runner).online == 1  # 出局的那一位不再上線，沒出局的還在
    world.mutate_battle(lambda b: setattr(b, "phase", "ended"))
    assert _tick_cleanly(runner).online == 0  # 戰鬥結束，大家都回到自己的作息


def test_a_warlord_bot_turns_up_for_a_battle_with_a_third_side_like_the_armies_do(
    runner, world, content, clock, monkeypatch,
):
    """決戰改版 5（假人的對等）：能站的每一方都算（兩軍加第三方），豪強的假人也擲「趕來參戰」；
    沒有第三方的決戰照舊只有兩軍的假人趕來。看不出誰是假人：兩邊的假人行為要一樣。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)  # 都不在作息時段
    monkeypatch.setattr(server_bots, "attends_battle", lambda profile, key: True)  # 但都擲中趕來參戰
    monkeypatch.setattr(bot_policy, "take_turn", lambda game, profile, rng, slot=None: None)  # 只看誰算在線
    content.scenario.factions.append(FactionDef(id="haoqiang", name="地方豪強", join_at=["town"]))
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000
    assert _tick_cleanly(runner).online == 0
    characters = open_characters()
    for state in characters.all(bots_only=True):  # 三個陣營各一位假人，都已投靠
        state.player.faction = state.player.bot.faction
        characters.save(state)
    assert sorted(s.player.faction for s in _bots()) == ["guan", "haoqiang", "huang"]
    world.start_battle(content.battles["t1"], clock[0])
    assert _tick_cleanly(runner).online == 2  # 這一場只有兩軍：豪強的假人不趕來
    world.clear_battle()
    content.battles["t1"].third = ThirdParty(faction="haoqiang", trend="kou")
    world.start_battle(content.battles["t1"], clock[0])
    assert _tick_cleanly(runner).online == 3  # 有第三方：豪強的假人也趕來


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


# ── 假人在鎖外請模型取名：首創的配方與絕學定名（A 鎖內開單 → B 鎖外取名 → C 再拿鎖）────────────────────


INSIGHTS = ("feng", "huo", "shui", "shan")  # 測試內容裡有的意境：每個假人各拿一個，配方才各不相同


def _armed_bots(runner, content, clock, monkeypatch, count=1):
    """補好假人，前 count 位換成有一門武學、一個意境（各不相同）、心得與體力都夠的（照 test_bot.armed），停在城裡、
    投靠好了、沒有在路上也沒有待處理的事件，存回去；每輪必合、不修練、不練成（心得只花在合成上）。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    monkeypatch.setattr(bot_policy, "FORGE_CHANCE", 1.0)
    monkeypatch.setattr(bot_policy, "CULTIVATE_CHANCE", 0.0)
    monkeypatch.setattr(bot_policy, "PRACTICE_CHANCE", 0.0)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000  # 在線就一定做一個動作
    runner.tick()
    store = open_characters()
    for i, state in enumerate(_bots()[:count]):
        p = state.player
        p.member.wugong_id, p.insights, p.stats["xinde"], p.stamina = "basic_fist", [INSIGHTS[i]], 100, 150
        p.journey, p.faction, p.location = None, p.bot.faction, "town"
        state.pending_event = None
        store.save(state)
    clock[0] += 60


@pytest.fixture
def lock_events(monkeypatch):
    events = []
    real = SqliteWorldStore.action_lock

    @contextlib.contextmanager
    def spy(self, timeout=None):
        with real(self, timeout):
            events.append("enter")
            yield
        events.append("exit")

    monkeypatch.setattr(SqliteWorldStore, "action_lock", spy)
    return events


def _check_b_call(world, content, budget, person):
    """B 段叫 naming.generate 的方式：一件最多 bot_naming_budget_seconds 秒（planner 的「一件最多 30 秒」；漏了 budget，
    模型慢的時候一次取名就照 ollama_timeout 的 120 秒、兩趟、最多三次佔著顯卡，整輪假人都被拖住），
    角色名號的查詢是這個世界的 is_character_name（模型取到江湖上角色的名號就再取一次）。這兩個引數的預設值是 None，
    假的 generate 照 naming.generate 的簽名收，漏帶的話預設值會把它藏起來——所以在這裡明確比對。"""
    assert budget == content.config.bot_naming_budget_seconds
    assert person == world.is_character_name


def _namer(world, events, name="凌風拳", fail=False):
    def generate(client, content, request, budget=None, person=None):
        events.append("name")
        assert not world.db.writing()  # 這個執行緒沒拿著寫入交易
        _check_b_call(world, content, budget, person)
        if fail:  # 模型叫不動：取不到名字
            return None, ""
        return (request.choices[0], "") if request.choices else (name, "一句話。")
    return generate


def test_a_bot_names_its_first_recipe_outside_the_lock(runner, world, content, clock, monkeypatch, lock_events):
    """Review Focus 1：A 鎖內開單 → B 鎖外取名 → C 再拿鎖開爐；登記的是模型取的名字。鎖內假人的 Game 沒有 client（一個模型都不叫）。"""
    runner.client = object()  # 有 client 就開放取名（generate 換成假的，不會真的連）
    _armed_bots(runner, content, clock, monkeypatch)
    monkeypatch.setattr(naming, "generate", _namer(world, lock_events))
    clients = []
    real_forge = Game.forge

    def forge_spy(self, *args, **kwargs):
        clients.append(self.client)
        return real_forge(self, *args, **kwargs)

    monkeypatch.setattr(Game, "forge", forge_spy)
    lock_events.clear()
    report = runner.tick()
    at = lock_events.index("name")
    assert lock_events[at - 1] == "exit" and lock_events[at + 1] == "enter"
    assert report.named == 1 and report.failed == 0
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")).name == "凌風拳"
    assert clients == [None]  # C 段開爐時，假人的 Game 照舊沒有 client


def test_only_one_bot_names_per_gap(runner, world, content, clock, monkeypatch):
    """Review Focus 2：同一輪兩個假人都想開首創的爐（配方各不相同），只有一個叫模型；隔夠了下一輪才輪到另一個。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch, count=2)
    calls = []
    monkeypatch.setattr(naming, "generate", _namer(world, calls))
    report = runner.tick()
    assert report.named == 1 and report.naming_skipped >= 1 and calls == ["name"]
    runner.tick()  # 時鐘沒動：還在間隔裡，不叫模型
    assert calls == ["name"]
    clock[0] += content.config.bot_naming_gap_seconds
    runner.tick()
    assert calls == ["name", "name"]


def test_without_a_model_client_bots_skip_first_recipes(runner, world, content, clock, monkeypatch):
    """Review Focus 4：沒有 client（或 bot_naming 關著）就不開要取名的爐，不用字表名字搶首創。"""
    _armed_bots(runner, content, clock, monkeypatch)
    report = runner.tick()
    assert report.named == 0 and report.naming_skipped >= 1
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None


def test_with_bot_naming_off_bots_skip_first_recipes_even_with_a_client(runner, world, content, clock, monkeypatch):
    runner.client = object()
    content.config.bot_naming = False
    _armed_bots(runner, content, clock, monkeypatch)
    monkeypatch.setattr(naming, "generate", _namer(world, []))
    report = runner.tick()
    assert report.named == 0 and report.naming_skipped >= 1
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None


def test_a_recipe_claimed_while_the_bot_waited_is_not_charged_twice(runner, world, content, clock, monkeypatch):
    """Review Focus 3：B 段等名字的時候，一位真人先合了同一爐：C 段照查到的配方給，不收第二次，名字是真人那一爐的。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)

    def generate(client, content_, request, budget=None, person=None):
        _check_b_call(world, content_, budget, person)
        player = armed(content, world, name="真人")
        player.forge("basic_fist", ["feng"], proposed=("先到拳", "一句話。"))
        return ("後到拳", "一句話。")

    monkeypatch.setattr(naming, "generate", generate)
    runner.tick()
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")).name == "先到拳"
    bot_state = next(s for s in _bots() if s.player.insights == ["feng"] and s.player.member.wugong_id == "basic_fist")
    fused = [a for a in library.owned_arts(bot_state) if a != "basic_fist"]
    assert len(fused) == 1 and team.resolve_art(fused[0], content, world).name == "先到拳"  # 照查到的那一門，沒有「後到拳」
    assert bot_state.player.stats["xinde"] == 100 - content.config.fuse_xinde  # 收一次


def _master_ready(runner, content, world, clock, monkeypatch):
    """一位假人合出「凌風拳」、練成絕學、輪到自己定名（存回去）；回傳它的名號。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)
    state = _bots()[0]
    game = Game(content, state, random.Random(0), world)
    game.forge("basic_fist", ["feng"], proposed=("凌風拳", "一句話。"))
    art_id = next(a for a in library.owned_arts(state) if a != "basic_fist")
    assert world.claim_master(art_id, state.player.name)  # 第一個練成絕學的人：不登記的話，Game 一建好就把取名權當作過期丟掉
    state.player.naming = art_id
    open_characters().save(state)
    return state.player.name


def test_a_bot_names_its_mastered_art_outside_the_lock(runner, world, content, clock, monkeypatch, lock_events):
    """絕學定名也走三段式（企劃者 2026-10-06）：鎖外請模型另取新名字，再拿鎖定名；江湖史寫的是新名字。"""
    victim = _master_ready(runner, content, world, clock, monkeypatch)
    monkeypatch.setattr(naming, "generate", _namer(world, lock_events, name="破雲拳"))
    lock_events.clear()
    report = runner.tick()
    at = lock_events.index("name")
    assert lock_events[at - 1] == "exit" and lock_events[at + 1] == "enter"
    assert report.named == 1 and report.failed == 0
    assert open_characters().load(victim).player.naming is None
    assert any("為之定名【破雲拳】" in r.text for r in world.get_season().chronicle)


def test_a_failed_naming_does_not_claim_the_recipe_with_a_table_name(runner, world, content, clock, monkeypatch):
    """F3：模型叫不動（連不上、逾時、取壞了）：假人這一爐不開，不用字表名字搶下首創（那正是會被看出來的情況）——
    真人在模型掛掉時會走字表，但真人本來就什麼名字都有，假人一個接一個都是字表風格就不一樣。沒收費、下次再來。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)
    monkeypatch.setattr(naming, "generate", _namer(world, [], fail=True))
    report = runner.tick()
    assert report.named == 1 and report.failed == 0
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None
    bot_state = next(s for s in _bots() if s.player.insights == ["feng"])
    assert library.owned_arts(bot_state) == ["basic_fist"] and bot_state.player.stats["xinde"] == 100
    runner.tick()  # 時鐘沒動：還在間隔裡，不會立刻再叫一次
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None


def test_a_failed_naming_goes_through_for_a_pick_but_not_for_a_new_name(runner, world, content, clock, monkeypatch):
    """取名失敗跳過 C 段只針對「沒有候選的取名單」：挑一個的單（choices 不空）沒挑到，C 段照常跑，由規則挑，不產生新名字。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)
    monkeypatch.setattr(naming, "generate", _namer(world, [], fail=True))
    applied = []
    monkeypatch.setattr(bot_policy, "apply_job", lambda game, job, proposed: applied.append(job) or [])
    name = _bots()[0].player.name
    ask = bot_policy.ForgeJob("basic_fist", ("feng",), None, naming.NamingRequest("fuse", "k", "武學", []))
    pick = bot_policy.ForgeJob(
        "basic_fist", ("feng",), None, naming.NamingRequest("fuse", "k", "武學", [], choices=("甲", "乙")),
    )
    runner._name_and_apply(name, ask, bot_runner.TickReport())
    assert applied == []
    runner._name_and_apply(name, pick, bot_runner.TickReport())
    assert applied == [pick]


def test_a_failed_mastery_naming_still_names_with_a_different_word_list_name(
    runner, world, content, clock, monkeypatch,
):
    """絕學定名不一樣：模型叫不動也要定（沿用原名江湖史同一個名字出現兩次，看得出是假人），用字表另組、一定跟原名不同。"""
    victim = _master_ready(runner, content, world, clock, monkeypatch)
    monkeypatch.setattr(naming, "generate", _namer(world, [], fail=True))
    assert runner.tick().failed == 0
    assert open_characters().load(victim).player.naming is None
    lines = [r.text for r in world.get_season().chronicle if "練成絕學，為之定名【" in r.text]
    assert len(lines) == 1 and "為之定名【凌風拳】" not in lines[0]


def test_a_bot_that_lost_the_lock_after_naming_drops_the_name(runner, world, content, clock, monkeypatch):
    """C 段拿不到鎖（真人拿著）：放掉這一件，什麼都沒開、沒收費，算一次等鎖跳過。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)
    monkeypatch.setattr(bot_runner, "LOCK_WAIT", 0.05)
    holder = Database(world.db.path)  # 另一組連線，像真人那邊的程式
    held = []

    def generate(client, content_, request, budget=None, person=None):
        _check_b_call(world, content_, budget, person)
        transaction = holder.transaction()
        transaction.__enter__()  # 取名的時候（鎖外），真人接著拿了行動鎖
        held.append(transaction)
        return ("凌風拳", "一句話。")

    monkeypatch.setattr(naming, "generate", generate)
    try:
        report = runner.tick()
    finally:
        for transaction in held:
            transaction.__exit__(None, None, None)
        holder.close()
    assert report.named == 1 and report.skipped >= 1
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None
    bot_state = next(s for s in _bots() if s.player.insights == ["feng"])
    assert library.owned_arts(bot_state) == ["basic_fist"] and bot_state.player.stats["xinde"] == 100


def test_a_season_that_ended_while_the_bot_waited_for_a_name_applies_nothing(runner, world, content, clock, monkeypatch):
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)

    def generate(client, content_, request, budget=None, person=None):
        _check_b_call(world, content_, budget, person)
        world.mutate_season(lambda season: setattr(season, "ended", True))  # 取名的時候季結束了
        return ("凌風拳", "一句話。")

    monkeypatch.setattr(naming, "generate", generate)
    report = runner.tick()
    assert report.named == 1  # 名字確實請過了（不是根本沒開單）
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None


def test_the_apply_step_syncs_the_bot_first_so_a_season_that_ran_out_meanwhile_is_seen(
    runner, world, content, clock, monkeypatch,
):
    """C 段重讀角色之後先 game.sync：取名花的時間讓季走到了季末，補算會把季收掉，那一爐就不開、不收費。
    沒有 sync，重讀的角色身上掛的是空的賽季（不是這一季）：看不出季已經完了、照樣開爐，還會把一份空的賽季寫回全服。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)
    trends = []

    def generate(client, content_, request, budget=None, person=None):
        _check_b_call(world, content_, budget, person)
        world.mutate_season(lambda season: setattr(season, "time", content.config.season_days * 86400 - 30))
        trends.append(dict(world.get_season().trends))
        clock[0] += 3600  # 取名花了一小時：C 段拿到鎖補算的時候，季就走過季末了
        return ("凌風拳", "一句話。")

    monkeypatch.setattr(naming, "generate", generate)
    report = runner.tick()
    assert report.named == 1 and report.failed == 0
    assert world.get_season().ended  # 補算把它收了
    assert trends[0] and set(world.get_season().trends) == set(trends[0])  # 全服的賽季沒被空的賽季蓋掉（補算本來就會動數字）
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None
    bot_state = next(s for s in _bots() if s.player.insights == ["feng"])
    assert library.owned_arts(bot_state) == ["basic_fist"] and bot_state.player.stats["xinde"] == 100


def test_a_bot_retired_by_a_new_season_while_waiting_for_a_name_is_left_alone(
    runner, world, content, clock, monkeypatch,
):
    """取名的時候管理者開了下一季：第 1 季的假人都算退隱，C 段不能把它補算進新的一季、存成這一季的角色
    （它會帶著新的賽季號出現在榜單上，直到被叫醒）。存檔一個位元都不動、什麼都沒開。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)
    snapshots = []

    def generate(client, content_, request, budget=None, person=None):
        _check_b_call(world, content_, budget, person)
        world.mutate_season(lambda season: setattr(season, "ended", True))
        assert world.next_season(content, now=clock[0])
        clock[0] += 120  # 取名花了一點時間：C 段要是還去補算、存檔，角色的 last_real 就變了
        snapshots.append(_saves_snapshot())
        return ("凌風拳", "一句話。")

    monkeypatch.setattr(naming, "generate", generate)
    report = runner.tick()
    assert report.named == 1 and report.failed == 0
    assert _saves_snapshot() == snapshots[0]
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "feng")) is None


def test_a_pause_that_starts_while_the_bot_waited_for_a_name_registers_no_recipe(
    runner, world, content, clock, monkeypatch,
):
    """賽季時鐘暫停（第 13 列）：取名的時候管理者按了暫停，C 段不能開爐、不能登記配方（暫停中全服不動）。
    名字丟掉、不收費；繼續之後照常再取一次。tick 與 _take_turn 的暫停判斷管不到 C 段：它是另外拿一次鎖。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)
    calls = []

    def generate(client, content_, request, budget=None, person=None):
        _check_b_call(world, content_, budget, person)
        calls.append(request.kind)
        if len(calls) == 1:
            assert world.pause_clock(clock[0])  # 取名的時候，管理者按了暫停
        return ("凌風拳", "一句話。")

    monkeypatch.setattr(naming, "generate", generate)
    report = runner.tick()
    assert report.named == 1 and report.failed == 0
    key = fusion.fuse_key("basic_fist", "feng")
    assert world.paused_at() is not None and world.lookup_recipe(key) is None
    bot_state = next(s for s in _bots() if s.player.insights == ["feng"])
    assert library.owned_arts(bot_state) == ["basic_fist"] and bot_state.player.stats["xinde"] == 100
    world.resume_clock(content, clock[0])
    clock[0] += content.config.bot_naming_gap_seconds
    assert _tick_cleanly(runner).named == 1
    assert world.lookup_recipe(key).name == "凌風拳"  # 繼續之後照常取名、登記


def test_a_pause_that_starts_while_the_bot_waited_to_name_a_mastered_art_names_nothing(
    runner, world, content, clock, monkeypatch,
):
    victim = _master_ready(runner, content, world, clock, monkeypatch)
    pending = open_characters().load(victim).player.naming

    def generate(client, content_, request, budget=None, person=None):
        _check_b_call(world, content_, budget, person)
        assert world.pause_clock(clock[0])
        return ("破雲拳", "一句話。")

    monkeypatch.setattr(naming, "generate", generate)
    report = runner.tick()
    assert report.named == 1 and report.failed == 0
    assert open_characters().load(victim).player.naming == pending  # 還等著定名
    assert not any("為之定名" in r.text for r in world.get_season().chronicle)


def test_a_failure_while_naming_is_counted_and_leaves_no_name_behind(
    runner, world, content, clock, monkeypatch, capsys, caplog,
):
    """取名那一段出錯：算一次出錯、不讓整個程式倒下，log 與主控台都看不到名號（連例外訊息裡的也不寫）。"""
    runner.client = object()
    _armed_bots(runner, content, clock, monkeypatch)
    victim = next(s for s in _bots() if s.player.insights == ["feng"]).player.name

    def generate(client, content_, request, budget=None, person=None):
        raise OSError(f"連不上（{victim}）")

    monkeypatch.setattr(naming, "generate", generate)
    capsys.readouterr()
    with caplog.at_level(logging.DEBUG):
        report = runner.tick()
    assert report.failed == 1 and "OSError" in caplog.text
    assert _identity_free(victim, capsys, caplog)


def test_a_bot_game_has_no_client_and_a_fresh_model_budget(runner, content, monkeypatch):
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: False)
    content.config.bots_min_per_faction = 1
    runner.tick()
    state = _bots()[0]
    runner.client = object()  # 就算假人程式有 client，鎖內的 Game 也不接
    resets = []
    monkeypatch.setattr(Game, "reset_model_budget", lambda self: resets.append(self))
    game = runner._bot_game(state)
    assert game.client is None and game.rng is runner.rng and resets == [game]


def test_the_naming_slot_opens_only_with_a_client_the_setting_and_a_quiet_gap(runner, content, clock):
    cfg = content.config
    assert not runner._naming_open()  # 沒有 client
    runner.client = object()
    assert runner._naming_open()  # 還沒請過
    cfg.bot_naming = False
    assert not runner._naming_open()
    cfg.bot_naming = True
    runner.last_naming = clock[0]
    assert not runner._naming_open()
    clock[0] += cfg.bot_naming_gap_seconds - 1
    assert not runner._naming_open()
    clock[0] += 1
    assert runner._naming_open()


def test_every_lock_hold_resets_the_in_lock_model_budget(runner, content, clock, monkeypatch):
    resets = []
    monkeypatch.setattr(Game, "reset_model_budget", lambda self: resets.append(1))
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    content.config.bots_min_per_faction = 1
    content.config.bot_tick_seconds = 1000
    runner.tick()
    clock[0] += 60
    report = runner.tick()
    assert len(resets) >= report.acted


def test_the_naming_settings_follow_the_planners_numbers(content):
    cfg = content.config
    assert cfg.bot_naming is True
    assert (cfg.bot_naming_gap_seconds, cfg.bot_naming_budget_seconds) == (120, 30)


def test_run_bots_gives_the_runner_a_model_client(monkeypatch):
    seen = {}

    class Spy(BotRunner):
        def __init__(self, content, *args, **kwargs):
            seen["client"] = kwargs.get("client")
            super().__init__(content, *args, **kwargs)

    monkeypatch.setattr(run_bots, "BotRunner", Spy)
    monkeypatch.setattr(run_bots.time, "sleep", lambda s: None)
    run_bots.main(ticks=1)
    assert seen["client"] is not None and seen["client"].model


def test_run_bots_gives_no_client_when_bot_naming_is_off(monkeypatch):
    seen = {}
    real_load = run_bots.load_content

    def load(*args, **kwargs):
        content = real_load(*args, **kwargs)
        content.config.bot_naming = False
        return content

    class Spy(BotRunner):
        def __init__(self, content, *args, **kwargs):
            seen["client"] = kwargs.get("client", "missing")
            super().__init__(content, *args, **kwargs)

    monkeypatch.setattr(run_bots, "load_content", load)
    monkeypatch.setattr(run_bots, "BotRunner", Spy)
    monkeypatch.setattr(run_bots.time, "sleep", lambda s: None)
    run_bots.main(ticks=1)
    assert seen["client"] is None


def test_run_bots_prints_how_many_names_it_asked_for_and_never_a_name(monkeypatch, capsys):
    monkeypatch.setattr(run_bots.time, "sleep", lambda s: None)
    monkeypatch.setattr(BotRunner, "tick", lambda self: bot_runner.TickReport(online=3, named=2))
    run_bots.main(ticks=1)
    assert "取名 2" in capsys.readouterr().out


def test_bots_sit_out_a_paused_season(runner, world, clock, content, monkeypatch):
    """賽季時鐘暫停（線上架構 8.3）：假人程式這一輪什麼都不做——不補人、不出手、不推時鐘；繼續之後照常補人。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    assert runner.tick().added == 2  # 兩個陣營各補一位
    name = _bots()[0].player.name
    season_time = world.get_season().time
    world.pause_clock(clock[0])
    clock[0] += content.config.bot_fill_seconds
    report = runner.tick()
    assert (report.online, report.acted, report.added) == (0, 0, 0)
    assert len(_bots()) == 2
    assert runner._take_turn(name, clock[0]) is False
    assert world.get_season().time == season_time
    world.resume_clock(content, clock[0])
    assert runner.tick().added == 2


def test_a_pause_that_commits_while_the_bot_waited_for_the_fill_lock_adds_no_bots(runner, world, clock, content):
    """tick 一開頭看到的是沒暫停，之後等補人的行動鎖等到管理者的暫停先寫進去：拿到鎖之後 _fill 自己再看一次，
    不補人（不然暫停中還會多出兩位假人）。直接呼叫 _fill 就是「拿到鎖之後」那一刻。"""
    world.pause_clock(clock[0])
    report = bot_runner.TickReport()
    runner._fill(clock[0], report)
    assert report.added == 0 and _bots() == []
    world.resume_clock(content, clock[0])
    runner._fill(clock[0], report)
    assert report.added == 2  # 繼續之後照常補
