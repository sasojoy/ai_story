import random
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tianxia import database
from tianxia.database import Database
from tianxia.martial_arts import generate_from_name
from tianxia.sqlite_world import SqliteWorldStore, open_world
from tianxia.state import Rumor

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def store(tmp_path):
    return open_world(tmp_path / "world.db")


def test_read_missing_file_returns_empty_state(store):
    assert store.read().companion_tag_counts == {}
    assert store.get_skill("裂石拳") is None


def test_claim_skill_name_succeeds_once(store):
    art = generate_from_name("裂石拳", "武學", "裂石拳")
    assert store.claim_skill_name(art) is True
    assert store.is_skill_name_taken("裂石拳") is True
    assert store.get_skill("裂石拳").name == "裂石拳"


def test_claim_skill_name_fails_when_already_taken(store):
    art = generate_from_name("裂石拳", "武學", "裂石拳")
    store.claim_skill_name(art)
    same_name_again = generate_from_name("裂石拳", "武學", "裂石拳")
    assert store.claim_skill_name(same_name_again) is False


def test_claim_skill_name_persists_across_store_instances(tmp_path):
    path = tmp_path / "world.db"
    art = generate_from_name("驚鴻一劍", "武學", "驚鴻一劍")
    open_world(path).claim_skill_name(art)
    database.close_all()  # 關掉再開：真的是從檔案讀回來
    assert open_world(path).is_skill_name_taken("驚鴻一劍") is True


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


def test_two_stores_on_one_file_see_each_others_writes(tmp_path):
    path = tmp_path / "world.db"
    store_a = open_world(path)
    other_db = Database(path)  # 另一組連線，像另一個程式
    store_b = SqliteWorldStore(other_db)
    try:
        for i in range(20):
            art = generate_from_name(f"武學{i}", "武學", f"武學{i}")
            (store_a if i % 2 == 0 else store_b).claim_skill_name(art)
        assert all(store_a.is_skill_name_taken(f"武學{i}") for i in range(20))
    finally:
        other_db.close()


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
    with store.db.snapshot() as conn:  # 換季不刪資料：上一季的登記留著
        assert conn.execute("SELECT season FROM skills WHERE name = '驚雷掌'").fetchone()["season"] == 1


def test_next_season_clears_the_crafting_recipes(store, content):
    """煉製配方每季清空、大家重新發現（第一季設計第十四節）。"""
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    key = "gang_1+gang_1|武學"
    store.claim_recipe(key, generate_from_name("玄雷式", "武學", "玄雷式"))
    assert store.lookup_recipe(key) is not None
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    with store.db.snapshot() as conn:  # 換季不刪資料：上一季的配方留著
        assert conn.execute("SELECT season FROM recipes WHERE key = ?", (key,)).fetchone()["season"] == 1
    assert store.lookup_recipe(key) is None


def test_next_season_clears_a_leftover_battle(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    store.start_battle(_battle_definition(), now=0.0)
    store.mutate_season(lambda season: setattr(season, "ended", True))
    store.next_season(content, now=1.0)
    assert store.get_battle() is None


# ── 兩個程式同時讀寫（伺服器假人設計第九節）──────────────────


def test_the_action_lock_is_released_afterwards(store):
    with store.action_lock(timeout=1):
        store.record_faction("甲", "guan")
    with store.action_lock(timeout=1):  # 放掉了才拿得到第二次
        pass
    assert store.faction_counts() == {"guan": 1}


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


_WRITER = """
import sys, time
from pathlib import Path
from tianxia.sqlite_world import open_world
store = open_world(Path(sys.argv[1]))
go = Path(sys.argv[3])
print("ready", flush=True)
deadline = time.monotonic() + 120
while not go.exists():  # 等起跑訊號：兩邊同時開跑，不會一邊跑完了另一邊才啟動
    if time.monotonic() > deadline:
        sys.exit(3)
    time.sleep(0.0005)
for _ in range(int(sys.argv[2])):
    with store.action_lock(timeout=60):
        season = store.get_season()  # 跟 Game 一樣：讀一份、改、整份寫回
        time.sleep(0.001)  # 讀與寫之間留一段空檔：沒有寫入權擋著的話，另一邊一定會插進來
        season.time += 1
        store.save_season(season)
"""

_READER = """
import sys
from pathlib import Path
from tianxia.sqlite_world import open_world
store = open_world(Path(sys.argv[1]))
for _ in range(int(sys.argv[2])):
    store.read()
"""


def test_two_programs_acting_at_once_lose_no_updates(tmp_path):
    """伺服器與假人程式同時對全服狀態「讀一份、改、整份寫回」，另一個程式同時一直在讀：
    寫入交易讓兩邊一個一個來（一次都不少），讀的人不用等。"""
    path = tmp_path / "world.db"
    go = tmp_path / "go"
    open_world(path).mutate(lambda s: None)
    writers = [
        subprocess.Popen(
            [sys.executable, "-c", _WRITER, str(path), "100", str(go)], cwd=ROOT, stdout=subprocess.PIPE, text=True,
        )
        for _ in range(2)
    ]
    reader = subprocess.Popen([sys.executable, "-c", _READER, str(path), "400"], cwd=ROOT)
    procs = [*writers, reader]
    try:
        for proc in writers:
            assert proc.stdout.readline().strip() == "ready"
        go.write_text("go")  # 兩個寫的都就緒了才一起開跑
        assert [proc.wait(timeout=180) for proc in procs] == [0, 0, 0]
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=60)
        for proc in writers:
            proc.stdout.close()
    assert open_world(path).get_season().time == 200


def test_next_season_clears_the_faction_roll(store, content):
    store.seed_first_season(content)  # 測試內容會直接開季
    store.record_faction("甲", "guan")
    store.record_faction("乙", "guan")
    store.record_faction("丙", "huang")
    assert store.faction_counts() == {"guan": 2, "huang": 1}
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    assert store.faction_counts() == {}


def test_one_action_is_one_transaction(store, content):
    """一個動作＝一筆交易（線上架構設計 3.1）：中途出錯，這個動作寫過的全部撤回。"""
    store.seed_first_season(content)
    with pytest.raises(ZeroDivisionError):
        with store.action_lock():
            store.record_companion_tag("dongzhuo", "真誠切磋")
            store.mutate_season(lambda season: season.trends.__setitem__("kou", 99))
            1 / 0
    assert store.read().companion_tag_counts == {}
    assert store.get_season().trends.get("kou") != 99


def test_next_season_keeps_the_old_season(store, content):
    """換季不刪資料：賽季編號加一，舊的一季整份留著（線上架構設計 3.2）。"""
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    with store.db.snapshot() as conn:
        rows = conn.execute("SELECT number, data FROM seasons ORDER BY number").fetchall()
    assert [row["number"] for row in rows] == [1, 2]
    assert '"ended":true' in rows[0]["data"]


# ── 傳聞與江湖史一筆一筆加（線上架構設計 3.1）──────────────────


def test_rumors_and_chronicle_are_added_one_row_at_a_time(store, content):
    store.seed_first_season(content)
    season = store.get_season()
    season.rumors.append(Rumor(time=1, text="甲"))
    season.chronicle.append(Rumor(time=1, text="史一"))
    store.save_season(season)
    assert season.rumors[0].id is not None and season.chronicle[0].id is not None
    season.rumors.append(Rumor(time=2, text="乙"))
    store.save_season(season)  # 甲已經寫過，不會再寫一次
    with store.db.snapshot() as conn:
        assert [row["text"] for row in conn.execute("SELECT text FROM rumors ORDER BY id")] == ["甲", "乙"]
        assert "rumors" not in conn.execute("SELECT data FROM seasons WHERE number = 1").fetchone()["data"]
    assert [r.text for r in store.get_season().rumors] == ["甲", "乙"]


def test_a_stale_copy_cannot_erase_rumors_written_since(store, content):
    store.seed_first_season(content)
    first, second = store.get_season(), store.get_season()
    second.rumors.append(Rumor(time=1, text="後來的人寫的"))
    store.save_season(second)
    first.rumors.append(Rumor(time=1, text="拿著舊的一份寫的"))
    store.save_season(first)  # 季的小資料照舊是後寫的蓋掉先寫的，傳聞一則都不會少
    assert {r.text for r in store.get_season().rumors} == {"後來的人寫的", "拿著舊的一份寫的"}


def test_reading_the_world_does_not_load_the_rumors(store, content):
    store.seed_first_season(content)
    store.mutate_season(lambda season: season.rumors.append(Rumor(time=0, text="甲")))
    assert store.read().season.rumors == []  # 只有 get_season 讀回來（給畫面看）
    assert [r.text for r in store.get_season().rumors] == ["甲"]


def test_last_seasons_chronicle_survives_the_next_season(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)

    def _end(season):
        season.chronicle.append(Rumor(time=0, text="第一季的大事"))
        season.ended = True

    store.mutate_season(_end)
    assert store.next_season(content, now=1.0)
    assert store.get_season().chronicle == []
    assert [(n, [e.text for e in entries]) for n, entries in store.chronicle_before(2)] == [(1, ["第一季的大事"])]


# ── 武學、配方、投靠名冊一筆一筆加（每季各一份）──────────────────


def test_faction_of_reads_this_seasons_roll(store, content):
    store.seed_first_season(content)
    store.record_faction("甲", "guan")
    store.record_faction("甲", "huang")  # 叛投：改記新的陣營
    assert store.faction_of("甲") == "huang" and store.faction_of("乙") is None
    assert store.faction_counts() == {"huang": 1}


def test_next_season_writes_last_seasons_first_crafts_into_its_chronicle(store, content):
    """第一季設計第十四節：配方每季清空，上一季的首創紀錄寫進江湖史。"""
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    art = generate_from_name("玄雷式", "武學", "玄雷式")
    art.creator = "沈浪"
    store.claim_recipe("gang_1+gang_1|武學", art)
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    [(number, entries)] = store.chronicle_before(2)
    assert number == 1 and entries[-1].text == "第 1 季煉製首創 1 門：【玄雷式】沈浪"


def test_a_season_without_first_crafts_adds_no_chronicle_entry(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    assert store.chronicle_before(2) == []


def test_recipe_keys_lists_only_this_seasons_recipes(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    key = "gang_1+gang_1|武學"
    assert store.recipe_keys() == set()
    store.claim_recipe(key, generate_from_name("玄雷式", "武學", "玄雷式"))
    assert store.recipe_keys() == {key}
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    assert store.recipe_keys() == set()  # 新的一季重新發現
    with store.db.snapshot() as conn:  # 上一季的那一列還在
        assert conn.execute("SELECT COUNT(*) AS n FROM recipes WHERE season = 1").fetchone()["n"] == 1
