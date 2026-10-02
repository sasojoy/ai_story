import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tianxia import world_state
from tianxia.martial_arts import generate_from_name
from tianxia.world_state import WorldStateStore, _locked

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def store(tmp_path):
    return WorldStateStore(path=tmp_path / "world" / "state.json")


def test_read_missing_file_returns_empty_state(store):
    state = store.read()
    assert state.created_skills == {}
    assert state.companion_tag_counts == {}


def test_claim_skill_name_succeeds_once(store):
    art = generate_from_name("裂石拳", "武學", "裂石拳")
    assert store.claim_skill_name(art) is True
    assert store.is_skill_name_taken("裂石拳") is True


def test_claim_skill_name_fails_when_already_taken(store):
    art = generate_from_name("裂石拳", "武學", "裂石拳")
    store.claim_skill_name(art)
    same_name_again = generate_from_name("裂石拳", "武學", "裂石拳")
    assert store.claim_skill_name(same_name_again) is False


def test_claim_skill_name_persists_across_store_instances(tmp_path):
    path = tmp_path / "world" / "state.json"
    art = generate_from_name("驚鴻一劍", "武學", "驚鴻一劍")
    WorldStateStore(path=path).claim_skill_name(art)
    reopened = WorldStateStore(path=path)
    assert reopened.is_skill_name_taken("驚鴻一劍") is True


def test_record_companion_tag_accumulates_counts(store):
    store.record_companion_tag("dongzhuo", "真誠切磋")
    store.record_companion_tag("dongzhuo", "真誠切磋")
    store.record_companion_tag("dongzhuo", "強攻鋪墊")
    counts = store.read().companion_tag_counts["dongzhuo"]
    assert counts == {"真誠切磋": 2, "強攻鋪墊": 1}


def test_companion_drift_note_round_trips(store):
    assert store.get_companion_drift_note("dongzhuo") == ""
    store.set_companion_drift_note("dongzhuo", "漸露驕縱之色")
    assert store.get_companion_drift_note("dongzhuo") == "漸露驕縱之色"


def test_lock_is_reclaimed_after_stale_timeout(tmp_path):
    lock_dir = tmp_path / "stale.lock"
    lock_dir.mkdir()
    old = time.time() - 999
    import os
    os.utime(lock_dir, (old, old))
    # 鎖已經存在但夠舊，_locked 應該強制回收而不是等到逾時炸掉。
    with _locked(lock_dir):
        assert lock_dir.exists()
    assert not lock_dir.exists()


def test_lock_prevents_concurrent_mutation_from_corrupting_state(tmp_path):
    path = tmp_path / "world" / "state.json"
    store_a = WorldStateStore(path=path)
    store_b = WorldStateStore(path=path)
    for i in range(20):
        art = generate_from_name(f"武學{i}", "武學", f"武學{i}")
        (store_a if i % 2 == 0 else store_b).claim_skill_name(art)
    assert len(store_a.read().created_skills) == 20


# ── 共享賽季（真正共享的大勢/門檻/主線，取代每個玩家各自的 WorldState）──────────


def test_get_season_before_anything_exists_is_an_empty_default(store):
    season = store.get_season()
    assert season.storyline == "" and season.trends == {}
    assert store.get_season_number() == 1


def test_save_season_overwrites_the_stored_copy(store, content):
    season = store.seed_first_season(content)
    season.trends["kou"] = 90
    store.save_season(season)
    assert store.get_season().trends["kou"] == 90


def test_catch_up_season_does_nothing_on_the_very_first_call(store, content):
    """第一次呼叫只記錄時間點（跟舊的 Game.sync() 行為一致），不會憑空推進一大段。"""
    store.seed_first_season(content)
    msgs = store.catch_up_season(content, 1000.0, __import__("random").Random(0))
    assert msgs == []
    assert store.get_season().time == 0


def test_catch_up_season_advances_the_shared_clock_by_elapsed_real_time(store, content):
    rng = __import__("random").Random(0)
    store.seed_first_season(content)
    store.catch_up_season(content, 1000.0, rng)  # 第一次：只記錄時間點
    store.catch_up_season(content, 1000.0 + 7200, rng)  # 第二次：過了 2 小時現實時間
    assert store.get_season().time == 7200 * content.config.time_scale


def _battle_definition():
    from tianxia.models import (
        BattleAct, BattleActionEffect, BattleAdvanceWhen, BattleDef, BattleFaction, BattleOption, BattleOutcome,
    )

    return BattleDef(
        id="b1", name="測試戰", factions=[BattleFaction(id="a", name="甲方"), BattleFaction(id="b", name="乙方")],
        acts=[BattleAct(id="a1", title="開戰", text="開戰了。", goal="打贏", options=[BattleOption(text="進攻", tag="go")])],
        action_tags={"go": BattleActionEffect(trend_delta=1, neili_damage=5)},
        outcomes=[BattleOutcome(faction="a", title="甲方勝", text="甲方贏了。")],
    )


def test_get_battle_is_none_before_any_battle_starts(store):
    assert store.get_battle() is None


def test_start_battle_creates_a_fresh_battle(store):
    battle = store.start_battle(_battle_definition(), now=0.0)
    assert battle.phase == "muster"
    assert store.get_battle().battle_id == "b1"


def test_start_battle_is_a_no_op_while_one_is_already_running(store):
    first = store.start_battle(_battle_definition(), now=0.0)
    again = store.start_battle(_battle_definition(), now=1000.0)
    assert again.muster_deadline_real == first.muster_deadline_real  # 沒有被重新開一場蓋掉


def test_start_battle_starts_a_new_one_once_the_previous_has_ended(store):
    store.start_battle(_battle_definition(), now=0.0)
    store.mutate_battle(lambda b: setattr(b, "phase", "ended"))
    again = store.start_battle(_battle_definition(), now=500.0)
    assert again.phase == "muster" and again.muster_deadline_real == 500.0 + 600.0


def test_mutate_battle_returns_none_without_an_active_battle(store):
    assert store.mutate_battle(lambda b: None) is None


def test_mutate_battle_persists_changes(store):
    store.start_battle(_battle_definition(), now=0.0)
    store.mutate_battle(lambda b: setattr(b, "trend", 77))
    assert store.get_battle().trend == 77


def test_clear_battle_removes_it(store):
    store.start_battle(_battle_definition(), now=0.0)
    store.clear_battle()
    assert store.get_battle() is None


def test_catch_up_season_only_advances_once_no_matter_who_calls_it(store, content):
    """不管幾個「玩家」在同一個現實時間點各自呼叫一次，世界時間只走一份，不會重複累加。"""
    rng = __import__("random").Random(0)
    store.seed_first_season(content)
    store.catch_up_season(content, 1000.0, rng)
    store.catch_up_season(content, 1000.0 + 3600, rng)
    store.catch_up_season(content, 1000.0 + 3600, rng)  # 同一個時間點，另一個「玩家」又呼叫一次
    assert store.get_season().time == 3600 * content.config.time_scale


def test_catch_up_season_never_turns_the_shared_clock_back(store, content):
    """拿比較早的時間來追趕（假人程式一輪開頭讀的錶，真人已經在這之後對過時鐘）：共用時鐘
    不能被撥回去，不然下一個人會把那一段再算一次；這一次也不多算時間。"""
    rng = random.Random(0)
    store.seed_first_season(content)
    store.catch_up_season(content, 1000.0, rng)
    store.catch_up_season(content, 1100.0, rng)
    store.catch_up_season(content, 1050.0, rng)  # 較早的時間
    assert store.read().season_last_real == 1100.0
    assert store.get_season().time == 100 * content.config.time_scale
    store.catch_up_season(content, 1200.0, rng)
    assert store.get_season().time == 200 * content.config.time_scale


# ── 江湖大事潤色（全服共用一次，還要改進第 3 點）──────────────────


def test_event_flavor_starts_empty(store):
    assert store.get_event_flavor("huangjin_80") == ""


def test_set_event_flavor_first_write_wins(store):
    store.set_event_flavor("huangjin_80", "城頭的旗幟已經換了顏色。")
    store.set_event_flavor("huangjin_80", "別的玩家搶先寫入的另一句話。")
    assert store.get_event_flavor("huangjin_80") == "城頭的旗幟已經換了顏色。"


# ── 傳國玉璽碎片（跨季，還要改進第 2 點）─────────────────────────


def test_record_jade_seal_fragment_numbers_in_order(store):
    first = store.record_jade_seal_fragment("強者", "黃巾之亂", "強者擊敗看守者，取得第一塊碎片。")
    second = store.record_jade_seal_fragment("弱者", "黃巾之亂", "弱者意外尋得第二塊碎片。")
    assert (first.number, second.number) == (1, 2)
    assert [f.finder for f in store.get_jade_seal_fragments()] == ["強者", "弱者"]


def test_record_jade_seal_fragment_stops_after_seven(store):
    for i in range(7):
        store.record_jade_seal_fragment(f"玩家{i}", "測試季", "找到了。")
    assert store.record_jade_seal_fragment("第八人", "測試季", "來晚了。") is None
    assert len(store.get_jade_seal_fragments()) == 7


def test_jade_seal_summary_before_and_after_a_fragment_is_found(store):
    assert "尚無人尋獲" in store.jade_seal_summary()
    store.record_jade_seal_fragment("強者", "黃巾之亂", "強者擊敗看守者，取得第一塊碎片。")
    summary = store.jade_seal_summary()
    assert "1/7" in summary and "強者" in summary and "黃巾之亂" in summary


# ── 賽季階段：籌備 → 進行中 → 休季（第一季設計第十四節）──────────


def test_seed_first_season_waits_for_the_admin_by_default(store, content):
    content.config.auto_open_first_season = False
    season = store.seed_first_season(content)
    assert season.storyline == content.scenario.storylines[0].id
    assert season.trends == {t.id: t.start for t in content.scenario.trends}
    assert store.season_phase() == "preparing"
    assert store.get_season_number() == 1


def test_seed_first_season_opens_directly_when_content_says_so(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    assert store.season_phase() == "running"


def test_seed_first_season_is_a_no_op_once_seeded(store, content):
    content.config.auto_open_first_season = False
    store.seed_first_season(content)
    store.mutate_season(lambda season: season.trends.__setitem__("kou", 77))
    store.seed_first_season(content)
    assert store.get_season().trends["kou"] == 77


def test_open_season_moves_preparing_to_running_once(store, content):
    content.config.auto_open_first_season = False
    store.seed_first_season(content)
    assert store.open_season(now=500.0) is True
    assert store.season_phase() == "running"
    assert store.read().season_last_real == 500.0
    assert store.open_season(now=600.0) is False


def test_open_season_needs_a_seeded_season(store):
    assert store.open_season(now=1.0) is False
    assert store.season_phase() == "preparing"


def test_catch_up_season_does_not_move_the_clock_while_preparing(store, content):
    content.config.auto_open_first_season = False
    content.config.time_scale = 60
    store.seed_first_season(content)
    store.catch_up_season(content, 1000.0, random.Random(0))
    store.catch_up_season(content, 1010.0, random.Random(0))
    assert store.get_season().time == 0


def test_next_season_only_works_while_resting(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    assert store.next_season(content, now=1.0) is False  # 還在進行中
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.season_phase() == "resting"
    assert store.next_season(content, now=2.0) is True
    assert store.season_phase() == "running"
    assert store.get_season_number() == 2
    assert store.get_season().ended is False
    assert store.read().season_last_real == 2.0


def test_next_season_keeps_the_jade_seal_fragments(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    store.record_jade_seal_fragment("甲", "測試劇本", "甲取得了碎片。")
    store.mutate_season(lambda season: setattr(season, "ended", True))
    store.next_season(content, now=1.0)
    assert [f.finder for f in store.get_jade_seal_fragments()] == ["甲"]


def test_next_season_frees_every_companion_and_resets_their_progress(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    store.try_recruit("mate", "甲")
    store.update_companion("mate", lambda progress: setattr(progress, "level", 9))
    store.mutate_season(lambda season: setattr(season, "ended", True))
    store.next_season(content, now=1.0)
    progress = store.get_companion("mate")
    assert progress.owner is None and progress.level == 1


def test_next_season_releases_every_created_skill_name_and_turns_the_tianji(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    store.claim_skill_name(generate_from_name("驚雷掌", "武學", "驚雷掌"))
    assert store.read().tianji == 0
    store.mutate_season(lambda season: setattr(season, "ended", True))
    store.next_season(content, now=1.0)
    assert store.is_skill_name_taken("驚雷掌") is False
    assert store.read().tianji == 1


def test_next_season_clears_the_crafting_recipes(store, content):
    """煉製配方每季清空、大家重新發現（第一季設計第十四節）。"""
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    key = "gang_1+gang_1|武學"
    store.claim_recipe(key, generate_from_name("玄雷式", "武學", "玄雷式"))
    assert store.lookup_recipe(key) is not None
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    assert store.read().recipes == {}
    assert store.lookup_recipe(key) is None


def test_next_season_clears_a_leftover_battle(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    store.start_battle(_battle_definition(), now=0.0)
    store.mutate_season(lambda season: setattr(season, "ended", True))
    store.next_season(content, now=1.0)
    assert store.get_battle() is None


# ── 兩個程式同時讀寫（伺服器假人設計第九節）──────────────────


def test_read_retries_while_another_program_has_the_file_open(store, monkeypatch):
    store.mutate(lambda s: setattr(s, "tianji", 3))
    real_read = Path.read_text
    calls = {"n": 0}

    def busy_twice(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("另一個程式正在用這個檔案")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", busy_twice)
    assert store.read().tianji == 3
    assert calls["n"] == 3


def test_write_retries_while_another_program_has_the_file_open(store, monkeypatch):
    store.mutate(lambda s: None)
    real_replace = Path.replace
    calls = {"n": 0}

    def busy_twice(self, target):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("另一個程式正在讀這個檔案")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", busy_twice)
    store.mutate(lambda s: setattr(s, "tianji", 5))
    assert calls["n"] == 3
    assert store.read().tianji == 5


def test_the_action_lock_is_released_afterwards(store):
    with store.action_lock(timeout=1):
        assert store.action_lock_dir.exists()
    assert not store.action_lock_dir.exists()
    with store.action_lock(timeout=1):
        pass


def test_the_action_lock_times_out_while_another_thread_holds_it(store):
    errors = []

    def other():
        try:
            with store.action_lock(timeout=0.2):
                pass
        except TimeoutError as error:
            errors.append(error)

    with store.action_lock():
        thread = threading.Thread(target=other)
        thread.start()
        thread.join(5)
    assert len(errors) == 1


def test_an_action_lock_held_for_two_minutes_is_not_mistaken_for_a_crash(store):
    """真人的行動可能在等 LLM：全服紀錄的鎖 30 秒就回收，行動鎖不能這樣搶走別人的鎖。"""
    store.action_lock_dir.mkdir(parents=True)
    two_minutes_ago = time.time() - 120
    os.utime(store.action_lock_dir, (two_minutes_ago, two_minutes_ago))
    with pytest.raises(TimeoutError):
        with store.action_lock(timeout=0.2):
            pass


def test_an_abandoned_action_lock_is_reclaimed(store):
    store.action_lock_dir.mkdir(parents=True)
    long_ago = time.time() - world_state.ACTION_LOCK_STALE_AFTER - 1
    os.utime(store.action_lock_dir, (long_ago, long_ago))
    with store.action_lock(timeout=1):
        pass


_WRITER = """
import sys
from pathlib import Path
from tianxia.world_state import WorldStateStore
store = WorldStateStore(Path(sys.argv[1]))
for _ in range(int(sys.argv[2])):
    with store.action_lock(timeout=60):
        season = store.get_season()  # 跟 Game 一樣：讀一份、改、整份寫回
        season.time += 1
        store.save_season(season)
"""

_READER = """
import sys
from pathlib import Path
from tianxia.world_state import WorldStateStore
store = WorldStateStore(Path(sys.argv[1]))
for _ in range(int(sys.argv[2])):
    store.read()
"""


def test_two_programs_acting_at_once_lose_no_updates_and_never_trip_over_the_file(tmp_path):
    """伺服器與假人程式同時對同一份全服紀錄「讀一份、改、整份寫回」，另一個程式同時一直在讀：
    行動鎖讓兩邊一個一個來（一次都不少），讀寫重試讓 Windows 不會報檔案被占用。"""
    path = tmp_path / "world" / "state.json"
    WorldStateStore(path).mutate(lambda s: None)
    procs = [subprocess.Popen([sys.executable, "-c", _WRITER, str(path), "40"], cwd=ROOT) for _ in range(2)]
    procs.append(subprocess.Popen([sys.executable, "-c", _READER, str(path), "400"], cwd=ROOT))
    assert [p.wait(timeout=180) for p in procs] == [0, 0, 0]
    assert WorldStateStore(path).get_season().time == 80


def test_next_season_clears_the_faction_roll(store, content):
    store.seed_first_season(content)  # 測試內容會直接開季
    store.record_faction("甲", "guan")
    store.record_faction("乙", "guan")
    store.record_faction("丙", "huang")
    assert store.faction_counts() == {"guan": 2, "huang": 1}
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    assert store.faction_counts() == {}
