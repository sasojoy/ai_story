"""公告停機時賽季時鐘暫停（線上架構設計第四節、8.3；賽季計畫 Task 2、3）。"""
import math
import random

import pytest

from conftest import install_season_one, install_showdowns
from tianxia import calendar, database
from tianxia.models import BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome
from tianxia.sqlite_world import open_world
from tianxia.world import keep_showdowns_on_time, start_pending_battle
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
    宛城還沒到，照樣往前挪、不開。呼叫端的順序是 resume_clock → catch_up_season → start_pending_battle（預檢 F2，
    見下面 test_resume_after_an_uncaught_span_…）：這一條停之前剛補算過，補算只剩不到一個曆時的零頭。"""
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


def test_a_moved_showdown_steps_off_a_regular_event(content):
    """往前挪剛好落在一件還沒結算的一般大事上（第 4 週週一 00:00 的波才）：再往後挪一個曆時，不然那件大事先結算、
    長社就被照起點判掉（T10 審查 I1，跟管理者排時間同一條規則）。"""
    install_season_one(content)
    install_showdowns(content)
    season = fresh_season(content)
    season.time = calendar.week_start(3, content, season) + 1
    week4 = calendar.week_start(4, content, season)
    shift = season.schedule["changshe_fire"] - week4
    keep_showdowns_on_time(season, content, shift / content.config.time_scale, season.time)
    assert season.schedule["changshe_fire"] == pytest.approx(week4 + calendar.cal_hour_seconds(content, season))
    assert season.showdowns_waiting == []


def test_a_long_pause_does_not_move_a_showdown_ahead_of_earlier_events(content):
    """停得很久，長社往前挪到第 3 週（張曼成、波才都還沒結算）：時刻表的先後不能亂，最早排在原本排在它前面的最後一件
    （第 4 週週一的波才）之後一個曆時（B13）。"""
    install_season_one(content)
    install_showdowns(content)
    season = fresh_season(content)
    season.time = calendar.week_start(2, content, season) + 1
    week4 = calendar.week_start(4, content, season)
    shift = season.schedule["changshe_fire"] - (calendar.week_start(3, content, season) + 5 * calendar.cal_hour_seconds(content, season))
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


# ── 預檢補的（賽季計畫預檢 F1、F2）──────────────────────────────────────


def test_resume_after_an_uncaught_span_settles_the_earlier_events_before_the_showdown_opens(content):
    """預檢 F2：主機端直接暫停（沒先補算）、停得很久：暫停前還沒補算的那一大段（裡面有第 4 週的波才）繼續當下還沒推。
    繼續之後呼叫端的順序是 resume_clock → catch_up_season → start_pending_battle：先補算，波才先結算，長社才開集結——
    省掉補算、直接 start_pending_battle 的話，長社會在波才還沒結算（時間軸上沒有）時就開成，前線起點、之後宛城的版本都亂了。"""
    store = _season_one_store(content)
    rng, scale = random.Random(0), content.config.time_scale
    store.catch_up_season(content, 0.0, rng)  # 記下時鐘，之後直到暫停都沒人補算
    changshe = store.get_season().schedule["changshe_fire"]
    paused = (changshe - 600) / scale  # 停在長社前十分鐘（季時間）：0～paused 這一大段（第 4 週的波才在裡面）沒人補算
    assert store.pause_clock(paused)
    resumed = paused + 40 * 3600
    store.resume_clock(content, resumed)
    assert "bocai" not in store.get_season().timeline and store.get_season().showdowns_waiting == ["changshe_fire"]
    store.catch_up_season(content, resumed, rng)  # 前一段補完：一般大事先結算，長社排在這一刻、排在它們後面
    start_pending_battle(store, content, resumed)
    battle, season = store.get_battle(), store.get_season()
    assert (battle.battle_id, battle.phase) == ("changshe_fire", "muster")
    assert battle.muster_deadline_real == resumed + content.battles["changshe_fire"].muster_seconds
    assert "bocai" in season.timeline and "changshe_fire" not in season.timeline
    assert season.showdowns_opened == {"changshe_fire": "changshe_fire"} and season.showdowns_waiting == []


def test_the_scheduler_tick_does_not_move_a_paused_season(store, content):
    """預檢 F1：伺服器排程（Game.world_tick）暫停中什麼都不推——季的時間不走、再久也不收季；繼續之後從停的那一刻接著走。
    排程走的就是 catch_up_season 這個關口（暫停中不推、對時點不動）。打到一半的決戰在排程那一路的逾時看的是另一個關口
    （Game._battle_status），它的暫停檢查與測試在 Task 3。"""
    from tianxia.engine import Game  # 區域 import：Task 3 會改上面的 import 區塊

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
