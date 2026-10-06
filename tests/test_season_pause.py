"""公告停機時賽季時鐘暫停（線上架構設計第四節、8.3；賽季計畫 Task 2、3）。"""
import math
import random

import pytest

from conftest import at, install_season_one, install_showdowns
from test_engine import (
    _install_battle_def, _install_battle_def_with_free_text, _join_and_open, _settle_without_fighters, _showdown_game,
    _to_showdown,
)
from tianxia import calendar, database
from tianxia.engine import PAUSED_TEXT, Game
from tianxia.models import BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome
from tianxia.sqlite_world import open_world
from tianxia.state import TimelineResult
from tianxia.world import keep_showdowns_on_time, resume_season_clock, start_pending_battle
from tianxia.world_state import fresh_season, season_length_days


@pytest.fixture
def store(content):
    store = open_world()
    store.seed_first_season(content)  # 測試內容直接開季
    return store


def _definition():
    return BattleDef(
        id="b1", name="測試戰", factions=[BattleFaction(id="a", name="甲方"), BattleFaction(id="b", name="乙方")],
        acts=[BattleAct(id="a1", title="開戰", text="開戰了。", goal="打贏", options=[BattleOption(text="進攻", tag="go")])],
        action_tags={"go": BattleActionEffect(trend_delta=1, neili_damage=5)},
        outcomes=[BattleOutcome(faction="a", title="甲方勝", text="甲方贏了。")],
        muster_seconds=600, round_seconds=120,
    )


# ── Task 2：資料庫裡的暫停 ──────────────────────────────────


def test_a_paused_season_clock_does_not_move_and_resume_skips_the_paused_span(store, content):
    """暫停中補算不推季的時間、對時點也不動；繼續之後停的那四個鐘頭不算進賽季（beta 那一季：一秒不差）。"""
    rng = random.Random(0)
    store.catch_up_season(content, 1000.0, rng)  # 記下時鐘
    store.catch_up_season(content, 1600.0, rng)
    assert store.pause_clock(1600.0)
    assert store.paused_at() == 1600.0
    assert store.catch_up_season(content, 1600.0 + 4 * 3600, rng) == []
    assert store.get_season().time == 600 * content.config.time_scale
    assert store.read().season_last_real == 1600.0
    assert store.resume_clock(content, 1600.0 + 4 * 3600) == 4 * 3600
    assert store.paused_at() is None
    store.catch_up_season(content, 1600.0 + 4 * 3600 + 300, rng)
    assert store.get_season().time == (600 + 300) * content.config.time_scale


def test_resume_still_counts_the_bit_before_the_pause_that_nobody_caught_up(store, content):
    """主機端腳本直接暫停（沒先補算）：暫停前還沒補算的那一小段，繼續之後照算，一秒不少。"""
    rng = random.Random(0)
    store.catch_up_season(content, 1000.0, rng)
    assert store.pause_clock(1300.0)  # 1000～1300 這段沒人補算
    store.resume_clock(content, 1300.0 + 7200)
    store.catch_up_season(content, 1300.0 + 7200 + 100, rng)
    assert store.get_season().time == (300 + 100) * content.config.time_scale


def test_pause_only_while_running_and_only_once(store, content):
    assert store.pause_clock(1000.0)
    assert not store.pause_clock(2000.0)  # 已經停著：不改起點
    assert store.paused_at() == 1000.0
    assert store.resume_clock(content, 1500.0) == 500.0
    assert store.resume_clock(content, 1600.0) is None  # 沒在暫停
    store.mutate_season(lambda s: setattr(s, "ended", True))
    assert not store.pause_clock(1700.0)  # 休季沒有時鐘可停
    assert store.paused_at() is None


def test_a_preparing_season_cannot_be_paused(content):
    content.config.auto_open_first_season = False
    store = open_world()
    store.seed_first_season(content)
    assert store.season_phase() == "preparing"
    assert not store.pause_clock(1000.0)


def test_resume_shifts_the_muster_deadline_and_the_open_round(store, content):
    """決戰的現實期限往後挪停的長度：集結、這一回合剩下的時間都跟暫停前一樣。"""
    battle = store.start_battle(_definition(), now=1000.0)
    assert battle.muster_deadline_real == 1600.0
    store.pause_clock(1100.0)
    store.resume_clock(content, 1100.0 + 3600)
    assert store.get_battle().muster_deadline_real == 1600.0 + 3600
    store.mutate_battle(lambda b: (setattr(b, "phase", "active"), setattr(b.round, "opened_real", 9000.0)))
    deadline = store.get_battle().muster_deadline_real
    store.pause_clock(9060.0)
    store.resume_clock(content, 9060.0 + 600)
    battle = store.get_battle()
    assert battle.round.opened_real == 9000.0 + 600
    assert battle.muster_deadline_real == deadline  # 開打之後集結截止不動（它也是這一場的識別值，假人程式看它）


def test_a_world_row_from_before_the_pause_field_reads_as_not_paused(store, content):
    """舊資料庫（這一欄上線之前存的 world 那一列，JSON 裡沒有 paused_at）：讀成沒有暫停，之後照樣能暫停。"""
    with store.db.transaction() as conn:
        conn.execute("UPDATE world SET data = json_remove(data, '$.paused_at') WHERE id = 1")
        assert "paused_at" not in conn.execute("SELECT data FROM world WHERE id = 1").fetchone()["data"]
    assert store.paused_at() is None and store.read().paused_at is None
    assert store.pause_clock(5.0) and store.paused_at() == 5.0


def test_the_pause_survives_a_restart(tmp_path, content):
    """伺服器停掉再開（重開資料庫）：暫停還在，要按「繼續」才走。"""
    path = tmp_path / "w.db"
    store = open_world(path)
    store.seed_first_season(content)
    store.pause_clock(1000.0)
    database.close_all()
    assert open_world(path).paused_at() == 1000.0


# ── Task 2：繼續之後排好的決戰照原本的現實時間開（企劃者 2026-10-06 定 B3、B11）────────


def _season_one_store(content):
    install_season_one(content)
    install_showdowns(content)
    store = open_world()
    store.seed_first_season(content)
    return store


def _grid(content, store) -> float:
    """一個曆時是幾個現實秒（季的事只在曆時交界跑；週末那季是 1 分 47 秒）。"""
    return calendar.cal_hour_seconds(content, store.get_season()) / content.config.time_scale


def test_resume_moves_unopened_showdowns_earlier_and_leaves_the_season_end(content):
    """停三個鐘頭：還沒開的決戰往前挪「跳過的長度」，現實時間不變；季末不挪，現實時間往後延。跳過的長度照整個曆時往下取整
    （曆時的交界在現實時間上才不動），所以季末晚了將近三個鐘頭、差不到一個曆時。"""
    store = _season_one_store(content)
    rng, scale = random.Random(0), content.config.time_scale
    store.catch_up_season(content, 0.0, rng)
    store.catch_up_season(content, 3600.0, rng)
    before = dict(store.get_season().schedule)
    store.pause_clock(3600.0)
    assert store.resume_clock(content, 3600.0 + 3 * 3600) == 3 * 3600
    grid = _grid(content, store)
    skipped = math.floor(3 * 3600 / grid + 1e-9) * grid
    assert 3 * 3600 - grid < skipped <= 3 * 3600
    after = store.get_season().schedule
    assert after["finale"] == before["finale"]
    for key in ("changshe_fire", "wancheng"):
        assert after[key] == pytest.approx(before[key] - skipped * scale)
    assert store.read().season_last_real == pytest.approx(3600.0 + skipped)
    assert store.get_season().showdowns_waiting == []


def test_a_showdown_whose_time_passed_during_the_pause_opens_at_resume(content):
    """長社原本的時間落在暫停裡：繼續時改排在這一刻、記進排隊，緊接著補算再 start_pending_battle 就開集結（集結截止從這一刻算）；
    宛城還沒到，照樣往前挪、不開。這一條拆開來測 resume_clock 本身留下的狀態（真正的「繼續」走 resume_season_clock，
    見下面的測試）：停之前剛補算過，補算只剩不到一個曆時的零頭。"""
    store = _season_one_store(content)
    rng, scale = random.Random(0), content.config.time_scale
    store.catch_up_season(content, 0.0, rng)
    changshe = store.get_season().schedule["changshe_fire"]
    paused = (changshe - 600) / scale  # 長社前十分鐘（季時間）
    store.catch_up_season(content, paused, rng)
    store.pause_clock(paused)
    resumed = paused + 12 * 3600
    store.resume_clock(content, resumed)
    season = store.get_season()
    assert season.showdowns_waiting == ["changshe_fire"]
    season_now = season.time + (resumed - store.read().season_last_real) * scale  # 繼續那一刻的季時間
    assert season.schedule["changshe_fire"] == pytest.approx(season_now)
    assert season.schedule["wancheng"] > season_now and "wancheng" not in season.showdowns_waiting
    msgs = store.catch_up_season(content, resumed, rng) + start_pending_battle(store, content, resumed)
    battle = store.get_battle()
    assert (battle.battle_id, battle.phase) == ("changshe_fire", "muster")
    assert battle.muster_deadline_real == resumed + content.battles["changshe_fire"].muster_seconds
    assert any("集結號角" in m for m in msgs)
    assert store.get_season().showdowns_opened == {"changshe_fire": "changshe_fire"}


@pytest.mark.parametrize(("now_week", "lands_at"), [
    # 往前挪剛好落在一件還沒結算的一般大事上（第 4 週週一 00:00 的波才）：再往後挪一個曆時，不然那件大事先結算、
    # 長社就被照起點判掉（T10 審查 I1，跟管理者排時間同一條規則）
    pytest.param(3, lambda c, s: calendar.week_start(4, c, s), id="onto-a-regular-event"),
    # 停得很久，長社往前挪到第 3 週（張曼成、波才都還沒結算）：時刻表的先後不能亂，最早排在原本排在它前面的最後一件
    # （第 4 週週一的波才）之後一個曆時（B13）
    pytest.param(2, lambda c, s: calendar.week_start(3, c, s) + 5 * calendar.cal_hour_seconds(c, s), id="ahead-of-earlier-events"),
])
def test_a_moved_showdown_steps_off_a_regular_event(content, now_week, lands_at):
    """暫停之後決戰往前挪：挪到的時刻不能落在、也不能早於排在它前面還沒結算的一般大事；最早是那一件之後一個曆時。"""
    install_season_one(content)
    install_showdowns(content)
    season = fresh_season(content)
    season.time = calendar.week_start(now_week, content, season) + 1
    week4 = calendar.week_start(4, content, season)
    shift = season.schedule["changshe_fire"] - lands_at(content, season)
    keep_showdowns_on_time(season, content, shift / content.config.time_scale, season.time)
    assert season.schedule["changshe_fire"] == pytest.approx(week4 + calendar.cal_hour_seconds(content, season))
    assert season.showdowns_waiting == []


def test_without_season_one_resume_moves_no_schedule(store, content):
    """開關關著（beta 那一季沒有季曆、沒有排好的決戰）：照停的長度一秒不差地跳過，排定一樣都不動。"""
    store.catch_up_season(content, 1000.0, random.Random(0))
    store.mutate_season(lambda s: s.schedule.update(finale=99999.0))
    store.pause_clock(1000.0)
    store.resume_clock(content, 1000.0 + 1234.5)
    assert store.get_season().schedule == {"finale": 99999.0}
    assert store.read().season_last_real == 1000.0 + 1234.5


# ── 「繼續」的順序：resume_season_clock（resume_clock → 補算 → 開集結）──────────────────────────


def _muster_lines(lines) -> list[str]:
    return [m for m in lines if "集結號角" in m]


def test_resuming_an_unpaused_clock_does_nothing(store, content):
    assert resume_season_clock(store, content, 1000.0, random.Random(0), "停了 {minutes} 分鐘") is None
    assert store.get_season().time == 0.0 and store.paused_at() is None


def test_resume_after_an_uncaught_span_settles_the_earlier_events_before_the_showdown_opens(content):
    """主機端直接暫停（沒先補算）、停得很久：暫停前還沒補算的那一大段（裡面有第 4 週的波才）繼續當下還沒推。
    「繼續」的順序是 resume_clock → catch_up_season → start_pending_battle：先補算，波才先結算，長社才開集結——
    省掉補算、直接 start_pending_battle 的話，長社會在波才還沒結算（時間軸上沒有）時就開成，前線起點、之後宛城的版本都亂了。
    resume_season_clock 把三步包在一起，三條「繼續」的路（管理者按鈕、主機端腳本、模擬）都走它。"""
    store = _season_one_store(content)
    rng, scale = random.Random(0), content.config.time_scale
    store.catch_up_season(content, 0.0, rng)  # 記下時鐘，之後直到暫停都沒人補算
    changshe = store.get_season().schedule["changshe_fire"]
    paused = (changshe - 600) / scale  # 停在長社前十分鐘（季時間）：0～paused 這一大段（第 4 週的波才在裡面）沒人補算
    assert store.pause_clock(paused)
    resumed = paused + 40 * 3600
    lines = resume_season_clock(store, content, resumed, rng, "停了 {minutes} 分鐘")
    battle, season = store.get_battle(), store.get_season()
    assert (battle.battle_id, battle.phase) == ("changshe_fire", "muster")
    assert battle.muster_deadline_real == resumed + content.battles["changshe_fire"].muster_seconds
    assert "bocai" in season.timeline and "changshe_fire" not in season.timeline
    assert season.showdowns_opened == {"changshe_fire": "changshe_fire"} and season.showdowns_waiting == []
    assert lines[0].startswith("停了 ") and len(_muster_lines(lines)) == 1  # 繼續的那一行，加上開集結的那一行（只一句）
    assert store.paused_at() is None


def test_when_the_catch_up_has_nothing_to_advance_start_pending_battle_opens_the_showdown(content):
    """繼續那一刻剛好落在曆時交界上（停的長度是整數個曆時）：補算沒有零頭可推、什麼都不做回 []，長社由 start_pending_battle 開，
    集結號角在它的回傳裡——所以 resume_season_clock 兩邊的訊息都要接上。數字挑成二進位小數（季長 2.625 天、
    time_scale 1：一個曆時剛好 112.5 個現實秒），不會有浮點誤差。"""
    install_season_one(content)
    content.config.season_days, content.config.time_scale = 2.625, 1.0
    install_showdowns(content)
    store = open_world()
    store.seed_first_season(content)
    rng, grid = random.Random(0), _grid(content, store)
    assert grid == 112.5
    store.catch_up_season(content, 0.0, rng)
    paused = store.get_season().schedule["changshe_fire"] - 600  # time_scale 1：季秒就是現實秒
    store.catch_up_season(content, paused, rng)
    assert store.pause_clock(paused)
    resumed = paused + 400 * grid
    assert store.resume_clock(content, resumed) == 400 * grid
    assert store.get_season().showdowns_waiting == ["changshe_fire"]
    assert store.catch_up_season(content, resumed, rng) == [] and store.get_battle() is None  # 補算什麼都沒推、什麼都沒開
    opened = start_pending_battle(store, content, resumed)
    assert len(_muster_lines(opened)) == 1 and store.get_battle().battle_id == "changshe_fire"


def test_the_resume_helper_keeps_the_muster_call_when_only_start_pending_battle_opens(content):
    """同一個交界上的情形，走 resume_season_clock：集結號角那一行還在回傳裡（只一句）。"""
    install_season_one(content)
    content.config.season_days, content.config.time_scale = 2.625, 1.0
    install_showdowns(content)
    store = open_world()
    store.seed_first_season(content)
    rng, grid = random.Random(0), _grid(content, store)
    store.catch_up_season(content, 0.0, rng)
    paused = store.get_season().schedule["changshe_fire"] - 600
    store.catch_up_season(content, paused, rng)
    store.pause_clock(paused)
    lines = resume_season_clock(store, content, paused + 400 * grid, rng, "停了 {minutes} 分鐘")
    assert lines[0] == "停了 750 分鐘" and len(_muster_lines(lines)) == 1 and len(lines) == 2
    assert store.get_battle().battle_id == "changshe_fire"


# ── keep_showdowns_on_time 的幾道防線 ──────────────────────────────────────


def _fresh_season_one(content):
    install_season_one(content)
    install_showdowns(content)
    return fresh_season(content)


def test_a_moved_showdown_that_lands_on_a_regular_event_steps_off_it_even_when_nothing_was_skipped(content):
    """往後挪（B13）之後 clear_of_events 照樣跑：這裡沒停過（挪 0），長社排的時間剛好跟兩件還沒結算的一般大事
    （第 7 週週一的盧植圍廣宗、秦頡）同一刻——再往後挪一個曆時。"""
    season = _fresh_season_one(content)
    week7 = calendar.week_start(7, content, season)
    season.schedule["changshe_fire"] = week7
    keep_showdowns_on_time(season, content, 0.0, season.time)
    assert season.schedule["changshe_fire"] == pytest.approx(week7 + calendar.cal_hour_seconds(content, season))


def test_a_regular_event_at_the_showdowns_own_time_does_not_hold_back_the_move(content):
    """B13 只看原本排在它「前面」的大事（嚴格小於）：同一刻的不算——長社原本跟盧植圍廣宗同在第 7 週週一，
    停了三個曆時，往前挪三個曆時就好，不會被同一刻那件拖到它後面去。"""
    season = _fresh_season_one(content)
    week7 = calendar.week_start(7, content, season)
    cal_hour = calendar.cal_hour_seconds(content, season)
    season.schedule["changshe_fire"] = week7
    keep_showdowns_on_time(season, content, 3 * cal_hour / content.config.time_scale, season.time)
    assert season.schedule["changshe_fire"] == pytest.approx(week7 - 3 * cal_hour)


@pytest.mark.parametrize("state", ["waiting", "opened", "resolved"])
def test_a_showdown_that_is_already_waiting_open_or_settled_is_left_alone(content, state):
    """已經在排隊、已經開過、已經收場的決戰，繼續時不動它的排定（不然排隊中的會被排兩次、收場的又被排回去）。"""
    season = _fresh_season_one(content)
    season.time = calendar.week_start(3, content, season) + 1
    before = season.schedule["changshe_fire"]
    if state == "waiting":
        season.showdowns_waiting.append("changshe_fire")
    elif state == "opened":
        season.showdowns_opened["changshe_fire"] = "changshe_fire"
    else:
        season.timeline["changshe_fire"] = TimelineResult(key="guan:險勝", time=0.0)
    keep_showdowns_on_time(season, content, before / content.config.time_scale, season.time)
    assert season.schedule["changshe_fire"] == before
    assert season.showdowns_waiting == (["changshe_fire"] if state == "waiting" else [])


# ── 伺服器排程（Game.world_tick）暫停中也不推 ──────────────────────────────


def test_the_scheduler_tick_does_not_move_a_paused_season(store, content):
    """伺服器排程（Game.world_tick）暫停中什麼都不推——季的時間不走、再久也不收季；繼續之後從停的那一刻接著走。
    排程走的就是 catch_up_season 這個關口（暫停中不推、對時點不動）。打到一半的決戰在排程那一路的逾時看的是另一個關口
    （Game._battle_status），見下面 test_the_scheduler_tick_waits_out_the_pause。"""
    ticker = Game.for_world(content, store, rng=random.Random(0))
    ticker.world_tick(1000.0)  # 記下時鐘
    ticker.world_tick(1600.0)
    stopped = store.get_season().time
    assert stopped == 600 * content.config.time_scale
    assert store.pause_clock(1600.0)
    far = 1600.0 + 3 * season_length_days(store.get_season(), content) * 86400 / content.config.time_scale  # 過了三個季長
    assert ticker.world_tick(far) == []
    assert (store.get_season().time, store.get_season().ended, store.season_phase()) == (stopped, False, "running")
    assert store.read().season_last_real == 1600.0
    store.resume_clock(content, far)
    ticker.world_tick(far + 10)
    assert store.get_season().time == stopped + 10 * content.config.time_scale
    assert not store.get_season().ended


def test_a_season_that_opens_or_turns_over_starts_unpaused(content):
    """N6：暫停不會漏進下一季（也不會漏進剛開的季）——開季、開下一季都把它清掉，就算存檔裡殘著一個舊的暫停。"""
    content.config.auto_open_first_season = False
    store = open_world()
    store.seed_first_season(content)
    store.mutate(lambda s: setattr(s, "paused_at", 123.0))  # 手改資料庫留下的殘值
    assert store.open_season(content, 1000.0)
    assert store.paused_at() is None
    store.mutate_season(lambda s: setattr(s, "ended", True))
    store.mutate(lambda s: setattr(s, "paused_at", 456.0))
    assert store.next_season(content, 2000.0)
    assert store.paused_at() is None and store.season_phase() == "running"


# ── Task 3：引擎（選單、決戰、快轉、管理者）────────────────────────


def test_the_admin_pauses_and_resumes_the_season_clock(content, world):
    """管理者按「暫停」：選單只剩一顆灰的、玩家什麼都做不了、季的時間不走、不能快轉，其他管理者動作也先擋著；
    按「繼續」：停的那兩個鐘頭不算進賽季。不是管理者的按不動。"""
    content.config.admins = ["掌門"]
    boss = Game.new(content, "掌門", rng=random.Random(0), world=world)
    other = Game.new(content, "路人", rng=random.Random(1), world=world)
    boss.sync(1000.0)
    assert "只有管理者" in other.admin_pause_clock(1000.0)[0]
    assert "賽季時鐘停了" in boss.admin_pause_clock(1000.0)[0]
    assert world.paused_at() == 1000.0
    assert "已經停著" in boss.admin_pause_clock(1100.0)[0]
    boss.sync(1000.0 + 7200)
    assert world.get_season().time == 0.0 and boss.paused_minutes() == 120
    assert [o.id for o in other.options()] == ["season:paused"]
    assert other.choose("act:explore") == ["（此刻無法這麼做。）"]
    assert "暫停中" in boss.advance(3600)[0]
    assert "暫停中" in boss.admin_push_trend("kou", 5)[0]
    assert "暫停中" in boss.admin_end_season(1000.0 + 7200)[0]
    assert world.season_phase() == "running" and world.get_season().time == 0.0
    assert "只有管理者" in other.admin_resume_clock(1000.0 + 7200)[0]
    assert "停了 120 分鐘" in boss.admin_resume_clock(1000.0 + 7200)[0]
    assert world.paused_at() is None and boss.paused_minutes() is None
    assert "沒有暫停" in boss.admin_resume_clock(1000.0 + 7300)[0]
    boss.sync(1000.0 + 7200 + 60)
    assert world.get_season().time == pytest.approx(60 * content.config.time_scale)
    titles = [e.title for e in boss.state.journal]
    assert "暫停賽季" in titles and "繼續賽季" in titles


def test_the_muster_countdown_stands_still_while_paused(content, game):
    """暫停中集結不倒數：畫面上剩下的時間停在按下暫停那一刻（截止 1600、1100 暫停：剩 500 秒）。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    game.world.pause_clock(1100.0)
    with at(game, 5000.0):
        assert "還剩現實 8 分 20 秒" in game.scene_text()


def test_a_running_showdown_round_waits_out_the_pause_and_keeps_its_remaining_time(content, world):
    """長社打到第一回合一半（120 秒過了 60 秒）時暫停十個鐘頭：這段時間每次刷新（options 的 tick）都不逾時、不代選；
    繼續之後還剩 60 秒——59 秒時還沒逾時，61 秒時逾時、系統代選、結算這一回合。"""
    game = _showdown_game(content, world)
    _to_showdown(game, "changshe_fire")
    with at(game, game.now):
        game.choose("battle:join:guan")
    deadline = world.get_battle().muster_deadline_real
    with at(game, deadline):
        game.options()  # 集結截止：開打，這一回合從 deadline 起算
    battle = world.get_battle()
    assert battle.phase == "active" and battle.round.opened_real == deadline
    paused = deadline + 60
    assert world.pause_clock(paused)
    for now in (paused + 600, paused + 10 * 3600):
        with at(game, now):
            assert [o.id for o in game.options()] == ["season:paused"]
    battle = world.get_battle()
    assert battle.phase == "active" and battle.round_number == 0 and battle.round.pending_actions == {}
    resumed = paused + 10 * 3600
    world.resume_clock(content, resumed)
    assert world.get_battle().round.opened_real == deadline + 10 * 3600
    with at(game, resumed + 59):
        game.options()
    assert world.get_battle().round_number == 0
    with at(game, resumed + 61):
        game.options()
    assert world.get_battle().round_number == 1


def _real_time(game, key: str) -> float:
    """排在 schedule[key] 的那一刻是哪個現實時間（照這個 Game 剛同步過的季時間與 now 換算）。"""
    season = game.world.get_season()
    return game.now + (season.schedule[key] - season.time) / game.content.config.time_scale


def test_scheduled_showdowns_keep_their_real_time_across_a_three_hour_pause(content, world):
    """企劃者 2026-10-06 定 B3：長社前四個鐘頭暫停三個鐘頭，繼續之後長社照原本的現實時間開（前一秒還沒開、後一秒開集結）；
    季末往後延「跳過的長度」（三個鐘頭照整個曆時往下取整，差不到一個曆時）。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    game.sync(5000.0)
    changshe, finale = _real_time(game, "changshe_fire"), _real_time(game, "finale")
    paused = changshe - 4 * 3600
    game.sync(paused)
    assert "賽季時鐘停了" in game.admin_pause_clock(paused)[0]
    resumed = paused + 3 * 3600
    assert "停了 180 分鐘" in game.admin_resume_clock(resumed)[0]
    assert world.get_battle() is None
    game.sync(resumed + 1)
    grid = calendar.cal_hour_seconds(content, world.get_season()) / content.config.time_scale
    assert _real_time(game, "changshe_fire") == pytest.approx(changshe)
    assert 3 * 3600 - grid < _real_time(game, "finale") - finale <= 3 * 3600 + 1e-6
    game.sync(changshe - 1)
    assert world.get_battle() is None
    game.sync(changshe + 1)
    battle = world.get_battle()
    assert (battle.battle_id, battle.phase) == ("changshe_fire", "muster")
    assert battle.muster_deadline_real == pytest.approx(changshe + 1 + content.battles["changshe_fire"].muster_seconds)


def test_a_showdown_inside_the_pause_opens_at_resume_and_everything_fires_once(content, world):
    """長社排定前十分鐘（季時間）暫停十二個現實鐘頭——長社原本的時間、第 7 週大事原本的時間都落在暫停裡。
    暫停中每次同步、刷新都什麼都沒發生；管理者按「繼續」那一刻長社就開集結（B11，集結截止從那一刻算），
    沒人參戰照前線起點判；第 7 週的盧植圍廣宗跟著季往後延、照常結算——每件都只一次。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    scale = content.config.time_scale
    schedule = world.get_season().schedule["changshe_fire"]
    week7 = calendar.week_start(7, content, world.get_season())
    start = 5000.0
    game.sync(start)  # 記下時鐘
    paused = start + (schedule - 600) / scale
    game.sync(paused)
    assert world.get_season().time == pytest.approx(schedule - 600)
    game.admin_pause_clock(paused)
    resumed = paused + 12 * 3600
    for now in (paused + 3600, paused + 6 * 3600, resumed):
        game.sync(now)
        assert [o.id for o in game.options()] == ["season:paused"]
    season = world.get_season()
    assert season.time == pytest.approx(schedule - 600)
    assert world.get_battle() is None and season.showdowns_opened == {}
    assert "changshe_fire" not in season.timeline and "luzhi_siege" not in season.timeline
    msgs = game.admin_resume_clock(resumed)
    assert any("集結號角" in m for m in msgs)
    battle = world.get_battle()
    assert (battle.battle_id, battle.phase) == ("changshe_fire", "muster")
    assert battle.muster_deadline_real == pytest.approx(resumed + content.battles["changshe_fire"].muster_seconds)
    assert world.get_season().showdowns_opened == {"changshe_fire": "changshe_fire"}
    _settle_without_fighters(game, content.battles["changshe_fire"])
    game.sync(resumed + 1)
    later = game.now + (week7 - world.get_season().time) / scale + 60
    game.sync(later)
    game.sync(later + 60)
    season = world.get_season()
    assert {"changshe_fire", "luzhi_siege"} <= set(season.timeline)
    assert [b.battle_id for _, b in world.ended_battles()] == ["changshe_fire"]
    chronicle = [r.text for r in season.chronicle]
    assert chronicle.count("波才敗走陽翟。") == 1  # 長社：沒人參戰、起點 55 → 官軍險勝
    assert sum(chronicle.count(t) for t in ("盧植圍張角於廣宗。", "盧植圍廣宗不成。")) == 1


# ── 排程推決戰、「繼續」的順序與集結號角（引擎這一半）────────────────────────────


def test_the_scheduler_tick_waits_out_the_pause(content, world):
    """伺服器排程（Game.world_tick，沒有人在線）暫停中也不推決戰：集結截止不關、回合不逾時、季不動也不收；
    繼續之後剩下的時間跟暫停前一樣——集結還剩 100 秒、回合還剩 60 秒（補算與決戰兩個關口，見 Task 2、3）。"""
    game = _showdown_game(content, world)
    _to_showdown(game, "changshe_fire")
    with at(game, 0.0):
        game.choose("battle:join:guan")
    ticker = Game.for_world(content, world, rng=random.Random(1))
    battle = world.get_battle()
    deadline = battle.muster_deadline_real
    assert battle.phase == "muster"
    season_time = world.get_season().time
    assert world.pause_clock(deadline - 100)  # 集結截止前 100 秒暫停
    resumed = deadline + 3 * 86400
    for now in (deadline + 1, resumed):
        ticker.world_tick(now)
        assert world.get_battle().phase == "muster"
        assert not world.get_season().ended and world.get_season().time == season_time
    assert world.resume_clock(content, resumed) == resumed - (deadline - 100)
    ticker.world_tick(resumed + 99)
    assert world.get_battle().phase == "muster"
    ticker.world_tick(resumed + 101)
    assert world.get_battle().phase == "active" and world.get_battle().round_number == 0
    opened = world.get_battle().round.opened_real
    assert world.pause_clock(opened + 60)  # 這一回合過了 60 秒暫停
    ticker.world_tick(opened + 60 + 36000)
    assert (world.get_battle().phase, world.get_battle().round_number) == ("active", 0)
    assert world.resume_clock(content, opened + 60 + 36000) == 36000
    ticker.world_tick(opened + 36000 + 119)
    assert world.get_battle().round_number == 0
    ticker.world_tick(opened + 36000 + 121)
    assert world.get_battle().round_number == 1


def _paused_across_changshe(content, world) -> tuple[Game, float]:
    """管理者在長社前十分鐘（季時間）暫停、停十二個現實鐘頭：長社原本的時間落在暫停裡。回傳（管理者, 準備按「繼續」的現實時間）。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    start = 5000.0
    game.sync(start)
    paused = start + (world.get_season().schedule["changshe_fire"] - 600) / content.config.time_scale
    game.sync(paused)
    game.admin_pause_clock(paused)
    return game, paused + 12 * 3600


def test_resume_hands_the_muster_call_to_the_admin_when_the_catch_up_opens_the_showdown(content, world, monkeypatch):
    """「繼續」的順序（resume_season_clock：resume_clock → catch_up_season → start_pending_battle）：繼續之後還有不到一個曆時的零頭要補算，
    長社就是補算那一路（advance_season 結尾的 start_pending_battle）開的，集結號角在 catch_up_season 的回傳裡——
    admin_resume_clock 要把兩邊的訊息都接上，不然那一句會丟掉；它也要進管理者自己的江湖紀錄。"""
    game, resumed = _paused_across_changshe(content, world)
    real, caught = world.catch_up_season, []
    monkeypatch.setattr(world, "catch_up_season", lambda *a, **k: caught.append(real(*a, **k)) or caught[-1])
    msgs = game.admin_resume_clock(resumed)
    assert len(_muster_lines(caught[0])) == 1  # 開集結的是補算那一路
    assert len(_muster_lines(msgs)) == 1 and "賽季時鐘接著走了" in msgs[0]
    entry = next(e for e in game.state.journal if e.title == "繼續賽季")
    assert len(_muster_lines(entry.lines)) == 1
    assert world.get_battle().battle_id == "changshe_fire"


def test_resume_hands_the_muster_call_to_the_admin_when_nothing_is_left_to_catch_up(content, world, monkeypatch):
    """同一條的另一邊：繼續那一刻沒有零頭要補算（補算什麼都不做、回 []），長社由緊接著的 start_pending_battle 開，
    集結號角在它的回傳裡——一樣要接上、一樣只一句。"""
    game, resumed = _paused_across_changshe(content, world)
    monkeypatch.setattr(world, "catch_up_season", lambda *a, **k: [])
    msgs = game.admin_resume_clock(resumed)
    assert len(_muster_lines(msgs)) == 1
    assert world.get_battle().battle_id == "changshe_fire" and world.get_season().showdowns_waiting == []
    assert len(_muster_lines(next(e for e in game.state.journal if e.title == "繼續賽季").lines)) == 1


def test_resume_settles_the_events_before_the_showdown_after_an_uncaught_span(content, world):
    """暫停前有一大段沒人補算（沒開排程、半夜沒人同步），裡面的一般大事（第 4 週的波才）繼續當下才推。
    管理者按「繼續」：先補算，波才先結算，長社才開集結——不是長社先開、波才還在時間軸外面。"""
    install_season_one(content)
    install_showdowns(content)
    store = open_world()
    store.seed_first_season(content)
    content.config.admins = ["沈浪"]
    game = Game.new(content, "沈浪", rng=random.Random(0), world=store)
    game.now = 0.0
    store.catch_up_season(content, 0.0, random.Random(0))  # 記下時鐘，之後直到暫停都沒人補算
    paused = (store.get_season().schedule["changshe_fire"] - 600) / content.config.time_scale
    assert store.pause_clock(paused)  # 主機端那樣直接暫停：0～paused 沒補算
    msgs = game.admin_resume_clock(paused + 40 * 3600)
    assert len(_muster_lines(msgs)) == 1
    season = store.get_season()
    assert "bocai" in season.timeline and "changshe_fire" not in season.timeline
    assert (store.get_battle().battle_id, store.get_battle().phase) == ("changshe_fire", "muster")


def test_the_admin_resume_goes_through_the_one_resume_helper(content, world, monkeypatch):
    """每一條「繼續」的路都走 world.resume_season_clock（三步的順序只寫在那一個地方）：管理者的按鈕也是。"""
    game, resumed = _paused_across_changshe(content, world)
    calls = []
    from tianxia import engine

    real = engine.resume_season_clock
    monkeypatch.setattr("tianxia.engine.resume_season_clock", lambda *a, **k: calls.append(a) or real(*a, **k))
    game.admin_resume_clock(resumed)
    assert len(calls) == 1


# ── B12：跳過的長度照整個曆時往下取整（企劃者已定），繼續的那一行照實說 ───────────────────


@pytest.mark.parametrize("cal_hours", [0.35, 0.99, 1.01, 2.8, 100.8])
def test_admin_resume_counts_only_the_part_under_one_calendar_hour(content, world, cal_hours):
    """B12（已定）：停的長度照整個曆時往下取整才跳過，不足一個曆時的零頭算進賽季——所以停得比一個曆時（週末那季現實
    約 107 秒）短的話，繼續之後季的時間照常多走了那一段，什麼都沒扣。這是照規則走的，不是 bug；釘在這裡，免得有人
    把它「修」成退步。繼續那一行也照這個說：沒扣就說不另外扣，扣了就說扣多少。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    scale = content.config.time_scale
    game.sync(5000.0)
    grid = calendar.cal_hour_seconds(content, world.get_season()) / scale
    paused = 5000.0 + 7.3 * grid
    game.sync(paused)
    before = world.get_season().time
    game.admin_pause_clock(paused)
    resumed = paused + cal_hours * grid
    line = game.admin_resume_clock(resumed)[0]
    counted = (cal_hours - int(cal_hours)) * grid  # 整個曆時跳過，剩下的零頭照算
    assert world.get_season().time - before == pytest.approx(counted * scale, abs=1e-6)
    game.sync(resumed)
    assert world.get_season().time - before == pytest.approx(counted * scale, abs=1e-6)
    game.sync(resumed + 10)
    assert world.get_season().time - before == pytest.approx((counted + 10) * scale, abs=1e-6)
    if cal_hours < 1:
        assert "不另外扣" in line and "不算進賽季" not in line
    else:
        assert "不算進賽季" in line and "零頭" in line and "不另外扣" not in line


def _exact_season_one_store(content):
    """第一季、季長 2.625 天、time_scale 1：一個曆時剛好 112.5 個現實秒（二進位小數，算起來沒有浮點誤差）。"""
    install_season_one(content)
    content.config.season_days, content.config.time_scale = 2.625, 1.0
    install_showdowns(content)
    store = open_world()
    store.seed_first_season(content)
    store.catch_up_season(content, 0.0, random.Random(0))
    return store


@pytest.mark.parametrize(
    ("grids", "has", "lacks"),
    [
        (0.5, ["不到一個季曆鐘頭", "1 分 52 秒", "不另外扣"], ["不算進賽季，", "零頭"]),  # 56.25 秒：什麼都沒扣；一個曆時 112.5 秒
        (2.5, ["其中 3 分 45 秒不算進賽季", "季末往後延一樣長", "零頭（56 秒）照算進賽季"], ["不另外扣"]),  # 扣兩個曆時，零頭半個
        (3.0, ["這一段不算進賽季，季末往後延一樣長"], ["零頭", "不另外扣"]),  # 剛好整數個曆時：全扣
    ],
)
def test_the_resume_line_says_how_much_of_the_pause_was_skipped(content, grids, has, lacks):
    store = _exact_season_one_store(content)
    assert store.pause_clock(1000.0)
    text = resume_season_clock(store, content, 1000.0 + grids * 112.5, random.Random(0), "停了 {minutes} 分鐘：{skip}")[0]
    assert all(part in text for part in has), text
    assert not any(part in text for part in lacks), text


def test_the_resume_line_in_the_beta_season_skips_the_whole_pause(store, content):
    """開關關著（beta 那一季）：停的長度一秒不差地跳過，那一行就是整段都不算。"""
    assert store.pause_clock(1000.0)
    text = resume_season_clock(store, content, 1000.0 + 50, random.Random(0), "停了 {minutes} 分鐘：{skip}")[0]
    assert text == "停了 0 分鐘：這一段不算進賽季，季末往後延一樣長"


def test_a_paused_battle_custom_action_is_refused_by_the_engine_itself(content, game):
    """自訂行動不走 choose()：引擎自己擋（伺服器雖然先擋了，引擎被別的呼叫端直接叫到時也不能把這一回合結算掉）。"""
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        assert game.world.pause_clock(after_muster)
        msgs = game.submit_battle_custom_action("直取波才首級")
    assert msgs == [f"（{PAUSED_TEXT}。）"]
    battle = game.world.get_battle()
    assert "沈浪" not in battle.round.pending_actions and battle.round_number == 0  # 機器人補位的那一份本來就在
    assert not any("直取波才首級" in line for line in battle.narrative_log)
